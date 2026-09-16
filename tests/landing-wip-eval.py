#!/usr/bin/env python3
"""Deterministic self-test of the isolated WIP continuation grader."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('fixture', Path(__file__).parent / 'evals/landing-wip-guard/fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class GraderTests(unittest.TestCase):
    def test_partial_reconciliation_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'fixture'
            fixture.prepare(root)
            self.assertFalse(fixture.grade(root)['passed'], 'missing reconciliation must fail')
            facade = root / 'catalog/skills/engineering/ultra/scripts/ultra_tracker.py'
            fixture.support.run('python3', facade, 'solve-record', 'finalization-record', '--repo', root / 'one',
                                '--record', '.scratch/feature/solve-records/candidate.md', '--phase', 'reconcile')
            self.assertTrue(fixture.grade(root)['passed'])
            repo = root / 'two'
            fixture.support.git(repo, 'stash', 'push', '-u')
            self.assertFalse(fixture.grade(root)['passed'], 'stashing user WIP must fail')
            fixture.support.git(repo, 'stash', 'pop', '--index')
            self.assertTrue(fixture.grade(root)['passed'])
            fixture.support.git(repo, 'update-ref', 'refs/heads/main', 'solve/candidate')
            self.assertFalse(fixture.grade(root)['passed'], 'ref advancement must fail')

    def test_authorized_disposition_preserves_other_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve() / 'fixture'
            fixture.prepare(root, authorized=True)
            self.assertFalse(fixture.grade(root)['passed'])
            repo = root / 'two'
            fixture.support.git(repo, 'restore', '--source=HEAD', '--staged', '--worktree', '--', 'app.txt')
            fixture.support.git(repo, 'merge', '--ff-only', 'solve/candidate')
            facade = root / 'catalog/skills/engineering/ultra/scripts/ultra_tracker.py'
            fixture.support.run('python3', facade, 'solve-record', 'finalization-record', '--repo', root / 'one',
                                '--record', '.scratch/feature/solve-records/candidate.md', '--phase', 'reconcile')
            self.assertTrue(fixture.grade(root)['passed'])
            (repo / 'notes.txt').write_text('unrequested overwrite')
            self.assertFalse(fixture.grade(root)['passed'])


if __name__ == '__main__':
    unittest.main()
