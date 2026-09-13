"""Renamed Sigma moves retain their source identity and bounded ROM effects.

These exercise real turn resolution with deterministic damage/RNG. They verify
the shipped alpha interpretation of the audited table, not full ROM emulation.
"""
from __future__ import annotations

import copy
import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
from nxt.combat import Battle
from nxt.content import Content
from nxt.security import RequestError


class SigmaMoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Content(ROOT / 'Server/data/world.json')
        cls.audit = json.loads((ROOT / 'Server/data/learnsets.json').read_text())

    def setUp(self):
        self.c = copy.copy(self.base)
        self.c.moves = dict(self.base.moves)
        self.c.rng = random.Random(671)

    def battle(self, move, enemy_move=150, attacker='fr_1', defender='fr_1'):
        lead = self.c.new_mon(attacker, 50)
        enemy = self.c.new_mon(defender, 50)
        lead['moves'] = [{'id': move, 'pp': self.c.moves[str(move)]['pp']}]
        enemy['moves'] = [{'id': enemy_move, 'pp': self.c.moves[str(enemy_move)]['pp']}]
        self.c.stats = lambda m: [500, 20, 100, 120 if m['uid'] == lead['uid'] else 60, 200, 100]
        lead['hp'] = enemy['hp'] = 500
        self.c.rng.randrange = lambda n: 1  # Hits, without critical damage.
        self.c.rng.randint = lambda low, high: high
        self.c.rng.random = lambda: .75
        return Battle(self.c, 'duel', [1, 2], ['Trainer', 'Opponent'], [[lead], [enemy]], [{}, {}])

    def turn(self, battle):
        battle.choose(0, {'action': 'attack', 'slot': 0})
        battle.choose(1, {'action': 'attack', 'slot': 0})
        battle.resolve()

    def test_all_seven_native_variants_are_used_and_selectable(self):
        learned = {mid for row in self.audit['speciesOverrides'].values() for level, mid in row['learnset']}
        self.assertEqual(set(self.audit['moveOverrides']), {'1207', '1234', '1261', '1318', '1319', '1321', '1370'})
        for key, move in self.audit['moveOverrides'].items():
            with self.subTest(move=key):
                self.assertIn(int(key), learned)
                self.assertEqual(move['id'], 1024 + move['sourceMoveId'])
                self.assertEqual(move['source'], 'johto')
                self.assertEqual(self.c.moves.get(key), move)
                battle = self.battle(int(key))
                self.assertEqual(battle.usable(battle.mon(0)), [0])
                self.turn(battle)
                self.assertEqual(battle.mon(0)['moves'][0]['pp'], move['pp'] - 1)
                event = next(e for e in battle.audio_events if e['cue'] == 'move' and e['side'] == 0)
                self.assertEqual(event['move'], int(key))
                self.assertEqual(event['moveType'], move['type'])

    def test_close_combat_is_source_hit_with_source_power_and_priority(self):
        battle = self.battle(1207, defender='fr_7')
        self.turn(battle)
        self.assertEqual(battle.mon(1)['hp'], 488)
        self.assertEqual(battle.tiers(battle.mon(0)), [0] * 7)
        self.assertEqual(self.c.moves['1207']['priority'], 0)
        self.assertEqual(self.c.moves['183']['priority'], 1)
        self.assertEqual(self.c.moves['183']['power'], 40)
        self.assertEqual(self.c.moves['183']['name'], 'Mach Punch')

    def test_x_scissor_is_a_repeatable_source_hit(self):
        battle = self.battle(1234)
        self.turn(battle)
        first = 500 - battle.mon(1)['hp']
        self.turn(battle)
        self.assertEqual(first, 9)
        self.assertEqual(500 - battle.mon(1)['hp'], first * 2)
        self.assertEqual(self.c.moves['210']['name'], 'Fury Cutter')
        self.assertEqual(self.c.moves['210']['power'], 10)

    def test_terastallize_uses_source_special_category_and_priority(self):
        battle = self.battle(1261)
        lead_uid = battle.mon(0)['uid']
        self.c.stats = lambda m: [500, 20, 100, 1 if m['uid'] == lead_uid else 200, 200, 100]
        battle.mon(0)['status'] = 'burn'
        self.turn(battle)
        self.assertEqual(battle.mon(1)['hp'], 393)
        self.assertEqual(self.c.moves['1261']['priority'], 1)
        self.assertEqual(next(e for e in battle.audio_events if e['cue'] == 'move')['side'], 0)
        self.assertEqual(battle.mon(0)['species'], 'fr_1')
        self.assertEqual(self.c.moves['237']['name'], 'Hidden Power')
        self.assertEqual(self.c.moves['237']['power'], 1)

    def test_special_hits_preserve_native_type_nine_and_category(self):
        for mid in (1318, 1319):
            with self.subTest(move=mid):
                battle = self.battle(mid, defender='fr_147')
                self.turn(battle)
                hit = next(e for e in battle.audio_events if e['cue'] == 'hit' and e['side'] == 1)
                self.assertEqual(self.c.moves[str(mid)]['sourceType'], 9)
                # The source type-name table still labels slot 9 as ???. Do
                # not infer modern Fairy matchups from these renamed moves.
                self.assertEqual(self.c.moves[str(mid)]['type'], 9)
                self.assertEqual(hit['effectiveness'], 1)
                self.assertEqual(hit['damage'], 72 if mid == 1318 else 81)

    def test_moonblast_uses_native_fifty_percent_special_defense_effect(self):
        for chance, expected in ((.49, -1), (.5, 0)):
            with self.subTest(chance=chance):
                battle = self.battle(1319)
                self.c.rng.random = lambda: chance
                self.turn(battle)
                self.assertEqual(battle.tiers(battle.mon(1))[5], expected)
                self.assertEqual(battle.tiers(battle.mon(1))[4], 0)
                self.assertEqual(battle.tiers(battle.mon(1))[0], 0)

    def test_moonblast_cannot_lower_stats_after_miss_protect_or_faint(self):
        for scenario in ('miss', 'protect', 'faint', 'minimum'):
            with self.subTest(scenario=scenario):
                battle = self.battle(1319, enemy_move=182 if scenario == 'protect' else 150)
                self.c.rng.random = lambda: .01
                if scenario == 'miss':
                    battle.tiers(battle.mon(0))[0] = -6
                    self.c.rng.randrange = lambda n: 99 if n == 100 else 1
                elif scenario == 'faint':
                    battle.mon(1)['hp'] = 1
                elif scenario == 'minimum':
                    battle.tiers(battle.mon(1))[5] = -6
                self.turn(battle)
                self.assertEqual(battle.tiers(battle.mon(1))[5], -6 if scenario == 'minimum' else 0)
                self.assertFalse(any(e['cue'] == 'stat_down' for e in battle.audio_events))

    def test_accuracy_and_special_defense_are_independent(self):
        battle = self.battle(28)
        self.turn(battle)
        self.assertEqual(battle.tiers(battle.mon(1))[0], -1)
        self.assertEqual(battle.tiers(battle.mon(1))[5], 0)
        battle = self.battle(33)
        battle.tiers(battle.mon(0))[5] = -6
        self.c.rng.randrange = lambda n: 90 if n == 100 else 1
        self.turn(battle)
        self.assertTrue(any(e['cue'] == 'hit' and e['side'] == 1 for e in battle.audio_events))

    def test_roost_and_aqua_ring_use_native_immediate_half_heal(self):
        for mid in (1321, 1370):
            with self.subTest(move=mid):
                battle = self.battle(mid, enemy_move=182, attacker='fr_16')
                battle.mon(0)['hp'] = 100
                self.turn(battle)
                self.assertEqual(battle.mon(0)['hp'], 350)
                recovered = next(e for e in battle.audio_events if e['cue'] == 'recover')
                self.assertEqual(recovered['side'], 0)
                self.assertEqual(recovered['amount'], 250)
                # The audited source records select Recover, with no residual
                # Aqua Ring heal or modern Roost Flying suppression added.
                battle.mon(0)['moves'] = [{'id': 150, 'pp': 10}]
                battle.mon(1)['moves'] = [{'id': 89, 'pp': 10}]
                self.turn(battle)
                self.assertEqual(battle.mon(0)['hp'], 350)
                self.assertFalse(any(e['cue'] == 'recover' for e in battle.audio_events))

    def test_source_recovery_caps_hp_and_reports_full_hp_failure(self):
        for mid in (1321, 1370):
            with self.subTest(move=mid):
                battle = self.battle(mid)
                battle.mon(0)['hp'] = 499
                self.turn(battle)
                self.assertEqual(battle.mon(0)['hp'], 500)
                self.assertEqual(next(e for e in battle.audio_events if e['cue'] == 'recover')['amount'], 1)
                self.turn(battle)
                self.assertFalse(any(e['cue'] == 'recover' for e in battle.audio_events))
                self.assertIn('But it failed!', battle.logs)

    def test_native_variants_do_not_enable_canonical_status_names(self):
        for mid in (294, 297, 346):
            with self.subTest(move=mid):
                battle = self.battle(mid)
                self.assertEqual(battle.usable(battle.mon(0)), [])
                with self.assertRaises(RequestError):
                    battle.choose(0, {'action': 'attack', 'slot': 0})


if __name__ == '__main__':
    unittest.main()
