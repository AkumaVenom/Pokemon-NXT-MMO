"""Real WebSocket login, cooldown and server restart persistence regressions.

SQLite fixtures use production password hashing and authentication. Synchronizing
two worker calls in the logout race makes the overlap repeatable; no fake login
success or fake persistence is used. This does not establish MySQL/Windows QA.
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

PASSWORD = '  Paßword_玩家_Test_987!  '
ORIGIN = 'http://127.0.0.1:45210'


class LoginLifecycleTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')
        cls.hashed = password_hash(PASSWORD)

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        config = Path(self.tmp.name) / 'config.ini'
        config.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
        settings = Settings.load(config)
        settings.config.set('database', 'backend', 'sqlite')
        settings.config.set('security', 'auth_attempts_per_minute', '100')
        self.settings = dataclasses.replace(settings, encounter_chance=0)
        self.session = aiohttp.ClientSession()
        await self.start_server()

    async def start_server(self):
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.service = Service(self.settings, self.content, self.db)
        self.service.dummy = self.hashed
        self.handlers = []
        self.clients = []

        async def tracked_socket(request):
            self.handlers.append(asyncio.current_task())
            return await self.service.socket(request)

        app = web.Application()
        app.router.add_get('/world', tracked_socket)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.address = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/world'

    async def stop_server(self):
        for socket, handler in self.clients:
            await socket.close()
        for handler in self.handlers:
            await asyncio.wait_for(asyncio.shield(handler), 6)
        await self.runner.cleanup()
        self.db.close()

    async def asyncTearDown(self):
        await self.stop_server()
        await self.session.close()
        self.tmp.cleanup()

    async def until(self, socket, kind):
        async with asyncio.timeout(6):
            for _ in range(40):
                packet = await socket.receive_json()
                if packet['type'] == kind:
                    return packet
                if packet['type'] == 'error' and kind != 'error':
                    self.fail(f'Unexpected authentication error: {packet}')
        self.fail(f'No {kind} packet received')

    async def connect(self):
        socket = await self.session.ws_connect(self.address, headers={'Origin': ORIGIN}, protocols=('nxt.v1',))
        self.clients.append((socket, self.handlers[-1]))
        await self.until(socket, 'hello')
        return socket

    async def close(self, socket):
        handler = next(handler for client, handler in self.clients if client is socket)
        await socket.close()
        await asyncio.wait_for(asyncio.shield(handler), 6)

    async def authenticate(self, name='LifecycleAlice', *, password=PASSWORD, mode='login'):
        socket = await self.connect()
        packet = {'op': 'auth', 'mode': mode, 'username': name, 'password': password, 'pack': self.content.pack}
        if mode == 'register':
            packet.update(home='Kanto', starter='fr_4', appearance=0)
        await socket.send_json(packet)
        return socket

    async def register(self, name='LifecycleAlice'):
        socket = await self.authenticate(name, mode='register')
        joined = await self.until(socket, 'joined')
        state = await self.until(socket, 'state')
        return socket, joined, state

    async def test_created_account_progress_and_password_survive_server_restart(self):
        socket, joined, state = await self.register()
        uid = joined['id']
        self.assertEqual(state['creatures'][0]['species'], 'fr_4')
        # Place this persistence fixture at a legitimate merchant; the normal
        # fresh-server proximity rule still applies to the real WebSocket buy.
        world = self.service.world
        market, x, y = next((m['id'], x, y) for m in self.content.maps.values()
                            for npc in m['objects'] if npc['graphics'] == 68
                            for x, y in [(npc['x'], npc['y'] + 1), (npc['x'] + 1, npc['y'])]
                            if m.get('playable', True) and world.walkable(m, x, y))
        await world.relocate_saved(world.players[uid], market, x, y)
        await self.until(socket, 'map')
        await socket.send_json({'op': 'buy', 'item': 'pokeball', 'quantity': 2})
        purchased = await self.until(socket, 'state')
        self.assertEqual(purchased['money'], state['money'] - 400)
        self.assertEqual(purchased['items']['pokeball'], state['items']['pokeball'] + 2)
        saved = copy.deepcopy(self.db.load(uid))
        stored_hash = self.db.account('lifecyclealice')['password_hash']
        self.assertNotEqual(stored_hash, PASSWORD)
        self.assertTrue(stored_hash.startswith('scrypt$'))
        await self.stop_server()
        await self.start_server()
        socket = await self.authenticate('lIfEcYcLeAlIcE')
        rejoined = await self.until(socket, 'joined')
        restored = await self.until(socket, 'state')
        self.assertEqual((rejoined['id'], rejoined['username']), (uid, 'LifecycleAlice'))
        self.assertEqual(restored['creatures'], purchased['creatures'])
        self.assertEqual(restored['money'], purchased['money'])
        self.assertEqual(restored['items'], purchased['items'])
        self.assertEqual(self.db.load(uid), saved)
        self.assertEqual(self.db.account('LifecycleAlice')['password_hash'], stored_hash)

    async def test_idle_hellos_and_reconnects_do_not_consume_login_attempts(self):
        self.settings.config.set('security', 'auth_attempts_per_minute', '1')
        for _ in range(8):
            socket = await self.connect()
            await self.close(socket)
        bucket, = self.service.auth_rates.values()
        self.assertEqual(bucket.tokens, 1)
        _, _, state = await self.register()
        self.assertEqual(state['creatures'][0]['species'], 'fr_4')
        self.assertEqual(bucket.tokens, 0)

    async def test_actual_authentication_attempts_return_explicit_cooldown(self):
        self.settings.config.set('security', 'auth_attempts_per_minute', '1')
        first = await self.authenticate('MissingAccount')
        first_error = await self.until(first, 'error')
        self.assertEqual(first_error['message'], 'Username or password is incorrect.')
        await self.close(first)
        second = await self.authenticate('DifferentAccount')
        cooldown = await self.until(second, 'error')
        self.assertTrue(cooldown['login'])
        self.assertIn('Too many login attempts from this network.', cooldown['message'])
        self.assertIn('seconds', cooldown['message'])
        self.assertIsNone(self.db.account('DifferentAccount'))
        self.assertFalse(self.service.world.players)

    async def test_wrong_password_empty_hash_and_malformed_hash_never_authenticate(self):
        socket, joined, _ = await self.register()
        await self.close(socket)
        wrong = await self.authenticate(password=PASSWORD.strip())
        self.assertEqual((await self.until(wrong, 'error'))['message'], 'Username or password is incorrect.')
        await self.close(wrong)
        for invalid_hash in ('', 'not-a-password-hash', 'scrypt$131072$8$1$bad$bad'):
            with self.db.transaction() as cursor:
                cursor.execute('UPDATE accounts SET password_hash=? WHERE id=?', (invalid_hash, joined['id']))
            attempt = await self.authenticate()
            error = await self.until(attempt, 'error')
            self.assertTrue(error['login'])
            self.assertEqual(error['message'], 'Username or password is incorrect.')
            await self.close(attempt)
            self.assertFalse(self.service.world.players)

    async def test_duplicate_live_login_is_rejected_before_loading_saved_character(self):
        _, joined, _ = await self.register()
        sql = []
        self.db.db.set_trace_callback(sql.append)
        duplicate = await self.authenticate('lifecyclealice')
        error = await self.until(duplicate, 'error')
        self.assertIn('already online', error['message'])
        self.assertEqual(list(self.service.world.players), [joined['id']])
        self.assertFalse(any('SELECT state_json FROM characters' in statement for statement in sql))

    async def test_relogin_waits_for_old_logout_save_before_reading_character(self):
        socket, joined, _ = await self.register()
        uid = joined['id']
        await socket.send_json({'op': 'move', 'seq': 1, 'direction': 'right'})
        moved = await self.until(socket, 'move')
        self.assertTrue(moved['accepted'])
        position = (moved['entity']['x'], moved['entity']['y'])
        self.assertNotEqual((self.db.load(uid)['x'], self.db.load(uid)['y']), position)
        saving = asyncio.Event()
        verified = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()
        old_save = self.db.save_many
        old_hash = self.service.hash
        old_load = self.db.load
        loaded_during_old_session = []

        def blocked_logout_save(records):
            loop.call_soon_threadsafe(saving.set)
            if not release.wait(5):
                raise RuntimeError('Test did not release logout save')
            old_save(records)

        async def tracked_hash(password, encoded=None):
            result = await old_hash(password, encoded)
            if encoded is not None:
                verified.set()
            return result

        def tracked_load(account_id):
            loaded_during_old_session.append(account_id in self.service.world.players)
            return old_load(account_id)

        with patch.object(self.db, 'save_many', side_effect=blocked_logout_save), \
             patch.object(self.service, 'hash', side_effect=tracked_hash), \
             patch.object(self.db, 'load', side_effect=tracked_load):
            closing = asyncio.create_task(self.close(socket))
            try:
                await asyncio.wait_for(saving.wait(), 3)
                relogin = await self.authenticate()
                await asyncio.wait_for(verified.wait(), 3)
                # Give the old unprotected load path time to read the previous
                # row while logout deliberately holds the world lock. The fixed
                # path remains queued at admission until save completion.
                await asyncio.sleep(.15)
            finally:
                release.set()
            await closing
            await self.until(relogin, 'joined')
            returned = await self.until(relogin, 'map')
            await self.until(relogin, 'state')
        self.assertEqual(loaded_during_old_session, [False])
        self.assertEqual((returned['entity']['x'], returned['entity']['y']), position)
        self.assertIn(uid, self.service.sockets)
        await self.close(relogin)
        self.assertEqual((self.db.load(uid)['x'], self.db.load(uid)['y']), position)


if __name__ == '__main__':
    unittest.main()
