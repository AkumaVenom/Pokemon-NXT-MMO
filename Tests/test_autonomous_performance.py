"""Regression coverage for autonomous-trainer long-uptime I/O behaviour.

These tests guard the architectural properties that prevent the 2,000-bot world
from turning routine simulation into repeated full-population JSON reads and
per-bot database commits.
"""
from __future__ import annotations

import asyncio
import dataclasses
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))

from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.world import World

TEMPLATE = ROOT / 'Build/config_templates/Server/config.ini'


class AutonomousPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')

    def _settings(self, tmp, population=96):
        cfg = Path(tmp) / 'config.ini'
        cfg.write_text(TEMPLATE.read_text(encoding='utf-8'), encoding='utf-8')
        settings = Settings.load(cfg)
        settings.config.set('database', 'backend', 'sqlite')
        settings.config.set('autonomous_trainers', 'population', str(population))
        settings.config.set('autonomous_trainers', 'simulation_batch', '8')
        settings.config.set('autonomous_trainers', 'background_field_batch', '4')
        return dataclasses.replace(settings, encounter_chance=0)

    def test_normal_refresh_is_zero_io_and_force_refresh_remains_explicit_recovery(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                db = Store(self._settings(tmp))
                db.acquire_lease()
                try:
                    world = World(self.content, db, db.s)
                    await world.autonomous.initialize()
                    ai = world.autonomous
                    with mock.patch.object(db, 'ai_world_snapshot', wraps=db.ai_world_snapshot) as snapshot:
                        await ai.refresh_snapshot()
                        self.assertEqual(snapshot.call_count, 0)
                        await ai.refresh_snapshot(force=True)
                        self.assertEqual(snapshot.call_count, 1)
                finally:
                    db.close()

        asyncio.run(exercise())

    def test_background_scheduler_batches_writes_without_population_reload(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                settings = self._settings(tmp)
                old_rng = self.content.rng
                self.content.rng = random.Random(1609202602)
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    ai = world.autonomous
                    now = int(time.time())
                    for bot in ai.snapshot:
                        bot['personality']['nextBackgroundFieldAt'] = now + 3600
                    for bot in ai.snapshot[:4]:
                        bot['personality']['nextBackgroundFieldAt'] = now - 1
                    ai.last_background_field = 0

                    with mock.patch.object(db, 'ai_commit_fields', wraps=db.ai_commit_fields) as commit, \
                         mock.patch.object(db, 'ai_world_snapshot', side_effect=AssertionError(
                             'background simulation must not reload the full population')):
                        processed = await ai.background_field_tick(set())

                    self.assertEqual(processed, 4)
                    self.assertEqual(commit.call_count, 1)
                    records = commit.call_args.args[0]
                    self.assertEqual(len(records), 4)
                finally:
                    self.content.rng = old_rng
                    db.close()

        asyncio.run(exercise())

    def test_competitive_pass_uses_memory_and_one_batched_commit(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                settings = self._settings(tmp)
                old_rng = self.content.rng
                self.content.rng = random.Random(1609202603)
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    ai = world.autonomous
                    now = int(time.time())
                    for bot in ai.snapshot:
                        bot['next_action_at'] = now + 3600
                    for bot in ai.snapshot[:8]:
                        bot['next_action_at'] = now - 1

                    with mock.patch.object(db, 'ai_recent_opponents_many', wraps=db.ai_recent_opponents_many) as recent, \
                         mock.patch.object(db, 'ai_commit_competitive_batch', wraps=db.ai_commit_competitive_batch) as commit, \
                         mock.patch.object(db, 'ai_due', side_effect=AssertionError('legacy due JSON query used')), \
                         mock.patch.object(db, 'ai_get', side_effect=AssertionError('per-actor JSON read used')), \
                         mock.patch.object(db, 'ai_candidates', side_effect=AssertionError('candidate JSON query used')), \
                         mock.patch.object(db, 'ai_world_snapshot', side_effect=AssertionError(
                             'competitive simulation must not reload the full population')):
                        await ai.simulate_due()

                    self.assertEqual(recent.call_count, 1)
                    self.assertEqual(commit.call_count, 1)
                    records, events = commit.call_args.args
                    self.assertGreaterEqual(len(records), 2)
                    self.assertGreaterEqual(len(events), 2)
                finally:
                    self.content.rng = old_rng
                    db.close()

        asyncio.run(exercise())

    def test_activity_retention_prune_is_hourly_not_per_bot_action(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                settings = self._settings(tmp)
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    bot = world.autonomous.snapshot[0]
                    statements = []
                    db.db.set_trace_callback(statements.append)
                    try:
                        event = {'kind': 'wild', 'opponent': 0, 'result': 'win',
                                 'summary': 'retention throttle regression'}
                        db.ai_commit_field(bot, event)
                        db.ai_commit_field(bot, event)
                    finally:
                        db.db.set_trace_callback(None)
                    deletes = [sql for sql in statements
                               if 'DELETE FROM ai_activity' in sql]
                    self.assertEqual(len(deletes), 1)
                finally:
                    db.close()

        asyncio.run(exercise())

    def test_visible_field_outcomes_share_one_commit_per_world_tick(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                settings = self._settings(tmp)
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    ai = world.autonomous
                    active_map = next(map_id for map_id, bots in ai.by_map.items()
                                      if len(bots) >= 2 and ai._materialized_bots(map_id))
                    bots = ai._materialized_bots(active_map)
                    self.assertGreaterEqual(len(bots), 2)
                    epoch = int(time.time())
                    for bot in bots:
                        bot['personality']['nextTravelAt'] = epoch + 3600
                        bot['personality']['travelPending'] = ''
                        rt = ai._runtime_for(bot)
                        rt['next_wild'] = 0
                        rt['busy_until'] = 0
                    ai.field_wild_chance = 1.0
                    ai.field_wild_per_tick = 2

                    fake_result = {'species': 'fr_1', 'result': 'win', 'summary': 'batched field test'}
                    with mock.patch.object(ai, '_step_bot', return_value=True), \
                         mock.patch.object(ai, '_simulate_wild_battle', side_effect=lambda _bot: dict(fake_result)), \
                         mock.patch.object(db, 'ai_commit_fields', wraps=db.ai_commit_fields) as commit:
                        await ai.field_tick({active_map})

                    self.assertEqual(commit.call_count, 1)
                    records = commit.call_args.args[0]
                    self.assertEqual(len(records), 2)
                    self.assertTrue(all(record['event']['kind'] == 'wild' for record in records))
                finally:
                    db.close()

        asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
