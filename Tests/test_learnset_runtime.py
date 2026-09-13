"""ROM move-learning contracts through production battle, trade and saved state.

Combat fixtures give a real Chansey one HP and Splash to isolate the server EXP
path. No client grants EXP. All persistence uses isolated temporary SQLite.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
from nxt.combat import Battle
from nxt.config import Settings
from nxt.content import Content
from nxt.growth import Growth
from nxt.security import RequestError
from nxt.store import Store
from nxt.world import World


def namespace_fixture(content):
    """Isolate namespace evidence without changing the shared ROM catalog."""
    aliases = {'183': 1207, '210': 1234, '237': 1261}
    content.data = dict(content.data, learnsets={'moveIdAliases': {'johto': aliases}})
    content.moves = dict(content.moves)
    for raw, alias in aliases.items():
        content.moves[str(alias)] = dict(content.moves[raw], source='johto', sourceMoveId=int(raw), pp=5)
    content.species = dict(content.species)
    content.species['sg_256'] = dict(content.species['sg_256'], source='johto',
                                   learnset=[[1, 33], [12, 1207], [18, 1234], [25, 1261]],
                                   learnsetProvenance={'rawLearnset': [[1, 33], [12, 183], [18, 210], [25, 237]]})
    return 'sg_256'


class NativeMoveRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Content(ROOT / 'Server/data/world.json')

    def setUp(self):
        self.c = copy.copy(self.base)
        self.c.species = dict(self.base.species)
        self.c.growth = Growth(self.c)
        self.c.rng = random.Random(674)

    def level_to(self, mon, level):
        return self.c.gain_xp(mon, self.c.xp(level, self.c.species[mon['species']]['growth']) - mon['exp'])

    def test_cyndaquil_does_not_earn_ember_at_ten_and_learns_it_at_twelve(self):
        mon = self.c.new_mon('fr_155', 5)
        self.assertEqual([m['id'] for m in mon['moves']], [33, 43])
        self.level_to(mon, 10)
        self.assertEqual([m['id'] for m in mon['moves']], [33, 43, 108])
        self.assertEqual(mon['pendingLearn'], [])
        self.level_to(mon, 12)
        self.assertEqual([m['id'] for m in mon['moves']], [33, 43, 108, 52])
        self.assertEqual(mon['pendingLearn'], [])

    def test_multi_level_gain_keeps_pp_and_every_overflow_choice(self):
        mon = self.c.new_mon('fr_155', 5)
        mon['moves'][0]['pp'] = 3
        before = copy.deepcopy(mon['moves'])
        self.assertEqual(self.level_to(mon, 46), 41)
        self.assertEqual(mon['moves'][:2], before)
        self.assertEqual([m['id'] for m in mon['moves']], [33, 43, 108, 52])
        self.assertEqual(mon['pendingLearn'], [
            {'move': 98, 'level': 19, 'species': 'fr_155'},
            {'move': 172, 'level': 27, 'species': 'fr_155'},
            {'move': 129, 'level': 36, 'species': 'fr_155'},
            {'move': 53, 'level': 46, 'species': 'fr_155'},
        ])
        pending = copy.deepcopy(mon['pendingLearn'])
        self.c.gain_xp(mon, 0)
        self.assertEqual(mon['pendingLearn'], pending)

    def test_no_earned_native_move_does_not_fabricate_tackle(self):
        # Native cocoon-style rows may start above the creation level.
        self.c.species['fr_11'] = dict(self.c.species['fr_11'], learnset=[[7, 106]])
        mon = self.c.new_mon('fr_11', 5)
        self.assertEqual(mon['moves'], [])
        self.level_to(mon, 7)
        self.assertEqual(mon['moves'], [{'id': 106, 'pp': self.c.moves['106']['pp']}])

    def test_initial_assignment_stops_at_first_high_native_row_but_level_up_searches_later_rows(self):
        native = [[1, 33], [66, 52], [26, 98]]
        self.c.species['fr_155'] = dict(self.c.species['fr_155'], learnset=native)
        mon = self.c.new_mon('fr_155', 25)
        self.assertEqual([m['id'] for m in mon['moves']], [33])
        self.level_to(mon, 26)
        self.assertEqual([m['id'] for m in mon['moves']], [33, 98])
        self.assertEqual(self.c.species['fr_155']['learnset'], native)
        self.assertEqual([(m['level'], m['move']) for m in self.c.growth.level_up_moves(mon)],
                         [(1, 33), (66, 52), (26, 98)])

    def test_initial_duplicate_does_not_reorder_known_moves_and_forgotten_move_can_return(self):
        native = [[1, 33], [1, 43], [6, 33], [7, 108], [8, 52], [9, 98], [10, 33]]
        self.c.species['fr_155'] = dict(self.c.species['fr_155'], learnset=native)
        for level, expected in ((8, [33, 43, 108, 52]),
                                (9, [43, 108, 52, 98]),
                                (10, [108, 52, 98, 33])):
            with self.subTest(level=level):
                self.assertEqual([m['id'] for m in self.c.new_mon('fr_155', level)['moves']], expected)

    def test_empty_moves_already_have_a_working_struggle_battle_contract(self):
        mon = self.c.new_mon('fr_11', 5)
        mon['moves'] = []
        enemy = self.c.new_mon('fr_129', 5)
        battle = Battle(self.c, 'wild', [1, None], ['Trainer', 'Wild'], [[mon], [enemy]], [{}, {}])
        self.assertEqual(battle.view(0)['usable'], [])
        battle.choose(0, {'action': 'attack', 'slot': -1})
        battle.resolve()
        self.assertTrue(any('Struggle' in line for line in battle.logs))
        self.assertEqual(battle.mon(0)['moves'], [])

    def test_stale_first_pending_choice_cannot_block_valid_choice_after_migration(self):
        for stale in ({'move': 172, 'level': 1, 'species': 'fr_155'},
                      {'move': 65535, 'level': 19, 'species': 'fr_155'}):
            with self.subTest(stale=stale):
                mon = self.c.new_mon('fr_155', 12)
                self.level_to(mon, 19)
                earned = copy.deepcopy(mon['pendingLearn'])
                self.assertEqual(earned, [{'move': 98, 'level': 19, 'species': 'fr_155'}])
                mon['pendingLearn'].insert(0, stale)
                state = {'creatures': [mon]}
                original = copy.deepcopy(state)
                migrated = self.c.growth.migrate(state)
                self.assertEqual(state, original)
                self.assertEqual(migrated['creatures'][0]['moves'], mon['moves'])
                self.assertEqual(migrated['creatures'][0]['pendingLearn'], earned)
                learned = self.c.growth.learn(migrated, mon['uid'], 98, 0)
                self.assertEqual(learned['creatures'][0]['moves'][0]['id'], 98)
                self.assertEqual(self.c.growth.migrate(migrated), migrated)

    def test_queue_migration_prunes_malformed_duplicates_and_known_without_changing_progress(self):
        mon = self.c.new_mon('fr_155', 12)
        mon['moves'][0]['pp'] = 2
        self.level_to(mon, 27)
        valid = copy.deepcopy(mon['pendingLearn'])
        mon['pendingLearn'] = [None, [], {}, {'species': [], 'move': 98, 'level': 19},
                               {'species': 'fr_155', 'move': [], 'level': 19},
                               {'species': 'fr_155', 'move': True, 'level': 19},
                               {'species': 'fr_155', 'move': 98, 'level': 1},
                               {'species': 'fr_155', 'move': 33, 'level': 1},
                               valid[0], copy.deepcopy(valid[0]),
                               {'species': 'fr_155', 'move': 53, 'level': 46},
                               {'species': 'fr_4', 'move': 10, 'level': 1}, valid[1]]
        state = {'creatures': [mon], 'revision': 4}
        original = copy.deepcopy(state)
        migrated = self.c.growth.migrate(state)
        self.assertEqual(state, original)
        expected = copy.deepcopy(original)
        expected['creatures'][0]['pendingLearn'] = valid
        self.assertEqual(migrated, expected)
        self.assertEqual(self.c.growth.migrate(migrated), migrated)

    def test_reminder_repairs_old_moves_only_in_explicit_slot_and_preserves_pp_elsewhere(self):
        mon = self.c.new_mon('fr_155', 12)
        # Old fallback-generated choices are preserved until the owner picks a
        # replacement; even an off-profile move must not disappear at login.
        mon['moves'] = [{'id': 33, 'pp': 2}, {'id': 45, 'pp': 1}]
        state = {'creatures': [mon], 'revision': 9}
        original = copy.deepcopy(state)
        migrated = self.c.growth.migrate(state)
        self.assertEqual(migrated, original)
        self.assertEqual([(m['level'], m['move']) for m in self.c.growth.reminder_options(mon)],
                         [(1, 43), (6, 108), (12, 52)])
        updated = self.c.growth.remember(state, mon['uid'], 52, 1)
        self.assertEqual(state, original)
        expected = copy.deepcopy(original)
        expected['creatures'][0]['moves'][1] = {'id': 52, 'pp': self.c.moves['52']['pp']}
        self.assertEqual(updated, expected)
        with self.assertRaises(RequestError):
            self.c.growth.remember(updated, mon['uid'], 52, 0)

    def test_reminder_accepts_next_empty_slot_and_rejects_unearned_or_invalid_inputs(self):
        mon = self.c.new_mon('fr_155', 12)
        mon['moves'] = [{'id': 33, 'pp': 1}]
        state = {'creatures': [mon]}
        original = copy.deepcopy(state)
        updated = self.c.growth.remember(state, mon['uid'], 52, 1)
        self.assertEqual(updated['creatures'][0]['moves'],
                         [{'id': 33, 'pp': 1}, {'id': 52, 'pp': self.c.moves['52']['pp']}])
        for slot in (None, True, False, '0', 0.5, -1, 2, 3, 4, [], {}):
            with self.subTest(slot=slot), self.assertRaises(RequestError):
                self.c.growth.remember(state, mon['uid'], 52, slot)
            self.assertEqual(state, original)
        for move in (None, True, '52', 52.0, -1, 0, 33, 53, 98, 65536, [], {}):
            with self.subTest(move=move), self.assertRaises(RequestError):
                self.c.growth.remember(state, mon['uid'], move, 0)
            self.assertEqual(state, original)
        with self.assertRaises(RequestError):
            self.c.growth.remember(state, self.c.new_mon('fr_155', 12)['uid'], 52, 0)

    def test_reminder_excludes_all_queued_moves_and_does_not_bypass_ancestor_level(self):
        mon = self.c.new_mon('fr_155', 12)
        self.level_to(mon, 19)
        state = {'creatures': [mon]}
        evolved = self.c.growth.evolve(state, mon['uid'], 'fr_156')
        migrated = self.c.growth.migrate(evolved)
        self.assertEqual(migrated, evolved)
        self.assertNotIn(98, [m['move'] for m in self.c.growth.reminder_options(migrated['creatures'][0])])
        # Ancestor authorization remains valid for its existing earned queue.
        learned = self.c.growth.learn(migrated, mon['uid'], 98, 0)
        self.assertEqual(learned['creatures'][0]['moves'][0]['id'], 98)
        declined = self.c.growth.learn(migrated, mon['uid'], 98, None)
        with self.assertRaises(RequestError):
            self.c.growth.remember(declined, mon['uid'], 98, 0)
        self.level_to(declined['creatures'][0], 21)
        with self.assertRaises(RequestError):
            self.c.growth.remember(declined, mon['uid'], 98, 0)
        declined = self.c.growth.learn(declined, mon['uid'], 98, None)
        self.assertIn(98, [m['move'] for m in self.c.growth.reminder_options(declined['creatures'][0])])
        self.c.growth.remember(declined, mon['uid'], 98, 0)

    def test_profile_keeps_duplicate_rows_reminder_deduplicates_and_fields_are_private(self):
        mon = self.c.new_mon('fr_156', 12)
        mon['moves'] = [{'id': 33, 'pp': 2}]
        private = self.c.public_mon(mon)
        self.assertEqual([(m['level'], m['move']) for m in private['levelUpMoves']
                          if m['move'] == 108], [(1, 108), (6, 108)])
        self.assertEqual([m['move'] for m in private['relearnMoves']].count(108), 1)
        public = self.c.public_mon(mon, False)
        self.assertNotIn('relearnMoves', public)
        self.assertNotIn('levelUpMoves', public)

    def test_sparse_sigma_move_alias_is_a_valid_factory_queue_and_reminder_id(self):
        alias = 1024 + 52
        self.c.moves = dict(self.c.moves)
        self.c.moves[str(alias)] = dict(self.c.moves['52'], name='Sigma native move')
        self.c.species['fr_155'] = dict(self.c.species['fr_155'], learnset=[[1, 33], [12, alias]])
        mon = self.c.new_mon('fr_155', 12)
        self.assertEqual(mon['moves'][-1]['id'], alias)
        mon['moves'] = [{'id': 33, 'pp': 2}]
        options = self.c.growth.reminder_options(mon)
        self.assertEqual(options, [{'move': alias, 'name': 'Sigma native move', 'level': 12}])
        state = {'creatures': [mon]}
        remembered = self.c.growth.remember(state, mon['uid'], alias, 1)
        self.assertEqual(remembered['creatures'][0]['moves'][1], {'id': alias, 'pp': self.c.moves[str(alias)]['pp']})
        mon = self.c.new_mon('fr_155', 11)
        mon['moves'] = [{'id': mid, 'pp': 1} for mid in (33, 43, 108, 98)]
        self.level_to(mon, 12)
        self.assertEqual(mon['pendingLearn'], [{'move': alias, 'level': 12, 'species': 'fr_155'}])
        learned = self.c.growth.learn({'creatures': [mon]}, mon['uid'], alias, 3)
        self.assertEqual(learned['creatures'][0]['moves'][3]['id'], alias)

    def test_legacy_sigma_namespace_repair_preserves_slots_spent_pp_and_native_queue_source(self):
        key = namespace_fixture(self.c)
        self.c.species['fr_155'] = dict(self.c.species['fr_155'], learnset=[[18, 183]])
        mon = self.c.new_mon(key, 18)
        mon.pop('moveNamespaceVersion')
        mon['moves'] = [{'id': 183, 'pp': 9}, {'id': 33, 'pp': 2}]
        mon['evolutionHistory'] = ['fr_155']
        mon['pendingLearn'] = [
            {'move': 210, 'level': 18, 'species': key},
            {'move': 1234, 'level': 18, 'species': key},
            {'move': 183, 'level': 12, 'species': key},
            {'move': 183, 'level': 18, 'species': 'fr_155'},
        ]
        original = {'creatures': [mon]}
        before = copy.deepcopy(original)
        migrated = self.c.growth.migrate(original)
        self.assertEqual(original, before)
        expected = copy.deepcopy(before)
        expected['creatures'][0].update(
            moves=[{'id': 1207, 'pp': 5}, {'id': 33, 'pp': 2}], moveNamespaceVersion=1,
            pendingLearn=[{'move': 1234, 'level': 18, 'species': key},
                          {'move': 183, 'level': 18, 'species': 'fr_155'}])
        self.assertEqual(migrated, expected)
        self.assertEqual(self.c.growth.migrate(migrated), migrated)

    def test_namespace_repair_is_once_only_and_leaves_unearned_off_profile_or_colliding_moves(self):
        key = namespace_fixture(self.c)
        for moves in ([{'id': 183, 'pp': 2}],
                      [{'id': 237, 'pp': 4}, {'id': 295, 'pp': 2}],
                      [{'id': 183, 'pp': 2}, {'id': 1207, 'pp': 4}]):
            with self.subTest(moves=moves):
                mon = self.c.new_mon(key, 18)
                mon['moves'] = copy.deepcopy(moves)
                state = {'creatures': [mon]}
                self.assertEqual(self.c.growth.migrate(state), state,
                                 'New namespace-stamped moves must never be reinterpreted')
                mon.pop('moveNamespaceVersion')
                migrated = self.c.growth.migrate(state)['creatures'][0]
                if len(moves) == 1:
                    self.assertEqual(migrated['moves'], [{'id': 1207, 'pp': 2}])
                else:
                    self.assertEqual(migrated['moves'], moves)
                self.assertEqual(len({entry['id'] for entry in migrated['moves']}), len(migrated['moves']))
        # Being in Johto does not change a canonical FireRed move identity.
        mon = self.c.new_mon('fr_155', 18)
        mon.pop('moveNamespaceVersion')
        mon['moves'] = [{'id': 183, 'pp': 2}]
        migrated = self.c.growth.migrate({'creatures': [mon], 'home': 'Johto'})
        self.assertEqual(migrated['creatures'][0]['moves'], mon['moves'])


class DurableLearnsetWorldTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Content(ROOT / 'Server/data/world.json')

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / 'config.ini'
        path.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
        settings = Settings.load(path)
        settings.config.set('database', 'backend', 'sqlite')
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.c = copy.copy(self.base)
        self.c.growth = Growth(self.c)
        self.c.rng = random.Random(574)
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.c, self.db, self.settings)
        self.player = await self.new_player('CyndaAudit', 'fr_155')

    async def asyncTearDown(self):
        self.db.close()
        self.tmp.cleanup()

    async def new_player(self, name, starter):
        state = self.world.initial(name, 'Johto', starter, 0)
        uid = self.db.create(name, 'isolated-runtime-test', state)
        return await self.world.join(uid, name, None, asyncio.Queue(maxsize=2048))

    async def cold_restart(self, *players):
        identities = [(p.id, p.username) for p in players]
        self.db.close()
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.c, self.db, self.settings)
        return [await self.world.join(uid, name, None, asyncio.Queue(maxsize=2048))
                for uid, name in identities]

    async def begin_chansey(self, level):
        await self.world.start_wild(self.player, ('fr_113', level))
        battle = self.world.battles[self.player.battle]
        enemy = battle.mon(1)
        enemy['hp'] = 1
        enemy['moves'] = [{'id': 150, 'pp': self.c.moves['150']['pp']}]
        return battle

    async def win_chansey(self, level):
        battle = await self.begin_chansey(level)
        with patch.object(self.c.rng, 'randrange', return_value=0):
            await self.world.dispatch(self.player, {'op': 'battle', 'id': battle.id,
                                                   'action': 'attack', 'slot': 0})
        self.assertIsNone(self.player.battle)
        return battle

    async def test_real_battle_level_five_to_twelve_ember_and_pp_survive_cold_restart(self):
        before = copy.deepcopy(self.player.state['creatures'][0])
        battle = await self.win_chansey(30)
        mon = self.player.state['creatures'][0]
        self.assertEqual(mon['level'], 12)
        self.assertEqual(mon['exp'], before['exp'] + self.c.species['fr_113']['baseExperience'] * 30 // 7)
        self.assertEqual([m['id'] for m in mon['moves']], [33, 43, 108, 52])
        self.assertEqual(mon['moves'][0]['pp'], before['moves'][0]['pp'] - 1)
        self.assertEqual(mon['pendingLearn'], [])
        self.assertTrue(any(event['cue'] == 'level_up' for event in battle.audio_events))
        expected = copy.deepcopy(self.player.state)
        self.assertEqual(self.db.load(self.player.id), expected)
        self.player, = await self.cold_restart(self.player)
        self.assertEqual(self.player.state, expected)

    async def test_failed_battle_checkpoint_grants_neither_exp_nor_moves(self):
        battle = await self.begin_chansey(30)
        before = copy.deepcopy(self.player.state)
        with patch.object(self.c.rng, 'randrange', return_value=0), \
             patch.object(self.db, 'save_many', side_effect=RuntimeError('injected save failure')), \
             self.assertLogs('nxt.world', level='ERROR'):
            await self.world.dispatch(self.player, {'op': 'battle', 'id': battle.id,
                                                   'action': 'attack', 'slot': 0})
        self.assertIsNone(self.player.battle)
        self.assertEqual(self.player.state, before)
        self.assertEqual(self.db.load(self.player.id), before)
        self.player, = await self.cold_restart(self.player)
        self.assertEqual(self.player.state, before)

    async def test_login_reconciles_stale_queue_durably_without_rewriting_chosen_moves(self):
        old_save = copy.deepcopy(self.player.state)
        mon = old_save['creatures'][0]
        self.c.gain_xp(mon, self.c.xp(19, self.c.species[mon['species']]['growth']) - mon['exp'])
        mon['moves'][0]['pp'] = 2
        earned = copy.deepcopy(mon['pendingLearn'])
        mon['pendingLearn'].insert(0, {'move': 172, 'level': 1, 'species': 'fr_155'})
        old_save['revision'] += 1
        self.db.save_many([(self.player.id, old_save)])
        expected = copy.deepcopy(old_save)
        expected['creatures'][0]['pendingLearn'] = earned
        expected['revision'] += 1
        self.player, = await self.cold_restart(self.player)
        self.assertEqual(self.player.state, expected)
        self.assertEqual(self.db.load(self.player.id), expected)
        self.player, = await self.cold_restart(self.player)
        self.assertEqual(self.player.state, expected)
        await self.world.dispatch(self.player, {'op': 'pokemon.learn', 'uid': mon['uid'], 'move': 98, 'slot': 1})
        self.assertEqual(self.player.state['creatures'][0]['moves'][1]['id'], 98)

    async def test_legacy_sigma_namespace_and_queue_upgrade_commit_once_at_login(self):
        key = namespace_fixture(self.c)
        old_save = copy.deepcopy(self.player.state)
        mon = self.c.new_mon(key, 18, self.player.username)
        mon['uid'] = old_save['party'][0]
        mon.pop('moveNamespaceVersion')
        mon['moves'] = [{'id': 183, 'pp': 2}, {'id': 33, 'pp': 1}]
        mon['pendingLearn'] = [{'move': 210, 'level': 18, 'species': key}]
        old_save['creatures'][0] = mon
        self.world.adventure.observe(old_save, [key], caught=True)
        old_save['revision'] += 1
        self.db.save_many([(self.player.id, old_save)])
        expected = copy.deepcopy(old_save)
        expected['creatures'][0]['moves'][0]['id'] = 1207
        expected['creatures'][0]['pendingLearn'][0]['move'] = 1234
        expected['creatures'][0]['moveNamespaceVersion'] = 1
        expected['revision'] += 1
        self.player, = await self.cold_restart(self.player)
        self.assertEqual(self.player.state, expected)
        self.assertEqual(self.db.load(self.player.id), expected)
        self.player, = await self.cold_restart(self.player)
        self.assertEqual(self.player.state, expected)

    async def test_battle_overflow_choice_follows_evolution_trade_and_relogin(self):
        await self.win_chansey(100)
        await self.win_chansey(100)
        mon = self.player.state['creatures'][0]
        uid = mon['uid']
        earned = copy.deepcopy(mon['pendingLearn'])
        self.assertEqual(earned, [{'move': 98, 'level': 19, 'species': 'fr_155'}])
        before_moves = copy.deepcopy(mon['moves'])
        await self.world.dispatch(self.player, {'op': 'pokemon.evolve', 'uid': uid, 'target': 'fr_156'})
        evolved = self.player.state['creatures'][0]
        self.assertEqual(evolved['pendingLearn'], earned)
        self.assertEqual(evolved['moves'], before_moves)
        self.assertEqual(evolved['evolutionHistory'], ['fr_155'])
        other = await self.new_player('QueueRecipient', 'fr_1')
        await self.world.dispatch(self.player, {'op': 'invite', 'kind': 'trade', 'target': other.id})
        invite = next(iter(self.world.invites))
        await self.world.dispatch(other, {'op': 'invite.answer', 'id': invite, 'accept': True})
        trade = self.world.trades[self.player.trade]
        for player in (self.player, other):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'offer',
                                              'revision': trade['revision'],
                                              'offer': {'pokemon': list(player.state['party']), 'items': {}, 'money': 0}})
        for player in (self.player, other):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'lock', 'revision': trade['revision']})
        for player in (self.player, other):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'confirm',
                                              'revision': trade['revision'], 'digest': self.world.trade_digest(trade)})
        transferred = other.state['creatures'][0]
        self.assertEqual(transferred, evolved)
        self.player, other = await self.cold_restart(self.player, other)
        self.assertEqual(other.state['creatures'][0], evolved)
        with self.assertRaises(RequestError):
            await self.world.dispatch(self.player, {'op': 'pokemon.learn', 'uid': uid, 'move': 98, 'slot': 1})
        await self.world.dispatch(other, {'op': 'pokemon.learn', 'uid': uid, 'move': 98, 'slot': 1})
        learned = other.state['creatures'][0]
        self.assertEqual(learned['pendingLearn'], [])
        self.assertEqual(learned['moves'][1], {'id': 98, 'pp': self.c.moves['98']['pp']})
        self.assertEqual([learned['moves'][i] for i in (0, 2, 3)], [before_moves[i] for i in (0, 2, 3)])
        expected = copy.deepcopy(other.state)
        other, = await self.cold_restart(other)
        self.assertEqual(other.state, expected)


if __name__ == '__main__':
    unittest.main()
