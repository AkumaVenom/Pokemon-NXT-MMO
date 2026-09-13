"""Real verified HTTPS/WSS and TLS startup regressions with temporary SQLite.

These exercise the Python world service and certificate validation on loopback.
They do not claim Windows certificate-store installation, public router access,
browser execution, or a production MySQL deployment.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest import mock

import aiohttp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
import server
from nxt.config import Settings
from nxt.content import Content
from nxt.store import Store
from nxt.tls import TLSConfigurationError, load_server_tls

ORIGIN = 'http://127.0.0.1:45210'


@contextlib.contextmanager
def expected_handshake_failures():
    """Keep deliberate TLS refusals out of asyncio's debug traceback output."""
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()

    def report(active_loop, context):
        error = context.get('exception')
        expected = isinstance(error, ConnectionResetError) or (
            isinstance(error, ssl.SSLError) and error.reason in (
                'HTTP_REQUEST', 'TLSV1_ALERT_UNKNOWN_CA', 'SSLV3_ALERT_BAD_CERTIFICATE'))
        if context.get('message') == 'Error on transport creation for incoming connection' and expected:
            return
        if previous is not None:
            previous(active_loop, context)
        else:
            active_loop.default_exception_handler(context)

    loop.set_exception_handler(report)
    try:
        yield
    finally:
        loop.set_exception_handler(previous)


def fixture_settings(root: Path) -> Settings:
    """Use the pristine build template, never a developer's live credentials."""
    config_path = root / 'config.ini'
    config_path.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
    settings = Settings.load(config_path)
    settings.config.set('database', 'backend', 'sqlite')
    settings.config.set('network', 'tls', 'true')
    settings.config.set('network', 'allow_insecure_lan', 'false')
    settings.config.set('network', 'public_host', 'localhost')
    return dataclasses.replace(settings, bind_ip='127.0.0.1', port=0, encounter_chance=0)


def write_certificate(settings: Settings, key, *, before=None, after=None,
                      san=True, ca=False, server_auth=True, encrypted=False):
    """Independent short-lived test fixtures, not the production setup code."""
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    builder = (x509.CertificateBuilder()
               .subject_name(name).issuer_name(name).public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(before or now - timedelta(minutes=5))
               .not_valid_after(after or now + timedelta(days=1))
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
               .add_extension(x509.ExtendedKeyUsage([
                   ExtendedKeyUsageOID.SERVER_AUTH if server_auth else ExtendedKeyUsageOID.CLIENT_AUTH
               ]), critical=False))
    if san:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
    certificate = builder.sign(key, hashes.SHA256())
    certificate_path = settings.path('network', 'certificate')
    key_path = settings.path('network', 'private_key')
    certificate_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    protection = (serialization.BestAvailableEncryption(b'fixture-only-passphrase')
                  if encrypted else serialization.NoEncryption())
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                           serialization.PrivateFormat.PKCS8, protection))
    return certificate_path, key_path


class TLSConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = fixture_settings(Path(self.tmp.name))
        self.certificate_path, self.key_path = write_certificate(self.settings, self.key)

    def test_valid_pair_enforces_tls_1_2_or_newer(self):
        context = load_server_tls(self.settings)
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertGreaterEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_explicit_private_lan_mode_does_not_require_certificates(self):
        self.settings.config.set('network', 'tls', 'false')
        self.settings.config.set('network', 'allow_insecure_lan', 'true')
        self.certificate_path.unlink()
        self.key_path.unlink()
        self.assertIsNone(load_server_tls(self.settings))

    def test_missing_files_name_the_exact_path_and_setup_command(self):
        for key in ('certificate', 'private_key'):
            with self.subTest(file=key):
                original = self.settings.config.get('network', key)
                self.settings.config.set('network', key, 'certificates/missing-' + key)
                with self.assertRaises(TLSConfigurationError) as captured:
                    load_server_tls(self.settings)
                self.assertIn(str(self.settings.path('network', key).resolve()), str(captured.exception))
                self.assertIn('2b - Configure Online Hosting.cmd', str(captured.exception))
                self.assertTrue(self.settings.flag('network', 'tls'))
                self.settings.config.set('network', key, original)

    def test_mismatched_private_key_is_rejected_without_key_contents(self):
        self.key_path.write_bytes(self.other_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        with self.assertRaisesRegex(TLSConfigurationError, 'do not match') as captured:
            load_server_tls(self.settings)
        self.assertNotIn('BEGIN PRIVATE KEY', str(captured.exception))

    def test_expired_and_future_certificates_are_rejected(self):
        now = datetime.now(timezone.utc)
        cases = [
            (now - timedelta(days=2), now - timedelta(days=1), 'expired'),
            (now + timedelta(days=1), now + timedelta(days=2), 'not valid until'),
        ]
        for before, after, message in cases:
            with self.subTest(condition=message):
                write_certificate(self.settings, self.key, before=before, after=after)
                with self.assertRaisesRegex(TLSConfigurationError, message):
                    load_server_tls(self.settings)

    def test_advertised_host_requires_matching_subject_alternative_name(self):
        self.settings.config.set('network', 'public_host', 'another-world.example')
        with self.assertRaisesRegex(TLSConfigurationError, 'subjectAltName'):
            load_server_tls(self.settings)
        self.settings.config.set('network', 'public_host', 'localhost')
        write_certificate(self.settings, self.key, san=False)
        with self.assertRaisesRegex(TLSConfigurationError, 'subjectAltName'):
            load_server_tls(self.settings)

    def test_ca_and_client_only_certificates_are_rejected(self):
        for options, message in (({'ca': True}, 'CA certificate'),
                                 ({'server_auth': False}, 'server authentication')):
            with self.subTest(options=options):
                write_certificate(self.settings, self.key, **options)
                with self.assertRaisesRegex(TLSConfigurationError, message):
                    load_server_tls(self.settings)

    def test_encrypted_key_is_rejected_before_openssl_can_prompt(self):
        write_certificate(self.settings, self.key, encrypted=True)
        with mock.patch('nxt.tls.ssl.SSLContext') as context:
            with self.assertRaisesRegex(TLSConfigurationError, 'passphrase'):
                load_server_tls(self.settings)
        context.assert_not_called()

    def test_malformed_pem_does_not_become_plaintext_or_echo_file_contents(self):
        for path in (self.certificate_path, self.key_path):
            with self.subTest(path=path.name):
                write_certificate(self.settings, self.key)
                path.write_text('SensitiveFixtureMarker_NotAPemFile')
                with self.assertRaises(TLSConfigurationError) as captured:
                    load_server_tls(self.settings)
                self.assertNotIn('SensitiveFixtureMarker_NotAPemFile', str(captured.exception))
                self.assertTrue(self.settings.flag('network', 'tls'))


class TLSNetworkTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = Content(ROOT / 'Server/data/world.json')
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = fixture_settings(Path(self.tmp.name))
        self.certificate_path, _ = write_certificate(self.settings, self.key)
        self.service = None
        self.task = None
        self.session = None
        self.sockets = []
        self.addAsyncCleanup(self.close_world)
        self.db = Store(self.settings)
        self.service = server.Service(self.settings, self.content, self.db)
        self.trust = ssl.create_default_context(cafile=str(self.certificate_path))
        self.assertTrue(self.trust.check_hostname)
        self.assertEqual(self.trust.verify_mode, ssl.CERT_REQUIRED)
        ready = asyncio.get_running_loop().create_future()
        original_site = server.web.TCPSite

        class CapturingSite(original_site):
            async def start(site):
                await super().start()
                ready.set_result(site._server.sockets[0].getsockname()[1])

        # Capture the real kernel-selected ephemeral port; the listener and all
        # Service.run startup, ownership, TLS and shutdown code remain real.
        with mock.patch.object(server.web, 'TCPSite', CapturingSite), contextlib.redirect_stdout(io.StringIO()):
            self.task = asyncio.create_task(self.service.run(no_console=True))
            completed, _ = await asyncio.wait((ready, self.task), timeout=5,
                                               return_when=asyncio.FIRST_COMPLETED)
            if self.task in completed:
                await self.task
                self.fail('The world exited before its TLS listener was ready.')
            if ready not in completed:
                self.fail('The TLS listener did not start within five seconds.')
            self.port = ready.result()
        self.base = f'https://localhost:{self.port}'
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))

    async def close_world(self):
        for websocket in self.sockets:
            await websocket.close()
        if self.session is not None:
            await self.session.close()
        if self.service is not None:
            self.service.stop.set()
        if self.task is not None:
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    await asyncio.wait_for(self.task, timeout=5)
            finally:
                self.assertTrue(self.db.closed)
        elif hasattr(self, 'db'):
            self.db.close()
        self.tmp.cleanup()

    async def test_health_and_authenticated_world_use_verified_tls(self):
        async with self.session.get(self.base + '/health', ssl=self.trust) as response:
            self.assertEqual(response.status, 200)
            data = await response.json()
            self.assertEqual(data['status'], 'online')
            self.assertEqual(data['pack'], self.content.pack)
        websocket = await self.session.ws_connect(
            self.base + '/world', ssl=self.trust,
            headers={'Origin': ORIGIN}, protocols=('nxt.v1',))
        self.sockets.append(websocket)
        self.assertEqual(websocket.protocol, 'nxt.v1')
        hello = await websocket.receive_json(timeout=3)
        self.assertEqual(hello['type'], 'hello')
        await websocket.send_json({
            'op': 'auth', 'mode': 'register', 'username': 'EncryptedTrainer',
            'password': 'Only_A_TLS_Fixture_987!', 'pack': self.content.pack,
            'home': 'Kanto', 'starter': 'fr_1', 'appearance': 0,
        })
        for _ in range(20):
            packet = await websocket.receive_json(timeout=3)
            if packet['type'] == 'joined':
                self.assertEqual(packet['username'], 'EncryptedTrainer')
                break
        else:
            self.fail('The encrypted client did not join the world.')
        self.assertIsNotNone(self.db.account('EncryptedTrainer'))

    async def test_tls_port_rejects_unknown_trust_wrong_hostname_and_plaintext(self):
        with expected_handshake_failures():
            with self.assertRaises(aiohttp.ClientConnectorCertificateError):
                await self.session.get(self.base + '/health', ssl=ssl.create_default_context())
            with self.assertRaises(aiohttp.ClientConnectorCertificateError):
                await self.session.get(f'https://127.0.0.1:{self.port}/health', ssl=self.trust)
            # A plaintext request must not receive a world response from a TLS port.
            reader, writer = await asyncio.open_connection('127.0.0.1', self.port)
            try:
                try:
                    writer.write(b'GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
                    await writer.drain()
                    reply = await asyncio.wait_for(reader.read(4096), timeout=3)
                except (ConnectionResetError, BrokenPipeError):
                    reply = b''
                self.assertEqual(reply, b'')
            finally:
                writer.close()
                with contextlib.suppress(ConnectionResetError, BrokenPipeError):
                    await writer.wait_closed()
            # Failed handshakes must not take down the listener or remove TLS.
            async with self.session.get(self.base + '/health', ssl=self.trust) as response:
                self.assertEqual(response.status, 200)
        self.assertTrue(self.settings.flag('network', 'tls'))
        self.assertFalse(self.settings.flag('network', 'allow_insecure_lan'))


if __name__ == '__main__':
    unittest.main()
