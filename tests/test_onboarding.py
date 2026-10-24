"""Onboarding: habits must come from the user, never from a bundled example."""
from contextlib import redirect_stdout
import io
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


class FakeStdin:
    def isatty(self):
        return True


def run_cli(*args):
    return subprocess.run([sys.executable, str(ROOT / 'habit.py'), *args],
                          capture_output=True, text=True, encoding='utf-8', cwd=ROOT)


def plan_args(profile, *extra):
    return ['plan', '--profile', str(profile),
            '--mapping', 'examples/replay/mapping.json',
            '--menu', 'examples/replay/menu.json',
            '--prices', 'examples/replay/prices.json',
            '--meal', 'lunch', '--store', 'MCD-DEMO-001', *extra]


class InitCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'private' / 'profile.json'

    def test_flags_write_a_user_profile(self):
        done = run_cli('init', '--out', str(self.path), '--burger', '2',
                       '--drink', 'none', '--budget', '25', '--tags', 'chicken')
        self.assertEqual(0, done.returncode, done.stderr)
        profile = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual('user', profile['source'])
        self.assertEqual({'burger': {'min': 2, 'max': 2}, 'drink': {'max': 0}},
                         profile['category_limits'])
        self.assertEqual(2500, profile['default_budget_cents'])
        self.assertEqual(['chicken'], profile['preferred_tags'])
        self.assertTrue(profile['created_at'])

    def test_drink_one_is_recorded_as_a_minimum(self):
        run_cli('init', '--out', str(self.path), '--burger', '1',
                '--drink', 'one', '--budget', '30')
        profile = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual({'min': 1, 'max': 1}, profile['category_limits']['drink'])

    def test_existing_profile_is_not_overwritten_without_force(self):
        run_cli('init', '--out', str(self.path), '--burger', '2', '--drink', 'none', '--budget', '25')
        done = run_cli('init', '--out', str(self.path), '--burger', '1',
                       '--drink', 'one', '--budget', '30')
        self.assertEqual(1, done.returncode)
        self.assertIn('已存在', done.stderr)
        self.assertEqual(2, json.loads(self.path.read_text(encoding='utf-8'))
                         ['category_limits']['burger']['min'])

    def test_force_overwrites(self):
        run_cli('init', '--out', str(self.path), '--burger', '2', '--drink', 'none', '--budget', '25')
        done = run_cli('init', '--out', str(self.path), '--burger', '1',
                       '--drink', 'one', '--budget', '30', '--force')
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertEqual(1, json.loads(self.path.read_text(encoding='utf-8'))
                         ['category_limits']['burger']['min'])

    def test_non_interactive_run_without_flags_is_refused(self):
        done = run_cli('init', '--out', str(self.path))
        self.assertEqual(1, done.returncode)
        self.assertIn('非交互环境', done.stderr)
        self.assertFalse(self.path.exists())

    def test_avoid_tags_ask_for_a_verified_scope_later(self):
        done = run_cli('init', '--out', str(self.path), '--burger', '2',
                       '--drink', 'none', '--budget', '25', '--avoid', 'peanut')
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('--checked-avoid', done.stdout)
        blocked = run_cli(*plan_args(self.path))
        self.assertEqual(1, blocked.returncode)
        self.assertIn('忌口', blocked.stderr)


class InteractiveInitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'profile.json'

    def run_init(self, answers):
        args = SimpleNamespace(out=str(self.path), category='burger', burger=None,
                               drink=None, budget=None, tags=None, avoid=None, force=False)
        buffer = io.StringIO()
        with patch('sys.stdin', FakeStdin()), patch('builtins.input', side_effect=answers), \
                redirect_stdout(buffer):
            code = cli.init_run(args)
        self.stdout = buffer.getvalue()
        return code

    def test_blank_answers_accept_the_shown_defaults(self):
        self.assertEqual(0, self.run_init(['', '', '', '', '']))
        profile = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual({'burger': {'min': 2, 'max': 2}, 'drink': {'max': 0}},
                         profile['category_limits'])
        self.assertEqual(3000, profile['default_budget_cents'])
        self.assertEqual('user', profile['source'])

    def test_typed_answers_win_over_defaults(self):
        self.run_init(['1', 'y', '45', 'beef', ''])
        profile = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual({'burger': {'min': 1, 'max': 1}, 'drink': {'min': 1, 'max': 1}},
                         profile['category_limits'])
        self.assertEqual(4500, profile['default_budget_cents'])
        self.assertEqual(['beef'], profile['preferred_tags'])

    def test_invalid_count_is_rejected_with_a_readable_message(self):
        with self.assertRaises(ValueError) as error:
            self.run_init(['0'])
        self.assertIn('取值范围', str(error.exception))


class HabitGateTests(unittest.TestCase):
    def test_recorded_budget_is_used_when_the_flag_is_omitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / 'p.json'
            run_cli('init', '--out', str(profile), '--burger', '2',
                    '--drink', 'none', '--budget', '25')
            done = run_cli(*plan_args(profile))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('预算：¥25.00', done.stdout)
        self.assertNotIn('示例档案', done.stderr)

    def test_example_profile_is_flagged_but_still_demoable(self):
        done = run_cli(*plan_args('examples/profile.json', '--budget', '25'))
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertIn('示例档案', done.stderr)
        self.assertIn('不是你的习惯', done.stderr)

    def test_example_profile_without_budget_cannot_guess_one(self):
        done = run_cli(*plan_args('examples/profile.json'))
        self.assertEqual(1, done.returncode)
        self.assertIn('--budget', done.stderr)
        self.assertEqual('', done.stdout)


if __name__ == '__main__':
    unittest.main()
