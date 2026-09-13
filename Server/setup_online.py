#!/usr/bin/env python3
"""Configure direct TLS hosting without touching database settings or live keys.

The generated connection kit contains only a public certificate. Installing its
trust is a separate, deliberate operation on each player's Windows account.
"""
from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile

from nxt.config import Settings
from nxt.tls import TLSConfigurationError, load_server_tls, normalize_public_host

ROOT = Path(__file__).resolve().parent
SETUP_VERSION = '1.2.2'


class SetupError(RuntimeError):
    """An actionable setup error with no private-key or password contents."""


@dataclass(frozen=True)
class SetupOptions:
    host: str
    generate: bool = True
    certificate: Path | None = None
    private_key: Path | None = None

    def validate(self) -> str:
        try:
            host = normalize_public_host(self.host)
        except TLSConfigurationError as exc:
            raise SetupError(str(exc)) from None
        if not host:
            raise SetupError('Enter the public hostname or IP that players will use. Do not enter a URL or port.')
        if self.generate and (self.certificate is not None or self.private_key is not None):
            raise SetupError('Choose either a new private certificate or an existing certificate/key pair.')
        if not self.generate and (self.certificate is None or self.private_key is None):
            raise SetupError('Select both the existing PEM certificate chain and its unencrypted PEM private key.')
        return host


@dataclass(frozen=True)
class SetupResult:
    config_path: Path
    backup_path: Path
    certificate_path: Path
    private_key_path: Path
    kit_path: Path
    host: str
    port: int
    bind_ip: str
    fingerprint: str
    expires: str
    generated: bool

    def message(self) -> str:
        url_host = '[' + self.host + ']' if ':' in self.host else self.host
        trust = ('On EACH player PC, open the connection kit and run Trust Server Certificate.cmd. '
                 'Verify the host and SHA-256 fingerprint with the server owner before typing TRUST. '
                 'Do this on the server PC too if it also runs a client.' if self.generated else
                 'Players need an operating-system/browser-trusted certificate chain for this hostname. '
                 'Existing-certificate mode does not install or establish client trust.')
        return (f'Online TLS settings saved for {self.host}:{self.port}.\n'
                f'World listen address: {self.bind_ip}:{self.port} (this PC must own the configured address).\n'
                f'Configuration: {self.config_path}\nBackup: {self.backup_path}\n'
                f'Server certificate: {self.certificate_path}\n'
                f'Private key (keep on server): {self.private_key_path}\n'
                f'Public connection kit to give players: {self.kit_path}\n'
                f'Certificate SHA-256: {self.fingerprint}\nExpires (UTC): {self.expires}\n'
                f'Encrypted health check (after trusting the certificate): https://{url_host}:{self.port}/health\n\n'
                f'{trust}\n'
                f'In Client/config.ini set [server] host = {self.host}, port = {self.port}, tls = true.\n'
                'Stop any running world, then run 3 - Start World Server.cmd.\n'
                f'Allow inbound TCP {self.port} in Windows Firewall and forward TCP {self.port} '
                'on the router to this server PC. Do not expose the MySQL port. '
                'DNS must point to your public address when using a hostname.\n'
                'This setup validates the local TLS files; it does not test public DNS, router forwarding, '
                'browser trust, or Internet reachability. Test from a separate Internet connection.')


def _crypto():
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError:
        raise SetupError('Certificate support is missing. Run "1 - Install Server Dependencies.cmd" first.') from None
    return x509, hashes, serialization, rsa, ExtendedKeyUsageOID, NameOID


def _create_certificate(host: str) -> tuple[bytes, bytes]:
    x509, hashes, serialization, rsa, eku, names = _crypto()
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    now = datetime.now(timezone.utc)
    try:
        san = x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        san = x509.DNSName(host)
    # A constant short CN avoids length errors for valid long DNS names; SAN is
    # the only hostname identity used by the validator and modern TLS clients.
    subject = x509.Name([x509.NameAttribute(names.COMMON_NAME, 'Pokemon NXT private world')])
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
                   .add_extension(x509.SubjectAlternativeName([san]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.ExtendedKeyUsage([eku.SERVER_AUTH]), critical=False)
                   .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                                                key_encipherment=True, data_encipherment=False,
                                                key_agreement=False, key_cert_sign=False,
                                                crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
                   .sign(key, hashes.SHA256()))
    return (certificate.public_bytes(serialization.Encoding.PEM),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()))


def _read_material(options: SetupOptions, host: str) -> tuple[bytes, bytes]:
    if options.generate:
        return _create_certificate(host)
    x509, _hashes, serialization, *_ = _crypto()
    try:
        # Size bounds also prevent selecting a ROM, database, or other large file.
        if options.certificate.stat().st_size > 2 * 1024 * 1024 or options.private_key.stat().st_size > 256 * 1024:
            raise SetupError('The selected certificate/key file is too large. Select a PEM certificate chain and PEM private key.')
        raw_cert = options.certificate.read_bytes()
        raw_key = options.private_key.read_bytes()
    except OSError:
        raise SetupError('Cannot read the selected certificate/key. Check both paths and file permissions.') from None
    try:
        chain = x509.load_pem_x509_certificates(raw_cert)
        if not chain:
            raise ValueError('empty chain')
        key = serialization.load_pem_private_key(raw_key, password=None)
        # Reserialize instead of copying arbitrary extra PEM blocks. In
        # particular, a combined certificate/key input cannot leak into the kit.
        return (b''.join(cert.public_bytes(serialization.Encoding.PEM) for cert in chain),
                key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    except (ValueError, TypeError, AttributeError):
        raise SetupError('Cannot parse the selected PEM certificate/key. The key must be unencrypted; provide a PEM chain with the server certificate first.') from None


def _network_config_bytes(original: bytes, values: dict[str, str]) -> bytes:
    """Change only the requested [network] values; retain all other text."""
    try:
        text = original.decode('utf-8')
        parsed = configparser.ConfigParser(interpolation=None)
        parsed.read_string(text)
        if not parsed.has_section('network'):
            raise SetupError('The [network] section is missing from config.ini. Restore the supplied configuration template.')
    except (UnicodeError, configparser.Error):
        raise SetupError('Cannot read config.ini as valid UTF-8 INI. No configuration was changed.') from None
    newline = '\r\n' if '\r\n' in text else '\n'
    section = ''
    done = set()
    lines = []
    appended = False
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if section == 'network' and not appended:
                if lines and not lines[-1].endswith(('\r', '\n')):
                    lines[-1] += newline
                lines.extend(f'{key} = {value}{newline}' for key, value in values.items() if key not in done)
                appended = True
            section = stripped[1:-1].strip()
        if section == 'network' and not stripped.startswith((';', '#')):
            key = stripped.split('=', 1)[0].strip().lower() if '=' in stripped else None
            if key in values:
                ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else newline
                prefix = line[:len(line) - len(line.lstrip())]
                line = f'{prefix}{key} = {values[key]}{ending}'
                done.add(key)
        lines.append(line)
    if section == 'network' and not appended:
        if lines and not lines[-1].endswith(('\r', '\n')):
            lines[-1] += newline
        lines.extend(f'{key} = {value}{newline}' for key, value in values.items() if key not in done)
    result = ''.join(lines)
    check = configparser.ConfigParser(interpolation=None)
    try:
        check.read_string(result)
        if any(check.get('network', key) != value for key, value in values.items()):
            raise ValueError('roundtrip mismatch')
    except (configparser.Error, ValueError):
        raise SetupError('The network settings cannot be saved safely. No configuration was changed.') from None
    return result.encode('utf-8')


def _write_new(path: Path, content: bytes, *, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def _trust_script(host: str, port: int, fingerprint: str) -> str:
    # Host validation rejects quotes/control characters. Fingerprint and port
    # are generated internally; no arbitrary operator text becomes script code.
    return rf'''# Public certificate only. Run as the Windows user who plays NXT.
$ErrorActionPreference = 'Stop'
try {{
    $certificatePath = Join-Path $PSScriptRoot 'server.cer'
    $expectedHash = '{fingerprint}'
    $certificate = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new([System.IO.File]::ReadAllBytes($certificatePath))
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {{ $actualHash = [System.BitConverter]::ToString($sha256.ComputeHash($certificate.RawData)).Replace('-', '') }} finally {{ $sha256.Dispose() }}
    if ($actualHash -ne $expectedHash) {{ throw 'Certificate fingerprint mismatch. Stop and obtain a fresh kit from the server owner.' }}
    if ($certificate.HasPrivateKey) {{ throw 'This kit must never contain a private key.' }}
    if ((Get-Date) -lt $certificate.NotBefore -or (Get-Date) -gt $certificate.NotAfter) {{ throw 'The certificate is not currently valid. Ask the server owner for a renewed kit.' }}
    Write-Host ''
    Write-Host 'Pokemon NXT world: {host}:{port}'
    Write-Host ('Certificate SHA-256: ' + $expectedHash)
    Write-Host ('Valid until: ' + $certificate.NotAfter.ToUniversalTime().ToString('u'))
    Write-Host 'Confirm this hostname and fingerprint with the server owner through a trusted channel.'
    Write-Host 'This trusts the displayed private world certificate for your Windows user account.'
    Write-Host 'Trust applies to browsers and other applications using your Windows certificate store.'
    Write-Host 'It does not change game settings, the server, or other Windows users.'
    $answer = Read-Host 'Type TRUST to install this certificate, or press Enter to cancel'
    if ($answer -cne 'TRUST') {{ Write-Host 'Cancelled; no trust was installed.'; exit 1 }}
    $store = [System.Security.Cryptography.X509Certificates.X509Store]::new('Root', 'CurrentUser')
    try {{ $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite); $store.Add($certificate) }} finally {{ $store.Close() }}
    Write-Host 'Installed. Close and reopen the NXT client before connecting.'
    Write-Host 'Use the host, port and tls=true values in README.txt for Client/config.ini.'
    Write-Host ('To remove this trust later: certmgr.msc > Trusted Root Certification Authorities > Certificates > thumbprint ' + $certificate.Thumbprint)
    exit 0
}} catch {{
    Write-Host ('Certificate trust was not completed: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}}
'''


def _make_kit(path: Path, certificate_pem: bytes, host: str, port: int, generated: bool) -> tuple[str, str]:
    import json
    x509, _hashes, serialization, *_ = _crypto()
    certificate = x509.load_pem_x509_certificate(certificate_pem)
    public_der = certificate.public_bytes(serialization.Encoding.DER)
    fingerprint = hashlib.sha256(public_der).hexdigest().upper()
    expires = certificate.not_valid_after_utc.isoformat()
    path.mkdir(mode=0o700)
    _write_new(path / 'server.cer', public_der, mode=0o644)
    _write_new(path / 'connection.json', (json.dumps(dict(host=host, port=port, tls=True,
               certificate_sha256=fingerprint, expires_utc=expires,
               certificate_kind='private-self-signed' if generated else 'operator-supplied'), indent=2) + '\n').encode(), mode=0o644)
    trust = (f'1. Verify the host and SHA-256 fingerprint below with the server owner.\n'
             f'2. On each player PC run "Trust Server Certificate.cmd" as the Windows user who plays.\n'
             f'   Type TRUST only after verification. No administrator login is required.\n'
             f'   This installs the displayed certificate in Current User / Trusted Root Certification Authorities.\n'
             f'   Browser and other application trust for this Windows user is affected.\n'
             f'   If your PC policy blocks the command, follow that policy; you can instead double-click\n'
             f'   server.cer, verify its file SHA-256 with Get-FileHash -Algorithm SHA256 server.cer, then Install Certificate >\n'
             f'   Current User > Place all certificates in the following store > Trusted Root Certification Authorities.\n'
             f'   Do not import an unverified certificate or disable browser certificate checks.\n' if generated else
             '1. This kit does not install trust. The server owner must provide a certificate chain already\n'
             '   trusted by the player OS/browser (or arrange managed private trust separately).\n')
    url_host = '[' + host + ']' if ':' in host else host
    guide = (f'Pokemon NXT MMO - connection kit\n\nWorld: {host}:{port}\n'
             f'Certificate SHA-256 (DER server.cer): {fingerprint}\nExpires UTC: {expires}\n'
             f'Health check after certificate trust: https://{url_host}:{port}/health\n\n'
             f'{trust}\n'
             'Close the NXT client. Open its existing Client/config.ini in a text editor.\n'
             'Change ONLY these values in its existing [server] section; keep the rest of the file:\n\n'
             f'[server]\nhost = {host}\nport = {port}\ntls = true\n\n'
             'Open the client again. The hostname/IP must match exactly, including on the server PC.\n'
             'Do not use 127.0.0.1 for a certificate issued only to your public hostname/IP.\n'
             'If this public address cannot be reached from your home LAN, configure split DNS for the\n'
             'same hostname or router NAT loopback; test from a different Internet connection too.\n\n'
             'The world owner must allow/forward the world TCP port in the firewall/router, start the world,\n'
             'and point DNS at their public address. This kit cannot verify Internet reachability.\n'
             'Never distribute Server/config.ini, the private key, the database, or server backups.\n'
             'Certificates expire: after renewal the owner must provide an updated kit; private trust\n'
             'must be updated on each player PC. Remove obsolete private certificates with certmgr.msc.\n')
    _write_new(path / 'README.txt', guide.encode('utf-8'), mode=0o644)
    if generated:
        script = _trust_script(host, port, fingerprint)
        _write_new(path / 'Trust Server Certificate.ps1', script.replace('\n', '\r\n').encode('utf-8'), mode=0o644)
        # Run fixed commands directly, so the default Windows Restricted script
        # policy does not prevent the deliberate trust operation. No execution
        # policy is changed, no downloaded script is evaluated, and the kit path
        # is data in an environment variable rather than executable command text.
        command_script = script.replace("Join-Path $PSScriptRoot 'server.cer'", "Join-Path $env:NXT_CERTIFICATE_KIT 'server.cer'")
        command_lines = [line.strip() for line in command_script.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        command = ' '.join(line if line.endswith('{') else line + ';' for line in command_lines)
        if '"' in command or '%' in command or len(command) > 7000:
            raise SetupError('Cannot prepare the Windows certificate trust command safely. No configuration was changed.')
        _write_new(path / 'Trust Server Certificate.cmd', (
            '@echo off\r\nsetlocal DisableDelayedExpansion\r\n'
            'title Pokemon NXT - Trust This Private World Certificate\r\n'
            'set "NXT_CERTIFICATE_KIT=%~dp0"\r\n'
            'powershell.exe -NoProfile -Command "' + command + '"\r\n'
            'set "NXT_TRUST_RESULT=%ERRORLEVEL%"\r\n'
            'echo.\r\n'
            'if not "%NXT_TRUST_RESULT%"=="0" echo Trust did not complete. Read README.txt before retrying.\r\n'
            'pause\r\nexit /b %NXT_TRUST_RESULT%\r\n').encode('ascii'), mode=0o644)
    return fingerprint, expires


def configure(options: SetupOptions, config_path: Path) -> SetupResult:
    host = options.validate()
    config_path = Path(config_path).resolve()
    try:
        original = config_path.read_bytes()
        current = Settings.load(config_path)
    except (OSError, ValueError, configparser.Error):
        raise SetupError('Cannot read valid Server/config.ini. Run setup from the built Server folder containing your configuration.') from None
    token = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(6)
    certificate_dir = config_path.parent / 'certificates' / ('online-' + token)
    kit_dir = config_path.parent / ('online-client-kit-' + token)
    backup = config_path.parent / ('config.before-online-' + token + '.ini.bak')
    values = {'tls': 'true', 'allow_insecure_lan': 'false', 'public_host': host,
              'certificate': certificate_dir.relative_to(config_path.parent).as_posix() + '/server.crt',
              'private_key': certificate_dir.relative_to(config_path.parent).as_posix() + '/server.key'}
    bind_ip = current.bind_ip
    try:
        advertised_ip = ipaddress.ip_address(host)
    except ValueError:
        advertised_ip = None
    try:
        listen_ip = ipaddress.ip_address(bind_ip)
    except ValueError:
        listen_ip = None
    public_endpoint = advertised_ip is None or not advertised_ip.is_loopback
    if public_endpoint and listen_ip is not None and listen_ip.is_loopback:
        bind_ip = '::' if advertised_ip is not None and advertised_ip.version == 6 else '0.0.0.0'
    elif advertised_ip is not None and advertised_ip.version == 6 and bind_ip == '0.0.0.0':
        bind_ip = '::'
    if bind_ip != current.bind_ip:
        values['bind_ip'] = bind_ip
    result_bytes = _network_config_bytes(original, values)
    cert_bytes, key_bytes = _read_material(options, host)
    published_cert = False
    published_kit = False
    made_backup = False
    made_parent = False
    committed = False
    try:
        with tempfile.TemporaryDirectory(prefix='online-setup-', dir=config_path.parent) as temporary:
            stage = Path(temporary)
            stage_cert = stage / 'certificate'
            stage_cert.mkdir(mode=0o700)
            _write_new(stage_cert / 'server.crt', cert_bytes, mode=0o644)
            _write_new(stage_cert / 'server.key', key_bytes)
            staged_config = stage / 'config.ini'
            # Validate against staged paths so no new network config can point
            # to unavailable or mismatched files at commit time.
            staged_values = dict(values, certificate=str(stage_cert / 'server.crt'), private_key=str(stage_cert / 'server.key'))
            _write_new(staged_config, _network_config_bytes(original, staged_values))
            load_server_tls(Settings.load(staged_config))
            stage_kit = stage / 'kit'
            fingerprint, expires = _make_kit(stage_kit, cert_bytes, host, current.port, options.generate)
            staged_final = stage / 'final.ini'
            _write_new(staged_final, result_bytes)
            if config_path.read_bytes() != original:
                raise SetupError('config.ini changed during setup. Your other changes were not overwritten; close the other editor and retry.')
            if not certificate_dir.parent.exists():
                certificate_dir.parent.mkdir(mode=0o700)
                made_parent = True
            # Reserve empty destinations exclusively; never replace an old kit
            # or live certificate, even in the unlikely event of a token clash.
            certificate_dir.mkdir(mode=0o700)
            published_cert = True
            for file in stage_cert.iterdir():
                _write_new(certificate_dir / file.name, file.read_bytes(), mode=0o600 if file.suffix == '.key' else 0o644)
            kit_dir.mkdir(mode=0o700)
            published_kit = True
            for file in stage_kit.iterdir():
                _write_new(kit_dir / file.name, file.read_bytes(), mode=0o644)
            _write_new(backup, original)
            made_backup = True
            if config_path.read_bytes() != original:
                raise SetupError('config.ini changed during setup. Your other changes were not overwritten; close the other editor and retry.')
            os.replace(staged_final, config_path)
            committed = True
        return SetupResult(config_path, backup, certificate_dir / 'server.crt', certificate_dir / 'server.key',
                           kit_dir, host, current.port, bind_ip, fingerprint, expires, options.generate)
    except BaseException as exc:
        if committed:
            raise SetupError('Online settings and certificates were saved, but temporary-file cleanup did not complete. Run Check Configuration before starting the world. Keep the saved connection kit and backup.') from None
        # Every path here is exclusively created by this attempt. Existing
        # certificates, backups and configuration never enter rollback removal.
        if made_backup:
            backup.unlink(missing_ok=True)
        if published_kit:
            shutil.rmtree(kit_dir, ignore_errors=True)
        if published_cert:
            shutil.rmtree(certificate_dir, ignore_errors=True)
        if made_parent:
            try:
                certificate_dir.parent.rmdir()
            except OSError:
                pass
        if isinstance(exc, (SetupError, KeyboardInterrupt, SystemExit)):
            raise
        if isinstance(exc, TLSConfigurationError):
            raise SetupError(str(exc)) from None
        if isinstance(exc, OSError):
            raise SetupError('Cannot save online setup files. Check folder permissions and free disk space. The previous configuration and certificates were not replaced.') from None
        raise


def _console_options() -> SetupOptions:
    print('Stop the world before saving. Online setup keeps existing database settings.')
    host = input('Public hostname or IP that players will enter (no URL or port): ').strip()
    print('1 - Generate a private world certificate (each player must explicitly trust it)')
    print('2 - Import an existing trusted PEM certificate chain and private key')
    choice = input('Certificate option [1/2]: ').strip()
    if choice == '1':
        return SetupOptions(host)
    if choice == '2':
        return SetupOptions(host, False, Path(input('Certificate chain PEM path: ').strip().strip('"')),
                            Path(input('Unencrypted private key PEM path: ').strip().strip('"')))
    raise SetupError('Choose certificate option 1 or 2. No files were changed.')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.ini')
    interface = parser.add_mutually_exclusive_group()
    interface.add_argument('--gui', action='store_true')
    interface.add_argument('--console', action='store_true')
    parser.add_argument('--host', help='Exact public hostname/IP players will use; no URL or port')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--generate', action='store_true', help='Create a private certificate and explicit Windows trust kit')
    mode.add_argument('--certificate', type=Path, help='Existing PEM server certificate chain')
    parser.add_argument('--private-key', type=Path, help='Existing unencrypted PEM private key')
    args = parser.parse_args(argv)
    try:
        if args.gui or (os.name == 'nt' and not args.console and args.host is None):
            try:
                from setup_online_gui import GuiUnavailable, run_gui
            except ImportError:
                raise SetupError('The setup window needs Tk. Run the server dependency installer, or use setup_online.py --console.') from None
            try:
                return run_gui(args.config)
            except GuiUnavailable:
                raise SetupError('Cannot open the setup window. Use setup_online.py --console in a terminal.') from None
        if args.console:
            options = _console_options()
            options.validate()
            if input('Type SAVE to create TLS files and update Server/config.ini: ').strip() != 'SAVE':
                print('Cancelled; no setup changes were made.')
                return 1
        else:
            if not args.host or not (args.generate or args.certificate):
                parser.error('provide --host and either --generate or --certificate/--private-key, or use --gui / --console')
            options = SetupOptions(args.host, args.generate, args.certificate, args.private_key)
        print(configure(options, args.config).message())
        return 0
    except (SetupError, TLSConfigurationError) as exc:
        print('ONLINE SETUP FAILED: ' + str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nOnline setup cancelled.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
