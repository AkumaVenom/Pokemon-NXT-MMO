"""Regression coverage for persistent, visible autonomous trainer world life."""
from __future__ import annotations

import asyncio
import collections
import copy
import dataclasses
import random
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))

from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.world import Player, World
from nxt.encounters import encounter_slots

TEMPLATE = ROOT / 'Build/config_templates/Server/config.ini'


class AutonomousWorldLifeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')

    def test_population_coverage_movement_wild_training_and_persistence(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                cfg = Path(tmp) / 'config.ini'
                cfg.write_text(TEMPLATE.read_text(encoding='utf-8'), encoding='utf-8')
                settings = Settings.load(cfg)
                settings.config.set('database', 'backend', 'sqlite')
                settings = dataclasses.replace(settings, encounter_chance=0)
                old_rng = self.content.rng
                self.content.rng = random.Random(9152026)
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    bots = world.autonomous.snapshot
                    self.assertEqual(len(bots), 2000)

                    counts = collections.Counter(b['state']['map'] for b in bots)
                    regions = collections.Counter((b['state']['home'], self.content.maps[b['state']['map']]['region']) for b in bots)
                    self.assertEqual(regions[('Kanto', 'Kanto')], 1000)
                    self.assertEqual(regions[('Johto', 'Johto / Sigma')], 1000)
                    self.assertEqual(collections.Counter(b['state']['appearance'] for b in bots), {0: 1000, 7: 1000})
                    self.assertTrue(all(world.autonomous._travel_map_allowed(self.content.maps[b['state']['map']]) for b in bots))
                    self.assertTrue(all(self.content.maps[b['state']['map']].get('mapType') != 8 for b in bots))
                    # Fresh level-five trainers must never start in a high-level field.
                    for bot in bots:
                        profile = world.autonomous._travel_profile(self.content.maps[bot['state']['map']])
                        level = world.autonomous._party_level(bot)
                        self.assertLessEqual(profile['q90'], level + world.autonomous.travel_safe_margin)
                        self.assertEqual(bot['personality']['travelRegion'], self.content.maps[bot['state']['map']]['region'])

                    encounter_maps = [m for m in self.content.maps.values() if world.autonomous._travel_map_allowed(m)]
                    self.assertGreater(len(encounter_maps), 100)
                    self.assertGreater(len(counts), 10)

                    # Route 30 is a representative large Johto field map. Residents
                    # begin on valid encounter terrain and use only Red/Leaf sprites.
                    route = next(m for m in encounter_maps if m['name'] == 'Route 30')
                    residents = world.autonomous.by_map[route['id']]
                    self.assertGreaterEqual(len(residents), world.autonomous._resident_floor(route['id']))
                    materialized = world.autonomous._materialized_bots(route['id'])
                    self.assertEqual(len(materialized), min(world.autonomous.world_per_map, len(residents)))
                    self.assertEqual([b['id'] for b in materialized],
                                     [b['id'] for b in world.autonomous._materialized_bots(route['id'])])
                    world.autonomous._ensure_materialized_spacing(route['id'], materialized, ())
                    positions = [(b['state']['x'], b['state']['y']) for b in materialized]
                    self.assertEqual(len(positions), len(set(positions)))
                    bot = materialized[0]
                    state = bot['state']
                    self.assertTrue(world.autonomous._field_walkable(route, state, state['x'], state['y']))
                    self.assertTrue(world.autonomous._training_points(route))

                    # A replicated step carries the follower from the trainer's old
                    # tile, matching the authoritative human movement contract.
                    rt = world.autonomous._runtime_for(bot)
                    rt['next_step'] = 0
                    rt['busy_until'] = 0
                    occupied = {(b['state']['x'], b['state']['y']) for b in materialized}
                    old = (state['x'], state['y'])
                    moved = world.autonomous._step_bot(bot, occupied, time.monotonic())
                    self.assertTrue(moved)
                    self.assertNotEqual((state['x'], state['y']), old)
                    entity = world.autonomous.entity(bot)
                    self.assertEqual((entity['fx'], entity['fy']), old)
                    self.assertTrue(entity['autonomous'])
                    self.assertIn(entity['appearance'], (0, 7))

                    # Put the resident back on a known encounter tile, run the real
                    # Battle engine and persist its changed party/items/collection.
                    training = world.autonomous._training_points(route)[0]
                    state['x'], state['y'] = training
                    before_revision = state['revision']
                    before_collection = len(state['creatures'])
                    result = world.autonomous._simulate_wild_battle(bot)
                    self.assertIsNotNone(result)
                    self.assertIn(result['result'], {'capture', 'win', 'loss', 'training'})
                    self.assertGreater(state['revision'], before_revision)
                    self.assertGreaterEqual(len(state['creatures']), before_collection)
                    bot['next_action_at'] = int(time.time()) + 120
                    await asyncio.to_thread(db.ai_commit_field, bot, {
                        'kind': 'wild', 'opponent': 0, 'result': result['result'], 'summary': result['summary']})
                    persisted = await asyncio.to_thread(db.ai_get, bot['id'])
                    self.assertEqual(persisted['state']['revision'], state['revision'])
                    self.assertEqual(len(persisted['state']['creatures']), len(state['creatures']))

                    # Materialized clients receive the same server-owned field actor.
                    observer = SimpleNamespace(state={'map': route['id'], 'x': state['x'], 'y': state['y']})
                    visible = world.autonomous.visible(observer, settings.interest_radius)
                    self.assertTrue(any(e['aiId'] == bot['id'] and e['map'] == route['id'] for e in visible))
                finally:
                    self.content.rng = old_rng
                    db.close()

        asyncio.run(exercise())

    def test_regional_travel_retreats_from_unsafe_maps_and_rotates_without_crossing_regions(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                cfg = Path(tmp) / 'config.ini'
                cfg.write_text(TEMPLATE.read_text(encoding='utf-8'), encoding='utf-8')
                settings = Settings.load(cfg)
                settings.config.set('database', 'backend', 'sqlite')
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    bot = world.autonomous.by_id[1]
                    self.assertEqual(bot['state']['home'], 'Kanto')
                    original = bot['state']['map']

                    # Routine travel teleports to a different eligible Kanto field,
                    # never an interior and never another region.
                    now = int(time.time())
                    bot['personality']['mapEnteredAt'] = now - world.autonomous.travel_min_dwell - 1
                    bot['personality']['nextTravelAt'] = now - 1
                    self.assertEqual(world.autonomous._travel_reason(bot, now), 'routine')
                    travel = world.autonomous._relocate_bot(bot, 'routine', int(time.time()))
                    self.assertIsNotNone(travel)
                    self.assertNotEqual(bot['state']['map'], original)
                    destination = self.content.maps[bot['state']['map']]
                    self.assertEqual(destination['region'], 'Kanto')
                    self.assertNotEqual(destination.get('mapType'), 8)
                    self.assertTrue(world.autonomous._travel_map_allowed(destination))
                    self.assertTrue(encounter_slots(destination, bot['state']))

                    # Force the same level-five bot into endgame Cerulean Cave. The
                    # policy must immediately classify it unsafe and retreat to a
                    # level-appropriate Kanto route/cave.
                    dangerous = self.content.maps['kanto_1_73']
                    point = world.autonomous._training_points(dangerous)[0]
                    old_map = bot['state']['map']
                    if old_map in world.autonomous.by_map:
                        world.autonomous.by_map[old_map] = [b for b in world.autonomous.by_map[old_map] if b['id'] != bot['id']]
                    bot['state'].update(map=dangerous['id'], x=point[0], y=point[1], direction='down', surf=False)
                    world.autonomous.by_map[dangerous['id']].append(bot)
                    world.autonomous.runtime.pop(bot['id'], None)
                    bot['personality']['travelPending'] = ''
                    bot['personality']['nextTravelAt'] = int(time.time()) + 9999
                    self.assertEqual(world.autonomous._travel_reason(bot, int(time.time())), 'unsafe')
                    retreat = world.autonomous._relocate_bot(bot, 'unsafe', int(time.time()))
                    self.assertIsNotNone(retreat)
                    safe = self.content.maps[bot['state']['map']]
                    profile = world.autonomous._travel_profile(safe)
                    level = world.autonomous._party_level(bot)
                    self.assertEqual(safe['region'], 'Kanto')
                    self.assertLessEqual(profile['q90'], level + world.autonomous.travel_safe_margin)
                    self.assertNotEqual(safe.get('mapType'), 8)

                    # Repeated losses mark a bot for retreat, and travel metadata is
                    # persisted together with the authoritative character state.
                    bot['personality']['consecutiveWildLosses'] = world.autonomous.travel_loss_retreats - 1
                    world.autonomous._record_wild_outcome(bot, {
                        'result': 'loss', 'level': int(level + 5), 'species': 'fr_1', 'summary': 'loss'})
                    self.assertEqual(bot['personality']['travelPending'], 'retreat')
                    bot['next_action_at'] = int(time.time()) + 30
                    await asyncio.to_thread(db.ai_commit_field, bot, {
                        'kind': 'travel', 'opponent': 0, 'result': 'relocate', 'summary': retreat['summary']})
                    persisted = await asyncio.to_thread(db.ai_get, bot['id'])
                    self.assertEqual(persisted['personality']['travelRegion'], 'Kanto')
                    self.assertEqual(persisted['personality']['travelPending'], 'retreat')
                    self.assertEqual(persisted['state']['map'], bot['state']['map'])

                    # Once a trainer has genuinely outgrown an early route, the
                    # progression policy selects a harder but still level-safe map
                    # instead of grinding the same starter field forever.
                    route1 = next(m for m in self.content.maps.values()
                                  if m['region'] == 'Kanto' and m['name'] == 'Route 1'
                                  and world.autonomous._travel_map_allowed(m))
                    old_map = bot['state']['map']
                    if old_map in world.autonomous.by_map:
                        world.autonomous.by_map[old_map] = [b for b in world.autonomous.by_map[old_map]
                                                            if b['id'] != bot['id']]
                    start = world.autonomous._training_points(route1)[0]
                    bot['state'].update(map=route1['id'], x=start[0], y=start[1], direction='down', surf=False)
                    world.autonomous.by_map[route1['id']].append(bot)
                    world.autonomous.runtime.pop(bot['id'], None)
                    for mon in world.autonomous._party_members(bot):
                        mon['level'] = 35
                    bot['personality']['travelPending'] = ''
                    bot['personality']['consecutiveWildLosses'] = 0
                    bot['personality']['mapWildWins'] = world.autonomous.travel_map_win_target
                    bot['personality']['mapEnteredAt'] = int(time.time()) - world.autonomous.travel_min_dwell - 1
                    bot['personality']['nextTravelAt'] = int(time.time()) + 9999
                    self.assertEqual(world.autonomous._travel_reason(bot, int(time.time())), 'progress')
                    harder = world.autonomous._select_travel_map(bot, 'progress')
                    self.assertIsNotNone(harder)
                    self.assertGreater(harder['mean'], world.autonomous._travel_profile(route1)['mean'])
                    self.assertLessEqual(harder['q90'], world.autonomous._party_level(bot)
                                         + world.autonomous.travel_safe_margin
                                         + min(6, int(world.autonomous._party_level(bot) // 20)))
                    advanced = world.autonomous._relocate_bot(bot, 'progress', int(time.time()), harder)
                    self.assertIsNotNone(advanced)
                    self.assertEqual(self.content.maps[bot['state']['map']]['region'], 'Kanto')
                    self.assertNotEqual(self.content.maps[bot['state']['map']].get('mapType'), 8)
                finally:
                    db.close()

        asyncio.run(exercise())

    def test_materialized_population_is_stable_scattered_and_cannot_mass_depart(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                cfg = Path(tmp) / 'config.ini'
                cfg.write_text(TEMPLATE.read_text(encoding='utf-8'), encoding='utf-8')
                settings = Settings.load(cfg)
                settings.config.set('database', 'backend', 'sqlite')
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    ai = world.autonomous
                    route = next(m for m in self.content.maps.values()
                                 if m['name'] == 'Route 29' and m['region'] == 'Johto / Sigma'
                                 and ai._travel_map_allowed(m))
                    residents = list(ai.by_map[route['id']])
                    self.assertGreater(len(residents), ai.world_per_map)

                    first = ai._materialized_bots(route['id'])
                    first_ids = [b['id'] for b in first]
                    self.assertEqual(len(first_ids), ai.world_per_map)
                    self.assertEqual(first_ids, [b['id'] for b in ai._materialized_bots(route['id'])])
                    ai._ensure_materialized_spacing(route['id'], first, ())
                    positions = [(b['state']['x'], b['state']['y']) for b in first]
                    self.assertEqual(len(positions), len(set(positions)))
                    # The greedy layout should keep a useful spatial spread even on
                    # irregular GBA grass geometry.
                    minimum = min(max(abs(a[0]-b[0]), abs(a[1]-b[1]))
                                  for i, a in enumerate(positions) for b in positions[i+1:])
                    self.assertGreaterEqual(minimum, 3)

                    # Every visible trainer becomes routine-travel eligible at once.
                    # One field tick may move only one; the immediate next tick moves
                    # none because the observed-map departure gate is still closed.
                    epoch = int(time.time())
                    for bot in first:
                        bot['personality']['mapEnteredAt'] = epoch - ai.travel_min_dwell - 1
                        bot['personality']['nextTravelAt'] = epoch - 1
                        bot['personality']['travelPending'] = ''
                    ai.field_wild_chance = 0
                    before = len(ai.by_map[route['id']])
                    await ai.field_tick({route['id']})
                    after_one = len(ai.by_map[route['id']])
                    self.assertEqual(after_one, before - 1)
                    second_ids = [b['id'] for b in ai._materialized_bots(route['id'])]
                    self.assertEqual(len(set(first_ids) & set(second_ids)), ai.world_per_map - 1)
                    await ai.field_tick({route['id']})
                    self.assertEqual(len(ai.by_map[route['id']]), after_one)
                    self.assertEqual(second_ids, [b['id'] for b in ai._materialized_bots(route['id'])])

                    # Even offline/routine relocation cannot drain the route below
                    # its persistent floor. This is the regression for empty maps.
                    for bot in list(ai.by_map[route['id']]):
                        bot['personality']['mapEnteredAt'] = epoch - ai.travel_min_dwell - 1
                        bot['personality']['nextTravelAt'] = epoch - 1
                        ai._relocate_bot(bot, 'routine', epoch)
                    self.assertEqual(len(ai.by_map[route['id']]), ai._resident_floor(route['id']))
                    self.assertGreater(len(ai.by_map[route['id']]), 0)
                finally:
                    db.close()

        asyncio.run(exercise())

    def test_party_uid_order_is_shared_by_follower_and_ranked_battle_and_legacy_fakes_are_removed(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                cfg = Path(tmp) / 'config.ini'
                cfg.write_text(TEMPLATE.read_text(encoding='utf-8'), encoding='utf-8')
                settings = Settings.load(cfg)
                settings.config.set('database', 'backend', 'sqlite')
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    # Fresh bots now start exactly like a real player: one starter.
                    self.assertTrue(all(len(b['state']['creatures']) == 1 and len(b['state']['party']) == 1
                                        for b in world.autonomous.snapshot))

                    bot = world.autonomous.by_id[2]
                    state = bot['state']
                    starter = state['creatures'][0]
                    real_a = self.content.new_mon('fr_19', 8, bot['username'])
                    real_b = self.content.new_mon('fr_25', 12, bot['username'])
                    state['creatures'].extend([real_a, real_b])
                    # Deliberately make party order disagree with collection order.
                    state['party'] = [real_b['uid'], starter['uid'], real_a['uid']]
                    state['revision'] += 1
                    await asyncio.to_thread(db.ai_save_world_states, [bot])
                    await world.autonomous.refresh_snapshot(force=True)
                    bot = world.autonomous.by_id[2]
                    entity = world.autonomous.entity(bot)
                    self.assertEqual(entity['followerUid'], real_b['uid'])
                    self.assertEqual(entity['follower'], real_b['species'])
                    self.assertEqual(entity['followerLevel'], real_b['level'])

                    human_state = world.initial('PartyTester', 'Johto', self.content.data['starters'][0], 0)
                    player = Player(9000002, 'PartyTester', human_state, asyncio.Queue())
                    await world.autonomous.challenge(player, bot['id'])
                    battle = world.battles[player.battle]
                    self.assertEqual([m['uid'] for m in battle.rosters[1]], bot['state']['party'])
                    self.assertEqual(battle.rosters[1][0]['uid'], entity['followerUid'])
                    self.assertEqual(battle.rosters[1][0]['species'], entity['follower'])
                    self.assertEqual(battle.rosters[1][0]['level'], entity['followerLevel'])
                    world.autonomous.release_engagement(bot['id'])

                    # Recreate exactly the old deterministic bootstrap extras and
                    # prove the one-time migration removes only those records while
                    # preserving a genuine captured Pokemon and the remaining order.
                    bot = await asyncio.to_thread(db.ai_get, 2)
                    state = bot['state']
                    starter = state['creatures'][0]
                    species = list(self.content.species)
                    legacy = []
                    for j in range(bot['id'] % 3):
                        key = species[(bot['id'] * 37 + j * 83) % len(species)]
                        legacy.append(self.content.new_mon(key, 4 + (bot['id'] + j) % 8, bot['username']))
                    captured = self.content.new_mon('fr_7', 14, bot['username'])
                    state['creatures'] = [starter, *legacy, captured]
                    state['party'] = [legacy[-1]['uid'], captured['uid'], starter['uid'], legacy[0]['uid']]
                    state['revision'] += 1
                    bot['personality'].pop('partyIdentityVersion', None)
                    await asyncio.to_thread(db.ai_rebalance_world, [bot])
                    await world.autonomous.refresh_snapshot(force=True)
                    async with world.autonomous.lock:
                        await world.autonomous._ensure_party_identity_locked()
                        await world.autonomous._refresh_snapshot_locked(force=True)
                    repaired = world.autonomous.by_id[2]
                    legacy_uids = {m['uid'] for m in legacy}
                    self.assertTrue(legacy_uids.isdisjoint({m['uid'] for m in repaired['state']['creatures']}))
                    self.assertIn(captured['uid'], {m['uid'] for m in repaired['state']['creatures']})
                    self.assertEqual(repaired['state']['party'], [captured['uid'], starter['uid']])
                    self.assertEqual(repaired['personality']['legacySyntheticPokemonRemoved'], 2)
                    repaired_entity = world.autonomous.entity(repaired)
                    self.assertEqual(repaired_entity['followerUid'], captured['uid'])
                finally:
                    db.close()

        asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
