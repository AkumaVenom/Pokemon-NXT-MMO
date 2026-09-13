"""Real, isolated TCP/WebSocket ownership and replication regressions.

These tests exercise production authentication, packet dispatch, persistence and
scene serialization. They do not claim Windows, MySQL or internet load coverage.
"""
from __future__ import annotations

import asyncio
import copy
import dataclasses
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import aiohttp
from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
from server import Service
from nxt.config import Settings
from nxt.content import Content
from nxt.security import password_hash
from nxt.store import Store

PASSWORD = 'Replication_Account_Test_987!'
ORIGIN = 'http://127.0.0.1:45210'
PRIVATE_MON_FIELDS = {'moves', 'exp', 'nextExp', 'levelExp', 'stats', 'nature', 'originalTrainer', 'ivs'}


class Peer:
    def __init__(self, case, socket):
        self.case = case
        self.socket = socket
        self.received = []
        self.nonce = 0

    async def send(self, **packet):
        await self.socket.send_json(packet)

    async def until(self, kind, predicate=lambda packet: True):
        # Every wait has a deadline and a packet bound; no background tick race.
        kinds = {kind} if isinstance(kind, str) else set(kind)
        async with asyncio.timeout(6):
            for _ in range(80):
                packet = await self.socket.receive_json()
                self.received.append(packet)
                if packet.get('type') in kinds and predicate(packet):
                    return packet
                if packet.get('type') == 'error' and 'error' not in kinds:
                    self.case.fail(f'Unexpected server error while awaiting {kind}: {packet}')
        self.case.fail(f'Expected {kind} packet')

    async def barrier(self):
        """Drain ordered server output without timing-based absence assertions."""
        start = len(self.received)
        self.nonce += 1
        await self.send(op='ping', nonce=self.nonce)
        await self.until('pong', lambda packet: packet['nonce'] == self.nonce)
        return self.received[start:]


class ReplicationNetworkTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')
        cls.hashed = password_hash(PASSWORD)

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / 'config.ini'
        path.write_text((ROOT / 'Build/config_templates/Server/config.ini').read_text(encoding='utf-8'), encoding='utf-8')
        settings = Settings.load(path)
        settings.config.set('database', 'backend', 'sqlite')
        settings.config.set('security', 'auth_attempts_per_minute', '100')
        # These replication fixtures isolate ownership/transport with the
        # explicit administrator exploration controls; progression gates have
        # separate real-network coverage in test_adventure_network.py.
        settings.config.set('world', 'allow_alpha_atlas', 'true')
        settings.config.set('world', 'allow_alpha_surf', 'true')
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.service = Service(self.settings, self.content, self.db)
        self.service.dummy = self.hashed
        self.handler_tasks = []

        async def socket_handler(request):
            self.handler_tasks.append(asyncio.current_task())
            return await self.service.socket(request)

        app = web.Application()
        app.router.add_get('/health', self.service.health)
        app.router.add_get('/world', socket_handler)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.base = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        self.session = aiohttp.ClientSession()
        self.peers = []

    async def asyncTearDown(self):
        for peer in self.peers:
            await peer.socket.close()
        await self.session.close()
        await self.runner.cleanup()
        self.db.close()
        self.tmp.cleanup()

    async def open_peer(self):
        socket = await self.session.ws_connect(self.base + '/world', headers={'Origin': ORIGIN}, protocols=('nxt.v1',))
        peer = Peer(self, socket)
        self.peers.append(peer)
        await peer.until('hello')
        return peer

    async def auth(self, name, starter, *, mode='register', appearance=0, home='Johto'):
        peer = await self.open_peer()
        await peer.send(op='auth', mode=mode, username=name, password=PASSWORD, pack=self.content.pack,
                        home=home, starter=starter, appearance=appearance)
        joined = await peer.until('joined')
        state = await peer.until('state')
        return peer, joined, state

    async def raw_auth(self, packet):
        peer = await self.open_peer()
        await peer.send(**packet)
        result = await peer.until(('joined', 'error'))
        return peer, result

    def auth_packet(self, name, starter='fr_4', **changes):
        packet = {'op': 'auth', 'mode': 'register', 'username': name, 'password': PASSWORD,
                  'pack': self.content.pack, 'home': 'Johto', 'starter': starter, 'appearance': 0}
        packet.update(changes)
        return packet

    async def pair(self, *, reserves=False):
        mode = 'register'
        if reserves:
            # Additional owned creatures are offline fixture data; every tested
            # gameplay mutation still goes through production WebSocket dispatch.
            for name, starter, reserve, appearance in (
                ('Akumavenom', 'fr_152', 'fr_7', 7),
                ('Spidermight', 'fr_4', 'fr_1', 0),
            ):
                state = self.service.world.initial(name, 'Johto', starter, appearance)
                mon = self.content.new_mon(reserve, 5, name)
                state['creatures'].append(mon)
                state['party'].append(mon['uid'])
                self.db.create(name, self.hashed, state)
            mode = 'login'
        return await asyncio.gather(
            self.auth('Akumavenom', 'fr_152', mode=mode, appearance=7),
            self.auth('Spidermight', 'fr_4', mode=mode),
        )

    def assert_owner(self, packet, species, owner):
        self.assertEqual(packet['creatures'][0]['species'], species)
        self.assertEqual(packet['creatures'][0]['originalTrainer'], owner)
        self.assertEqual(packet['party'][0], packet['creatures'][0]['uid'])
        self.assertTrue({'moves', 'stats', 'exp', 'nature'} <= set(packet['creatures'][0]))

    def assert_public_entity(self, entity):
        self.assertFalse({'creatures', 'party', 'items', 'money', 'uid', 'hp'} & entity.keys())
        self.assertFalse(PRIVATE_MON_FIELDS & entity.keys())

    async def scenes(self, *peers):
        await self.service.world.tick()
        return await asyncio.gather(*(peer.until('scene') for peer in peers))

    async def close_account(self, peer, account_id):
        await peer.socket.close()
        async with asyncio.timeout(5):
            while account_id in self.service.world.players:
                await asyncio.sleep(.005)

    async def test_simultaneous_distinct_starters_are_separate_in_state_database_and_both_scenes(self):
        (a, aj, ast), (b, bj, bst) = await self.pair()
        self.assertNotEqual(aj['id'], bj['id'])
        self.assert_owner(ast, 'fr_152', 'Akumavenom')
        self.assert_owner(bst, 'fr_4', 'Spidermight')
        self.assertNotEqual(ast['party'][0], bst['party'][0])
        self.assertEqual(self.db.load(aj['id'])['creatures'][0]['species'], 'fr_152')
        self.assertEqual(self.db.load(bj['id'])['creatures'][0]['species'], 'fr_4')
        for scene in await self.scenes(a, b):
            entities = {entity['id']: entity for entity in scene['players']}
            self.assertEqual(set(entities), {aj['id'], bj['id']})
            self.assertEqual(entities[aj['id']]['follower'], 'fr_152')
            self.assertEqual(entities[bj['id']]['follower'], 'fr_4')
            self.assertEqual(entities[aj['id']]['appearance'], 7)
            self.assertEqual(entities[bj['id']]['appearance'], 0)
            for entity in entities.values():
                self.assert_public_entity(entity)

    async def test_every_starter_in_both_regions_survives_concurrent_creation_logout_and_login(self):
        cases = [(region + species.replace('_', ''), region, species)
                 for region in self.content.data['homes']
                 for species in self.content.data['starters']]
        self.assertEqual(len(cases), 12)
        created = await asyncio.gather(*(self.auth(name, species, home=region)
                                         for name, region, species in cases))
        self.assertEqual(len({joined['id'] for _, joined, _ in created}), len(cases))
        self.assertEqual(len({state['party'][0] for _, _, state in created}), len(cases))
        for (name, region, species), (peer, joined, state) in zip(cases, created):
            self.assert_owner(state, species, name)
            self.assertEqual(state['home'], region)
            saved = self.db.load(joined['id'])
            self.assertEqual(saved['map'], self.content.data['homes'][region])
            self.assertEqual(saved['party'], state['party'])
        scenes = await self.scenes(*(peer for peer, _, _ in created))
        for (_, region, _), scene in zip(cases, scenes):
            expected = {joined['id']: species for (_, other_region, species), (_, joined, _) in zip(cases, created)
                        if other_region == region}
            self.assertEqual({entity['id']: entity['follower'] for entity in scene['players']}, expected)
        await asyncio.gather(*(self.close_account(peer, joined['id']) for peer, joined, _ in created))
        # Login fields must never reset a saved character, even when they carry
        # the opposite region and an entirely different valid starter.
        restored = await asyncio.gather(*(
            self.auth(name, 'fr_4' if species != 'fr_4' else 'fr_152', mode='login',
                      home='Johto' if region == 'Kanto' else 'Kanto')
            for name, region, species in cases
        ))
        for (name, region, species), (_, original, before), (_, joined, after) in zip(cases, created, restored):
            self.assertEqual(joined['id'], original['id'])
            self.assert_owner(after, species, name)
            self.assertEqual(after['home'], region)
            self.assertEqual(after['party'], before['party'])
            self.assertEqual(after['creatures'], before['creatures'])
            self.assertEqual(self.db.load(joined['id'])['map'], self.content.data['homes'][region])

    async def test_missing_invalid_or_tampered_starter_is_rejected_without_creating_an_account(self):
        _, joined, _ = await self.auth('ExistingTrainer', 'fr_152')
        before = copy.deepcopy(self.db.load(joined['id']))
        invalid = [None, '', 'fr_9999', 'fr_4 ', 'Charmander', 4, True, [], {'species': 'fr_4'}]
        packets = [self.auth_packet(f'InvalidStarter{i}', value) for i, value in enumerate(invalid)]
        for field in ('starter', 'home'):
            packet = self.auth_packet('Missing' + field.title())
            del packet[field]
            packets.append(packet)
        for packet in packets:
            with self.subTest(selection=packet.get('starter', '<missing>'), home=packet.get('home', '<missing>')):
                peer, result = await self.raw_auth(packet)
                self.assertEqual(result['type'], 'error', 'Invalid registration must not silently choose a starter')
                self.assertTrue(result['login'])
                self.assertIsNone(self.db.account(packet['username']))
                await peer.socket.close()
                self.assertEqual(self.db.load(joined['id']), before)
        self.assertEqual(set(self.service.world.players), {joined['id']})

    async def test_duplicate_and_failed_registration_cannot_replace_any_existing_starter(self):
        peer, existing, state = await self.auth('ExistingTrainer', 'fr_152')
        before = copy.deepcopy(self.db.load(existing['id']))
        attempts = [
            self.auth_packet('ExistingTrainer', 'fr_4'),
            self.auth_packet('EXISTINGTRAINER', 'fr_7'),
            self.auth_packet('ExistingTrainer', 'fr_4', mode='login', password='Incorrect_Password_987!'),
            self.auth_packet('WrongPackTrainer', 'fr_7', pack='wrong-content-pack'),
            self.auth_packet('BadPasswordTrainer', 'fr_7', password='short'),
        ]
        outcomes = await asyncio.gather(*(self.raw_auth(packet) for packet in attempts))
        self.assertTrue(all(result['type'] == 'error' and result['login'] for _, result in outcomes))
        self.assertEqual(self.db.load(existing['id']), before)
        self.assertIsNone(self.db.account('WrongPackTrainer'))
        self.assertIsNone(self.db.account('BadPasswordTrainer'))
        # A second auth packet on an authenticated socket is an invalid game
        # command, not a way to overwrite that character's creation choice.
        await peer.send(**self.auth_packet('ExistingTrainer', 'fr_4'))
        await peer.until('error')
        self.assertEqual(self.db.load(existing['id']), before)
        # Two racing requests for the same account must produce one character
        # containing the winning request's explicit starter, never a mixture.
        candidate_species = ('fr_4', 'fr_158')
        contenders = await asyncio.gather(*(self.raw_auth(self.auth_packet('StarterRace', species))
                                             for species in candidate_species))
        winners = [(index, candidate, result) for index, (candidate, result) in enumerate(contenders)
                   if result['type'] == 'joined']
        self.assertEqual(len(winners), 1)
        self.assertEqual(sum(result['type'] == 'error' for _, result in contenders), 1)
        index, winner, result = winners[0]
        selected = await winner.until('state')
        self.assert_owner(selected, candidate_species[index], 'StarterRace')
        self.assertEqual(self.db.load(result['id'])['creatures'][0]['species'], candidate_species[index])
        self.assertNotEqual(selected['party'][0], state['party'][0])
        await self.close_account(winner, result['id'])
        _, again, preserved = await self.auth('StarterRace', candidate_species[1 - index], mode='login')
        self.assertEqual(again['id'], result['id'])
        self.assertEqual(preserved['creatures'], selected['creatures'])
        self.assertEqual(self.db.load(existing['id']), before)

    async def test_forged_creation_snapshots_cannot_override_selected_starter_or_owner(self):
        _, existing, state = await self.auth('ExistingTrainer', 'fr_152')
        before = copy.deepcopy(self.db.load(existing['id']))
        packet = self.auth_packet('ExplicitCharmander', 'fr_4', playerId=existing['id'],
                                  uid=state['party'][0], party=state['party'], creatures=state['creatures'],
                                  species='fr_152', state=before, money=999999)
        peer, joined = await self.raw_auth(packet)
        self.assertEqual(joined['type'], 'joined')
        created = await peer.until('state')
        self.assert_owner(created, 'fr_4', 'ExplicitCharmander')
        self.assertNotEqual(joined['id'], existing['id'])
        self.assertNotEqual(created['party'][0], state['party'][0])
        self.assertEqual(created['money'], self.settings.int('gameplay', 'starting_money'))
        self.assertEqual(self.db.load(existing['id']), before)

    async def test_party_lead_change_updates_both_followers_without_other_owner_state(self):
        (a, aj, ast), (b, bj, bst) = await self.pair(reserves=True)
        await self.scenes(a, b)
        await a.barrier()
        await b.barrier()
        b_start = len(b.received)
        before_b = copy.deepcopy(self.db.load(bj['id']))
        reordered = list(reversed(ast['party']))
        await a.send(op='party', party=reordered, playerId=bj['id'])
        state = await a.until('state')
        self.assertEqual(state['party'], reordered)
        for scene in await self.scenes(a, b):
            changed = {entity['id']: entity for entity in scene['players']}
            self.assertEqual(changed[aj['id']]['follower'], 'fr_7')
            self.assertNotIn(bj['id'], changed)
        await b.barrier()
        self.assertFalse(any(packet['type'] in ('state', 'audio') for packet in b.received[b_start:]))
        self.assertEqual(self.db.load(bj['id']), before_b)
        self.assertEqual(self.service.world.players[bj['id']].state['party'], bst['party'])
        await self.close_account(a, aj['id'])
        _, rejoined, restored = await self.auth('Akumavenom', 'fr_4', mode='login')
        self.assertEqual(rejoined['id'], aj['id'])
        self.assertEqual(restored['party'], reordered)

    async def test_movement_map_visibility_logout_and_relogin_preserve_distinct_owners(self):
        (a, aj, ast), (b, bj, bst) = await self.pair()
        await self.scenes(a, b)
        player = self.service.world.players[aj['id']]
        initial = (player.state['x'], player.state['y'])
        current_map = self.content.maps[player.state['map']]
        direction, expected = next(
            (direction, (initial[0] + dx, initial[1] + dy))
            for direction, dx, dy in (('right', 1, 0), ('left', -1, 0), ('down', 0, 1), ('up', 0, -1))
            if self.service.world.walkable(current_map, initial[0] + dx, initial[1] + dy)
            and not any((warp['x'], warp['y']) == (initial[0] + dx, initial[1] + dy) for warp in current_map['warps'])
        )
        await a.send(op='move', seq=1, direction=direction, playerId=bj['id'])
        movement = await a.until('move')
        self.assertTrue(movement['accepted'])
        for scene in await self.scenes(a, b):
            entity = next(entity for entity in scene['players'] if entity['id'] == aj['id'])
            self.assertEqual((entity['x'], entity['y']), expected)
            self.assertEqual((entity['fx'], entity['fy']), initial)
            self.assertEqual(entity['follower'], 'fr_152')
        destination = self.content.data['homes']['Kanto']
        await a.send(op='travel', map=destination)
        moved = await a.until('map')
        self.assertEqual(moved['id'], destination)
        first, second = await self.scenes(a, b)
        self.assertEqual({entity['id'] for entity in first['players']}, {aj['id']})
        self.assertIn(aj['id'], second['gone'])
        self.assertFalse(any(entity['id'] == aj['id'] for entity in second['players']))
        await self.close_account(a, aj['id'])
        await self.close_account(b, bj['id'])
        (a2, aj2, ast2), (b2, bj2, bst2) = await asyncio.gather(
            self.auth('Akumavenom', 'fr_4', mode='login'),
            self.auth('Spidermight', 'fr_152', mode='login'),
        )
        self.assertEqual((aj2['id'], bj2['id']), (aj['id'], bj['id']))
        self.assert_owner(ast2, 'fr_152', 'Akumavenom')
        self.assert_owner(bst2, 'fr_4', 'Spidermight')
        self.assertEqual(ast2['party'], ast['party'])
        self.assertEqual(bst2['party'], bst['party'])
        for peer, expected_map in ((a2, destination), (b2, self.content.data['homes']['Johto'])):
            packet = next(packet for packet in peer.received if packet['type'] == 'map')
            self.assertEqual(packet['id'], expected_map)
        for scene, own_id in zip(await self.scenes(a2, b2), (aj['id'], bj['id'])):
            self.assertEqual({entity['id'] for entity in scene['players']}, {own_id})

    async def test_cross_owner_party_and_item_uids_cannot_mutate_either_account(self):
        (a, aj, ast), (b, bj, bst) = await self.pair()
        snapshots = {joined['id']: copy.deepcopy(self.db.load(joined['id'])) for joined in (aj, bj)}
        for peer, own, other in ((a, aj, bst), (b, bj, ast)):
            for command in (
                {'op': 'party', 'party': other['party'], 'playerId': own['id']},
                {'op': 'use', 'item': 'potion', 'uid': other['party'][0]},
                {'op': 'party', 'party': [other['party'][0], other['party'][0]]},
            ):
                await peer.send(**command)
                await peer.until('error')
        for account_id, before in snapshots.items():
            self.assertEqual(self.db.load(account_id), before)
            self.assertEqual(self.service.world.players[account_id].state, before)
        await a.barrier()
        await b.barrier()
        await a.send(op='buy', item='potion', quantity=1, playerId=bj['id'], money=999999)
        state = await a.until('state')
        self.assertEqual(state['money'], ast['money'] - self.content.items['potion']['price'])
        self.assertEqual(state['items']['potion'], ast['items']['potion'] + 1)
        self.assertEqual(self.db.load(bj['id']), snapshots[bj['id']])
        self.assertFalse(any(packet['type'] == 'state' for packet in await b.barrier()))

    async def test_cancelled_socket_waits_for_real_purchase_commit_before_logout_save(self):
        a, joined, initial = await self.auth('Akumavenom', 'fr_152')
        await a.barrier()
        entered, release = threading.Event(), threading.Event()
        original_save = self.db.save_many
        blocked = False

        def delayed_save(records):
            nonlocal blocked
            if not blocked:
                blocked = True
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('Test did not release the real database worker')
            return original_save(records)

        # The only injected fault is a paused database worker. The actual TCP
        # handler, command validation, SQL write, publication and logout all run.
        with patch.object(self.db, 'save_many', side_effect=delayed_save):
            try:
                await a.send(op='buy', item='potion', quantity=1)
                self.assertTrue(await asyncio.wait_for(asyncio.to_thread(entered.wait, 3), 4))
                handler = self.handler_tasks[0]
                handler.cancel()
                await asyncio.sleep(0)
                handler.cancel()
                await asyncio.sleep(0)
                self.assertTrue(self.service.world.lock.locked())
                self.assertIn(joined['id'], self.service.world.players)
            finally:
                release.set()
            async with asyncio.timeout(5):
                while joined['id'] in self.service.world.players:
                    await asyncio.sleep(.005)
        saved = self.db.load(joined['id'])
        self.assertEqual(saved['money'], initial['money'] - self.content.items['potion']['price'])
        self.assertEqual(saved['items']['potion'], initial['items']['potion'] + 1)
        self.assertEqual(saved['party'], initial['party'])
        self.assertEqual(saved['revision'], initial['revision'] + 1)
        _, again, restored = await self.auth('Akumavenom', 'fr_4', mode='login')
        self.assertEqual(again['id'], joined['id'])
        self.assertEqual(restored['money'], saved['money'])
        self.assertEqual(restored['items'], saved['items'])
        self.assert_owner(restored, 'fr_152', 'Akumavenom')

    async def begin_interaction(self, a, b, target_id, kind):
        await a.send(op='invite', target=target_id, kind=kind)
        invitation = await b.until('invite')
        await b.send(op='invite.answer', id=invitation['id'], accept=True)
        pa, pb = await asyncio.gather(a.until('trade' if kind == 'trade' else 'battle'),
                                      b.until('trade' if kind == 'trade' else 'battle'))
        return pa, pb

    async def test_three_client_trade_is_private_and_transfers_unique_ownership_atomically(self):
        (a, aj, ast), (b, bj, bst) = await self.pair(reserves=True)
        c, cj, cst = await self.auth('ObserverTrainer', 'fr_155')
        await self.scenes(a, b, c)
        await c.barrier()
        c_start = len(c.received)
        pa, pb = await self.begin_interaction(a, b, bj['id'], 'trade')
        trade = pa['trade']
        tid = trade['id']
        scenes = await self.scenes(a, b, c)
        self.assertEqual({entity['id'] for entity in scenes[2]['players'] if entity['busy']}, {aj['id'], bj['id']})
        for entity in scenes[2]['players']:
            self.assert_public_entity(entity)
        await c.send(op='trade', id=tid, action='cancel', revision=0)
        await c.until('error')
        await a.send(op='trade', id=tid, action='offer', revision=0,
                     offer={'pokemon': [bst['party'][0]], 'items': {}, 'money': 0})
        await a.until('error')
        self.assertEqual(self.service.world.trades[tid]['revision'], 0)
        await a.send(op='trade', id=tid, action='offer', revision=0,
                     offer={'pokemon': [ast['party'][0]], 'items': {'potion': 1}, 'money': 100})
        await a.until('trade', lambda packet: packet['trade']['revision'] == 1)
        tb = (await b.until('trade', lambda packet: packet['trade']['revision'] == 1))['trade']
        public_offer = tb['offers'][str(aj['id'])]['pokemon'][0]
        self.assertFalse(PRIVATE_MON_FIELDS & public_offer.keys())
        self.assertEqual(public_offer['uid'], ast['party'][0])
        await b.send(op='trade', id=tid, action='offer', revision=1,
                     offer={'pokemon': [bst['party'][0]], 'items': {}, 'money': 25})
        ta = (await a.until('trade', lambda packet: packet['trade']['revision'] == 2))['trade']
        await b.until('trade', lambda packet: packet['trade']['revision'] == 2)
        for peer in (a, b):
            await peer.send(op='trade', id=tid, action='lock', revision=2)
            packets = await asyncio.gather(a.until('trade'), b.until('trade'))
            ta = packets[0]['trade']
        self.assertEqual(set(ta['ready']), {aj['id'], bj['id']})
        await a.send(op='trade', id=tid, action='confirm', revision=2, digest=ta['digest'])
        await asyncio.gather(a.until('trade'), b.until('trade'))
        await b.send(op='trade', id=tid, action='confirm', revision=2, digest=ta['digest'])
        final_a, final_b = await asyncio.gather(a.until('state'), b.until('state'))
        done = await asyncio.gather(a.until('trade_done'), b.until('trade_done'))
        self.assertTrue(all(packet['success'] for packet in done))
        ids_a = {mon['uid'] for mon in final_a['creatures']}
        ids_b = {mon['uid'] for mon in final_b['creatures']}
        self.assertFalse(ids_a & ids_b)
        self.assertEqual(ids_a | ids_b, {mon['uid'] for packet in (ast, bst) for mon in packet['creatures']})
        self.assertIn(bst['party'][0], ids_a)
        self.assertIn(ast['party'][0], ids_b)
        self.assertEqual(final_a['money'], ast['money'] - 75)
        self.assertEqual(final_b['money'], bst['money'] + 75)
        self.assertEqual(final_a['items']['potion'], ast['items']['potion'] - 1)
        self.assertEqual(final_b['items']['potion'], bst['items']['potion'] + 1)
        for joined, packet in ((aj, final_a), (bj, final_b)):
            saved = self.db.load(joined['id'])
            self.assertEqual(saved['party'], packet['party'])
            self.assertEqual({mon['uid'] for mon in saved['creatures']}, {mon['uid'] for mon in packet['creatures']})
        await c.barrier()
        observer = c.received[c_start:]
        self.assertFalse(any(packet['type'] in ('state', 'trade', 'trade_done', 'invite', 'audio') for packet in observer))
        self.assert_owner(cst, 'fr_155', 'ObserverTrainer')
        self.assertNotIn(tid, self.service.world.trades)

    async def test_three_client_duel_views_actions_and_disconnect_are_owner_scoped(self):
        (a, aj, ast), (b, bj, bst) = await self.pair(reserves=True)
        c, cj, cst = await self.auth('ObserverTrainer', 'fr_155')
        await self.scenes(a, b, c)
        await c.barrier()
        c_start = len(c.received)
        pa, pb = await self.begin_interaction(a, b, bj['id'], 'challenge')
        ba, bb = pa['battle'], pb['battle']
        self.assertEqual(ba['id'], bb['id'])
        self.assertEqual((ba['you']['species'], ba['opponent']['species']), ('fr_152', 'fr_4'))
        self.assertEqual((bb['you']['species'], bb['opponent']['species']), ('fr_4', 'fr_152'))
        for packet, owned in ((ba, ast), (bb, bst)):
            self.assertEqual({mon['uid'] for mon in packet['party']}, set(owned['party']))
            self.assertFalse(PRIVATE_MON_FIELDS & packet['opponent'].keys())
            self.assertTrue({'moves', 'stats', 'exp'} <= packet['you'].keys())
        await c.send(op='battle', id=ba['id'], action='run')
        await c.until('error')
        await a.send(op='battle', id=ba['id'], action='switch', uid=bst['party'][1])
        await a.until('error')
        self.assertFalse(self.service.world.battles[ba['id']].choice)
        await a.send(op='battle', id=ba['id'], action='switch', uid=ast['party'][1])
        waiting = (await a.until('battle'))['battle']
        self.assertTrue(waiting['waiting'])
        self.assertFalse(any(packet['type'] == 'battle' for packet in await b.barrier()))
        scenes = await self.scenes(a, b, c)
        observer_scene = scenes[2]
        self.assertEqual({entity['id'] for entity in observer_scene['players'] if entity['busy']}, {aj['id'], bj['id']})
        for entity in observer_scene['players']:
            self.assert_public_entity(entity)
        await c.barrier()
        self.assertFalse(any(packet['type'] in ('battle', 'invite', 'state', 'audio') for packet in c.received[c_start:]))
        before_a, before_b = copy.deepcopy(self.db.load(aj['id'])), copy.deepcopy(self.db.load(bj['id']))
        await self.close_account(b, bj['id'])
        ended = (await a.until('battle'))['battle']
        self.assertTrue(ended['ended'])
        self.assertEqual(ended['result'], 'won')
        self.assertNotIn(ba['id'], self.service.world.battles)
        self.assertIsNone(self.service.world.players[aj['id']].battle)
        self.assertEqual(self.db.load(aj['id']), before_a)
        self.assertEqual(self.db.load(bj['id']), before_b)
        after = await self.scenes(a, c)
        for scene in after:
            self.assertIn(bj['id'], scene['gone'])
            self.assertFalse(next(entity for entity in scene['players'] if entity['id'] == aj['id'])['busy'])


if __name__ == '__main__':
    unittest.main()
