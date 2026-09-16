"""Regression coverage for authoritative autonomous Pokemon level evolution."""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))

from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.world import World

TEMPLATE = ROOT / 'Build/config_templates/Server/config.ini'


class AutonomousEvolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')

    def test_level_evolution_is_real_persistent_and_shared_by_field_follower_and_party(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as tmp:
                cfg = Path(tmp) / 'config.ini'
                cfg.write_text(TEMPLATE.read_text(encoding='utf-8'), encoding='utf-8')
                settings = Settings.load(cfg)
                settings.config.set('database', 'backend', 'sqlite')
                old_rng = self.content.rng
                self.content.rng = random.Random(1609202601)
                db = Store(settings)
                db.acquire_lease()
                try:
                    world = World(self.content, db, settings)
                    await world.autonomous.initialize()
                    ai = world.autonomous
                    bot = ai.by_id[1]

                    # Start one real owned Charmander one EXP point below Lv.16.
                    # A real wild battle must level it and the AI must accept the
                    # authored FireRed level evolution through Growth.evolve().
                    mon = self.content.new_mon('fr_4', 15, bot['username'])
                    mon['exp'] = self.content.xp(16, self.content.species['fr_4']['growth']) - 1
                    uid = mon['uid']
                    state = bot['state']
                    state['creatures'] = [mon]
                    state['party'] = [uid]
                    state['money'] = 0
                    state['items']['pokeball'] = 0
                    bot['personality']['capture'] = 0

                    route = next(m for m in self.content.maps.values()
                                 if m['region'] == 'Kanto' and m['name'] == 'Route 1'
                                 and ai._travel_map_allowed(m))
                    x, y = ai._training_points(route)[0]
                    old_map = state['map']
                    if old_map in ai.by_map:
                        ai.by_map[old_map] = [b for b in ai.by_map[old_map] if b['id'] != bot['id']]
                    state.update(map=route['id'], x=x, y=y, direction='down', surf=False)
                    ai.by_map[route['id']].append(bot)
                    ai.runtime.pop(bot['id'], None)

                    before_moves = copy.deepcopy(mon['moves'])
                    result = ai._simulate_wild_battle(bot)
                    self.assertIsNotNone(result)
                    evolved = next(m for m in state['creatures'] if m['uid'] == uid)
                    self.assertGreaterEqual(evolved['level'], 16)
                    self.assertEqual(evolved['species'], 'fr_5')
                    self.assertEqual(evolved['uid'], uid)
                    self.assertEqual(state['party'], [uid])
                    self.assertIn('fr_4', evolved['evolutionHistory'])
                    self.assertEqual(evolved['originalTrainer'], bot['username'])
                    self.assertTrue(result['evolutions'])
                    self.assertEqual(result['evolutions'][0]['source'], 'fr_4')
                    self.assertEqual(result['evolutions'][0]['target'], 'fr_5')
                    self.assertIn('evolved into Charmeleon', result['summary'])
                    # Evolution never replaces chosen move slots; the wild battle
                    # may legitimately spend PP before the species transition.
                    self.assertEqual([m['id'] for m in evolved['moves'][:len(before_moves)]],
                                     [m['id'] for m in before_moves])

                    entity = ai.entity(bot)
                    self.assertEqual(entity['followerUid'], uid)
                    self.assertEqual(entity['follower'], 'fr_5')
                    self.assertEqual(entity['followerLevel'], evolved['level'])

                    await asyncio.to_thread(db.ai_save_world_states, [bot])
                    persisted = await asyncio.to_thread(db.ai_get, bot['id'])
                    saved = next(m for m in persisted['state']['creatures'] if m['uid'] == uid)
                    self.assertEqual(saved['species'], 'fr_5')
                    self.assertEqual(saved['uid'], uid)
                    self.assertEqual(persisted['state']['party'], [uid])
                finally:
                    self.content.rng = old_rng
                    db.close()

        asyncio.run(exercise())

    def test_ranked_development_and_upgrade_repair_level_evolutions_without_faking_stone_or_trade(self):
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
                    bot = ai.by_id[2]

                    # Ranked development uses the same level-evolution path.
                    bulb = self.content.new_mon('fr_1', 15, bot['username'])
                    bulb['exp'] = self.content.xp(16, self.content.species['fr_1']['growth']) - 1
                    bot['state']['creatures'] = [bulb]
                    bot['state']['party'] = [bulb['uid']]
                    bot['personality']['training'] = 1.0
                    events = ai._develop(bot, True)
                    evolved = bot['state']['creatures'][0]
                    self.assertEqual(evolved['species'], 'fr_2')
                    self.assertEqual(evolved['uid'], bulb['uid'])
                    self.assertEqual(bot['state']['party'], [bulb['uid']])
                    self.assertEqual([(e['source'], e['target']) for e in events], [('fr_1', 'fr_2')])

                    # Recreate an old v0.6.2 state with a badly overdue level form,
                    # alongside stone/trade evolutions. The one-time upgrade must
                    # repair only real level rules; it must not invent a stone or
                    # trade event that never happened.
                    charmander = self.content.new_mon('fr_4', 36, bot['username'])
                    pikachu = self.content.new_mon('fr_25', 50, bot['username'])
                    kadabra = self.content.new_mon('fr_64', 50, bot['username'])
                    # A freshly caught over-level Caterpie is legitimate and has
                    # no post-capture EXP evidence; migration must not invent a
                    # missed level-up event for it.
                    caterpie = self.content.new_mon('fr_10', 10, bot['username'])
                    party = [charmander['uid'], pikachu['uid'], kadabra['uid']]
                    bot['state']['creatures'] = [charmander, pikachu, kadabra, caterpie]
                    bot['state']['party'] = list(party)
                    bot['personality'].pop('levelEvolutionVersion', None)
                    bot['personality'].pop('legacyLevelEvolutionsRepaired', None)
                    await asyncio.to_thread(db.ai_rebalance_world, [bot])
                    await ai.refresh_snapshot(force=True)
                    async with ai.lock:
                        await ai._ensure_autonomous_level_evolution_locked()
                        await ai._refresh_snapshot_locked(force=True)

                    repaired = ai.by_id[2]
                    owned = {m['uid']: m for m in repaired['state']['creatures']}
                    self.assertEqual(owned[charmander['uid']]['species'], 'fr_6')
                    self.assertEqual(owned[charmander['uid']]['evolutionHistory'], ['fr_4', 'fr_5'])
                    self.assertEqual(owned[pikachu['uid']]['species'], 'fr_25')
                    self.assertEqual(owned[kadabra['uid']]['species'], 'fr_64')
                    self.assertEqual(owned[caterpie['uid']]['species'], 'fr_10')
                    self.assertEqual(repaired['state']['party'], party)
                    self.assertEqual(repaired['personality']['levelEvolutionVersion'], 1)
                    self.assertEqual(repaired['personality']['legacyLevelEvolutionsRepaired'], 2)

                    persisted = await asyncio.to_thread(db.ai_get, 2)
                    persisted_owned = {m['uid']: m for m in persisted['state']['creatures']}
                    self.assertEqual(persisted_owned[charmander['uid']]['species'], 'fr_6')
                    self.assertEqual(persisted_owned[pikachu['uid']]['species'], 'fr_25')
                    self.assertEqual(persisted_owned[kadabra['uid']]['species'], 'fr_64')
                    self.assertEqual(persisted_owned[caterpie['uid']]['species'], 'fr_10')
                finally:
                    db.close()

        asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
