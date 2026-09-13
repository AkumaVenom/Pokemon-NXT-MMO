"""World-startup hotfix: narrow updates, integrity, rollback and link safety."""
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
import apply_world_startup_fix as fixer


class WorldStartupPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='NXT startup (space) ! ')
        self.root = Path(self.temp.name)
        self.server = self.root / 'Project' / 'Server'
        self.original = {
            'server.py': b'"Pokemon NXT MMO"\n# old world service\n',
            'nxt/store.py': b'# old world store\n',
            '3 - Start World Server.cmd': b'@echo off\r\nrem old launcher\r\n',
        }
        self.preserved = {
            'config.ini': b'[database]\npassword=PRIVATE_UNTOUCHED!',
            'data/save.sqlite3': b'PRESERVED_SAVE',
            '.venv/Scripts/python.exe': b'PRESERVED_PYTHON',
            'setup_mysql.py': b'PRESERVED_SETUP',
            'Pokemon NXT World Server.exe': b'PRESERVED_EXE',
            'assets/map.png': b'PRESERVED_ASSET',
        }
        for name, data in {**self.original, **self.preserved}.items():
            path = self.server / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.payload = self.root / 'Payload'
        self.manifest = {}
        for name in fixer.FILES:
            data = (ROOT / 'Server' / name).read_bytes()
            path = self.payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.manifest[name] = hashlib.sha256(data).hexdigest()
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self):
        (self.payload / 'SHA256.json').write_text(json.dumps(self.manifest), encoding='utf-8')

    def symlink(self, link, target, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable')

    def assert_original(self):
        for name, data in self.original.items():
            self.assertEqual((self.server / name).read_bytes(), data, name)

    def assert_preserved(self):
        for name, data in self.preserved.items():
            self.assertEqual((self.server / name).read_bytes(), data, name)

    def test_patch_updates_only_three_scripts_with_nested_backups(self):
        server, backup = fixer.apply_patch(self.server.parent, self.payload)
        self.assertEqual(server, self.server)
        for name, data in self.original.items():
            self.assertEqual((backup / name).read_bytes(), data)
            self.assertEqual((server / name).read_bytes(), (self.payload / name).read_bytes())
        self.assertEqual({str(path.relative_to(backup)).replace('\\', '/') for path in backup.rglob('*') if path.is_file()},
                         set(fixer.FILES) | {'PATCH_INFO.json'})
        self.assert_preserved()

    def test_reapplication_is_idempotent(self):
        fixer.apply_patch(self.server, self.payload)
        _, backup = fixer.apply_patch(self.server, self.payload)
        self.assertIsNone(backup)
        self.assertEqual(len(list((self.server / 'backups').iterdir())), 1)
        self.assert_preserved()

    def test_hash_failure_changes_nothing(self):
        (self.payload / 'nxt/store.py').write_text('altered payload')
        with self.assertRaisesRegex(fixer.PatchError, 'integrity'):
            fixer.apply_patch(self.server, self.payload)
        self.assert_original()
        self.assertFalse((self.server / 'backups').exists())

    def test_manifest_rejects_unexpected_config_and_traversal_entries(self):
        for name in ('config.ini', '../config.ini', 'nxt/../../config.ini'):
            self.manifest[name] = 'anything'
            self.write_manifest()
            with self.assertRaises(fixer.PatchError):
                fixer.apply_patch(self.server, self.payload)
            del self.manifest[name]
        self.assert_original()
        self.assert_preserved()
        self.assertFalse((self.server / 'backups').exists())

    def test_non_object_manifest_is_rejected(self):
        (self.payload / 'SHA256.json').write_text('null')
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
        self.assert_original()

    def test_unrelated_folder_is_rejected(self):
        (self.server / 'server.py').write_text('Unrelated project')
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
        self.assertFalse((self.server / 'backups').exists())

    def test_third_file_failure_restores_nested_and_top_level_scripts(self):
        write = fixer.atomic_write
        calls = 0
        def failing(path, data):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError('simulated third-file failure')
            return write(path, data)
        with patch.object(fixer, 'atomic_write', side_effect=failing):
            with self.assertRaisesRegex(fixer.PatchError, 'restored'):
                fixer.apply_patch(self.server, self.payload)
        self.assert_original()
        self.assert_preserved()

    def test_missing_launcher_can_be_installed_and_is_recorded(self):
        (self.server / fixer.FILES[-1]).unlink()
        _, backup = fixer.apply_patch(self.server, self.payload)
        info = json.loads((backup / 'PATCH_INFO.json').read_text())
        self.assertEqual(info['new_files'], [fixer.FILES[-1]])
        self.assertEqual((self.server / fixer.FILES[-1]).read_bytes(), (self.payload / fixer.FILES[-1]).read_bytes())

    def test_concurrent_edit_stops_patch_and_preserves_external_change(self):
        write = fixer.atomic_write
        def changing(path, data):
            write(path, data)
            if path.name == 'server.py' and data != self.original['server.py']:
                (self.server / 'nxt/store.py').write_bytes(b'EXTERNAL EDIT')
        with patch.object(fixer, 'atomic_write', side_effect=changing):
            with self.assertRaisesRegex(fixer.PatchError, 'changed'):
                fixer.apply_patch(self.server, self.payload)
        self.assertEqual((self.server / 'server.py').read_bytes(), self.original['server.py'])
        self.assertEqual((self.server / 'nxt/store.py').read_bytes(), b'EXTERNAL EDIT')
        self.assert_preserved()

    def test_target_nested_directory_symlink_is_rejected(self):
        outside = self.root / 'outside_nxt'
        (self.server / 'nxt').rename(outside)
        self.symlink(self.server / 'nxt', outside, directory=True)
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
        self.assertEqual((outside / 'store.py').read_bytes(), self.original['nxt/store.py'])
        self.assertFalse((self.server / 'backups').exists())

    def test_target_file_symlink_is_rejected(self):
        outside = self.root / 'outside_store.py'
        (self.server / 'nxt/store.py').rename(outside)
        self.symlink(self.server / 'nxt/store.py', outside)
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
        self.assertEqual(outside.read_bytes(), self.original['nxt/store.py'])
        self.assertFalse((self.server / 'backups').exists())

    def test_selected_directory_replaced_during_validation_is_rejected(self):
        validate = fixer.validated_payload
        old_server = self.root / 'OriginalServer'
        def replacing(payload):
            content = validate(payload)
            self.server.rename(old_server)
            (self.server / 'nxt').mkdir(parents=True)
            for name, data in self.original.items():
                (self.server / name).write_bytes(data)
            return content
        with patch.object(fixer, 'validated_payload', side_effect=replacing):
            with self.assertRaisesRegex(fixer.PatchError, 'folder changed'):
                fixer.apply_patch(self.server, self.payload)
        self.assert_original()
        for name, data in self.original.items():
            self.assertEqual((old_server / name).read_bytes(), data)
        self.assertFalse((self.server / 'backups').exists())

    def test_selected_folder_symlink_is_rejected_before_resolution(self):
        linked = self.root / 'LinkedServer'
        self.symlink(linked, self.server, directory=True)
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(linked, self.payload)
        self.assert_original()

    def test_backup_directory_symlink_is_rejected(self):
        outside = self.root / 'outside_backups'
        outside.mkdir()
        self.symlink(self.server / 'backups', outside, directory=True)
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
        self.assertEqual(list(outside.iterdir()), [])
        self.assert_original()

    def test_payload_nested_directory_symlink_is_rejected(self):
        outside = self.root / 'outside_payload'
        (self.payload / 'nxt').rename(outside)
        self.symlink(self.payload / 'nxt', outside, directory=True)
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
        self.assert_original()

    def test_payload_file_symlink_is_rejected(self):
        target = self.payload / 'server.py'
        target.unlink()
        self.symlink(target, ROOT / 'Server/server.py')
        with self.assertRaises(fixer.PatchError):
            fixer.apply_patch(self.server, self.payload)
        self.assert_original()

    def test_nested_directory_swapped_during_patch_never_writes_outside(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'store.py').write_bytes(b'OUTSIDE FILE')
        # Confirm symlink support before entering the installer.
        probe = self.root / 'link_probe'
        self.symlink(probe, outside, directory=True)
        probe.unlink()
        write = fixer.atomic_write
        def changing(path, data):
            write(path, data)
            if path.name == 'server.py' and data != self.original['server.py']:
                (self.server / 'nxt').rename(self.server / 'original_nxt')
                (self.server / 'nxt').symlink_to(outside, target_is_directory=True)
        with patch.object(fixer, 'atomic_write', side_effect=changing):
            with self.assertRaises(fixer.PatchError):
                fixer.apply_patch(self.server, self.payload)
        self.assertEqual((outside / 'store.py').read_bytes(), b'OUTSIDE FILE')
        self.assertEqual((self.server / 'server.py').read_bytes(), self.original['server.py'])
        self.assertEqual((self.server / 'original_nxt/store.py').read_bytes(), self.original['nxt/store.py'])
        self.assert_preserved()

    def test_rollback_does_not_overwrite_external_edit_to_patched_file(self):
        write = fixer.atomic_write
        def changing(path, data):
            if path.name == 'store.py':
                (self.server / 'server.py').write_bytes(b'EXTERNALLY EDITED PATCHED FILE')
                raise OSError('simulated write failure')
            write(path, data)
        with patch.object(fixer, 'atomic_write', side_effect=changing):
            with self.assertRaisesRegex(fixer.PatchError, 'Previous scripts are in'):
                fixer.apply_patch(self.server, self.payload)
        self.assertEqual((self.server / 'server.py').read_bytes(), b'EXTERNALLY EDITED PATCHED FILE')
        self.assertEqual((self.server / 'nxt/store.py').read_bytes(), self.original['nxt/store.py'])
        self.assert_preserved()


if __name__ == '__main__':
    unittest.main()
