"""Online setup regression coverage with real certificates and isolated files.

Windows GUI/trust execution and public network reachability are separate checks.
"""
from __future__ import annotations

import configparser
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
import setup_online as setup
from nxt.config import Settings
from nxt.tls import load_server_tls
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID


class OnlineSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.certificate, cls.key = setup._create_certificate('world.example.com')
        cls.other_certificate, cls.other_key = setup._create_certificate('other.example.com')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='NXT online setup (safe) ')
        self.root = Path(self.temporary.name)
        self.config_path = self.root / 'config.ini'
        original = (ROOT / 'Build/config_templates/Server/config.ini').read_text()
        original = original.replace('password = CHANGE_ME_WITH_SETUP', 'password = Keep!%&this_12345')
        original = original.replace('[database]', '; Preserve this database comment exactly\n[database]')
        self.original = original.replace('\n', '\r\n').encode()
        self.config_path.write_bytes(self.original)
        self.import_certificate = self.root / 'import-chain.pem'
        self.import_key = self.root / 'import-private.pem'
        self.import_certificate.write_bytes(self.certificate)
        self.import_key.write_bytes(self.key)

    def tearDown(self):
        self.temporary.cleanup()

    def imported_options(self, host='world.example.com'):
        return setup.SetupOptions(host, False, self.import_certificate, self.import_key)

    def assert_original_unchanged(self):
        self.assertEqual(self.original, self.config_path.read_bytes())
        self.assertFalse(list(self.root.glob('online-client-kit-*')))
        self.assertFalse(list(self.root.glob('config.before-online-*')))
        self.assertFalse(list(self.root.glob('online-setup-*')))

    def test_generate_real_leaf_and_public_kit_preserves_database_comments_and_newlines(self):
        result = setup.configure(setup.SetupOptions('World.Example.COM'), self.config_path)
        settings = Settings.load(self.config_path)
        self.assertEqual(result.host, 'world.example.com')
        self.assertTrue(settings.flag('network', 'tls'))
        self.assertFalse(settings.flag('network', 'allow_insecure_lan'))
        self.assertEqual(settings.get('network', 'public_host'), 'world.example.com')
        self.assertEqual(settings.get('database', 'password'), 'Keep!%&this_12345')
        self.assertIn(b'; Preserve this database comment exactly\r\n', self.config_path.read_bytes())
        self.assertNotIn(b'\n', self.config_path.read_bytes().replace(b'\r\n', b''))
        self.assertEqual(self.original.split(b'[database]', 1)[1], self.config_path.read_bytes().split(b'[database]', 1)[1])
        self.assertEqual(self.original, result.backup_path.read_bytes())
        self.assertIsInstance(load_server_tls(settings), ssl.SSLContext)
        cert = x509.load_pem_x509_certificate(result.certificate_path.read_bytes())
        self.assertFalse(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        self.assertIn(ExtendedKeyUsageOID.SERVER_AUTH, cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)
        self.assertEqual(cert.public_key().key_size, 3072)
        self.assertEqual(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName), ['world.example.com'])
        days = (cert.not_valid_after_utc - datetime.now(timezone.utc)).total_seconds() / 86400
        self.assertGreater(days, 364)
        self.assertLessEqual(days, 365)
        public_der = (result.kit_path / 'server.cer').read_bytes()
        self.assertEqual(public_der, cert.public_bytes(serialization.Encoding.DER))
        self.assertEqual(result.fingerprint, hashlib.sha256(public_der).hexdigest().upper())
        metadata = json.loads((result.kit_path / 'connection.json').read_text())
        self.assertEqual(metadata['host'], result.host)
        self.assertTrue(metadata['tls'])
        for file in result.kit_path.iterdir():
            self.assertNotIn(b'BEGIN PRIVATE KEY', file.read_bytes())
            self.assertNotIn(b'Keep!%&this_12345', file.read_bytes())
        script = (result.kit_path / 'Trust Server Certificate.ps1').read_text()
        self.assertIn(result.fingerprint, script)
        self.assertIn("if ($actualHash -ne $expectedHash)", script)
        self.assertIn("$answer -cne 'TRUST'", script)
        self.assertIn("X509Store]::new('Root', 'CurrentUser')", script)
        self.assertNotIn('LocalMachine', script)
        self.assertLess(script.index("$answer -cne 'TRUST'"), script.index('$store.Add($certificate)'))
        command = (result.kit_path / 'Trust Server Certificate.cmd').read_text()
        self.assertIn('powershell.exe -NoProfile -Command', command)
        self.assertNotIn(' -File ', command)
        self.assertNotIn('-ExecutionPolicy', command)
        self.assertIn("Join-Path $env:NXT_CERTIFICATE_KIT 'server.cer'", command)
        self.assertEqual(script.count('ReadAllBytes'), 1)
        self.assertIn('$sha256.ComputeHash($certificate.RawData)', script)
        self.assertIn('https://world.example.com:7777/health', result.message())

    def test_valid_import_is_reserialized_without_leaking_combined_private_pem(self):
        self.import_certificate.write_bytes(self.certificate + self.key)
        result = setup.configure(self.imported_options(), self.config_path)
        self.assertEqual(result.certificate_path.read_bytes(), self.certificate)
        self.assertEqual(self.import_key.read_bytes(), self.key)
        self.assertIsInstance(load_server_tls(Settings.load(self.config_path)), ssl.SSLContext)
        self.assertFalse((result.kit_path / 'Trust Server Certificate.cmd').exists())
        for file in result.kit_path.iterdir():
            self.assertNotIn(b'BEGIN PRIVATE KEY', file.read_bytes())
        self.assertIn('does not install or establish client trust', result.message())

    def test_bad_host_does_not_create_or_change_files(self):
        for host in ('', 'https://world.example.com', 'world.example.com:7777', '*.example.com',
                     'world.example.com/path', '0.0.0.0', '999.2.3.4', 'bad host'):
            with self.subTest(host=host), self.assertRaises(setup.SetupError):
                setup.configure(setup.SetupOptions(host), self.config_path)
            self.assert_original_unchanged()

    def test_wrong_hostname_import_leaves_configuration_and_certificates_untouched(self):
        with self.assertRaisesRegex(setup.SetupError, 'host|hostname|SAN'):
            setup.configure(self.imported_options('wrong.example.com'), self.config_path)
        self.assert_original_unchanged()
        self.assertFalse((self.root / 'certificates').exists())

    def test_mismatched_private_key_is_rejected_before_mutation(self):
        self.import_key.write_bytes(self.other_key)
        with self.assertRaisesRegex(setup.SetupError, 'match'):
            setup.configure(self.imported_options(), self.config_path)
        self.assert_original_unchanged()

    def test_invalid_pem_does_not_echo_private_input(self):
        secret = 'SECRET_PRIVATE_MATERIAL_NOT_FOR_LOGS'
        self.import_key.write_text(secret)
        with self.assertRaises(setup.SetupError) as caught:
            setup.configure(self.imported_options(), self.config_path)
        self.assertNotIn(secret, str(caught.exception))
        self.assert_original_unchanged()

    def test_atomic_config_replace_failure_rolls_back_only_new_material(self):
        existing = self.root / 'certificates' / 'existing'
        existing.mkdir(parents=True)
        old_key = existing / 'server.key'
        old_key.write_bytes(b'existing-live-key')
        with mock.patch.object(setup.os, 'replace', side_effect=PermissionError('simulated file lock')):
            with self.assertRaises(setup.SetupError):
                setup.configure(self.imported_options(), self.config_path)
        self.assert_original_unchanged()
        self.assertEqual(old_key.read_bytes(), b'existing-live-key')
        self.assertEqual(list((self.root / 'certificates').iterdir()), [existing])

    def test_config_edited_during_validation_is_not_overwritten(self):
        changed = self.original + b'\r\n; changed by another editor\r\n'
        validator = setup.load_server_tls
        def mutate_after_validation(settings):
            result = validator(settings)
            self.config_path.write_bytes(changed)
            return result
        with mock.patch.object(setup, 'load_server_tls', side_effect=mutate_after_validation):
            with self.assertRaisesRegex(setup.SetupError, 'changed during setup'):
                setup.configure(self.imported_options(), self.config_path)
        self.assertEqual(self.config_path.read_bytes(), changed)
        self.assertFalse(list(self.root.glob('online-client-kit-*')))
        self.assertFalse(list(self.root.glob('config.before-online-*')))

    def test_repeat_setup_keeps_previous_certificate_key_kit_and_backup(self):
        first = setup.configure(self.imported_options(), self.config_path)
        old_key = first.private_key_path.read_bytes()
        old_config = self.config_path.read_bytes()
        second = setup.configure(self.imported_options(), self.config_path)
        self.assertNotEqual(first.certificate_path, second.certificate_path)
        self.assertEqual(first.private_key_path.read_bytes(), old_key)
        self.assertTrue(first.kit_path.exists())
        self.assertEqual(first.backup_path.read_bytes(), self.original)
        self.assertEqual(second.backup_path.read_bytes(), old_config)

    def test_public_dns_promotes_loopback_listener_and_preserves_port(self):
        self.config_path.write_bytes(self.original.replace(b'bind_ip = 0.0.0.0', b'bind_ip = 127.0.0.1').replace(b'port = 7777', b'port = 8888'))
        result = setup.configure(self.imported_options(), self.config_path)
        self.assertEqual(result.bind_ip, '0.0.0.0')
        self.assertEqual(Settings.load(self.config_path).bind_ip, '0.0.0.0')
        self.assertEqual(result.port, 8888)

    def test_specific_interface_is_preserved(self):
        self.config_path.write_bytes(self.original.replace(b'bind_ip = 0.0.0.0', b'bind_ip = 192.168.1.99'))
        result = setup.configure(self.imported_options(), self.config_path)
        self.assertEqual(result.bind_ip, '192.168.1.99')
        self.assertEqual(Settings.load(self.config_path).bind_ip, '192.168.1.99')

    def test_ipv6_certificate_has_ip_san_listener_and_bracketed_health_url(self):
        result = setup.configure(setup.SetupOptions('2001:db8::1234'), self.config_path)
        self.assertEqual(result.bind_ip, '::')
        cert = x509.load_pem_x509_certificate(result.certificate_path.read_bytes())
        addresses = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)
        self.assertEqual(str(addresses[0]), '2001:db8::1234')
        self.assertIn('https://[2001:db8::1234]:7777/health', result.message())

    def test_post_commit_temporary_cleanup_failure_keeps_published_files(self):
        real_temporary = tempfile.TemporaryDirectory
        class CleanupFailure:
            def __init__(self, *args, **kwargs):
                self.inner = real_temporary(*args, **kwargs)
            def __enter__(self):
                return self.inner.__enter__()
            def __exit__(self, *args):
                self.inner.__exit__(*args)
                raise PermissionError('simulated cleanup failure after commit')
        with mock.patch.object(setup.tempfile, 'TemporaryDirectory', CleanupFailure):
            with self.assertRaisesRegex(setup.SetupError, 'were saved'):
                setup.configure(self.imported_options(), self.config_path)
        self.assertNotEqual(self.config_path.read_bytes(), self.original)
        settings = Settings.load(self.config_path)
        self.assertIsInstance(load_server_tls(settings), ssl.SSLContext)
        self.assertEqual(len(list(self.root.glob('online-client-kit-*'))), 1)
        self.assertEqual(len(list(self.root.glob('config.before-online-*'))), 1)


if __name__ == '__main__':
    unittest.main()
