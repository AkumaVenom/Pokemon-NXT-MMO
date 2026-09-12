#!/usr/bin/env python3
"""NXT's create-only MySQL/MariaDB setup; never resets an administrator password.

Windows defaults to a form with masked, editable password fields. --console is
also available. Both interfaces share the same validation and provisioning code.
No password is passed through CMD, printed in errors, or written to a client.
"""
from __future__ import annotations

import argparse
import configparser
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
from typing import Callable

ROOT = Path(__file__).resolve().parent
SETUP_VERSION = '1.1.0'
PLACEHOLDER = 'CHANGE_ME_WITH_SETUP'
IDENTIFIER = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,31}$')
SYSTEM_DATABASES = {'mysql', 'sys', 'information_schema', 'performance_schema'}
SYSTEM_USERS = {'root', 'mysql', 'mysql.sys', 'mysql.session', 'mysql.infoschema', 'mariadb.sys'}


class SetupError(RuntimeError):
    """A safe, actionable message that never contains a credential or SQL text."""


@dataclass(frozen=True)
class SetupOptions:
    host: str
    port: int
    database: str
    username: str
    account_host: str = 'localhost'
    admin_username: str = 'root'
    admin_password: str = field(default='', repr=False)
    application_password: str = field(default='', repr=False)
    allow_wildcard: bool = False

    def validate(self, *, administrator_only: bool = False) -> None:
        if not self.host or any(c.isspace() or ord(c) < 32 for c in self.host) or len(self.host) > 255:
            raise SetupError('Enter a MySQL hostname or IP, such as 127.0.0.1. Do not enter a URL.')
        if '://' in self.host or '/' in self.host or '\\' in self.host:
            raise SetupError('Enter only the MySQL hostname or IP, without a URL or path.')
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise SetupError('MySQL port must be a whole number from 1 to 65535.')
        if not self.admin_username or len(self.admin_username) > 80 or any(ord(c) < 32 for c in self.admin_username):
            raise SetupError('Enter your existing MySQL administrator username; usually root.')
        if any(c in self.admin_password for c in '\r\n\0'):
            raise SetupError('The administrator password contains a line break or NUL. Paste only the password.')
        # An EMPTY existing administrator password is deliberately valid input.
        if administrator_only:
            return
        identifier(self.database)
        identifier(self.username)
        if self.database.casefold() in SYSTEM_DATABASES:
            raise SetupError('Choose a separate NXT database, not a MySQL system database.')
        if self.username.casefold() in SYSTEM_USERS or self.username.casefold() == self.admin_username.casefold():
            raise SetupError('The NXT application username must be separate from the administrator. Use pokemon_nxt or a new dedicated name.')
        if not re.fullmatch(r'[A-Za-z0-9_.:%-]{1,255}', self.account_host):
            raise SetupError('Invalid account host. Use localhost when MySQL and the world server are on this PC.')
        if '%' in self.account_host and not self.allow_wildcard:
            raise SetupError('A wildcard account host requires explicit approval. Use localhost for a local installation.')
        if self.application_password:
            validate_application_password(self.application_password)


def identifier(value: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise SetupError('Database and application user names must be 1-32 letters, numbers or underscores, starting with a letter.')
    return value


def validate_application_password(value: str) -> None:
    if not 12 <= len(value) <= 256:
        raise SetupError('The NXT application password must contain 12-256 characters. Leave it blank to generate or reuse one automatically.')
    if value != value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise SetupError('The application password cannot contain control characters or leading/trailing whitespace. Punctuation such as ! ? % & is supported.')
    if value == PLACEHOLDER:
        raise SetupError('The template placeholder is not a password. Leave the application field blank to generate one.')


def load_config(path: Path) -> configparser.ConfigParser:
    config = configparser.ConfigParser(interpolation=None)
    try:
        with path.open('r', encoding='utf-8-sig') as stream:
            config.read_file(stream)
        for key in ('backend', 'host', 'port', 'database', 'user', 'password'):
            config.get('database', key)
    except (OSError, configparser.Error) as exc:
        raise SetupError('Cannot read the required database fields in Server/config.ini. Restore the configuration template; do not delete a live database.') from None
    return config


def defaults(config: configparser.ConfigParser) -> SetupOptions:
    try:
        port = config.getint('database', 'port')
    except ValueError:
        port = 3306
    return SetupOptions(host=config.get('database', 'host'), port=port,
                        database=config.get('database', 'database'), username=config.get('database', 'user'))


def _connect_function(connect=None):
    if connect is not None:
        return connect
    try:
        import pymysql
    except ImportError:
        raise SetupError('PyMySQL is missing. Run "1 - Install Server Dependencies.cmd" in this Server folder first.') from None
    return pymysql.connect


def connection_options(options: SetupOptions, config: configparser.ConfigParser, path: Path) -> dict:
    ca_value = config.get('database', 'ssl_ca', fallback='').strip()
    ca = str((path.parent / ca_value).resolve()) if ca_value else None
    if ca and not Path(ca).is_file():
        raise SetupError('The MySQL CA certificate configured by database.ssl_ca was not found. Correct that path; do not disable certificate checks for a remote production server.')
    return dict(host=options.host, port=options.port, charset='utf8mb4',
                connect_timeout=8, read_timeout=10, write_timeout=10,
                ssl_ca=ca, ssl_verify_cert=bool(ca), ssl_verify_identity=bool(ca))


def database_error(exc: Exception, stage: str, *, blank_admin: bool = False) -> SetupError:
    """Never include str(exc): some driver/server errors contain SQL/passwords."""
    code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
    suffix = f' [MySQL error {code}]' if code is not None else f' [{type(exc).__name__}]'
    if code in (1045, 1698):
        if stage == 'administrator':
            if blank_admin:
                text = ('MySQL rejected an EMPTY administrator password. Leave this field blank only when that existing MySQL account really has no password. '
                        'Otherwise type the password already set for MySQL root (not your Windows password or a newly invented one). '
                        'The NXT installer cannot create or reset that administrator password.')
            else:
                text = ('MySQL rejected the administrator login. Use Show password to check typing and verify the username, host and port. '
                        'This must be the EXISTING MySQL administrator password, not a new NXT password. '
                        'No administrator password was changed.')
        else:
            text = ('MySQL rejected the NXT application login. An existing NXT account may have a different password, or the configured account host may not match. '
                    'Enter its existing application password or choose a NEW dedicated application username, such as pokemon_nxt2. '
                    'This setup never silently resets an existing account password.')
    elif code in (2002, 2003, 2005, 2006, 2013):
        text = ('Cannot reach MySQL, or the connection was interrupted. Start the MySQL service (or XAMPP Control Panel > MySQL > Start), '
                'then check the MySQL host and port. Local defaults are 127.0.0.1 and 3306. This is not a password-entry error.')
    elif code in (1044, 1142, 1227):
        text = ('This MySQL account does not have the required access. Use an existing administrator permitted to inspect mysql.user, '
                'create the separate NXT database/user and grant privileges. The world service itself uses only the dedicated NXT account.')
    elif code == 1819:
        text = ('The MySQL password policy rejected the NXT application password. Enter a stronger application password that meets your server policy; '
                'the administrator password does not need changing.')
    elif code in (2026, 3159):
        text = ('MySQL requires a valid secure connection. Check database.ssl_ca and the MySQL TLS configuration. '
                'Do not bypass certificate verification on a remote production server.')
    elif code in (1251, 1524, 2059, 2061) or isinstance(exc, ImportError):
        text = ('MySQL authentication support is missing or incompatible. Run the server dependency installer including PyMySQL[rsa], '
                'then check the authentication plugin configured for this existing MySQL account.')
    else:
        text = (f'MySQL setup failed during {stage}. Verify the running database service, account permissions and server configuration. '
                'No credential or SQL text is included in this message.')
    return SetupError(text + suffix)


def test_administrator(options: SetupOptions, config_path: Path, *, connect=None) -> str:
    options.validate(administrator_only=True)
    config = load_config(config_path)
    connector = _connect_function(connect)
    kwargs = connection_options(options, config, config_path)
    try:
        conn = connector(**kwargs, user=options.admin_username, password=options.admin_password, autocommit=True)
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
                if cur.fetchone()[0] != 1:
                    raise SetupError('Unexpected response to the MySQL login test.')
        finally:
            conn.close()
    except SetupError:
        raise
    except Exception as exc:
        raise database_error(exc, 'administrator', blank_admin=not options.admin_password) from None
    return 'Administrator login verified. This test did not create a database, change a password or save config.ini.'


# Prevent pytest treating a public setup operation as a test fixture.
test_administrator.__test__ = False


def choose_application_password(config: configparser.ConfigParser, options: SetupOptions) -> str:
    existing = config.get('database', 'password')
    same_account = (options.username == config.get('database', 'user')
                    and options.host == config.get('database', 'host')
                    and str(options.port) == config.get('database', 'port'))
    if options.application_password:
        password = options.application_password
    elif same_account and existing and existing != PLACEHOLDER:
        password = existing
    else:
        # Include all common complexity classes while keeping INI-safe content.
        password = 'Nxt!9aA-' + secrets.token_urlsafe(32)
    validate_application_password(password)
    override_name = config.get('database', 'password_environment', fallback='POKEMON_NXT_DB_PASSWORD')
    if override_name and override_name in os.environ and os.environ[override_name] != password:
        raise SetupError(f'The environment variable {override_name} overrides Server/config.ini with a different password. '
                         'Remove the stale override or enter its matching application password, then rerun setup. No database change was attempted.')
    return password


def _config_bytes(original: bytes, values: dict[str, str]) -> bytes:
    section = ''
    lines = []
    done = set()
    text = original.decode('utf-8-sig')
    newline = '\r\n' if '\r\n' in text else '\n'
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped[1:-1].strip().lower()
        key = stripped.split('=', 1)[0].strip().lower() if '=' in stripped and not stripped.startswith((';', '#')) else None
        if section == 'database' and key in values:
            if key in done:
                raise SetupError('A database key appears more than once in config.ini; correct the duplicate before setup.')
            line = f'{key} = {values[key]}'
            done.add(key)
        lines.append(line)
    if set(values) - done:
        raise SetupError('Required database keys are missing in config.ini. Restore the supplied template.')
    result = newline.join(lines) + newline
    parsed = configparser.ConfigParser(interpolation=None)
    try:
        parsed.read_string(result)
        if any(parsed.get('database', key) != str(value) for key, value in values.items()):
            raise SetupError('A database value cannot be saved without changing it. No configuration was replaced.')
    except configparser.Error:
        raise SetupError('Invalid INI configuration. No configuration was replaced.') from None
    return result.encode('utf-8')


def replace_values(path: Path, values: dict[str, str], *, expected: bytes | None = None) -> None:
    original = path.read_bytes()
    if expected is not None and original != expected:
        raise SetupError('config.ini changed while setup was running. Close the other editor/setup and retry; those changes were not overwritten.')
    result = _config_bytes(original, values)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile('wb', dir=path.parent, delete=False, suffix='.tmp') as stream:
            temporary = Path(stream.name)
            stream.write(result)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != original:
            raise SetupError('config.ini changed while setup was running; it was not overwritten.')
        os.replace(temporary, path)
    except OSError:
        raise SetupError('The application login worked but config.ini could not be saved. Check folder permissions. '
                         'Existing MySQL passwords were not reset; retain any custom application password, or use a new dedicated username on retry.') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def provision(options: SetupOptions, config_path: Path, *, connect=None,
              progress: Callable[[str], None] = lambda _: None) -> str:
    options.validate()
    config = load_config(config_path)
    original = config_path.read_bytes()
    password = choose_application_password(config, options)
    values = dict(backend='mysql', host=options.host, port=str(options.port),
                  database=options.database, user=options.username, password=password)
    _config_bytes(original, values)  # Fail malformed INI before attempting any DDL.
    connector = _connect_function(connect)
    kwargs = connection_options(options, config, config_path)
    progress('Checking your EXISTING MySQL administrator login...')
    try:
        conn = connector(**kwargs, user=options.admin_username, password=options.admin_password, autocommit=True)
    except Exception as exc:
        raise database_error(exc, 'administrator', blank_admin=not options.admin_password) from None
    try:
        progress('Checking whether the dedicated NXT application account already exists...')
        with conn.cursor() as cur:
            cur.execute('SELECT User, Host FROM mysql.user WHERE User = %s', (options.username,))
            existing_accounts = cur.fetchall()
        if existing_accounts:
            # Authenticate BEFORE any DDL/grant. CREATE USER IF NOT EXISTS alone
            # does not repair a previously created account with a different password.
            try:
                check = connector(**kwargs, user=options.username, password=password)
                check.close()
            except Exception as exc:
                raise database_error(exc, 'existing application account') from None
        progress('Creating the separate NXT database/account and database-scoped grants...')
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE IF NOT EXISTS `{options.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            hosts = [options.account_host]
            if options.account_host == 'localhost':
                hosts.append('127.0.0.1')
            for access_host in hosts:
                cur.execute('CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s', (options.username, access_host, password))
                cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES ON `{options.database}`.* TO %s@%s',
                            (options.username, access_host))
    except SetupError:
        raise
    except Exception as exc:
        raise database_error(exc, 'account/database creation') from None
    finally:
        conn.close()
    progress('Verifying the dedicated application login before saving config.ini...')
    try:
        check = connector(**kwargs, user=options.username, password=password, database=options.database)
        try:
            with check.cursor() as cur:
                cur.execute('SELECT 1')
                if cur.fetchone()[0] != 1:
                    raise SetupError('Unexpected response to the application login test.')
        finally:
            check.close()
    except SetupError:
        raise
    except Exception as exc:
        raise database_error(exc, 'application verification') from None
    replace_values(config_path, values, expected=original)
    return ('SUCCESS: NXT application login verified and Server/config.ini saved. '
            'Your MySQL administrator password was NOT changed or stored. '
            'Start "3 - Start World Server.cmd" next. Give players only the Client folder.')


def ask(label: str, default: str) -> str:
    return input(f'{label} [{default}]: ').strip() or default


def run_console(config_path: Path, *, visible_passwords: bool = False) -> int:
    from setup_password_input import read_password
    config = load_config(config_path)
    current = defaults(config)
    print('\nPokemon NXT MMO - MySQL setup ' + SETUP_VERSION)
    print('Start MySQL / XAMPP MySQL first; stop the NXT world before configuration.')
    print('ADMIN password = the EXISTING MySQL root password. It is NOT being created here.')
    print('Blank is valid ONLY when that existing MySQL account has no password.')
    print('APPLICATION password = the separate NXT password. Blank generates/reuses it.')
    print('No administrator passwords, other games or databases are reset.\n')
    if visible_passwords:
        print('WARNING: --visible-passwords displays entered passwords. Do not screen-share or save the terminal output.\n')
    host = ask('MySQL host', current.host)
    try:
        port = int(ask('MySQL port', str(current.port)))
    except ValueError:
        raise SetupError('MySQL port must be a whole number.') from None
    admin = ask('EXISTING MySQL administrator username', 'root')
    while True:
        secret = read_password('EXISTING MySQL administrator password (Enter only if none): ', visible=visible_passwords)
        options = SetupOptions(host, port, current.database, current.username,
                               admin_username=admin, admin_password=secret)
        try:
            print(test_administrator(options, config_path))
            break
        except SetupError as exc:
            print('\n' + str(exc))
            if ask('Retry administrator password? Y/N', 'Y').upper() != 'Y':
                return 1
    database = ask('Separate NXT database', current.database)
    username = ask('Separate NXT application username', current.username)
    account_host = ask('World server host as MySQL sees it (same PC: localhost)', 'localhost')
    wildcard = '%' in account_host and ask('Approve wildcard account host? Type YES', 'NO') == 'YES'
    password = read_password('NXT application password (Enter = reuse/generate): ', visible=visible_passwords)
    if password:
        confirm = read_password('Confirm NXT application password: ', visible=visible_passwords)
        if password != confirm:
            raise SetupError('The NXT application password confirmation does not match. No database changes were attempted.')
    options = SetupOptions(host, port, database, username, account_host, admin, secret, password, wildcard)
    print('\n' + provision(options, config_path, progress=print))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='NXT MySQL setup with editable password fields; never resets MySQL root.')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--gui', action='store_true', help='Open the password-entry form (Windows default).')
    modes.add_argument('--console', action='store_true', help='Use the console with visible masking feedback.')
    parser.add_argument('--visible-passwords', action='store_true', help='Console only: show typed passwords, explicitly opting out of masking.')
    args = parser.parse_args(argv)
    if args.visible_passwords and not args.console:
        parser.error('--visible-passwords requires --console')
    path = ROOT / 'config.ini'
    try:
        if args.gui or (os.name == 'nt' and not args.console):
            try:
                from setup_mysql_gui import run_gui, GuiUnavailable
            except ImportError:
                print('The optional Python Tk interface is unavailable; using the console with password-entry feedback.')
            else:
                try:
                    return run_gui(path)
                except GuiUnavailable:
                    print('The graphical window is unavailable; using the console with password-entry feedback.')
        return run_console(path, visible_passwords=args.visible_passwords)
    except (KeyboardInterrupt, EOFError):
        print('\nSetup cancelled. No administrator password was changed.')
        return 1
    except SetupError as exc:
        print('\nMYSQL SETUP NOT COMPLETED: ' + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f'\nMYSQL SETUP NOT COMPLETED [{type(exc).__name__}]. No raw credential-bearing error was printed. '
              'Check the configuration and dependency installation.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    # Keep one copy of the core module when the GUI imports it.
    sys.modules.setdefault('setup_mysql', sys.modules[__name__])
    raise SystemExit(main())
