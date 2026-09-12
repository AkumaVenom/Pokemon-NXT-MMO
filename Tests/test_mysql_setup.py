"""MySQL setup contracts using a deterministic fake connector, not a DB daemon."""
from __future__ import annotations
import configparser
from dataclasses import replace
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Server'))
import setup_mysql as setup
from setup_password_input import read_masked


class DatabaseFailure(Exception):
    pass


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.query = ''
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def execute(self, query, args=None):
        self.query = query
        db = self.connection.db
        db.queries.append((query, args))
        if db.fail_ddl and query.startswith('CREATE'):
            raise DatabaseFailure(1819, 'secret SQL must never be printed: Password12345!')
    def fetchone(self):
        return (1,)
    def fetchall(self):
        return [(self.connection.db.username, 'localhost')] if self.connection.db.existing else []


class FakeConnection:
    def __init__(self, db, kwargs):
        self.db = db
        self.kwargs = kwargs
        self.closed = False
    def cursor(self):
        return FakeCursor(self)
    def close(self):
        self.closed = True


class FakeDatabase:
    def __init__(self, *, root_password='', app_password=None, existing=False):
        self.root_password = root_password
        self.app_password = app_password
        self.existing = existing
        self.username = 'pokemon_nxt'
        self.calls = []
        self.connections = []
        self.queries = []
        self.fail_ddl = False
        self.fail_final = False
        self.admin_error = None
    def connect(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs['user'] == 'root':
            if self.admin_error:
                raise DatabaseFailure(self.admin_error, 'private database/SQL details')
            if kwargs['password'] != self.root_password:
                raise DatabaseFailure(1045, 'credentials rejected; sensitive text')
        elif self.app_password is not None and kwargs['password'] != self.app_password:
            raise DatabaseFailure(1045, 'wrong application password')
        if 'database' in kwargs and self.fail_final:
            raise DatabaseFailure(1045, 'application final failed')
        connection = FakeConnection(self, kwargs)
        self.connections.append(connection)
        return connection


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='NXT setup (safe) ')
        self.path = Path(self.tmp.name) / 'config.ini'
        self.path.write_bytes((ROOT / 'Build/config_templates/Server/config.ini').read_bytes())
        self.original = self.path.read_bytes()
        self.options = setup.defaults(setup.load_config(self.path))
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()
    def test_blank_admin_is_sent_as_empty_and_not_replaced(self):
        db = FakeDatabase()
        setup.test_administrator(self.options, self.path, connect=db.connect)
        self.assertEqual(db.calls[0]['password'], '')
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual([q[0] for q in db.queries], ['SELECT 1'])
    def test_existing_password_exact_punctuation_and_spaces(self):
        secret = '  Existing%&!?^|Password  '
        db = FakeDatabase(root_password=secret)
        setup.test_administrator(replace(self.options, admin_password=secret), self.path, connect=db.connect)
        self.assertEqual(db.calls[0]['password'], secret)
    def test_admin_test_ignores_unfinished_application_fields(self):
        db = FakeDatabase()
        setup.test_administrator(replace(self.options, username='root', database='?', application_password='short'), self.path, connect=db.connect)
        self.assertEqual(len(db.calls), 1)
    def test_rejected_blank_has_actionable_message_and_no_mutations(self):
        db = FakeDatabase(root_password='existing-secret')
        with self.assertRaisesRegex(setup.SetupError, 'EMPTY administrator password'):
            setup.provision(self.options, self.path, connect=db.connect)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(db.queries, [])
    def test_wrong_nonblank_admin_does_not_print_credentials(self):
        wrong = 'WrongPrivatePassword!123'
        db = FakeDatabase(root_password='other')
        with self.assertRaises(setup.SetupError) as raised:
            setup.test_administrator(replace(self.options, admin_password=wrong), self.path, connect=db.connect)
        self.assertNotIn(wrong, str(raised.exception))
        self.assertIn('EXISTING', str(raised.exception))
    def test_connection_refused_is_not_called_wrong_password(self):
        db = FakeDatabase()
        db.admin_error = 2003
        with self.assertRaisesRegex(setup.SetupError, 'Start the MySQL service'):
            setup.provision(self.options, self.path, connect=db.connect)
        self.assertEqual(self.path.read_bytes(), self.original)
    def test_first_setup_generates_password_and_saves_verified_account(self):
        db = FakeDatabase()
        result = setup.provision(self.options, self.path, connect=db.connect)
        config = setup.load_config(self.path)
        password = config.get('database', 'password')
        self.assertGreaterEqual(len(password), 40)
        self.assertNotEqual(password, setup.PLACEHOLDER)
        self.assertNotIn(password, result)
        self.assertEqual(db.calls[-1]['password'], password)
        self.assertEqual(db.calls[-1]['database'], 'pokemon_nxt_mmo')
        self.assertTrue(all(c.closed for c in db.connections))
    def test_custom_password_special_characters_round_trip(self):
        password = 'Nxt%!?&^|<>#;= Test123'
        setup.provision(replace(self.options, application_password=password), self.path, connect=FakeDatabase().connect)
        self.assertEqual(setup.load_config(self.path).get('database', 'password'), password)
    def test_blank_app_reuses_configured_password_for_same_account(self):
        password = 'AlreadyConfigured!123'
        setup.replace_values(self.path, {'password': password})
        db = FakeDatabase(app_password=password, existing=True)
        setup.provision(self.options, self.path, connect=db.connect)
        self.assertEqual(setup.load_config(self.path).get('database', 'password'), password)
        self.assertEqual(db.calls[1]['password'], password)
        self.assertNotIn('database', db.calls[1])
    def test_changed_username_does_not_reuse_another_accounts_password(self):
        setup.replace_values(self.path, {'password': 'AlreadyConfigured!123'})
        cfg = setup.load_config(self.path)
        chosen = setup.choose_application_password(cfg, replace(self.options, username='pokemon_nxt2'))
        self.assertNotEqual(chosen, 'AlreadyConfigured!123')
    def test_changed_host_does_not_reuse_another_servers_password(self):
        setup.replace_values(self.path, {'password': 'AlreadyConfigured!123'})
        chosen = setup.choose_application_password(setup.load_config(self.path), replace(self.options, host='192.168.1.2'))
        self.assertNotEqual(chosen, 'AlreadyConfigured!123')
    def test_existing_wrong_application_password_fails_before_ddl(self):
        db = FakeDatabase(existing=True, app_password='OldNxtPassword!123')
        with self.assertRaisesRegex(setup.SetupError, 'NEW dedicated application username'):
            setup.provision(replace(self.options, application_password='DifferentPassword!123'), self.path, connect=db.connect)
        self.assertTrue(all(q.startswith('SELECT') for q, _ in db.queries))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(all(c.closed for c in db.connections))
    def test_failed_final_application_login_does_not_replace_config(self):
        db = FakeDatabase()
        db.fail_final = True
        with self.assertRaises(setup.SetupError):
            setup.provision(self.options, self.path, connect=db.connect)
        self.assertEqual(self.path.read_bytes(), self.original)
    def test_ddl_policy_error_is_redacted_and_config_unchanged(self):
        db = FakeDatabase()
        db.fail_ddl = True
        with self.assertRaises(setup.SetupError) as raised:
            setup.provision(self.options, self.path, connect=db.connect)
        self.assertNotIn('Password12345!', str(raised.exception))
        self.assertIn('policy rejected', str(raised.exception))
        self.assertEqual(self.path.read_bytes(), self.original)
    def test_no_admin_password_written_to_config_or_ddl(self):
        secret = 'AdminSecretNeverSave!123'
        db = FakeDatabase(root_password=secret)
        setup.provision(replace(self.options, admin_password=secret), self.path, connect=db.connect)
        self.assertNotIn(secret, self.path.read_text())
        self.assertNotIn(secret, repr(db.queries))
        self.assertFalse(any(q.upper().startswith(('ALTER USER', 'DROP', 'UPDATE MYSQL')) for q, _ in db.queries))
    def test_localhost_accounts_and_database_scoped_grants(self):
        db = FakeDatabase()
        setup.provision(self.options, self.path, connect=db.connect)
        creates = [args for q, args in db.queries if q.startswith('CREATE USER')]
        self.assertEqual([x[1] for x in creates], ['localhost', '127.0.0.1'])
        for q, _ in db.queries:
            if q.startswith('GRANT'):
                self.assertIn('`pokemon_nxt_mmo`.*', q)
                self.assertNotIn('ON *.*', q)
    def test_environment_override_mismatch_blocks_before_database(self):
        os.environ['POKEMON_NXT_DB_PASSWORD'] = 'StaleEnvironment!123'
        db = FakeDatabase()
        with self.assertRaisesRegex(setup.SetupError, 'overrides Server/config.ini'):
            setup.provision(self.options, self.path, connect=db.connect)
        self.assertEqual(db.calls, [])
    def test_matching_environment_override_is_supported(self):
        password = 'MatchingEnvironment!123'
        os.environ['POKEMON_NXT_DB_PASSWORD'] = password
        setup.provision(replace(self.options, application_password=password), self.path, connect=FakeDatabase().connect)
        self.assertEqual(setup.load_config(self.path).get('database', 'password'), password)
    def test_other_sections_and_comments_are_preserved(self):
        old = self.path.read_text()
        world = old[old.index('[world]'):]
        setup.provision(self.options, self.path, connect=FakeDatabase().connect)
        self.assertIn(world, self.path.read_text())
        self.assertIn('; Pokemon NXT MMO', self.path.read_text())
    def test_missing_key_fails_before_database_access(self):
        self.path.write_text(self.path.read_text().replace('password = CHANGE_ME_WITH_SETUP', ''))
        db = FakeDatabase()
        with self.assertRaises(setup.SetupError):
            setup.provision(self.options, self.path, connect=db.connect)
        self.assertEqual(db.calls, [])
    def test_concurrent_config_change_is_not_overwritten(self):
        self.path.write_bytes(self.original + b'\n; concurrent edit\n')
        with self.assertRaisesRegex(setup.SetupError, 'changed while setup'):
            setup.replace_values(self.path, {'password': 'SecretPassword!123'}, expected=self.original)
        self.assertTrue(self.path.read_bytes().endswith(b'; concurrent edit\n'))
    def test_atomic_replace_failure_keeps_original_and_cleans_temp(self):
        with patch.object(setup.os, 'replace', side_effect=OSError('simulated')):
            with self.assertRaises(setup.SetupError):
                setup.replace_values(self.path, {'password': 'SecretPassword!123'})
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])
    def test_crlf_bom_and_punctuation_save_correctly(self):
        self.path.write_bytes(b'\xef\xbb\xbf' + self.original.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
        setup.replace_values(self.path, {'password': 'Percent%And!123'})
        self.assertIn(b'\r\n', self.path.read_bytes())
        self.assertEqual(setup.load_config(self.path).get('database', 'password'), 'Percent%And!123')
    def test_system_names_admin_as_application_and_bad_ports_blocked(self):
        for change in ({'username':'root'}, {'username':'mysql'}, {'database':'mysql'}, {'database':'sys'},
                       {'port':0}, {'port':70000}, {'port':True}, {'host':'http://localhost'}, {'host':'a b'},
                       {'database':'bad;sql'}, {'username':'root', 'admin_username':'root'}):
            with self.subTest(change=change):
                with self.assertRaises(setup.SetupError):
                    replace(self.options, **change).validate()
    def test_app_policy_blank_valid_but_short_whitespace_control_invalid(self):
        self.options.validate()
        for value in ('short', ' secretLong!123', 'secretLong!123 ', 'secret\nLong123', setup.PLACEHOLDER):
            with self.subTest(value=value):
                with self.assertRaises(setup.SetupError):
                    replace(self.options, application_password=value).validate()
    def test_wildcard_account_requires_explicit_approval(self):
        with self.assertRaises(setup.SetupError):
            replace(self.options, account_host='%').validate()
        replace(self.options, account_host='%', allow_wildcard=True).validate()
    def test_credentials_excluded_from_dataclass_repr(self):
        value = replace(self.options, admin_password='SensitiveAdmin', application_password='SensitiveApplication')
        self.assertNotIn('Sensitive', repr(value))
    def test_missing_ca_fails_before_connect(self):
        text = self.path.read_text().replace('ssl_ca =', 'ssl_ca = missing-ca.pem')
        self.path.write_text(text)
        db = FakeDatabase()
        with self.assertRaisesRegex(setup.SetupError, 'certificate'):
            setup.test_administrator(self.options, self.path, connect=db.connect)
        self.assertEqual(db.calls, [])
    def test_driver_errors_do_not_leak_exception_text(self):
        for code in (1044,1045,1698,1142,1227,1819,2003,2026,3159,1251,1524,2059,2061,9999):
            with self.subTest(code=code):
                msg = str(setup.database_error(DatabaseFailure(code, 'VeryPrivatePassword!'), 'administrator'))
                self.assertNotIn('VeryPrivatePassword!', msg)
                self.assertIn(str(code), msg)


class MaskedInputTests(unittest.TestCase):
    def run_input(self, text, windows=True):
        chars = iter(text)
        output = io.StringIO()
        result = read_masked(lambda: next(chars, ''), output, windows=windows)
        return result, output.getvalue()
    def test_typing_echoes_stars_not_secrets(self):
        value, shown = self.run_input('Pass%!?&123\r')
        self.assertEqual(value, 'Pass%!?&123')
        self.assertEqual(shown, '*' * len(value) + '\n')
    def test_blank_remains_blank(self):
        self.assertEqual(self.run_input('\r'), ('', '\n'))
    def test_backspace_edits_value_and_mask(self):
        value, shown = self.run_input('ab\bC\r')
        self.assertEqual(value, 'aC')
        self.assertIn('\b \b', shown)
    def test_extended_windows_keys_are_not_inserted(self):
        value, _ = self.run_input('a\xe0Kb\x00Hc\r')
        self.assertEqual(value, 'abc')
    def test_ctrl_u_and_escape_clear_field(self):
        for char in ('\x15', '\x1b'):
            self.assertEqual(self.run_input('wrong' + char + 'right\r')[0], 'right')
    def test_cancel_and_eof_do_not_return_partial_secret(self):
        for value, exception in (('pass\x03', KeyboardInterrupt), ('pass\x1a', EOFError), ('pass', EOFError)):
            with self.assertRaises(exception):
                self.run_input(value)
    def test_spaces_unicode_and_punctuation_preserved(self):
        text = ' Päss#?%&!  '
        self.assertEqual(self.run_input(text + '\r')[0], text)
    def test_windows_utf16_surrogate_pair_normalized(self):
        self.assertEqual(self.run_input('\ud83d\ude00\r')[0], '\U0001f600')


if __name__ == '__main__':
    unittest.main()
