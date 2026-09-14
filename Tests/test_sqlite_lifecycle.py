"""Catch leaked fixture handles without relying on Windows or garbage collection.

Run the actual schema/lease regression with real SQLite connections held alive
until inspection. On Windows an unclosed handle also breaks temporary-directory
cleanup; on POSIX explicit-close assertions catch the same defect. These tests
must remain active without filesystem-link privileges.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'Server')]
# Import the module, not its TestCase class: unittest must not rediscover that
# entire suite as a second set of tests in this module.
from Tests import test_admin_console as admin_tests


class SQLiteFixtureLifetimeTests(unittest.TestCase):
    def run_lease_fixture(self, fault: str | None = None) -> None:
        real_connect = sqlite3.connect
        retained = []
        marker = 'deliberate SQLite fixture lifetime probe failure'

        class TrackedConnection(sqlite3.Connection):
            explicitly_closed = False
            inject_exit_failure = False

            def close(self):
                super().close()
                self.explicitly_closed = True

            def execute(self, sql, parameters=(), /):
                if fault == 'read' and sql == 'SELECT version FROM nxt_schema':
                    raise RuntimeError(marker)
                if fault == 'transaction_exit' and sql == 'UPDATE nxt_schema SET version=1 WHERE id=1':
                    self.inject_exit_failure = True
                return super().execute(sql, parameters)

            def __exit__(self, exc_type, exc_value, traceback):
                if self.inject_exit_failure:
                    # A transaction-exit error must still release the outer
                    # connection handle. Roll back the private fixture first.
                    self.rollback()
                    raise RuntimeError(marker)
                return super().__exit__(exc_type, exc_value, traceback)

        def connect(*args, **kwargs):
            conn = real_connect(*args, **{**kwargs, 'factory': TrackedConnection})
            retained.append(conn)  # Deliberately prevent destructor/GC cleanup.
            return conn

        case = admin_tests.LocalConsoleTests(
            'test_schema_upgrade_refuses_recent_or_future_old_world_lease')
        stream = io.StringIO()
        try:
            with mock.patch.object(sqlite3, 'connect', connect):
                result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
                    unittest.TestSuite([case]))
            if fault is None:
                self.assertTrue(result.wasSuccessful(), stream.getvalue())
                # Main Store, six raw probes, two refused constructors and the
                # final successful migration all use actual tracked handles.
                self.assertEqual(len(retained), 10)
            else:
                self.assertEqual(len(result.errors), 1, stream.getvalue())
                self.assertIn(marker, result.errors[0][1])
                self.assertNotIn('PermissionError', result.errors[0][1])
                self.assertFalse(result.failures, stream.getvalue())
            self.assertFalse(result.skipped, stream.getvalue())
            self.assertTrue(retained)
            self.assertTrue(all(conn.explicitly_closed for conn in retained),
                            'Fixture handles must close before teardown, not during GC.')
            self.assertFalse(case.root.exists(), 'Private fixture directory must be removed.')
            for conn in retained:
                with self.assertRaises(sqlite3.ProgrammingError):
                    conn.execute('SELECT 1')
        finally:
            # Keep a regressing test from contaminating later cases. Assertions
            # above inspect the real outcome BEFORE this emergency test cleanup.
            for conn in retained:
                conn.close()
            if hasattr(case, 'tmp'):
                case.tmp.cleanup()

    def test_actual_lease_fixture_closes_all_handles_with_strong_references(self):
        self.run_lease_fixture()

    def test_read_failure_closes_handles_without_masking_original_error(self):
        self.run_lease_fixture('read')

    def test_transaction_exit_failure_still_closes_handle(self):
        self.run_lease_fixture('transaction_exit')

    def test_unit_and_process_probes_keep_transaction_and_close_contexts(self):
        from Build.build import REQUIRED_SOURCE, is_source_file
        name = 'Tests/test_sqlite_lifecycle.py'
        self.assertIn(name, REQUIRED_SOURCE)
        self.assertTrue(is_source_file(Path(name)))
        for relative, expected in (
                ('Tests/test_admin_console.py', 4),
                ('Tests/check_admin_console_process.py', 3)):
            tree = ast.parse((ROOT / relative).read_text(encoding='utf-8'))
            managed = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.With):
                    continue
                for item in node.items:
                    call = item.context_expr
                    if not isinstance(call, ast.Call):
                        continue
                    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
                        self.assertNotEqual((call.func.value.id, call.func.attr),
                                            ('sqlite3', 'connect'), relative)
                    if not (isinstance(call.func, ast.Name) and call.func.id == 'closing'):
                        continue
                    self.assertEqual(len(call.args), 1)
                    inner = call.args[0]
                    self.assertIsInstance(inner, ast.Call)
                    self.assertIsInstance(inner.func, ast.Attribute)
                    self.assertEqual(ast.unparse(inner.func), 'sqlite3.connect')
                    self.assertEqual(len(node.items), 2)
                    self.assertEqual(ast.unparse(node.items[1].context_expr),
                                     ast.unparse(item.optional_vars))
                    managed += 1
            self.assertEqual(managed, expected, relative)


if __name__ == '__main__':
    unittest.main()
