"""Build smoke diagnostics must distinguish actual denial from broken TCP."""
from __future__ import annotations

import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nxt_launcher_smoke', ROOT / 'Build/smoke_launcher.py')
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


class LauncherSmokeTests(unittest.TestCase):
    def test_real_http_denial_and_original_post_are_preserved(self):
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            'http://127.0.0.1:43210/audio-settings', 403, 'Forbidden',
            {'Content-Type': 'text/plain'}, io.BytesIO(b'Forbidden\n'))
        values = {'master': .3, 'muted': True}
        status, _, body = smoke.request_http(opener, 'http://127.0.0.1:43210',
                                             '/audio-settings?token=test', 'POST', data=values)
        self.assertEqual((status, body), (403, b'Forbidden\n'))
        request = opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data), values)
        self.assertIsNone(request.get_header('Origin'))
        self.assertEqual(request.get_header('Content-type'), 'application/json')
        self.assertEqual(opener.open.call_args.kwargs['timeout'], 4)

    def test_reset_timeout_and_eof_fail_without_retry_or_fabricated_status(self):
        for error in (ConnectionResetError('[WinError 10054] Connection reset'),
                      TimeoutError('timed out'), http.client.RemoteDisconnected('closed without response')):
            with self.subTest(error=type(error).__name__):
                opener = Mock()
                opener.open.side_effect = error
                with self.assertRaises(smoke.LauncherSmokeError) as caught:
                    smoke.request_http(opener, 'http://127.0.0.1:43210',
                                       '/audio-settings?token=private-test-nonce', 'POST', data={})
                self.assertIn('POST /audio-settings', str(caught.exception))
                self.assertIn(type(error).__name__, str(caught.exception))
                self.assertNotIn('private-test-nonce', str(caught.exception))
                opener.open.assert_called_once()

    def test_truncated_error_response_is_still_a_failed_check(self):
        class TruncatedBody(io.BytesIO):
            def read(self, *args):
                raise http.client.IncompleteRead(b'Forbid', 4)
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            'http://127.0.0.1:43210/audio-settings', 403, 'Forbidden', {}, TruncatedBody())
        with self.assertRaises(smoke.LauncherSmokeError):
            smoke.request_http(opener, 'http://127.0.0.1:43210', '/audio-settings', 'POST', data={})

    def test_cli_records_transport_failure_and_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'smoke.json'
            args = ['smoke_launcher.py', '--exe', 'test.exe', '--client-root', 'Client', '--output', str(output)]
            with patch.object(sys, 'argv', args), \
                 patch.object(smoke, 'check', side_effect=smoke.LauncherSmokeError('POST /audio-settings reset')):
                with self.assertRaises(SystemExit) as caught:
                    smoke.main()
            self.assertNotEqual(caught.exception.code, 0)
            result = json.loads(output.read_text())
            self.assertIs(result['passed'], False)
            self.assertIn('/audio-settings', result['error'])


if __name__ == '__main__':
    unittest.main()
