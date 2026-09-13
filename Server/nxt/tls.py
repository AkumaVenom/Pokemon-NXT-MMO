"""Validate direct world-server TLS before opening the game database.

Validation here checks the local certificate/key pair and optional advertised
hostname. It cannot establish whether a player's browser trusts its issuer.
"""
from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import re
import ssl
from pathlib import Path


class TLSConfigurationError(RuntimeError):
    """Operator guidance that never includes PEM contents or private-key data."""


SETUP_GUIDANCE = 'Run "2b - Configure Online Hosting.cmd" in the Server folder to create or import the certificate and save the matching client connection settings.'


def normalize_public_host(value: str) -> str:
    """Return a single DNS name or IP, without a scheme, port or wildcard."""
    if not isinstance(value, str):
        raise TLSConfigurationError('The public host must be a hostname or IP address.')
    host = value.strip()
    if not host or any(character.isspace() for character in host):
        raise TLSConfigurationError('Enter a public hostname or IP address without spaces.')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if '%' in host or address.is_unspecified or address.is_multicast:
            raise TLSConfigurationError('The public host must be a usable hostname or IP address, not a bind wildcard, scoped IP or multicast address.')
        return str(address)
    if host.endswith('.'):
        host = host[:-1]
    try:
        host = host.encode('idna').decode('ascii').lower()
    except (UnicodeError, ValueError):
        raise TLSConfigurationError('The public hostname is not a valid DNS name.') from None
    labels = host.split('.')
    if len(host) > 253 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels):
        raise TLSConfigurationError('Enter only the public hostname or IP address, without https://, a port, brackets, a path or a wildcard.')
    # A misspelled numeric address should not turn into a DNS certificate.
    if all(label.isdigit() for label in labels):
        raise TLSConfigurationError('The public IP address is not valid.')
    return host


def certificate_matches_host(certificate, host: str) -> bool:
    """Match DNS/IP subjectAltName only; commonName is never a fallback."""
    from cryptography import x509
    host = normalize_public_host(host)
    try:
        alternatives = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        return address in alternatives.get_values_for_type(x509.IPAddress)
    for name in alternatives.get_values_for_type(x509.DNSName):
        name = name.lower()
        if name == host:
            return True
        if name.startswith('*.') and name.count('*') == 1:
            suffix = name[2:]
            # A wildcard replaces exactly one complete leftmost label.
            if len(suffix.split('.')) >= 2 and host.count('.') == name.count('.') and host.endswith('.' + suffix):
                return True
    return False


def _configured_path(settings, key: str, label: str) -> Path:
    value = settings.config.get('network', key, fallback='').strip()
    if not value:
        raise TLSConfigurationError(f'TLS is enabled but network.{key} is empty. {SETUP_GUIDANCE}')
    path = (settings.root / value).resolve()
    try:
        exists = path.is_file()
    except OSError:
        exists = False
    if not exists:
        raise TLSConfigurationError(f'TLS {label} file is missing or is not a readable file: {path}. {SETUP_GUIDANCE}')
    return path


def load_server_tls(settings) -> ssl.SSLContext | None:
    """Load validated TLS configuration, or None for explicit private-LAN mode."""
    if not settings.flag('network', 'tls'):
        return None
    certificate_path = _configured_path(settings, 'certificate', 'certificate')
    key_path = _configured_path(settings, 'private_key', 'private key')
    try:
        from cryptography import x509
        from cryptography.exceptions import UnsupportedAlgorithm
        from cryptography.hazmat.primitives import serialization
        from cryptography.x509.oid import ExtendedKeyUsageOID
    except ImportError:
        raise TLSConfigurationError('TLS certificate validation requires cryptography. Run "1 - Install Server Dependencies.cmd" in the Server folder, then retry.') from None

    def read_file(path: Path, label: str) -> bytes:
        try:
            if path.stat().st_size > 4 * 1024 * 1024:
                raise TLSConfigurationError(f'TLS {label} file is too large to be a PEM certificate/key: {path}. {SETUP_GUIDANCE}')
            return path.read_bytes()
        except OSError:
            raise TLSConfigurationError(f'Cannot read TLS {label} file: {path}. Check its permissions and availability. {SETUP_GUIDANCE}') from None

    try:
        certificate = x509.load_pem_x509_certificate(read_file(certificate_path, 'certificate'))
    except (ValueError, UnsupportedAlgorithm):
        raise TLSConfigurationError(f'TLS certificate is not a supported PEM certificate: {certificate_path}. Put the server leaf first, followed by any intermediate certificates. {SETUP_GUIDANCE}') from None
    try:
        private_key = serialization.load_pem_private_key(read_file(key_path, 'private key'), password=None)
    except TypeError:
        raise TLSConfigurationError(f'TLS private key requires a passphrase: {key_path}. This unattended server needs a separate unencrypted server key protected by folder permissions. {SETUP_GUIDANCE}') from None
    except (ValueError, UnsupportedAlgorithm):
        raise TLSConfigurationError(f'TLS private key is not a supported PEM private key: {key_path}. {SETUP_GUIDANCE}') from None
    certificate_public = certificate.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    key_public = private_key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if certificate_public != key_public:
        raise TLSConfigurationError(f'TLS certificate and private key do not match: {certificate_path} | {key_path}. {SETUP_GUIDANCE}')
    now = datetime.now(timezone.utc)
    # The dependency installer may retain an older cryptography satisfying
    # PyMySQL[rsa]. Its legacy properties use naive UTC datetimes.
    not_before = getattr(certificate, 'not_valid_before_utc', None)
    not_after = getattr(certificate, 'not_valid_after_utc', None)
    if not_before is None:
        not_before = certificate.not_valid_before.replace(tzinfo=timezone.utc)
    if not_after is None:
        not_after = certificate.not_valid_after.replace(tzinfo=timezone.utc)
    if now < not_before:
        raise TLSConfigurationError(f'TLS certificate is not valid until {not_before.isoformat()}: {certificate_path}. Check this computer\'s clock or import a current certificate. {SETUP_GUIDANCE}')
    if now >= not_after:
        raise TLSConfigurationError(f'TLS certificate expired at {not_after.isoformat()}: {certificate_path}. Renew or replace it. {SETUP_GUIDANCE}')
    try:
        if certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise TLSConfigurationError(f'TLS certificate is a CA certificate, not a server leaf: {certificate_path}. Import a server certificate for your host, with its intermediate chain after it. {SETUP_GUIDANCE}')
    except x509.ExtensionNotFound:
        pass
    try:
        if ExtendedKeyUsageOID.SERVER_AUTH not in certificate.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value:
            raise TLSConfigurationError(f'TLS certificate does not permit server authentication: {certificate_path}. {SETUP_GUIDANCE}')
    except x509.ExtensionNotFound:
        pass
    public_host = settings.config.get('network', 'public_host', fallback='').strip()
    if public_host:
        try:
            public_host = normalize_public_host(public_host)
        except TLSConfigurationError as error:
            raise TLSConfigurationError(f'Invalid network.public_host. {error} {SETUP_GUIDANCE}') from None
        if not certificate_matches_host(certificate, public_host):
            raise TLSConfigurationError(f'TLS certificate subjectAltName does not cover network.public_host "{public_host}": {certificate_path}. Use the exact hostname/IP covered by the certificate or create a matching certificate. {SETUP_GUIDANCE}')
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # Supplying an empty password prevents OpenSSL from prompting on stdin if
        # the files are replaced with an encrypted key between validation/loading.
        context.load_cert_chain(certificate_path, key_path, password=b'')
    except (OSError, ValueError):
        raise TLSConfigurationError(f'OpenSSL could not load the TLS certificate chain/key: {certificate_path} | {key_path}. Check the complete PEM chain, key algorithm/strength and file permissions. {SETUP_GUIDANCE}') from None
    return context
