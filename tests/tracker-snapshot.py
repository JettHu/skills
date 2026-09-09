#!/usr/bin/env python3
"""Highest-interface deterministic Tracker Snapshot fixtures."""
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/engineering/ultra/scripts'
sys.path.insert(0, str(SCRIPTS))
import tracker_snapshot as query
import local_ticket_frontier as frontier
import local_ticket_publication as publication

CONTRACT = '''Frontier adapter: bundled-local-markdown-v1
Publication strategy: local-review-pending
Local Ticket representation: file-per-ticket
Local Ticket path: .tracker/tickets/<ticket-file>.md
Cancellation policy: retain-until-explicit-cleanup
Ticket ID field aliases: Ticket ID, ID
Publication Run field aliases: Publication Run
Source field aliases: Source Spec, Parent
Ticket state fields: Status, State
Ticket state values: review-pending, ready-for-agent, completed, ready-for-human, needs-info
Ready state: ready-for-agent
Completed state: completed
Human-blocked states: ready-for-human, needs-info
Blocker metadata fields: Blocked By, Blockers
Blocker body heading: Blocked by
Claim field: Flags
Claim field aliases: Flags, Labels
Claim value: solve-in-progress
Solve branch field: Solve Branch
Solve branch field aliases: Solve Branch, Branch
Solve worktree field: Solve Worktree
Solve worktree field aliases: Solve Worktree, Worktree
'''


def write(repo, path, text):
    target = repo / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)
    return target


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE, text=True).strip()


def ticket(identity, state='ready-for-agent', extra='', body=''):
    return f'Status: {state}\nTicket ID: {identity}\n{extra}\n# Ticket {identity}\n{body}\n'


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='snapshot-')
        self.repo = Path(self.tmp.name).resolve() / 'repo'; self.repo.mkdir()
        git(self.repo, 'init', '-q', '-b', 'main'); git(self.repo, 'config', 'user.name', 'Fixture'); git(self.repo, 'config', 'user.email', 'snapshot@example.invalid')
        write(self.repo, '.gitignore', '.scratch/\n.tracker/\n')
        write(self.repo, 'docs/agents/ultra-tracker.md', CONTRACT)
        git(self.repo, 'add', '.'); git(self.repo, 'commit', '-qm', 'baseline')
        self.initial = git(self.repo, 'rev-parse', 'HEAD')

    def tearDown(self): self.tmp.cleanup()

    def add(self, identity, **kw): return write(self.repo, f'.tracker/tickets/{identity}.md', ticket(identity, **kw))

    def snapshot(self): return query.snapshot(self.repo)

    def assert_fatal(self, code=None):
        with self.assertRaises(query.SnapshotError) as caught: self.snapshot()
        if code: self.assertEqual(caught.exception.code, code)

    def test_empty_full_readonly_and_frontier_reuse(self):
        self.assertEqual(self.snapshot()['summary']['ticket_count'], 0)
        (self.repo / '.gitignore').write_text('.scratch/\n')
        self.add('A'); self.add('B', body='## Blocked by\n- A')
        self.add('C', state='completed')
        before = {str(p): p.read_bytes() for p in self.repo.rglob('*') if p.is_file() and '.git' not in p.parts}
        first = self.snapshot(); second = self.snapshot()
        self.assertEqual(first, second)
        self.assertEqual(first['summary']['claimable_count'], 1)
        actual, _, _, _ = frontier.frontier(self.repo, [])
        self.assertEqual(actual['claimable'], [e['key'] for e in first['tickets'] if e['eligibility']['claimable']])
        self.assertFalse(first['tickets'][1]['blockers'][0]['satisfied'])
        after = {str(p): p.read_bytes() for p in self.repo.rglob('*') if p.is_file() and '.git' not in p.parts}
        self.assertEqual(before, after)
        self.assertEqual(git(self.repo, 'rev-parse', 'HEAD'), self.initial)
        self.assertNotIn('buckets', json.dumps(first)); self.assertNotIn('command', json.dumps(first))

    def test_malformed_isolation_and_reserved_identity(self):
        self.add('A'); bad = self.add('B', state='unknown')
        snapshot = self.snapshot()
        self.assertEqual(snapshot['summary']['ticket_count'], 2)
        self.assertEqual(snapshot['summary']['claimable_count'], 1)
        self.assertTrue(any(e['locator'].endswith('B.md') and not e['eligibility']['claimable'] for e in snapshot['tickets']))
        bad.write_text(ticket('A', state='unknown'))
        self.assert_fatal('ambiguous-identity')

    def test_metadata_scope_aliases_and_block_lists(self):
        config = self.repo / 'docs/agents/ultra-tracker.md'
        config.write_text(CONTRACT.replace('Ticket ID field aliases: Ticket ID, ID', 'Ticket ID field aliases: Ticket ID, ID, Work ID'))
        self.add('A', body='Example:\n```\nID: Example\n```')
        write(self.repo, '.tracker/tickets/B.md', '---\nstatus: ready-for-agent\nWork ID: B\nflags:\n  - solve-in-progress\nsolve_records:\n  - ../receipts/missing.md\n---\n# Claimed list\n')
        data = self.snapshot(); b = next(t for t in data['tickets'] if t['key'] == 'B')
        self.assertTrue(b['claim']['active']); self.assertFalse(b['eligibility']['claimable'])
        self.assertEqual(b['receipt_references'], ['../receipts/missing.md'])
        write(self.repo, '.tracker/tickets/C.md', 'Status: unknown\nWork ID: B\n\n# Bad duplicate\n')
        self.assert_fatal('ambiguous-identity')

    def test_sections_malformed_isolation_and_missing_identity(self):
        write(self.repo, 'docs/agents/ultra-tracker.md', CONTRACT.replace('file-per-ticket', 'tickets-file').replace('.tracker/tickets/<ticket-file>.md', '.tracker/tickets.md'))
        write(self.repo, '.tracker/tickets.md', '<!-- ultra-ticket:begin id=A -->\n'+ticket('A', state='unknown')+'<!-- ultra-ticket:end -->\n<!-- ultra-ticket:begin id=B -->\n'+ticket('B')+'<!-- ultra-ticket:end -->\n')
        data = self.snapshot(); self.assertEqual(data['summary']['claimable_count'], 1)
        self.assertTrue(any(e['key'] == 'B' for e in data['tickets']))
        write(self.repo, 'docs/agents/ultra-tracker.md', CONTRACT)
        write(self.repo, '.tracker/tickets/legacy.md', 'Status: ready-for-agent\n\n# Legacy\n')
        self.assertEqual(self.snapshot()['summary']['claimable_count'], 0)

    def test_publication_outside_scratch_and_fingerprint(self):
        self.add('A', state='review-pending', extra='Publication Run: run\nSource Spec: docs/spec.md')
        location = '.tracker/tickets'
        for action in ('register', 'promote'):
            subprocess.run([sys.executable, str(SCRIPTS/'local_ticket_publication.py'), action, '--repo', str(self.repo), '--representation', 'file-per-ticket', '--location', location, '--run-id', 'run'], check=True, stdout=subprocess.DEVNULL)
        before = self.snapshot(); self.assertEqual(before['summary']['claimable_count'], 1)
        journal = self.repo / location / '.ultra-publications/run.json'
        data = json.loads(journal.read_text()); data['phase'] = 'review-pending'; journal.write_text(json.dumps(data))
        after = self.snapshot(); self.assertNotEqual(before['source_fingerprint'], after['source_fingerprint'])
        self.assertEqual(after['summary']['claimable_count'], 0)

    def test_path_escape_and_explicit_canonical_repo(self):
        outside = Path(self.tmp.name).resolve() / 'outside'; outside.mkdir()
        (self.repo / '.tracker').symlink_to(outside, target_is_directory=True)
        write(outside, 'tickets/A.md', ticket('A'))
        self.assert_fatal('path-escape')
        (self.repo / '.tracker').unlink()
        wt = Path(self.tmp.name).resolve() / 'wt'; git(self.repo, 'worktree', 'add', '-b', 'candidate', str(wt))
        (wt / '.scratch').symlink_to(self.repo / '.scratch', target_is_directory=True)
        with self.assertRaises(query.SnapshotError): query.snapshot(wt)
        self.assertEqual(self.snapshot()['repository']['root'], str(self.repo))

    def test_lock_timeout_and_uncoordinated_source_churn(self):
        self.add('A')
        with frontier.frontier_lock(self.repo):
            started = time.monotonic(); self.assert_fatal('observation-busy')
            self.assertLess(time.monotonic()-started, 2)
        with publication.mutation_lock(self.repo / '.tracker/tickets', 'file-per-ticket'):
            self.assert_fatal('observation-busy')
        original = query._observe
        def changing(*args):
            result = original(*args)
            with (self.repo / '.tracker/tickets/A.md').open('a') as stream: stream.write('churn\n')
            return result
        with patch.object(query, '_observe', changing): self.assert_fatal('incoherent-read')

    def test_optional_git_incomplete_and_visible_html(self):
        original = query.subprocess.run
        def unavailable(args, **kw):
            if args[0] == 'git' and any(v in args for v in ('for-each-ref', 'worktree')):
                raise FileNotFoundError('injected Git observation unavailable <unsafe>')
            return original(args, **kw)
        with patch.object(query.subprocess, 'run', unavailable):
            data = self.snapshot(); self.assertTrue(data['summary']['incomplete'])
            spec = importlib.util.spec_from_file_location('board', ROOT/'skills/in-progress/maintainer-board/scripts/maintainer-board.py'); board = importlib.util.module_from_spec(spec); spec.loader.exec_module(board)
            html = board.render_html(board.build_snapshot(self.repo))
            self.assertIn('Snapshot incomplete', html); self.assertIn('&lt;unsafe&gt;', html); self.assertNotIn('<unsafe>', html)

    def test_all_receipts_git_drift_and_fingerprint(self):
        # Malformed historical receipts remain individually visible beyond dashboard's ten-card limit.
        for index in range(12): write(self.repo, f'.scratch/history/solve-records/{index}.md', f'---\nid: {index}\nstate: open\n---\n# Legacy {index}\n')
        first = self.snapshot(); self.assertEqual(first['summary']['receipt_count'], 12)
        git(self.repo, 'branch', 'later'); second = self.snapshot()
        self.assertNotEqual(first['source_fingerprint'], second['source_fingerprint'])
        self.assertEqual(first['summary']['receipt_count'], second['summary']['receipt_count'])
        write(self.repo, 'changed.txt', 'dirty\n'); third = self.snapshot()
        self.assertNotEqual(second['source_fingerprint'], third['source_fingerprint'])

    def test_compact_candidate_and_interrupted_handoff(self):
        self.add('A')
        read, _, _, _ = frontier.frontier(self.repo, [])
        wt = Path(self.tmp.name).resolve() / 'candidate'
        cmd = [sys.executable, str(SCRIPTS / 'ultra_tracker.py')]
        subprocess.run(cmd + ['ticket', 'claim', '--repo', str(self.repo), '--ticket-id', 'A', '--expected-snapshot', read['snapshot'], '--branch', 'candidate', '--worktree', str(wt)], check=True, stdout=subprocess.DEVNULL)
        git(self.repo, 'worktree', 'add', '-b', 'candidate', str(wt))
        write(wt, 'result.txt', 'done\n'); git(wt, 'add', '.'); git(wt, 'commit', '-qm', 'candidate')
        subprocess.run(cmd + ['ticket', 'handoff', '--repo', str(self.repo), '--ticket-id', 'A', '--handoff-key', 'snapshot-fixture', '--outcome', 'candidate', '--summary', 'Fixture candidate complete'], check=True, stdout=subprocess.DEVNULL)
        data = self.snapshot()
        self.assertEqual(data['tickets'][0]['state'], 'completed')
        self.assertEqual(data['receipts'][0]['handoff_consistency']['status'], 'consistent')
        self.assertEqual(data['tickets'][0]['receipt_keys'], [data['receipts'][0]['key']])
        path = self.repo / '.tracker/tickets/A.md'; path.write_text(path.read_text().replace('Status: completed', 'Status: ready-for-agent'))
        interrupted = self.snapshot()
        self.assertTrue(interrupted['summary']['incomplete'])
        self.assertEqual(interrupted['receipts'][0]['handoff_consistency']['status'], 'inconsistent')
        shutil.rmtree(self.repo / '.tracker/tickets')
        missing = self.snapshot()
        self.assertEqual(missing['summary']['receipt_count'], 1)
        self.assertTrue(any(d['code'] == 'unresolved-ticket' for d in missing['receipts'][0]['diagnostics']))

    def test_installed_siblings_and_timeout_envelope(self):
        skills = Path(self.tmp.name).resolve() / 'installed'
        for name, source in [('ultra', ROOT / 'skills/engineering/ultra'), ('solve-records', ROOT / 'skills/engineering/solve-records'), ('maintainer-board', ROOT / 'skills/in-progress/maintainer-board')]:
            shutil.copytree(source, skills / name)
        self.add('A')
        proc = subprocess.run([sys.executable, str(skills / 'maintainer-board/scripts/maintainer-board.py'), '--repo', str(self.repo), '--json'], text=True, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['issues']['count'], 1)
        wt = Path(self.tmp.name).resolve() / 'wt'; git(self.repo, 'worktree', 'add', '-b', 'timeout', str(wt))
        with patch.object(frontier, 'git_lock_path', side_effect=subprocess.TimeoutExpired('git', 0.5)):
            with self.assertRaises(query.SnapshotError): query.snapshot(wt)

    def test_structured_cli_missing_helper(self):
        catalog = Path(self.tmp.name) / 'copy'; shutil.copytree(SCRIPTS, catalog)
        (catalog / 'local_ticket_frontier.py').unlink()
        proc = subprocess.run([sys.executable, str(catalog/'ultra_tracker.py'), 'snapshot', '--repo', str(self.repo)], text=True, capture_output=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)['error']['code'], 'helper-unavailable')


if __name__ == '__main__': unittest.main()
