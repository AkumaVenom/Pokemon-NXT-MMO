"""Real SQLite ownership regressions; these do not claim native MySQL coverage."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
from nxt.config import Settings
from nxt.store import Store, WorldLeaseBusy


class WorldLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='NXT lease test ')
        self.root = Path(self.temp.name)
        config = self.root / 'config.ini'
        config.write_bytes((ROOT / 'Server/config.ini').read_bytes())
        self.settings = Settings.load(config)
        self.settings.config.set('database', 'backend', 'sqlite')
        self.stores = []

    def tearDown(self):
        for store in self.stores:
            store.close()
        self.temp.cleanup()

    def store(self):
        store = Store(self.settings)
        self.stores.append(store)
        return store

    def row(self, store):
        with store.transaction() as cursor:
            cursor.execute('SELECT owner,heartbeat FROM world_leases WHERE id=1')
            return cursor.fetchone()

    def test_recent_lease_rejects_contender_and_close_preserves_live_owner(self):
        owner, contender = self.store(), self.store()
        with patch('nxt.store.time.time', return_value=1000):
            owner.acquire_lease()
            with self.assertRaises(WorldLeaseBusy) as raised:
                contender.acquire_lease()
        self.assertEqual(raised.exception.remaining_seconds, 60)
        contender.close()
        self.assertEqual(self.row(owner), (owner.lease_id, 1000))
        with patch('nxt.store.time.time', return_value=1010):
            owner.heartbeat()
        self.assertEqual(self.row(owner), (owner.lease_id, 1010))

    def test_exact_expiry_boundary_and_previous_owner_cannot_write_or_release_successor(self):
        owner, successor = self.store(), self.store()
        with patch('nxt.store.time.time', return_value=1000):
            owner.acquire_lease()
        with patch('nxt.store.time.time', return_value=1059):
            with self.assertRaises(WorldLeaseBusy) as raised:
                successor.acquire_lease()
            self.assertEqual(raised.exception.remaining_seconds, 1)
        with patch('nxt.store.time.time', return_value=1060):
            successor.acquire_lease()
            with self.assertRaisesRegex(RuntimeError, 'lease lost'):
                owner.heartbeat()
            with self.assertRaisesRegex(RuntimeError, 'fencing'):
                owner.create('OldOwner', 'test-hash', {'revision': 1})
        owner.close()
        self.assertEqual(self.row(successor), (successor.lease_id, 1060))

    def test_clean_shutdown_allows_immediate_restart_without_timeout(self):
        owner, successor = self.store(), self.store()
        with patch('nxt.store.time.time', return_value=1000):
            owner.acquire_lease()
            owner.close()
            owner.close()
            successor.acquire_lease()
        self.assertEqual(self.row(successor), (successor.lease_id, 1000))

    def test_future_clock_timestamp_is_not_forcibly_taken_over(self):
        owner, contender = self.store(), self.store()
        with patch('nxt.store.time.time', return_value=1100):
            owner.acquire_lease()
        with patch('nxt.store.time.time', return_value=1000):
            with self.assertRaises(WorldLeaseBusy) as raised:
                contender.acquire_lease()
        self.assertEqual(raised.exception.remaining_seconds, 160)
        self.assertEqual(raised.exception.heartbeat, 1100)
        self.assertEqual(raised.exception.observed_at, 1000)
        self.assertEqual(self.row(owner), (owner.lease_id, 1100))

    def test_closed_store_cannot_reconnect_and_write_without_ownership(self):
        owner = self.store()
        owner.acquire_lease()
        owner.close()
        with self.assertRaisesRegex(RuntimeError, 'connection is closed'):
            owner.create('ClosedOwner', 'test-hash', {'revision': 1})
        with self.assertRaisesRegex(RuntimeError, 'connection is closed'):
            owner.acquire_lease()

    def test_constructor_failure_closes_database_connection(self):
        connection = unittest.mock.Mock()
        def connect(store):
            store.db = connection
        with patch.object(Store, 'connect', connect), patch.object(Store, 'migrate', side_effect=RuntimeError('migration failed')):
            with self.assertRaisesRegex(RuntimeError, 'migration failed'):
                Store(self.settings)
        connection.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
