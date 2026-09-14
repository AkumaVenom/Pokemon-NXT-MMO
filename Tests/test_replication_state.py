"""Multi-owner replication and queued snapshot regression contracts.

These tests use the real world actor, content and a temporary SQLite database.
They do not establish Windows/MySQL deployment or a concurrent-player load limit.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
from nxt.config import Settings
from nxt.content import Content
from nxt.security import RequestError
from nxt.store import Store
from nxt.world import Player, World


class ReplicationStateTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / 'config.ini'
        path.write_text((ROOT / 'Build/config_templates/Server/config.ini').read_text())
        settings = Settings.load(path)
        settings.config.set('database', 'backend', 'sqlite')
        # Replication fixtures explicitly enable the administrator exploration tools.
        settings.config.set('world', 'allow_alpha_atlas', 'true')
        settings.config.set('world', 'allow_alpha_surf', 'true')
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.content, self.db, self.settings)
        self.original_rng = self.content.rng
        self.content.rng = random.Random(123)
        self.a = await self.add_player('AkumaVenom', 'fr_152')
        self.b = await self.add_player('SpiderMight', 'fr_4')

    async def asyncTearDown(self):
        self.world.players.clear()
        self.content.rng = self.original_rng
        self.db.close()
        self.tmp.cleanup()

    async def add_player(self, name, starter):
        state = self.world.initial(name, 'Johto', starter, 0)
        uid = self.db.create(name, 'not-a-network-password-hash', state)
        return await self.world.join(uid, name, state, asyncio.Queue(maxsize=2048))

    def packets(self, player, kind=None):
        result = []
        while not player.queue.empty():
            packet = player.queue.get_nowait()
            if kind is None or packet['type'] == kind:
                result.append(packet)
        return result

    async def establish_visibility(self):
        await self.world.tick()
        self.packets(self.a)
        self.packets(self.b)

    async def invite(self, kind):
        await self.world.dispatch(self.a, {'op': 'invite', 'kind': kind, 'target': self.b.id})
        key = next(iter(self.world.invites))
        await self.world.dispatch(self.b, {'op': 'invite.answer', 'id': key, 'accept': True})

    async def test_distinct_starters_keep_owner_party_and_public_follower(self):
        a = self.packets(self.a, 'state')[-1]
        b = self.packets(self.b, 'state')[-1]
        self.assertEqual((a['ownerId'], b['ownerId']), (self.a.id, self.b.id))
        self.assertEqual(a['creatures'][0]['species'], 'fr_152')
        self.assertEqual(b['creatures'][0]['species'], 'fr_4')
        self.assertNotEqual(a['party'][0], b['party'][0])
        await self.world.tick()
        for player in (self.a, self.b):
            scene = self.packets(player, 'scene')[-1]
            followers = {p['id']: p['follower'] for p in scene['players']}
            self.assertEqual(followers, {self.a.id: 'fr_152', self.b.id: 'fr_4'})
        self.assertEqual(self.db.load(self.a.id)['creatures'][0]['species'], 'fr_152')
        self.assertEqual(self.db.load(self.b.id)['creatures'][0]['species'], 'fr_4')

    async def test_initial_and_joined_state_do_not_share_mutable_ownership(self):
        state = self.world.initial('ThirdTrainer', 'Johto', 'fr_7', 7)
        uid = self.db.create('ThirdTrainer', 'unused', state)
        player = await self.world.join(uid, 'ThirdTrainer', state, asyncio.Queue())
        state['items']['pokeball'] = 0
        state['creatures'][0]['moves'][0]['pp'] = 0
        state['party'].clear()
        self.assertEqual(player.state['items']['pokeball'], 20)
        self.assertGreater(player.state['creatures'][0]['moves'][0]['pp'], 0)
        self.assertEqual(len(player.state['party']), 1)
        self.assertEqual(self.a.state['creatures'][0]['species'], 'fr_152')
        self.assertEqual(self.b.state['creatures'][0]['species'], 'fr_4')

    async def test_queued_private_snapshot_is_frozen_at_its_revision(self):
        self.packets(self.a)
        original = copy.deepcopy(self.a.state)
        self.world.send_state(self.a)
        # A trusted world extension may mutate state before the writer drains it.
        self.a.state['items']['pokeball'] = 0
        self.a.state['creatures'][0]['moves'][0]['pp'] = 0
        self.a.state['party'].clear()
        self.a.state['revision'] += 1
        packet = self.packets(self.a, 'state')[-1]
        self.assertEqual(packet['revision'], original['revision'])
        self.assertEqual(packet['items'], original['items'])
        self.assertEqual(packet['party'], original['party'])
        self.assertEqual(packet['creatures'][0]['moves'], original['creatures'][0]['moves'])

    async def test_slow_writers_cannot_share_one_nested_broadcast(self):
        self.packets(self.a)
        self.packets(self.b)
        payload = {'members': [{'name': 'Original'}]}
        self.a.send('extension_event', data=payload)
        self.b.send('extension_event', data=payload)
        payload['members'][0]['name'] = 'Changed later'
        a = self.packets(self.a)[0]
        b = self.packets(self.b)[0]
        self.assertEqual(a['data']['members'][0]['name'], 'Original')
        a['data']['members'][0]['name'] = 'Changed by first writer'
        self.assertEqual(b['data']['members'][0]['name'], 'Original')

    async def test_owner_mutation_sends_no_other_private_state(self):
        await self.establish_visibility()
        before_b = copy.deepcopy(self.b.state)
        await self.world.dispatch(self.a, {'op': 'buy', 'item': 'potion', 'quantity': 1,
                                          'ownerId': self.b.id, 'playerId': self.b.id})
        own = self.packets(self.a, 'state')[-1]
        self.assertEqual(own['ownerId'], self.a.id)
        self.assertEqual(own['items']['potion'], 6)
        await self.world.tick()
        self.assertFalse(self.packets(self.b, 'state'))
        self.assertEqual(self.b.state, before_b)
        self.assertEqual(self.db.load(self.b.id), before_b)

    async def test_cross_owner_party_and_item_targets_are_rejected(self):
        before_a = copy.deepcopy(self.a.state)
        before_b = copy.deepcopy(self.b.state)
        for command in ({'op': 'party', 'party': self.b.state['party']},
                        {'op': 'use', 'item': 'potion', 'uid': self.b.state['party'][0]}):
            with self.assertRaises(RequestError):
                await self.world.dispatch(self.a, command)
        self.assertEqual(self.a.state, before_a)
        self.assertEqual(self.b.state, before_b)

    async def test_replaced_session_cannot_dispatch_as_current_owner(self):
        impostor = Player(self.a.id, self.a.username, copy.deepcopy(self.a.state), asyncio.Queue())
        before = self.db.load(self.a.id)
        with self.assertRaisesRegex(RequestError, 'session is closed'):
            await self.world.dispatch(impostor, {'op': 'buy', 'item': 'potion', 'quantity': 1})
        self.assertEqual(self.db.load(self.a.id), before)
        self.assertEqual(self.a.state, before)

    async def test_party_input_cannot_mutate_committed_state_after_dispatch(self):
        selection = list(self.a.state['party'])
        await self.world.dispatch(self.a, {'op': 'party', 'party': selection})
        selection.clear()
        self.assertEqual(len(self.a.state['party']), 1)
        self.assertEqual(self.db.load(self.a.id)['party'], self.a.state['party'])

    async def test_stationary_lead_and_shiny_changes_replicate_to_both_clients(self):
        state = copy.deepcopy(self.a.state)
        extra = self.content.new_mon('fr_7', 5, self.a.username)
        extra.update(variety='shiny', shiny=True)
        state['creatures'].append(extra)
        state['party'].append(extra['uid'])
        await self.world.commit(self.a, state)
        await self.establish_visibility()
        await self.world.dispatch(self.a, {'op': 'party', 'party': list(reversed(state['party']))})
        await self.world.tick()
        for observer in (self.a, self.b):
            scenes = self.packets(observer, 'scene')
            changed = next(p for p in scenes[-1]['players'] if p['id'] == self.a.id)
            self.assertEqual(changed['follower'], 'fr_7')
            self.assertTrue(changed['shiny'])
        self.assertEqual(self.b.entity()['follower'], 'fr_4')

    async def test_stationary_busy_and_surf_flags_replicate(self):
        await self.establish_visibility()
        await self.world.dispatch(self.a, {'op': 'surf'})
        await self.world.tick()
        changed = self.packets(self.b, 'scene')[-1]['players']
        self.assertTrue(next(p for p in changed if p['id'] == self.a.id)['surf'])
        await self.invite('trade')
        await self.world.tick()
        for observer in (self.a, self.b):
            changed = self.packets(observer, 'scene')[-1]['players']
            self.assertTrue(all(p['busy'] for p in changed))
        trade = self.world.trades[self.a.trade]
        await self.world.dispatch(self.a, {'op': 'trade', 'id': trade['id'], 'action': 'cancel'})
        await self.world.tick()
        self.assertTrue(all(not p['busy'] for p in self.packets(self.b, 'scene')[-1]['players']))

    async def test_movement_sequence_and_follower_delta_remain_owner_bound(self):
        await self.establish_visibility()
        old = (self.a.state['x'], self.a.state['y'])
        b_before = copy.deepcopy(self.b.state)
        await self.world.dispatch(self.a, {'op': 'move', 'seq': 1, 'direction': 'right',
                                          'id': self.b.id, 'x': 500, 'follower': 'fr_4'})
        await self.world.tick()
        e = next(p for p in self.packets(self.b, 'scene')[-1]['players'] if p['id'] == self.a.id)
        self.assertEqual((e['x'], e['y']), (old[0] + 1, old[1]))
        self.assertEqual((e['fx'], e['fy']), old)
        self.assertEqual(e['follower'], 'fr_152')
        self.assertEqual(self.b.state, b_before)
        await self.world.dispatch(self.a, {'op': 'move', 'seq': 1, 'direction': 'right'})
        self.assertEqual(self.a.state['x'], old[0] + 1)

    async def test_map_transfer_removes_old_entity_and_reintroduces_new_snapshot(self):
        await self.establish_visibility()
        await self.world.dispatch(self.a, {'op': 'travel', 'map': 'kanto_3_0'})
        await self.world.tick()
        scene = self.packets(self.b, 'scene')[-1]
        self.assertIn(self.a.id, scene['gone'])
        self.assertNotIn(self.a.id, [p['id'] for p in scene['players']])
        own = self.packets(self.a, 'scene')[-1]
        self.assertEqual(own['map'], 'kanto_3_0')
        self.assertNotIn(self.b.id, [p['id'] for p in own['players']])
        await self.world.dispatch(self.a, {'op': 'travel', 'map': 'johto_3_0'})
        await self.world.tick()
        entity = next(p for p in self.packets(self.b, 'scene')[-1]['players'] if p['id'] == self.a.id)
        self.assertEqual(entity['follower'], 'fr_152')

    async def test_interest_exit_and_reentry_send_removal_and_complete_entity(self):
        self.world.s = dataclasses.replace(self.settings, interest_radius=2)
        await self.establish_visibility()
        self.world.relocate(self.a, 'johto_3_0', 10, 10)
        await self.world.tick()
        self.assertIn(self.a.id, self.packets(self.b, 'scene')[-1]['gone'])
        self.world.relocate(self.a, 'johto_3_0', *self.content.maps['johto_3_0']['spawn'])
        await self.world.tick()
        entity = next(p for p in self.packets(self.b, 'scene')[-1]['players'] if p['id'] == self.a.id)
        self.assertEqual(entity, self.a.entity())

    async def test_logout_removes_presence_and_relogin_restores_own_starter(self):
        await self.establish_visibility()
        old = self.a
        await self.world.leave(old)
        await self.world.tick()
        self.assertIn(old.id, self.packets(self.b, 'scene')[-1]['gone'])
        self.a = await self.world.join(old.id, old.username, self.db.load(old.id), asyncio.Queue())
        await self.world.tick()
        state = self.packets(self.a, 'state')[-1]
        self.assertEqual(state['creatures'][0]['species'], 'fr_152')
        entity = next(p for p in self.packets(self.b, 'scene')[-1]['players'] if p['id'] == old.id)
        self.assertEqual(entity['follower'], 'fr_152')
        with self.assertRaises(RequestError):
            await self.world.dispatch(old, {'op': 'save'})

    async def test_duel_snapshots_are_private_and_do_not_change_saved_rosters(self):
        observer = await self.add_player('Observer', 'fr_7')
        before = {p.id: copy.deepcopy(p.state) for p in (self.a, self.b)}
        self.packets(observer)
        await self.invite('challenge')
        battle = self.world.battles[self.a.battle]
        a = self.packets(self.a, 'battle')[-1]['battle']
        b = self.packets(self.b, 'battle')[-1]['battle']
        self.assertEqual(a['you']['species'], 'fr_152')
        self.assertEqual(b['you']['species'], 'fr_4')
        self.assertEqual(a['opponent']['species'], 'fr_4')
        self.assertEqual(b['opponent']['species'], 'fr_152')
        for view in (a, b):
            for private_key in ('moves', 'stats', 'nature', 'originalTrainer', 'exp'):
                self.assertNotIn(private_key, view['opponent'])
        with self.assertRaises(RequestError):
            await self.world.dispatch(observer, {'op': 'battle', 'id': battle.id,
                                                 'action': 'run', 'playerId': self.a.id})
        self.assertFalse(self.packets(observer, 'battle'))
        await self.world.dispatch(self.a, {'op': 'battle', 'id': battle.id, 'action': 'run'})
        for p in (self.a, self.b):
            self.assertEqual(p.state, before[p.id])
            self.assertEqual(self.db.load(p.id), before[p.id])

    async def test_pending_battle_packet_preserves_pp_before_later_turn(self):
        await self.world.start_wild(self.a, ('fr_129', 2))
        battle = self.world.battles[self.a.battle]
        original_pp = battle.mon(0)['moves'][0]['pp']
        battle.mon(0)['moves'][0]['pp'] = 0
        view = self.packets(self.a, 'battle')[-1]['battle']
        self.assertEqual(view['you']['moves'][0]['pp'], original_pp)
        self.assertEqual(view['party'][0]['moves'][0]['pp'], original_pp)

    async def test_trade_swaps_unique_owners_and_replicates_both_new_followers(self):
        await self.establish_visibility()
        old_ids = {p.id: p.state['party'][0] for p in (self.a, self.b)}
        await self.invite('trade')
        trade = self.world.trades[self.a.trade]
        for player in (self.a, self.b):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'offer',
                                               'revision': trade['revision'],
                                               'offer': {'pokemon': [old_ids[player.id]], 'money': 0, 'items': {}}})
        for player in (self.a, self.b):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'lock',
                                               'revision': trade['revision']})
        for player in (self.a, self.b):
            await self.world.dispatch(player, {'op': 'trade', 'id': trade['id'], 'action': 'confirm',
                                               'revision': trade['revision'], 'digest': self.world.trade_digest(trade)})
        self.assertEqual(self.a.state['party'], [old_ids[self.b.id]])
        self.assertEqual(self.b.state['party'], [old_ids[self.a.id]])
        await self.world.tick()
        for player in (self.a, self.b):
            packets = self.packets(player)
            state = [p for p in packets if p['type'] == 'state'][-1]
            self.assertEqual(state['ownerId'], player.id)
            self.assertEqual(state['party'], player.state['party'])
            scene = [p for p in packets if p['type'] == 'scene'][-1]
            followers = {p['id']: p['follower'] for p in scene['players']}
            self.assertEqual(followers, {self.a.id: 'fr_4', self.b.id: 'fr_152'})
            self.assertEqual(self.db.load(player.id), player.state)

    async def test_autosave_completion_cannot_mark_a_replacement_session_saved(self):
        self.a.state['revision'] += 1
        entered = threading.Event()
        finish = threading.Event()
        save = self.db.save_many

        def delayed_save(records):
            entered.set()
            if not finish.wait(5):
                raise AssertionError('Test failed to release autosave worker')
            save(records)

        self.db.save_many = delayed_save
        task = asyncio.create_task(self.world.save_all())
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 3))
            replacement = Player(self.a.id, self.a.username, copy.deepcopy(self.a.state), asyncio.Queue())
            replacement.saved_revision = 0
            self.world.players[self.a.id] = replacement
            finish.set()
            self.assertEqual(await task, 1)
            self.assertEqual(replacement.saved_revision, 0)
        finally:
            finish.set()
            await task
            self.db.save_many = save


if __name__ == '__main__':
    unittest.main()
