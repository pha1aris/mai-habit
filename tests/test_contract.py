"""SKILL.md makes promises a user can check. Test those, not the internals.

Two defects found while walking the real user path are pinned here:

* the read-only whitelist used to be checked *after* the token, so refusing a
  write tool reported "set MCD_MCP_TOKEN" instead of the real reason;
* an unreachable budget reported "no candidates" without saying what the floor
  actually was, which reads as "your habits are impossible".
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/mai-habit/scripts'))
import main as cli
import mcp_client


def run_cli(*args, env=None):
    return subprocess.run([sys.executable, str(ROOT / 'habit.py'), *args],
                          capture_output=True, text=True, encoding='utf-8',
                          cwd=ROOT, env=env)


def replay_args(profile, *extra):
    return ['plan', '--profile', str(profile),
            '--mapping', 'examples/replay/mapping.json',
            '--menu', 'examples/replay/menu.json',
            '--prices', 'examples/replay/prices.json',
            '--meal', 'lunch', '--store', 'MCD-DEMO-001', *extra]


class ReadOnlyPolicyTests(unittest.TestCase):
    """The whitelist is policy: it must not depend on having a credential."""

    def bare_env(self):
        import os
        env = {k: v for k, v in os.environ.items() if k != 'MCD_MCP_TOKEN'}
        return env

    def test_write_tool_is_refused_without_a_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = run_cli('mcp-call', '--tool', 'create-order',
                           '--args', 'examples/replay/mapping.json',
                           '--out', str(Path(tmp) / 'r.json'), env=self.bare_env())
        self.assertNotEqual(0, done.returncode)
        # The reason must be the policy, not the missing credential.
        self.assertIn('不在查询与试算范围内', done.stderr)
        self.assertNotIn('MCD_MCP_TOKEN', done.stderr)

    def test_allowed_tool_still_reports_the_missing_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            done = run_cli('mcp-call', '--tool', 'query-meals',
                           '--args', 'examples/replay/mapping.json',
                           '--out', str(Path(tmp) / 'r.json'), env=self.bare_env())
        self.assertNotEqual(0, done.returncode)
        # The whitelist must not mask a genuine credential problem.
        self.assertIn('MCD_MCP_TOKEN', done.stderr)

    def test_policy_predicate_is_independent_of_any_client(self):
        mcp_client.ensure_read_only('query-meals')
        with self.assertRaises(mcp_client.MCPError) as caught:
            mcp_client.ensure_read_only('auto-bind-coupons')
        self.assertIn('auto-bind-coupons', str(caught.exception))


class UnreachableBudgetTests(unittest.TestCase):
    """An impossible budget must say what would work, without widening habits."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.profile = self.write_profile({'burger': {'min': 2, 'max': 2},
                                           'drink': {'max': 0}})

    def write_profile(self, limits):
        path = Path(self.tmp.name) / 'profile.json'
        path.write_text(json.dumps({'source': 'user', 'preferred_tags': [],
                                    'category_limits': limits,
                                    'default_budget_cents': 3000,
                                    'feedback': {}}), encoding='utf-8')
        return path

    def plan(self, budget):
        args = SimpleNamespace(
            profile=str(self.profile), mapping='examples/replay/mapping.json',
            menu='examples/replay/menu.json', prices='examples/replay/prices.json',
            meal='lunch', budget=str(budget), store='MCD-DEMO-001',
            checked_avoid=None, max_quotes=40, out=None, json=False)
        with patch('builtins.print'):
            return cli.plan_run(args)

    def test_error_names_the_floor_and_the_number_to_relax(self):
        with self.assertRaises(ValueError) as caught:
            self.plan(8)
        message = str(caught.exception)
        self.assertIn('19.00', message)      # the real floor, in yuan
        self.assertIn('放宽到', message)      # an actionable instruction
        self.assertIn('吉士汉堡×2', message)  # which combination that price buys

    def test_the_floor_never_widens_the_stated_habits(self):
        # Re-enumerating without a budget must still honour composition rules:
        # no drink may appear just because the budget was dropped.
        items = self.plan(28)[0]
        self.assertTrue(items['recommendations'])
        with self.assertRaises(ValueError):
            self.plan(8)
        floor = cli.planner.build(
            cli.adapter.meals(cli.read(ROOT / 'examples/replay/menu.json'),
                              cli.read(ROOT / 'examples/replay/mapping.json')['menu'],
                              'lunch'),
            {'burger': {'min': 2, 'max': 2}, 'drink': {'max': 0}},
            'lunch', None, max_candidates=1)
        self.assertEqual(['burger'], [i['category'] for i in floor[0]['items']])
        self.assertEqual(2, floor[0]['items'][0]['quantity'])

    def test_a_sufficient_budget_returns_recommendations(self):
        result = self.plan(28)[0]
        self.assertTrue(result['recommendations'])
        self.assertLessEqual(len(result['recommendations']), 3)


class ReportingContractTests(unittest.TestCase):
    """Numbers the skill promises to keep in the summary must be present."""

    def test_skipped_quotes_are_disclosed(self):
        done = run_cli(*replay_args('examples/profile.demo.json',
                                    '--budget', '28', '--max-quotes', '3'))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('跳过 7 个', done.stdout)

    def test_demo_data_is_labelled_as_fiction(self):
        done = run_cli(*replay_args('examples/profile.demo.json', '--budget', '28'))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('演示数据', done.stdout)
        self.assertIn('非真实', done.stdout)


if __name__ == '__main__':
    unittest.main()
