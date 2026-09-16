#!/usr/bin/env python3
"""Approved contract amendments exercised exclusively through public CLIs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'skills/engineering/ultra/scripts/ultra_tracker.py'
spec = importlib.util.spec_from_file_location('snapshot_fixtures', ROOT / 'tests/tracker-snapshot.py')
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class Amendments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        fixtures.git(self.repo, 'init', '-q')
        fixtures.write(self.repo, 'docs/agents/ultra-tracker.md', fixtures.CONTRACT.replace('.tracker/tickets/', '.scratch/feature/issues/'))
        self.ticket = fixtures.write(self.repo, '.scratch/feature/issues/T.md',
            fixtures.ticket('T', 'review-pending', 'Publication Run: run\nSource Spec: spec.md',
                '## What to build\n\nDeletion policy.\n\n## Acceptance criteria\n\n- [ ] Allow deletion without references.'))
        self.pub('register')
        self.pub('promote')

    def cli(self, *args, ok=True, env=None):
        result = subprocess.run([sys.executable, str(CLI), *args, '--repo', str(self.repo)],
                                capture_output=True, text=True, env={**os.environ, **(env or {})})
        payload = json.loads(result.stdout)
        if ok:
            self.assertEqual(result.returncode, 0, payload)
            return payload['data']
        self.assertNotEqual(result.returncode, 0, payload)
        return payload

    def pub(self, action, *args, **kwargs):
        return self.cli('publication', action, '--run-id', 'run', '--location', '.scratch/feature/issues', *args, **kwargs)

    def observed(self):
        return next(t for t in self.cli('snapshot')['tickets'] if t['key'] == 'T')

    def request(self, identity='A1', predecessor=None, **changes):
        data = dict(id=identity, ticket='T', status='approved', approval='Human decision: forbid all deletion',
                    predecessor=predecessor, replaces={'Acceptance criteria': '- [ ] Forbid all deletion.'})
        data.update(changes)
        return fixtures.write(self.repo, f'inputs/{identity}.json', json.dumps(data))

    def apply(self, request, digest=None, **kwargs):
        current = self.observed()
        digest = digest or current['publication']['current_digest']
        self.assertTrue(digest, current['publication'])
        return self.pub('amend', '--ticket-id', 'T', '--expected-digest', digest,
                        '--amendment', str(request), **kwargs)

    def test_approved_policy_is_read_from_canonical_ticket_and_retry_converges(self):
        before = self.observed()['publication']['current_digest']
        request = self.request()
        result = self.apply(request, before)
        current = self.observed()
        self.assertEqual(current['contract']['amendment']['head'], 'A1')
        self.assertIn('Forbid all deletion.', current['contract']['effective_text'])
        self.assertNotIn('Allow deletion without references.', current['contract']['effective_text'])
        self.assertTrue(current['eligibility']['claimable'])
        self.assertEqual(self.apply(request, before)['status'], 'unchanged')
        self.assertIn('Allow deletion without references.', (self.repo / result['amendment']).read_text())

    def test_interrupted_amendment_blocks_claim_and_identical_retry_recovers(self):
        for point in ('intent', 'ticket', 'journal'):
            with self.subTest(point=point):
                before = self.observed()['publication']['current_digest']
                previous = self.observed()['contract']['amendment']['head']
                request = self.request('A-' + point, previous)
                self.apply(request, before, ok=False, env={'ULTRA_AMENDMENT_FAIL_AFTER': point})
                if point != 'journal':
                    current = self.observed()
                    self.assertFalse(current['eligibility']['claimable'])
                    self.assertIsNone(current['contract']['effective_text'])
                self.apply(request, before)
                self.assertTrue(self.observed()['eligibility']['claimable'])

    def test_completed_ticket_reopens_and_old_candidate_cannot_satisfy_new_contract(self):
        self.ticket.write_text(self.ticket.read_text().replace('Status: ready-for-agent', 'Status: completed'))
        record = fixtures.write(self.repo, '.scratch/solve-records/old.md',
            '---\nstate: open\noutcome: candidate\ntickets:\n  - .scratch/feature/issues/T.md\nhead: main\nhead_sha: ' + 'a' * 40 +
            '\n---\n\n# Old candidate\n\n## Summary\nOld policy verified.\n')
        self.apply(self.request())
        current = self.observed()
        self.assertEqual(current['state'], 'ready-for-agent')
        self.assertTrue(current['contract']['amendment']['historical_completion'])
        self.assertFalse(current['contract']['completed'])
        gate = self.cli('solve-record', 'merge-gate', '--record', '.scratch/solve-records/old.md', ok=False)
        self.assertIn('contract amendment', json.dumps(gate))

    def test_draft_is_visible_but_not_effective_and_can_be_approved(self):
        draft = json.loads(self.request().read_text())
        draft['status'] = 'draft'
        draft['approval'] = ''
        fixtures.write(self.repo, '.scratch/feature/issues/.ultra-publications/amendments/run/A1.json', json.dumps(draft))
        current = self.observed()
        self.assertTrue(current['eligibility']['claimable'])
        self.assertEqual(current['contract']['amendment']['drafts'][0]['id'], 'A1')
        self.assertIn('Allow deletion without references.', current['contract']['effective_text'])
        self.apply(self.request())
        self.assertEqual(self.observed()['contract']['amendment']['head'], 'A1')

    def claim(self, snapshot=None, **kwargs):
        snapshot = snapshot or self.cli('ticket', 'frontier')['snapshot']
        return self.cli('ticket', 'claim', '--ticket-id', 'T', '--expected-snapshot', snapshot,
                        '--branch', 'solve/T', '--worktree', str(self.repo), **kwargs)

    def test_dependency_revision_stale_snapshot_and_explicit_successor(self):
        fixtures.write(self.repo, '.scratch/feature/issues/D.md', fixtures.ticket('D', 'review-pending', 'Publication Run: dependency\nSource Spec: spec.md'))
        self.cli('publication', 'register', '--run-id', 'dependency', '--location', '.scratch/feature/issues')
        self.cli('publication', 'promote', '--run-id', 'dependency', '--location', '.scratch/feature/issues')
        before = self.cli('ticket', 'frontier')['snapshot']
        self.apply(self.request(replaces={'Blocked by': '- D'}))
        current = self.observed()
        self.assertFalse(current['eligibility']['claimable'])
        self.assertEqual(current['blockers'][0]['ticket_key'], 'D')
        self.assertFalse(current['blockers'][0]['satisfied'])
        self.claim(before, ok=False)
        self.apply(self.request('A2', 'A1', replaces={'Blocked by': '', 'Acceptance criteria': '- [ ] Forbid all deletion.'}))
        self.assertTrue(self.observed()['eligibility']['claimable'])
        self.assertEqual([a['id'] for a in self.observed()['contract']['amendment']['chain']], ['A1', 'A2'])
        self.apply(self.request('fork', 'A1'), ok=False)
        self.apply(self.request('cycle', 'cycle'), ok=False)
        self.apply(self.request('broken', 'missing'), ok=False)
        self.assertEqual(self.observed()['contract']['amendment']['head'], 'A2')

    def test_active_attempt_refuses_without_mutation(self):
        self.claim()
        before = self.ticket.read_bytes()
        self.apply(self.request(), ok=False)
        self.assertEqual(self.ticket.read_bytes(), before)
        self.assertFalse((self.repo / '.scratch/feature/issues/.ultra-publications/amendments').exists())

    def test_tampered_or_missing_approved_file_blocks_read_and_claim(self):
        result = self.apply(self.request())
        path = self.repo / result['amendment']
        good = path.read_text()
        for corrupt in (good.replace('"approved"', '"draft"'), good.replace('"predecessor": null', '"predecessor": "A1"'), None):
            with self.subTest(corrupt=corrupt):
                if corrupt is None:
                    path.unlink()
                else:
                    path.write_text(corrupt)
                current = self.observed()
                self.assertFalse(current['eligibility']['claimable'])
                self.assertIsNone(current['contract']['effective_text'])
                self.claim(ok=False)
                path.write_text(good)

    def test_new_candidate_binds_amended_contract_and_old_key_cannot_be_reused(self):
        fixtures.git(self.repo, 'config', 'user.name', 'Fixture')
        fixtures.git(self.repo, 'config', 'user.email', 'fixture@example.test')
        fixtures.write(self.repo, '.gitignore', '.tracker/\ninputs/\n.scratch/\n')
        fixtures.git(self.repo, 'add', '.')
        fixtures.git(self.repo, 'commit', '-qm', 'baseline')
        fixtures.git(self.repo, 'checkout', '-qb', 'solve/T')
        self.apply(self.request())
        self.claim()
        first = self.cli('ticket', 'handoff', '--ticket-id', 'T', '--handoff-key', 'new-contract',
                         '--outcome', 'candidate', '--summary', 'All deletion forbidden and verified.')
        self.assertEqual(self.observed()['state'], 'completed')
        receipt = first['receipt']
        gate = self.cli('solve-record', 'merge-gate', '--record', receipt, ok=False)
        self.assertNotIn('contract amendment', json.dumps(gate))
        self.apply(self.request('A2', 'A1', replaces={'Acceptance criteria': '- [ ] Forbid deletion, including archived records.'}))
        self.cli('ticket', 'handoff', '--ticket-id', 'T', '--handoff-key', 'new-contract',
                 '--outcome', 'candidate', '--summary', 'Old evidence.', ok=False)
        gate = self.cli('solve-record', 'merge-gate', '--record', receipt, ok=False)
        self.assertIn('contract amendment', json.dumps(gate))

    def test_tickets_file_changes_only_selected_ticket(self):
        path = self.repo / '.scratch/feature/tickets.md'
        original = self.ticket.read_text().replace('ready-for-agent', 'review-pending')
        self.ticket.unlink()
        path.write_text('<!-- ultra-ticket:begin id=T -->\n' + original +
                        '<!-- ultra-ticket:end -->\n<!-- ultra-ticket:begin id=D -->\n' +
                        fixtures.ticket('D', 'review-pending', 'Publication Run: run\nSource Spec: spec.md') +
                        '<!-- ultra-ticket:end -->\n')
        contract = self.repo / 'docs/agents/ultra-tracker.md'
        contract.write_text(contract.read_text().replace('file-per-ticket', 'tickets-file').replace(
            '.scratch/feature/issues/<ticket-file>.md', '.scratch/feature/tickets.md'))
        def command(action, *args, **kwargs):
            return self.cli('publication', action, '--run-id', 'run', '--location', '.scratch/feature/tickets.md', *args, **kwargs)
        command('register')
        command('promote')
        before = path.read_text().split('<!-- ultra-ticket:begin id=D -->')[1]
        command('amend', '--ticket-id', 'T', '--expected-digest', self.observed()['publication']['current_digest'],
                '--amendment', str(self.request(replaces={'Blocked by': '- D'})))
        self.assertEqual(path.read_text().split('<!-- ultra-ticket:begin id=D -->')[1], before)
        self.assertEqual(self.observed()['contract']['amendment']['head'], 'A1')
        self.assertFalse(self.observed()['eligibility']['claimable'])

    def test_integrity_repair_and_amendment_preserve_ordered_publication_history(self):
        self.pub('terminal-repair', '--ticket-id', 'T', '--expected-digest', self.observed()['publication']['current_digest'],
                 '--repair-type', 'ticket-identity', '--old-value', 'T', '--new-value', 'T', '--reason', 'Identity checked')
        self.apply(self.request())
        inspect = self.pub('inspect')
        self.assertEqual(len(inspect['amendments']), 1)
        self.assertNotEqual(inspect['original_body_digests']['T'], inspect['body_digests']['T'])
        before = self.ticket.read_bytes()
        self.pub('terminal-repair', '--ticket-id', 'T', '--expected-digest', self.observed()['publication']['current_digest'],
                 '--repair-type', 'ticket-identity', '--old-value', 'T', '--new-value', 'RENAMED', '--reason', 'Cannot erase history', ok=False)
        self.assertEqual(self.ticket.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
