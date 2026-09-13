"""Cancellation must keep database commit and live state publication together."""
from __future__ import annotations

import asyncio
import copy
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))

from nxt.async_tasks import complete_before_cancelling
from nxt.config import Settings
from nxt.content import Content
from nxt.security import RequestError
from nxt.store import Store
from nxt.world import World


class AsyncTransactionTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        config = Path(self.tmp.name) / 'config.ini'
        config.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
        self.settings = Settings.load(config)
        self.settings.config.set('database', 'backend', 'sqlite')
        self.db = Store(self.settings)
        self.db.acquire_lease()
        self.world = World(self.content, self.db, self.settings)
        self.player = await self.create_player('CancelAlice', 'fr_4')
        self.other = await self.create_player('CancelBobby', 'fr_152')
        self.before = copy.deepcopy(self.player.state)
        self.other_before = copy.deepcopy(self.other.state)

    async def asyncTearDown(self):
        self.db.close()
        self.tmp.cleanup()

    async def create_player(self, name, starter):
        state = self.world.initial(name, 'Johto', starter, 0)
        account = self.db.create(name, 'isolated-test-hash', state)
        return await self.world.join(account, name, state, asyncio.Queue(maxsize=1024))

    async def buy(self):
        return await complete_before_cancelling(self.world.dispatch(
            self.player, {'op': 'buy', 'item': 'pokeball', 'quantity': 1}))

    async def cancel_during_save(self, fail=False):
        started = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()
        original_save = self.db.save_many

        def blocked_save(records):
            loop.call_soon_threadsafe(started.set)
            if not release.wait(5):
                raise RuntimeError('Test did not release database worker')
            if fail:
                raise RuntimeError('Injected database transaction failure')
            original_save(records)

        with patch.object(self.db, 'save_many', side_effect=blocked_save):
            task = asyncio.create_task(self.buy())
            try:
                await asyncio.wait_for(started.wait(), 3)
                task.cancel()
                await asyncio.sleep(0)
                task.cancel()
                await asyncio.sleep(0)
                self.assertFalse(task.done())
                self.assertTrue(self.world.lock.locked())
            finally:
                release.set()
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(task, 3)

    def assert_other_unchanged(self):
        self.assertEqual(self.other.state, self.other_before)
        self.assertEqual(self.db.load(self.other.id), self.other_before)

    async def test_cancelled_commit_cannot_be_overwritten_by_logout(self):
        await self.cancel_during_save()
        self.assertFalse(self.world.lock.locked())
        self.assertEqual(self.player.state['money'], self.before['money'] - 200)
        self.assertEqual(self.player.state['items']['pokeball'], self.before['items']['pokeball'] + 1)
        self.assertEqual(self.db.load(self.player.id), self.player.state)
        saved = copy.deepcopy(self.player.state)
        uid = self.player.id
        await self.world.leave(self.player)
        self.assertEqual(self.db.load(uid), saved)
        rejoined = await self.world.join(uid, 'CancelAlice', self.db.load(uid), asyncio.Queue())
        self.assertEqual(rejoined.state, saved)
        self.assert_other_unchanged()

    async def test_cancelled_failed_commit_leaves_both_accounts_unchanged(self):
        with self.assertLogs('nxt.world', level='ERROR'):
            await self.cancel_during_save(fail=True)
        self.assertFalse(self.world.lock.locked())
        self.assertEqual(self.player.state, self.before)
        self.assertEqual(self.db.load(self.player.id), self.before)
        await self.world.leave(self.player)
        self.assertEqual(self.db.load(self.player.id), self.before)
        self.assert_other_unchanged()

    async def test_uncancelled_operation_still_reports_database_failure(self):
        with patch.object(self.db, 'save_many', side_effect=RuntimeError('injected failure')):
            with self.assertLogs('nxt.world', level='ERROR'):
                with self.assertRaises(RequestError):
                    await self.buy()
        self.assertEqual(self.player.state, self.before)
        self.assertEqual(self.db.load(self.player.id), self.before)
        self.assert_other_unchanged()


if __name__ == '__main__':
    unittest.main()
