#!/usr/bin/env python3
"""Behavior fixtures for Ultra's public read-only change detection CLI."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).resolve().parents[1] / 'skills/engineering/ultra/scripts/detect_owned_changes.py'


class Changes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo'
        self.repo.mkdir()
        self.state = Path(self.tmp.name) / 'baseline.json'
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'user.name', 'Fixture')
        self.write('tracked.py', 'original\n')
        self.git('add', 'tracked.py')
        self.git('commit', '-qm', 'baseline')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args])

    def write(self, name, value):
        (self.repo / name).write_text(value)

    def cli(self, command, *args, ok=True):
        result = subprocess.run([sys.executable, str(HELPER), command,
                                 '--repo', str(self.repo), '--snapshot', str(self.state), *args],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_clean_and_untracked_review_selection(self):
        self.write('user notes.txt', 'private work\n')
        self.cli('snapshot')
        clean = self.cli('detect')
        self.assertEqual(clean['status'], 'clean')
        self.assertFalse(clean['review_required'])
        self.write('new implementation.py', 'answer = 42\n')
        pending = self.cli('detect')
        self.assertEqual(pending['status'], 'needs-ownership')
        self.assertEqual(pending['unclassified_untracked'], ['new implementation.py'])
        selected = self.cli('detect', '--owned-untracked', 'new implementation.py')
        self.assertTrue(selected['review_required'])
        self.assertEqual(selected['owned_untracked'], ['new implementation.py'])
        self.assertEqual(selected['preexisting_untracked'], ['user notes.txt'])
        self.assertEqual(self.git('diff', '--cached'), b'')
        self.assertEqual((self.repo / 'user notes.txt').read_text(), 'private work\n')

    def test_all_change_kinds_special_paths_and_ignored_cache(self):
        self.write('.gitignore', 'cache/\n')
        self.git('add', '.gitignore')
        self.git('commit', '-qm', 'ignore cache')
        self.cli('snapshot')
        (self.repo / 'cache').mkdir()
        self.write('cache/generated', 'ignored')
        self.assertEqual(self.cli('detect')['status'], 'clean')
        self.write('committed.py', 'committed')
        self.git('add', 'committed.py')
        self.git('commit', '-qm', 'implementation')
        self.assertEqual(self.cli('detect')['committed'], ['committed.py'])
        self.write('staged.py', 'staged')
        self.git('add', 'staged.py')
        self.assertEqual(self.cli('detect')['staged'], ['staged.py'])
        self.write('tracked.py', 'unstaged')
        self.assertEqual(self.cli('detect')['unstaged'], ['tracked.py'])
        special = '空 格\nnew.py'
        self.write(special, 'special')
        report = self.cli('detect', '--owned-untracked', special)
        self.assertEqual(report['status'], 'review')
        self.assertEqual(report['tracked_paths'], ['committed.py', 'staged.py', 'tracked.py'])
        self.assertEqual(report['owned_untracked'], [special])
        self.assertEqual(self.cli('detect', '--exclude-untracked', special)['owned_untracked'], [])

    def test_preserve_user_provenance_after_staging_and_commit(self):
        self.write('user.txt', 'user')
        self.write('tracked.py', 'existing dirty')
        self.cli('snapshot')
        self.git('add', 'user.txt')
        report = self.cli('detect')
        self.assertNotIn('user.txt', report['tracked_paths'])
        self.assertEqual(report['starting_dirty'], ['tracked.py'])
        self.git('commit', '-qm', 'user file staged by target')
        self.assertNotIn('user.txt', self.cli('detect')['tracked_paths'])
        self.write('user.txt', 'modified user content')
        report = self.cli('detect')
        self.assertEqual(report['status'], 'needs-ownership')
        self.assertEqual(report['changed_preexisting_untracked'], ['user.txt'])
        self.cli('detect', '--owned-untracked', 'user.txt', ok=False)

    def test_starting_index_change_survives_worktree_cancellation(self):
        self.write('tracked.py', 'staged user work')
        self.git('add', 'tracked.py')
        self.write('tracked.py', 'original\n')
        self.cli('snapshot')
        self.assertEqual(self.cli('detect')['starting_dirty'], ['tracked.py'])

    def test_repository_root_whitespace_is_preserved(self):
        renamed = self.repo.with_name(' repo 空格\n')
        self.repo.rename(renamed)
        self.repo = renamed
        self.cli('snapshot')
        self.assertEqual(self.cli('detect')['status'], 'clean')

    def test_bad_baseline_and_git_failures_are_errors(self):
        self.assertEqual(self.cli('detect', ok=False)['status'], 'error')
        self.cli('snapshot')
        self.assertEqual(self.cli('snapshot', ok=False)['status'], 'error')
        state = json.loads(self.state.read_text())
        for base in ['', 'missing-commit', 'HEAD', '0' * 40]:
            state['base_sha'] = base
            self.state.write_text(json.dumps(state))
            self.assertEqual(self.cli('detect', ok=False)['status'], 'error')
        self.state.unlink()
        self.cli('snapshot')
        (self.repo / '.git').rename(self.repo / '.git-unavailable')
        self.assertEqual(self.cli('detect', ok=False)['status'], 'error')


if __name__ == '__main__':
    unittest.main()
