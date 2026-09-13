"""Authoritative move reminders over real TCP with isolated SQLite accounts.

Trained creatures are fixture data. Authentication, reminder commands, packets,
commit failures and logout/relogin all use the production server paths.
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

import aiohttp
from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
sys.path.insert(0, str(ROOT / 'Tests'))
from test_replication_network import Peer, PASSWORD, ORIGIN
from nxt.config import Settings
from nxt.content import Content
from nxt.growth import Growth
from nxt.store import Store
from server import Service


class LearnsetNetworkTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_content = Content(ROOT / 'Server/data/world.json')

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        config = Path(self.tmp.name) / 'config.ini'
        config.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
        settings = Settings.load(config)
        settings.config.set('database', 'backend', 'sqlite')
        settings.config.set('security', 'auth_attempts_per_minute', '100')
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.content = copy.copy(self.base_content)
        self.content.rng = random.Random(311)
        self.content.growth = Growth(self.content)
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.service = Service(self.settings, self.content, self.db)
        self.world = self.service.world
        app = web.Application()
        app.router.add_get('/world', self.service.socket)
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

    async def auth(self, name, starter='fr_4', mode='register'):
        socket = await self.session.ws_connect(
            self.base + '/world', headers={'Origin': ORIGIN}, protocols=('nxt.v1',))
        peer = Peer(self, socket)
        self.peers.append(peer)
        await peer.until('hello')
        await peer.send(op='auth', mode=mode, username=name, password=PASSWORD,
                        pack=self.content.pack, home='Johto', starter=starter, appearance=0)
        joined = await peer.until('joined')
        state = await peer.until('state')
        return peer, joined['id'], state

    async def pair(self):
        return await asyncio.gather(self.auth('ReminderOwner'), self.auth('ReminderPeer', 'fr_7'))

    async def stage_reminder(self, peer, account):
        """Create a current-species earned move that has been forgotten."""
        species, level = 'fr_4', 30
        rows = self.content.species[species]['learnset']
        earned = list(dict.fromkeys(move for required, move in rows if required <= level))
        self.assertGreaterEqual(len(earned), 5)
        target = earned[0]
        future = next(move for required, move in rows if required > level and move not in earned)
        foreign = next(int(move) for move in self.content.moves
                       if int(move) not in {mid for _, mid in rows} and int(move) > 0)
        async with self.world.lock:
            player = self.world.players[account]
            candidate = copy.deepcopy(player.state)
            mon = self.content.new_mon(species, level, player.username)
            mon['uid'] = candidate['party'][0]
            mon['moves'] = [{'id': move, 'pp': 1} for move in earned[1:5]]
            mon['pendingLearn'] = []
            candidate['creatures'][0] = mon
            await self.world.commit(player, candidate)
        state = await peer.until('state')
        await peer.barrier()
        return mon['uid'], target, future, foreign, state

    async def rejected(self, peer, account, other, **packet):
        await peer.barrier()
        before, peer_before = self.db.load(account), self.db.load(other)
        index = len(peer.received)
        await peer.send(**packet)
        error = await peer.until('error')
        await peer.barrier()
        messages = peer.received[index:]
        self.assertFalse([p for p in messages if p['type'] in ('state', 'notice', 'audio')])
        self.assertEqual(self.db.load(account), before)
        self.assertEqual(self.world.players[account].state, before)
        self.assertEqual(self.db.load(other), peer_before)
        return error

    async def close_account(self, peer, account):
        await peer.socket.close()
        async with asyncio.timeout(5):
            while account in self.world.players:
                await asyncio.sleep(.005)

    async def test_reminder_rejects_foreign_future_duplicate_and_invalid_slot_without_mutation(self):
        (a, aid, _), (b, bid, bst) = await self.pair()
        uid, target, future, foreign, state = await self.stage_reminder(a, aid)
        mon = state['creatures'][0]
        self.assertIn(target, [entry['move'] for entry in mon['relearnMoves']])
        self.assertNotIn(future, [entry['move'] for entry in mon['relearnMoves']])
        self.assertTrue(all(entry['level'] <= mon['level'] for entry in mon['relearnMoves']))
        other_uid = bst['party'][0]
        for changes in (
            {'uid': other_uid}, {'move': future}, {'move': foreign, 'species': 'fr_7'},
            {'move': mon['moves'][0]['id']}, {'slot': 4}, {'slot': -1},
            {'slot': True}, {'move': True}, {'move': str(target)},
        ):
            await self.rejected(a, aid, bid, **{'op': 'pokemon.remember', 'uid': uid,
                                               'move': target, 'slot': 0, **changes})
        await self.rejected(b, bid, aid, op='pokemon.remember', uid=uid, move=target, slot=0)

    async def test_reminder_saves_full_pp_owner_only_and_survives_logout_relogin(self):
        (a, aid, _), (b, bid, _) = await self.pair()
        uid, target, _, _, state = await self.stage_reminder(a, aid)
        other = self.db.load(bid)
        before = self.db.load(aid)
        await b.barrier()
        # No NPC interaction or service proximity is required by this operation.
        await a.send(op='pokemon.remember', uid=uid, move=target, slot=0)
        saved = await a.until('state')
        await a.until('notice')
        audio = await a.until('audio')
        self.assertEqual([event['cue'] for event in audio['events']], ['party_changed'])
        moves = saved['creatures'][0]['moves']
        self.assertEqual(moves[0], {'id': target, 'pp': self.content.moves[str(target)]['pp']})
        self.assertEqual(moves[1:], state['creatures'][0]['moves'][1:])
        self.assertEqual(saved['revision'], before['revision'] + 1)
        self.assertNotIn(target, [entry['move'] for entry in saved['creatures'][0]['relearnMoves']])
        self.assertEqual(self.db.load(aid)['creatures'][0]['moves'], moves)
        self.assertEqual(self.db.load(bid), other)
        packets = await b.barrier()
        self.assertFalse([p for p in packets if p['type'] in ('state', 'notice', 'audio')])
        await self.rejected(a, aid, bid, op='pokemon.remember', uid=uid, move=target, slot=1)
        committed = self.db.load(aid)
        await self.close_account(a, aid)
        a, rejoined, reloaded = await self.auth('ReminderOwner', mode='login')
        self.assertEqual(rejoined, aid)
        self.assertEqual(reloaded['creatures'][0]['moves'], moves)
        self.assertEqual(self.db.load(aid)['creatures'], committed['creatures'])
        self.assertEqual(self.db.load(bid), other)

    async def test_failed_reminder_save_publishes_no_success_and_retry_commits(self):
        (a, aid, _), (b, bid, _) = await self.pair()
        uid, target, _, _, _ = await self.stage_reminder(a, aid)
        with patch.object(self.db, 'save_many', side_effect=RuntimeError('injected reminder storage outage')):
            with self.assertLogs('nxt.world', level='ERROR'):
                error = await self.rejected(a, aid, bid, op='pokemon.remember', uid=uid,
                                            move=target, slot=0)
        self.assertIn('database', error['message'].lower())
        await a.send(op='pokemon.remember', uid=uid, move=target, slot=0)
        saved = await a.until('state')
        await a.until('notice')
        audio = await a.until('audio')
        self.assertEqual(saved['creatures'][0]['moves'][0]['id'], target)
        self.assertEqual([event['cue'] for event in audio['events']], ['party_changed'])
        self.assertEqual(self.db.load(aid)['creatures'][0]['moves'], saved['creatures'][0]['moves'])


if __name__ == '__main__':
    unittest.main()
