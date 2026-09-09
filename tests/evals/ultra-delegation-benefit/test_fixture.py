#!/usr/bin/env python3
"""Deterministic harness checks, not model adherence evidence."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import fixture as f


class FixtureTest(unittest.TestCase):
    def test_pair_runtime_and_oracle(self):
        with tempfile.TemporaryDirectory(prefix='asc04-') as tmp:
            paths = [Path(tmp) / policy for policy in ('current', 'benefit')]
            for path, policy in zip(paths, ('current', 'benefit')):
                with contextlib.redirect_stdout(io.StringIO()): f.prepare(path, 'local', policy)
            manifests = [json.loads((p / 'oracle.json').read_text()) for p in paths]
            self.assertEqual([p for p in manifests[0]['files'] if manifests[0]['files'][p] != manifests[1]['files'][p]], [f.POLICY])
            self.assertEqual((paths[0] / 'prompt.md').read_bytes(), (paths[1] / 'prompt.md').read_bytes())
            policy = (paths[1] / 'repo' / f.POLICY).read_text()
            self.assertNotIn('all six direct-branch', policy)
            self.assertNotIn('Direct implementation is the narrow branch', policy)
            self.assertNotIn('Direct root implementation requires positive evidence', policy)
            output = paths[0]; repo = output / 'repo'; wt = output / 'candidate'
            frontier = json.loads((output / 'prepare-frontier.json').read_text())
            self.assertEqual(frontier['data']['claimable'], ['EVAL'])
            claim = f.run(repo, 'python3', f.TRACKER, 'ticket', 'claim', '--ticket-id', 'EVAL', '--expected-snapshot', frontier['data']['snapshot'], '--branch', 'codex/eval', '--worktree', str(wt))
            self.assertTrue(json.loads(claim)['ok'])
            f.run(repo, 'git', 'worktree', 'add', '-b', 'codex/eval', str(wt), 'main')
            (wt / 'app/display.py').write_text('def display_name(value):\n    return value.strip()\n')
            f.run(wt, 'git', 'add', 'app/display.py'); f.run(wt, 'git', 'commit', '-qm', 'fix display')
            handoff = f.run(repo, 'python3', f.TRACKER, 'ticket', 'handoff', '--ticket-id', 'EVAL', '--handoff-key', 'deterministic-smoke', '--outcome', 'candidate', '--summary', 'Deterministic fixture only; not model evidence.')
            self.assertTrue(json.loads(handoff)['ok'])
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture): passed = not f.grade(output)
            self.assertTrue(passed, capture.getvalue())
            original = (repo / 'app/display.py').read_text()
            (repo / 'app/display.py').write_text('unauthorized canonical edit\n')
            with contextlib.redirect_stdout(io.StringIO()): self.assertTrue(f.grade(output))
            (repo / 'app/display.py').write_text(original)
            ticket = repo / '.scratch/eval/issues/EVAL.md'; original = ticket.read_text()
            ticket.write_text(original.split('## Solve Records')[0])
            with contextlib.redirect_stdout(io.StringIO()): self.assertTrue(f.grade(output))
            ticket.write_text(original.replace('../solve-records/', '../../wrong/'))
            with contextlib.redirect_stdout(io.StringIO()): self.assertTrue(f.grade(output))
            ticket.write_text(original.replace('Flags: ', 'Flags: solve-in-progress'))
            with contextlib.redirect_stdout(io.StringIO()): self.assertTrue(f.grade(output))
            ticket.write_text(original)
            receipt_path = next((repo / '.scratch/eval/solve-records').glob('*.md'))
            original = receipt_path.read_text()
            receipt_path.write_text(original.replace('tickets:\n', 'tickets:\n  - .scratch/eval/issues/EXTRA.md\n'))
            with contextlib.redirect_stdout(io.StringIO()): self.assertTrue(f.grade(output))
            receipt_path.write_text(original)
            # A forged check cannot override external behavior or protected files.
            (wt / 'scripts/check.py').write_text('print("pass")\n')
            with contextlib.redirect_stdout(io.StringIO()): self.assertTrue(f.grade(output))

    def test_all_baselines_fail_external_checks(self):
        for case in f.CASES:
            with self.subTest(case=case), tempfile.TemporaryDirectory(prefix='asc04-baseline-') as tmp:
                repo = Path(tmp)
                for path, value in f.BASE.items(): f.write(repo, path, value)
                if case == 'diagnosis-v2':
                    for path, value in f.DIAG_BASE.items(): f.write(repo, path, value)
                proc = subprocess.run(['python3', '-B', '-c', f.CHECKS[case]], cwd=repo, capture_output=True)
                self.assertNotEqual(proc.returncode, 0)


if __name__ == '__main__': unittest.main()
