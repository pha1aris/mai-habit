"""Failure-mode tests: console encoding, retries, request budget, diagnosability."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/mai-habit/scripts'))
from mcp_client import Client, MCPError
import console
from test_mcp import Response, rpc


class FakeStream:
    """Minimal stdout stand-in so the encoding fallback is testable off-Windows."""

    def __init__(self, encoding, tty):
        self.encoding = encoding
        self._tty = tty
        self.reconfigured = False

    def isatty(self):
        return self._tty

    def reconfigure(self, encoding=None, errors=None):
        self.reconfigured = True
        self.encoding = encoding


class ConsoleTests(unittest.TestCase):
    def test_utf8_stream_keeps_the_yen_sign(self):
        stream = FakeStream('utf-8', tty=False)
        self.assertEqual('¥', console.prepare(stream))
        self.assertFalse(stream.reconfigured)

    def test_redirected_gbk_stream_is_switched_to_utf8(self):
        stream = FakeStream('cp936', tty=False)
        self.assertEqual('¥', console.prepare(stream))
        self.assertTrue(stream.reconfigured)

    def test_interactive_gbk_stream_falls_back_to_fullwidth_yen(self):
        # A real console must not be reconfigured under the user's feet.
        stream = FakeStream('cp936', tty=True)
        self.assertEqual('￥', console.prepare(stream))
        self.assertFalse(stream.reconfigured)

    @unittest.skipUnless(sys.platform == 'win32', 'cp936 only exists on Windows')
    def test_cli_survives_a_chinese_windows_code_page(self):
        import os
        env = {k: v for k, v in os.environ.items()
               if k not in ('PYTHONUTF8', 'PYTHONIOENCODING')}
        env.update({'PYTHONUTF8': '0', 'PYTHONIOENCODING': 'cp936'})
        done = subprocess.run([sys.executable, str(ROOT / 'habit.py'), 'demo'],
                              capture_output=True, env=env, cwd=ROOT)
        self.assertEqual(0, done.returncode, done.stderr.decode('utf-8', 'replace'))
        self.assertIn('麦懂你', done.stdout.decode('utf-8'))


def http_error(code, retry_after=None):
    headers = {'Retry-After': str(retry_after)} if retry_after is not None else {}
    return HTTPError('https://mcp.mcd.cn', code, 'boom', headers, None)


MEALS = {'name': 'query-meals', 'inputSchema': {'required': ['store']}}


class RetryTests(unittest.TestCase):
    def client(self, **kwargs):
        client = Client('FAKE-TEST-TOKEN', **kwargs)
        client.opener = Mock()
        return client

    def test_transient_error_is_retried_once(self):
        client = self.client(backoff=0)
        client.opener.open.side_effect = [http_error(503), rpc(1, {'tools': [MEALS]})]
        self.assertEqual(['query-meals'], [t['name'] for t in client.tools()])
        self.assertEqual(2, client.calls)

    def test_retry_budget_is_bounded(self):
        client = self.client(backoff=0, retries=2)
        client.opener.open.side_effect = [http_error(503), http_error(503), http_error(503)]
        with self.assertRaises(MCPError) as error:
            client.tools()
        self.assertIn('503', str(error.exception))
        self.assertEqual(3, client.calls)

    def test_client_error_is_not_retried(self):
        client = self.client(backoff=0)
        client.opener.open.side_effect = http_error(401)
        with self.assertRaises(MCPError):
            client.tools()
        self.assertEqual(1, client.calls)

    def test_retry_after_is_honoured(self):
        client = self.client(backoff=0, retries=1)
        client.opener.open.side_effect = [http_error(429, retry_after=1), rpc(1, {'tools': []})]
        with patch('mcp_client.time.sleep') as sleep:
            client.tools()
        sleep.assert_called_once_with(1.0)

    def test_tool_catalog_is_fetched_once_per_session(self):
        client = self.client(backoff=0)
        client.opener.open.side_effect = [
            rpc(1, {'tools': [MEALS]}),
            rpc(2, {'content': [{'type': 'text', 'text': 'A'}]}),
            rpc(3, {'content': [{'type': 'text', 'text': 'B'}]})]
        client.call('query-meals', {'store': 'S1'})
        client.call('query-meals', {'store': 'S1'})
        # One tools/list plus one tools/call per candidate -- not two per candidate.
        self.assertEqual(3, client.opener.open.call_count)
        self.assertEqual(3, client.calls)

    def test_refresh_rereads_a_changed_catalog(self):
        client = self.client(backoff=0)
        client.opener.open.side_effect = [rpc(1, {'tools': [MEALS]}), rpc(2, {'tools': []})]
        self.assertEqual(1, len(client.tools()))
        self.assertEqual([], client.tools(refresh=True))


class PlanDiagnosticsTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'habit.py'), *args],
                              capture_output=True, text=True, encoding='utf-8', cwd=ROOT)

    def args(self, mapping, *extra):
        return ['plan', '--profile', 'examples/profile.demo.json',
                '--mapping', mapping, '--menu', 'examples/replay/menu.json',
                '--prices', 'examples/replay/prices.json',
                '--meal', 'lunch', '--budget', '30', '--store', 'MCD-DEMO-001', *extra]

    def test_broken_mapping_reports_an_aggregated_reason(self):
        mapping = json.loads((ROOT / 'examples/replay/mapping.json').read_text(encoding='utf-8'))
        mapping['quote'] = {'total_cents': 'notThere'}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'mapping.json'
            path.write_text(json.dumps(mapping), encoding='utf-8')
            done = self.run_cli(*self.args(str(path)))
        self.assertEqual(1, done.returncode)
        self.assertIn('主要原因', done.stderr)
        self.assertIn('应付总价', done.stderr)
        self.assertIn('10 次', done.stderr)

    def test_quote_budget_is_reported_when_it_truncates(self):
        done = self.run_cli(*self.args('examples/replay/mapping.json', '--max-quotes', '3'))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('试算其中 3 个', done.stdout)
        self.assertIn('跳过 7 个', done.stdout)

    def test_quote_budget_must_be_a_positive_number(self):
        done = self.run_cli(*self.args('examples/replay/mapping.json', '--max-quotes', '0'))
        self.assertNotEqual(0, done.returncode)
        self.assertIn('1-200', done.stderr)

    def test_replay_budget_reports_zero_network_calls(self):
        done = self.run_cli(*self.args('examples/replay/mapping.json', '--json'))
        self.assertEqual(0, done.returncode, done.stderr)
        payload = json.loads(done.stdout)
        self.assertEqual({'enumerated': 10, 'quoted': 10, 'skipped': 0,
                          'estimate_dropped': 0, 'failed': 0, 'requests': 0},
                         payload['request_budget'])

    def test_missing_file_is_named_instead_of_generic(self):
        done = self.run_cli(*self.args('examples/replay/absent.json'))
        self.assertEqual(1, done.returncode)
        self.assertIn('找不到文件', done.stderr)
        self.assertIn('absent.json', done.stderr)

    def test_broken_json_points_at_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'mapping.json'
            path.write_text('{"menu": {,}}', encoding='utf-8')
            done = self.run_cli(*self.args(str(path)))
        self.assertEqual(1, done.returncode)
        self.assertIn('不是有效 JSON', done.stderr)
        self.assertIn('第 1 行', done.stderr)

    def test_non_utf8_file_is_reported_as_an_encoding_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'mapping.json'
            path.write_bytes('{"menu": "汉堡"}'.encode('gbk'))
            done = self.run_cli(*self.args(str(path)))
        self.assertEqual(1, done.returncode)
        self.assertIn('UTF-8', done.stderr)


class PlannerStatsTests(unittest.TestCase):
    def test_stats_explain_truncation_instead_of_hiding_it(self):
        import adapter
        import planner
        mapping = json.loads((ROOT / 'examples/replay/mapping.json').read_text(encoding='utf-8'))
        menu = json.loads((ROOT / 'examples/replay/menu.json').read_text(encoding='utf-8'))
        items = adapter.meals(menu, mapping['menu'], 'lunch')
        stats = {}
        kept = planner.build(items, {'burger': {'min': 2, 'max': 2}}, 'lunch',
                             max_candidates=4, stats=stats)
        self.assertEqual(4, len(kept))
        self.assertEqual(10, stats['generated'])
        self.assertEqual(6, stats['skipped'])

    def test_null_maximum_is_treated_as_unbounded(self):
        import planner
        self.assertEqual({'burger': (1, 1)}, planner.bounds_of({'burger': {'min': 1, 'max': None}}))


if __name__ == '__main__':
    unittest.main()
