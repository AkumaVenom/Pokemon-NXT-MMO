"""Patch installer contracts: scripts-only updates, backups, rollback and hashes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Tools'))
import apply_mysql_setup_fix as fixer


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='NXT patch (space) ')
        self.root = Path(self.temp.name)
        self.server = self.root / 'Project' / 'Server'
        (self.server / 'nxt').mkdir(parents=True)
        (self.server / 'server.py').write_text('"Pokemon NXT MMO"\n')
        (self.server / 'nxt/store.py').write_text('# preserved world store')
        (self.server / 'setup_mysql.py').write_text('# old setup')
        (self.server / '2 - Configure MySQL.cmd').write_bytes(b'@echo off\r\nrem old\r\n')
        (self.server / 'config.ini').write_text('[database]\npassword=PRIVATE_UNTOUCHED!')
        (self.server / 'data').mkdir()
        (self.server / 'data/save.sqlite3').write_bytes(b'PRESERVED_SAVE')
        self.payload = self.root / 'Payload'
        self.payload.mkdir()
        self.manifest = {}
        for name in fixer.FILES:
            data = (ROOT / 'Server' / name).read_bytes()
            (self.payload / name).write_bytes(data)
            self.manifest[name] = hashlib.sha256(data).hexdigest()
        self.write_manifest()
    def write_manifest(self):
        (self.payload / 'SHA256.json').write_text(json.dumps(self.manifest))
    def tearDown(self):
        self.temp.cleanup()
    def test_patch_preserves_secrets_saves_and_store_with_script_backups(self):
        before = {name: (self.server / name).read_bytes() for name in ('config.ini','nxt/store.py','data/save.sqlite3')}
        server, backup = fixer.apply_patch(self.server.parent, self.payload)
        self.assertEqual(server, self.server)
        self.assertIsNotNone(backup)
        for name, data in before.items():
            self.assertEqual((server / name).read_bytes(), data)
        self.assertEqual((backup / 'setup_mysql.py').read_text(), '# old setup')
        self.assertFalse((backup / 'config.ini').exists())
        for name in fixer.FILES:
            self.assertEqual((server / name).read_bytes(), (self.payload / name).read_bytes())
    def test_reapplication_is_idempotent(self):
        fixer.apply_patch(self.server, self.payload)
        _, backup = fixer.apply_patch(self.server, self.payload)
        self.assertIsNone(backup)
        self.assertEqual(len(list((self.server / 'backups').iterdir())), 1)
    def test_hash_failure_changes_nothing(self):
        (self.payload / 'setup_mysql.py').write_text('altered')
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
        self.assertEqual((self.server / 'setup_mysql.py').read_text(), '# old setup')
        self.assertFalse((self.server / 'backups').exists())
    def test_manifest_cannot_add_a_config_or_traversal_path(self):
        for name in ('config.ini', '../config.ini'):
            self.manifest[name] = 'anything'
            self.write_manifest()
            with self.assertRaises(fixer.PatchError):
                fixer.apply_patch(self.server, self.payload)
            self.manifest.pop(name)
        self.assertFalse((self.server / 'backups').exists())
    def test_unrelated_folder_is_rejected(self):
        (self.server / 'server.py').write_text('Unrelated project')
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
    def test_partial_write_failure_restores_all_changed_files(self):
        original = fixer.atomic_write
        calls = 0
        def failing(path, data):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('simulated third-file failure')
            return original(path, data)
        with patch.object(fixer, 'atomic_write', side_effect=failing):
            with self.assertRaises(fixer.PatchError):
                fixer.apply_patch(self.server, self.payload)
        self.assertEqual((self.server / 'setup_mysql.py').read_text(), '# old setup')
        self.assertFalse((self.server / 'setup_mysql_gui.py').exists())
        self.assertFalse((self.server / 'setup_password_input.py').exists())
        self.assertIn('PRIVATE_UNTOUCHED!', (self.server / 'config.ini').read_text())
    def test_payload_symlink_is_rejected(self):
        target = self.payload / 'setup_mysql.py'
        target.unlink()
        try:
            target.symlink_to(ROOT / 'Server/setup_mysql.py')
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)


if __name__ == '__main__':
    unittest.main()
