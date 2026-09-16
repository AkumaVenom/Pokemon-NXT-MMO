"""Build-only regression tests. All filesystem work uses temporary directories."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nxt_build_tools", ROOT / "Build/build.py")
assert spec and spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class SourceSelectionTests(unittest.TestCase):
    def test_regional_dialogue_sidecars_and_extractors_are_required_and_preserved(self):
        for name in ("kanto_dialogue.json", "johto_dialogue.json"):
            path = "Server/data/" + name
            self.assertIn(name, builder.SOURCE_DATA_FILES)
            self.assertIn(path, builder.REQUIRED_SOURCE)
            self.assertTrue(builder.is_source_file(PurePosixPath(path)))
            self.assertTrue((ROOT / path).is_file())
        for path in ("Tools/publish_dialogue.py", "Tools/extract_firered_dialogue.py", "Tools/extract_sigma_dialogue.py", "Tests/test_kanto_dialogue.py", "Tests/test_johto_dialogue.py"):
            self.assertIn(path, builder.REQUIRED_SOURCE)
            self.assertTrue(builder.is_source_file(PurePosixPath(path)))

    def test_regional_encounter_republish_sidecars_are_required_and_preserved(self):
        names = ("encounters_firered.json", "encounters_crystal.json", "encounter_bindings.json", "species_additions.json")
        for name in names:
            path = "Server/data/" + name
            self.assertIn(name, builder.SOURCE_DATA_FILES)
            self.assertIn(path, builder.REQUIRED_SOURCE)
            self.assertTrue(builder.is_source_file(PurePosixPath(path)))
            self.assertTrue((ROOT / path).is_file())
        for path in ("Tools/publish_encounters.py", "Tools/crystal_encounter_catalog.py", "Server/nxt/encounters.py", "Server/nxt/field_moves.py"):
            self.assertIn(path, builder.REQUIRED_SOURCE)
            self.assertTrue(builder.is_source_file(PurePosixPath(path)))

    def test_required_editable_source_is_included(self):
        for name in (
            "Client/launcher/main.go", "Server/launcher/go.mod", "Server/nxt/store.py",
            "Client/app/app.js", "Client/app/assets/maps/kanto/3_0.png",
            "Server/data/world.json", "Tools/extract_assets.py", "Tests/test_core.py",
            "Docs/TEST_REPORT.md", "Build/build.py", "BUILD_ALL.bat", "START_HERE_BUILD.md",
            "Server/setup_online.py", "Server/setup_online_gui.py", "Server/nxt/tls.py",
            "Server/2b - Configure Online Hosting.cmd", "Tests/test_online_setup.py", "Tests/test_tls_network.py",
        ):
            with self.subTest(name=name):
                self.assertTrue(builder.is_source_file(PurePosixPath(name)))

    def test_runtime_configurations_are_not_copied(self):
        for name in ("Client/config.ini", "Server/config.ini", "Server/config.backup.ini"):
            self.assertFalse(builder.is_source_file(PurePosixPath(name)))

    def test_saves_logs_certificates_and_roms_are_excluded(self):
        for name in (
            "Server/data/development.sqlite3", "Server/data/development.sqlite3-wal",
            "Server/data/accounts.json", "Server/data/backup.sql", "Server/data/users.db",
            "Server/logs/passwords.txt", "Server/logs/world.log.1", "Server/certificates/server.key",
            "Server/certificates/server.crt", "Server/certificates/secret.txt", "Server/.env",
            "Client/app/original.gba", "Client/app/game.gbc", "Client/app/private.pfx",
            "Server/certificates/online-123/server.key", "Server/certificates/online-123/server.crt",
            "Server/online-client-kit-123/connection.json", "Server/online-client-kit-123/README.md",
            "Server/online-client-kit-123/Trust Server Certificate.cmd",
            "Server/online-setup-123/kit/connection.json",
        ):
            with self.subTest(name=name):
                self.assertFalse(builder.is_source_file(PurePosixPath(name)))

    def test_existing_executables_caches_and_build_outputs_are_excluded(self):
        for name in (
            "Client/Pokemon NXT MMO.exe", "Server/Pokemon NXT World Server.exe",
            "Client/launcher/app.dll", "Server/nxt/__pycache__/store.pyc",
            "Server/.venv/pyvenv.cfg", "dist/Client/app/app.js", ".build/build.py",
            "Client/node_modules/test.js", "Tests/ui_artifacts/test.png",
            "Client/app/.env.local", "SHA256SUMS.txt",
        ):
            self.assertFalse(builder.is_source_file(PurePosixPath(name)))

    def test_traversal_absolute_and_unapproved_paths_rejected(self):
        for name in ("../Client/app/app.js", "/Client/app/app.js", "Other/code.py", "notes.txt"):
            self.assertFalse(builder.is_source_file(PurePosixPath(name)))

    def test_config_templates_are_the_only_included_ini_files(self):
        self.assertTrue(builder.is_source_file(PurePosixPath("Build/config_templates/Server/config.ini")))
        self.assertTrue(builder.is_source_file(PurePosixPath("Build/config_templates/Client/config.ini")))
        self.assertFalse(builder.is_source_file(PurePosixPath("Build/private.ini")))

    def test_runtime_placeholder_readmes_are_preserved(self):
        for name in ("Server/logs/README.txt", "Server/certificates/README.md"):
            self.assertTrue(builder.is_source_file(PurePosixPath(name)))


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "Build/config_templates", self.root / "Build/config_templates")

    def tearDown(self):
        self.temp.cleanup()

    def edit(self, component: str, before: str, after: str):
        path = self.root / f"Build/config_templates/{component}/config.ini"
        path.write_text(path.read_text(encoding="utf-8").replace(before, after), encoding="utf-8")

    def test_shipped_templates_pass(self):
        builder.validate_templates(self.root)

    def test_real_database_password_in_release_template_rejected(self):
        self.edit("Server", "CHANGE_ME_WITH_SETUP", "ExampleSecretMustNotShip123!")
        with self.assertRaises(builder.BuildError):
            builder.validate_templates(self.root)

    def test_sqlite_release_default_rejected(self):
        self.edit("Server", "backend = mysql", "backend = sqlite")
        with self.assertRaises(builder.BuildError):
            builder.validate_templates(self.root)

    def test_custom_local_browser_path_in_release_template_rejected(self):
        self.edit("Client", "edge_path=", "edge_path=C:\\Users\\Private\\msedge.exe")
        with self.assertRaises(builder.BuildError):
            builder.validate_templates(self.root)

    def test_missing_template_rejected(self):
        (self.root / "Build/config_templates/Server/config.ini").unlink()
        with self.assertRaises(builder.BuildError):
            builder.validate_templates(self.root)

    def test_client_database_section_rejected(self):
        path = self.root / "Build/config_templates/Client/config.ini"
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\n[database]\npassword=secret\n")
        with self.assertRaises(builder.BuildError):
            builder.validate_templates(self.root)


class BuildFilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Pokemon NXT build (space) ")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_manifest_has_expected_digest_and_relative_paths(self):
        (self.root / "Client").mkdir()
        file = self.root / "Client/sample.txt"
        file.write_text("alpha", encoding="utf-8")
        builder.write_manifest(self.root)
        text = (self.root / "SHA256SUMS.txt").read_text()
        self.assertEqual(text, builder.sha256(file) + "  Client/sample.txt\n")
        builder.write_manifest(self.root)
        self.assertEqual((self.root / "SHA256SUMS.txt").read_text(), text)

    def test_zip_prefix_integrity_and_space_paths(self):
        source = self.root / "Source with spaces"
        source.mkdir()
        (source / "config.ini").write_text("[server]\nhost=127.0.0.1\n")
        (source / "hello.txt").write_text("hello")
        archive = self.root / "out.zip"
        self.assertEqual(builder.archive_tree(source, archive, "Client"), 2)
        with zipfile.ZipFile(archive) as zipped:
            self.assertEqual(zipped.namelist(), ["Client/config.ini", "Client/hello.txt"])
            self.assertIsNone(zipped.testzip())

    def test_atomic_latest_pointer_replaces_only_pointer(self):
        path = self.root / "LATEST_BUILD.txt"
        previous = self.root / "previous-build"
        previous.mkdir()
        builder.atomic_text(path, "one\n")
        builder.atomic_text(path, "two\n")
        self.assertEqual(path.read_text(), "two\n")
        self.assertTrue(previous.is_dir())
        self.assertFalse((self.root / "LATEST_BUILD.txt.tmp").exists())

    def test_build_lock_rejects_concurrent_build_and_releases(self):
        lock = self.root / "build.lock"
        with builder.build_lock(lock):
            with self.assertRaises(builder.BuildError):
                with builder.build_lock(lock):
                    self.fail("Second builder acquired an exclusive lock")
        with builder.build_lock(lock):
            pass

    def test_symlinked_source_file_is_rejected(self):
        (self.root / "Client").mkdir()
        target = self.root / "outside.txt"
        target.write_text("do not copy")
        try:
            (self.root / "Client/README.md").symlink_to(target)
        except OSError:
            self.skipTest("Creating symlinks requires privileges on this Windows host")
        with self.assertRaises(builder.BuildError):
            list(builder.iter_source_files(self.root))

    def test_symlinked_source_directory_is_rejected(self):
        (self.root / "Client").mkdir()
        target = self.root / "outside"
        target.mkdir()
        try:
            (self.root / "Client/app").symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks requires privileges on this Windows host")
        with self.assertRaises(builder.BuildError):
            list(builder.iter_source_files(self.root))

    def test_clean_snapshot_never_reads_live_password_or_executables(self):
        source = self.root / "source"
        for name in builder.REQUIRED_SOURCE:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source test fixture", encoding="utf-8")
        shutil.copytree(ROOT / "Build/config_templates", source / "Build/config_templates", dirs_exist_ok=True)
        for component in ("Client", "Server"):
            (source / component / "config.ini").write_text("THIS_IS_A_LIVE_PRIVATE_PASSWORD")
            (source / component / "old.exe").write_text("old binary")
        destination = self.root / "snapshot"
        builder.snapshot_source(source, destination)
        self.assertNotIn("LIVE_PRIVATE", (destination / "Server/config.ini").read_text())
        self.assertIn("CHANGE_ME_WITH_SETUP", (destination / "Server/config.ini").read_text())
        self.assertFalse((destination / "Server/old.exe").exists())
        self.assertEqual((source / "Server/config.ini").read_text(), "THIS_IS_A_LIVE_PRIVATE_PASSWORD")

    def test_incomplete_source_fails_before_copy(self):
        source = self.root / "source"
        shutil.copytree(ROOT / "Build/config_templates", source / "Build/config_templates")
        with self.assertRaises(builder.BuildError):
            builder.snapshot_source(source, self.root / "snapshot")
        self.assertFalse((self.root / "snapshot").exists())


class PortableExecutableTests(unittest.TestCase):
    def make_pe(self, path: Path, subsystem: int = 2, machine: int = 0x8664):
        raw = bytearray(256)
        raw[:2] = b"MZ"
        struct.pack_into("<I", raw, 60, 64)
        raw[64:68] = b"PE\0\0"
        struct.pack_into("<H", raw, 68, machine)
        struct.pack_into("<H", raw, 64+24, 0x20B)
        struct.pack_into("<H", raw, 64+24+68, subsystem)
        path.write_bytes(raw)

    def test_x64_gui_and_console_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.exe"
            for subsystem in (2, 3):
                self.make_pe(path, subsystem)
                self.assertEqual(builder.inspect_pe(path, subsystem)["subsystem"], subsystem)

    def test_wrong_architecture_and_subsystem_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.exe"
            self.make_pe(path, 2, 0x14C)
            with self.assertRaises(builder.BuildError):
                builder.inspect_pe(path, 2)
            self.make_pe(path, 3)
            with self.assertRaises(builder.BuildError):
                builder.inspect_pe(path, 2)

    def test_non_windows_binary_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "test.exe"
            path.write_bytes(b"\x7fELF" + b"\0" * 200)
            with self.assertRaises(builder.BuildError):
                builder.inspect_pe(path, 2)


if __name__ == "__main__":
    unittest.main()
