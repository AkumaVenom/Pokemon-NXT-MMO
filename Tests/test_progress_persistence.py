"""Server-owned progress: durable checkpoints, periodic movement and cold restart.

Temporary SQLite databases exercise the production world/save code. These are
not claims of zero movement loss on power failure or live MySQL deployment.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import random
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
from nxt.config import Settings
from nxt.content import Content
from nxt.security import RequestError
from nxt.store import Store
from nxt.world import World, DIRECTIONS
from server import Service


class ProgressPersistenceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / 'config.ini'
        path.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
        settings = Settings.load(path)
        settings.config.set('database', 'backend', 'sqlite')
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.content, self.db, self.settings)
        self.old_rng = self.content.rng
        self.content.rng = random.Random(901)
        initial = self.world.initial('ProgressTrainer', 'Kanto', 'fr_4', 0)
        self.uid = self.db.create('ProgressTrainer', 'isolated-test-hash', initial)
        self.player = await self.world.join(self.uid, 'ProgressTrainer', None, asyncio.Queue(maxsize=2048))
        self.packets()

    async def asyncTearDown(self):
        self.content.rng = self.old_rng
        self.db.close()
        self.tmp.cleanup()

    def packets(self):
        result = []
        while not self.player.queue.empty():
            result.append(self.player.queue.get_nowait())
        return result

    async def cold_restart(self):
        # No logout/manual save: recreate the database connection and world.
        self.db.close()
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.content, self.db, self.settings)
        self.player = await self.world.join(self.uid, 'ProgressTrainer', None, asyncio.Queue(maxsize=2048))

    async def test_periodic_snapshot_persists_movement_without_manual_save(self):
        before = self.db.load(self.uid)
        await self.world.dispatch(self.player, {'op': 'move', 'seq': 1, 'direction': 'right'})
        self.assertEqual(self.db.load(self.uid), before)
        expected = copy.deepcopy(self.player.state)
        self.assertEqual(await self.world.save_all(), 1)
        self.assertEqual(await self.world.save_all(), 0)
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)
        self.assertEqual((self.player.state['x'], self.player.state['y']), (11, 10))

    async def test_service_automatically_saves_later_movement_at_configured_interval(self):
        self.assertEqual(self.settings.save_seconds, 5)
        service = Service(self.settings, self.content, self.db)
        service.world = self.world
        first_checkpoint = asyncio.Event()
        changed_checkpoint = asyncio.Event()
        loop = asyncio.get_running_loop()
        original_save = self.db.save_many

        def observed_save(records):
            original_save(records)
            loop.call_soon_threadsafe(first_checkpoint.set)
            if records:
                loop.call_soon_threadsafe(changed_checkpoint.set)

        with patch.object(self.db, 'save_many', side_effect=observed_save):
            periodic = asyncio.create_task(service.periodic('save', self.settings.save_seconds))
            try:
                await asyncio.wait_for(first_checkpoint.wait(), 2)
                await self.world.dispatch(self.player, {'op': 'move', 'seq': 1, 'direction': 'right'})
                expected = copy.deepcopy(self.player.state)
                self.assertNotEqual(self.db.load(self.uid), expected)
                # The production service loop performs the next save itself.
                await asyncio.wait_for(changed_checkpoint.wait(), self.settings.save_seconds + 3)
                self.assertEqual(self.db.load(self.uid), expected)
            finally:
                service.stop.set()
                await asyncio.wait_for(periodic, 3)
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)

    async def test_newer_commit_wins_over_older_inflight_autosave_snapshot(self):
        await self.world.dispatch(self.player, {'op': 'move', 'seq': 1, 'direction': 'right'})
        entered = threading.Event()
        release = threading.Event()
        original_save = self.db.save_many
        calls = 0

        def delayed_first_save(records):
            nonlocal calls
            calls += 1
            if calls == 1:
                entered.set()
                if not release.wait(5):
                    raise AssertionError('Autosave worker was not released')
            original_save(records)

        with patch.object(self.db, 'save_many', side_effect=delayed_first_save):
            saving = asyncio.create_task(self.world.save_all())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 3))
                await self.world.dispatch(self.player, {'op': 'buy', 'item': 'potion', 'quantity': 1})
                expected = copy.deepcopy(self.player.state)
                release.set()
                self.assertEqual(await saving, 1)
            finally:
                release.set()
                await saving
        self.assertEqual(self.db.load(self.uid), expected)
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)

    async def test_travel_home_and_surf_are_durable_before_success_packets(self):
        original_send = self.player.send
        durable_events = []

        def checked_send(kind, **data):
            if kind in ('state', 'map', 'notice', 'audio'):
                self.assertEqual(self.db.load(self.uid), self.player.state)
                durable_events.append(kind)
            original_send(kind, **data)

        self.player.send = checked_send
        await self.world.dispatch(self.player, {'op': 'travel', 'map': 'johto_3_0'})
        await self.world.dispatch(self.player, {'op': 'surf'})
        expected = copy.deepcopy(self.player.state)
        self.assertTrue(expected['surf'])
        self.assertIn('map', durable_events)
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)
        await self.world.dispatch(self.player, {'op': 'unstuck'})
        expected = copy.deepcopy(self.player.state)
        self.assertEqual(expected['map'], 'kanto_3_0')
        self.assertFalse(expected['surf'])
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)

    async def test_failed_travel_and_surf_leave_live_and_saved_progress_unchanged(self):
        before = copy.deepcopy(self.player.state)
        for command in ({'op': 'travel', 'map': 'johto_3_0'}, {'op': 'surf'}, {'op': 'unstuck'}):
            self.packets()
            with patch.object(self.db, 'save_many', side_effect=RuntimeError('injected save failure')):
                with self.assertLogs('nxt.world', level='ERROR'):
                    with self.assertRaises(RequestError):
                        await self.world.dispatch(self.player, command)
            self.assertEqual(self.player.state, before)
            self.assertEqual(self.db.load(self.uid), before)
            self.assertFalse(self.packets(), 'Failed checkpoint must not publish a success/map')

    def position_before_warp(self):
        for map_id, source in self.content.maps.items():
            if not source.get('playable', True):
                continue
            for warp in source['warps']:
                target = self.content.maps.get(warp['target'])
                if not target or target['id'] == map_id or not target.get('playable', True):
                    continue
                if not 0 <= warp['targetIndex'] < len(target['warps']):
                    continue
                for direction, (dx, dy, _) in DIRECTIONS.items():
                    x, y = warp['x'] - dx, warp['y'] - dy
                    if not self.world.walkable(source, x, y):
                        continue
                    elevation = source['elevation'][y * source['width'] + x]
                    if not self.world.walkable(source, warp['x'], warp['y'], from_elevation=elevation):
                        continue
                    if source['behavior'][warp['y'] * source['width'] + warp['x']] in (56, 57, 58, 59):
                        continue
                    self.player.state.update(map=map_id, x=x, y=y, direction='down')
                    self.world.follower_anchor(self.player)
                    self.db.save_many([(self.uid, copy.deepcopy(self.player.state))])
                    return direction, target['id']
        self.fail('Content has no usable warp fixture')

    async def test_warp_checkpoint_survives_cold_restart(self):
        direction, destination = self.position_before_warp()
        await self.world.dispatch(self.player, {'op': 'move', 'seq': 1, 'direction': direction})
        self.assertEqual(self.player.state['map'], destination)
        expected = copy.deepcopy(self.player.state)
        packets = self.packets()
        self.assertEqual([p['transition'] for p in packets if p['type'] == 'map'], ['warp'])
        self.assertEqual(self.db.load(self.uid), expected)
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)

    async def test_failed_warp_rejects_movement_and_restores_position_and_follower(self):
        direction, _ = self.position_before_warp()
        before = copy.deepcopy(self.player.state)
        follower = (self.player.fx, self.player.fy)
        with patch.object(self.db, 'save_many', side_effect=RuntimeError('injected warp failure')):
            with self.assertLogs('nxt.world', level='ERROR'):
                with self.assertRaises(RequestError):
                    await self.world.dispatch(self.player, {'op': 'move', 'seq': 1, 'direction': direction})
        self.assertEqual(self.player.state, before)
        self.assertEqual(self.db.load(self.uid), before)
        self.assertEqual((self.player.fx, self.player.fy), follower)
        packets = self.packets()
        self.assertFalse(any(p['type'] == 'map' for p in packets))
        move = next(p for p in packets if p['type'] == 'move')
        self.assertFalse(move['accepted'])
        self.assertEqual(move['reason'], 'save_failed')
        self.assertEqual(move['entity']['map'], before['map'])

    async def test_capture_xp_level_money_and_pp_survive_without_logout_save(self):
        self.content.rng.random = lambda: 0.0
        await self.world.start_wild(self.player, ('fr_129', 2))
        battle = self.world.battles[self.player.battle]
        await self.world.dispatch(self.player, {'op': 'battle', 'id': battle.id,
                                                'action': 'capture', 'item': 'pokeball'})
        captured_uid = self.player.state['creatures'][1]['uid']
        self.assertEqual(self.player.state['items']['pokeball'], 19)
        await self.cold_restart()
        self.assertIn(captured_uid, self.player.state['party'])
        self.assertEqual(self.player.state['creatures'][1]['species'], 'fr_129')

        # Begin one EXP short of level six to make level-up deterministic.
        state = copy.deepcopy(self.player.state)
        lead = state['creatures'][0]
        lead['exp'] = self.content.xp(6, self.content.species[lead['species']]['growth']) - 1
        lead['hp'] -= 2
        await self.world.commit(self.player, state)
        pp_before = lead['moves'][0]['pp']
        money_before = self.player.state['money']
        await self.world.start_wild(self.player, ('fr_129', 10))
        battle = self.world.battles[self.player.battle]
        battle.mon(1)['hp'] = 1
        await self.world.dispatch(self.player, {'op': 'battle', 'id': battle.id, 'action': 'attack', 'slot': 0})
        self.assertIsNone(self.player.battle)
        expected = copy.deepcopy(self.player.state)
        self.assertEqual(expected['creatures'][0]['level'], 6)
        self.assertEqual(expected['creatures'][0]['moves'][0]['pp'], pp_before - 1)
        self.assertEqual(expected['money'], money_before + 25)
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)
        self.assertIn(captured_uid, self.player.state['party'])

    async def test_battle_save_failure_spends_no_ball_and_grants_no_capture(self):
        self.content.rng.random = lambda: 0.0
        before = copy.deepcopy(self.player.state)
        await self.world.start_wild(self.player, ('fr_129', 2))
        battle = self.world.battles[self.player.battle]
        with patch.object(self.db, 'save_many', side_effect=RuntimeError('injected battle failure')):
            with self.assertLogs('nxt.world', level='ERROR'):
                await self.world.dispatch(self.player, {'op': 'battle', 'id': battle.id,
                                                        'action': 'capture', 'item': 'pokeball'})
        self.assertIsNone(self.player.battle)
        self.assertEqual(self.player.state, before)
        await self.cold_restart()
        self.assertEqual(self.player.state, before)

    async def test_heal_items_and_party_order_are_durable_on_server(self):
        state = copy.deepcopy(self.player.state)
        extra = self.content.new_mon('fr_7', 5, self.player.username)
        extra['hp'] -= 3
        state['creatures'].append(extra)
        state['party'].append(extra['uid'])
        await self.world.commit(self.player, state)
        await self.world.dispatch(self.player, {'op': 'party', 'party': list(reversed(state['party']))})
        await self.world.dispatch(self.player, {'op': 'use', 'item': 'potion', 'uid': extra['uid']})
        expected = copy.deepcopy(self.player.state)
        self.assertEqual(expected['party'][0], extra['uid'])
        self.assertEqual(expected['items']['potion'], 4)
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)
        state = copy.deepcopy(self.player.state)
        state['creatures'][0]['hp'] = 1
        state['creatures'][0]['moves'][0]['pp'] = 0
        await self.world.commit(self.player, state)
        await self.world.dispatch(self.player, {'op': 'heal'})
        expected = copy.deepcopy(self.player.state)
        await self.cold_restart()
        self.assertEqual(self.player.state, expected)
        for mon in self.world.party(self.player):
            self.assertEqual(mon['hp'], self.content.stats(mon)[0])
            self.assertTrue(all(move['pp'] == self.content.moves[str(move['id'])]['pp'] for move in mon['moves']))

    async def test_registration_rejects_invalid_home_starter_and_boolean_appearance(self):
        for home, starter, appearance in (([], 'fr_4', 0), ('Kanto', [], 0),
                                         ('Johto', 'fr_4', False), ('Johto', 'fr_4', 0.0)):
            with self.assertRaises(RequestError):
                self.world.initial('InvalidTrainer', home, starter, appearance)


if __name__ == '__main__':
    unittest.main()
