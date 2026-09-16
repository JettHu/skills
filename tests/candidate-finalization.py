#!/usr/bin/env python3
"""Public facade/Git integration fixtures for canonical candidate finalization."""
import json
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FACADE = ROOT / 'skills/engineering/ultra/scripts/ultra_tracker.py'
HELPER = ROOT / 'skills/engineering/solve-records/scripts/solve-records.py'


def run(*args, check=True, env=None):
    p = subprocess.run([str(x) for x in args], text=True, capture_output=True, env=env)
    if check and p.returncode:
        raise AssertionError(p.stdout + p.stderr)
    return p


def git(repo, *args):
    return run('git', '-C', repo, *args).stdout.strip()


def fixture(root, name='one'):
    repo = root / name
    repo.mkdir()
    git(repo, 'init', '-qb', 'main')
    git(repo, 'config', 'user.name', 'Fixture')
    git(repo, 'config', 'user.email', 'fixture@example.test')
    (repo / '.gitignore').write_text('.scratch/\n')
    (repo / 'app.txt').write_text('base\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'base')
    base = git(repo, 'rev-parse', 'HEAD')
    wt = root / (name + '-candidate')
    git(repo, 'worktree', 'add', '-qb', 'solve/candidate', wt)
    (wt / 'app.txt').write_text('candidate\n')
    git(wt, 'commit', '-qam', 'candidate')
    head = git(wt, 'rev-parse', 'HEAD')
    record = repo / '.scratch/feature/solve-records/candidate.md'
    record.parent.mkdir(parents=True)
    record.write_text(f'''---
state: open
outcome: candidate
tickets:
  - .scratch/feature/issues/01.md
head: solve/candidate
head_sha: {head}
---

## Summary
Implemented app change; validation and requirement audit passed.
''')
    run(sys.executable, HELPER, 'candidate-gate-record', '--repo', repo, '--record', str(record.relative_to(repo)), '--base', 'main', '--checks', 'passed', '--review', 'passed', '--merge', 'ready', '--rollout-config', 'none', '--json')
    member = dict(repo=str(repo), base='main', base_sha=base, head='solve/candidate', head_sha=head,
                  worktree=str(wt), landing_sha=head, ownership={'branch': 'solve-owned', 'worktree': 'solve-owned'},
                  ownership_evidence='Fixture created this branch and worktree for the selected Ticket.',
                  gate_evidence=dict(checks='passed', review='passed', merge='ready', rollout_config='none', activation='none',
                                     audit='passed', dependencies='satisfied'))
    return repo, record, member


class FinalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.repo, self.record, self.member = fixture(self.root)
        self.evidence = self.root / 'evidence.json'
        self.write_evidence([self.member])

    def write_evidence(self, members):
        self.evidence.write_text(json.dumps(dict(authorization='User authorized landing and cleanup of the complete selected scope.',
                                               scope_evidence='Selected Ticket requires exactly these repositories.', repositories=members)))

    def call(self, action, *args, check=True, env=None):
        p = run(sys.executable, FACADE, 'solve-record', action, '--repo', self.repo,
                '--record', self.record.relative_to(self.repo), *args, check=check, env=env)
        return json.loads(p.stdout)

    def prepare(self):
        return self.call('finalization-record', '--phase', 'prepare', '--evidence', self.evidence)

    def reconcile(self, **kwargs):
        return self.call('finalization-record', '--phase', 'reconcile', **kwargs)

    def test_prepared_landing_blocks_new_ticket_contract(self):
        spec = importlib.util.spec_from_file_location('snapshot_fixtures', ROOT / 'tests/tracker-snapshot.py')
        fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixtures)
        contract = fixtures.CONTRACT.replace('.tracker/tickets/', '.scratch/feature/issues/')
        fixtures.write(self.repo, 'docs/agents/ultra-tracker.md', contract)
        ticket = fixtures.write(self.repo, '.scratch/feature/issues/01.md', fixtures.ticket('T', 'review-pending',
            'Publication Run: run\nSource Spec: spec.md', '## Acceptance criteria\n\n- [ ] Old criterion.'))
        def publication(action, *args):
            return json.loads(run(sys.executable, FACADE, 'publication', action, '--repo', self.repo,
                '--location', '.scratch/feature/issues', '--run-id', 'run', *args).stdout)['data']
        publication('register')
        publication('promote')
        ticket.write_text(ticket.read_text().replace('Status: ready-for-agent', 'Status: completed'))
        self.prepare()
        old_digest = publication('inspect')['body_digests']['T']
        request = self.root / 'amend.json'
        request.write_text(json.dumps(dict(id='A1', ticket='T', status='approved', approval='Approved scope change',
            predecessor=None, replaces={'Acceptance criteria': '- [ ] New criterion.'})))
        publication('amend', '--ticket-id', 'T', '--expected-digest', old_digest, '--amendment', str(request))
        plan = self.call('landing-plan', check=False)
        self.assertIn('contract amendment', json.dumps(plan))
        self.assertFalse(plan['ok'])

    def land(self, member=None):
        m = member or self.member
        git(m['repo'], 'merge', '--ff-only', m['landing_sha'])

    def cleanup(self, member=None):
        m = member or self.member
        git(m['repo'], 'worktree', 'remove', m['worktree'])
        git(m['repo'], 'branch', '-d', m['head'])

    def dashboard(self):
        return json.loads(run(sys.executable, FACADE, 'solve-record', 'dashboard', '--repo', self.repo).stdout)['data']['buckets']

    def test_two_repositories_partial_landing_and_retry(self):
        other, _, member = fixture(self.root, 'two')
        self.write_evidence([self.member, member])
        self.prepare()
        self.land()
        partial = self.reconcile()['data']
        self.assertEqual(partial['state'], 'open')
        self.assertEqual([m['landing'] for m in partial['repositories']], ['verified', 'pending'])
        self.assertEqual(len(self.dashboard()['manual']), 1)
        self.cleanup()
        self.land(member)
        self.assertEqual(self.reconcile()['data']['state'], 'merged')
        self.cleanup(member)
        self.assertTrue(self.reconcile()['data']['cleanup_done'])
        self.assertEqual(git(other, 'rev-parse', 'main'), member['head_sha'])

    def test_interrupted_write_after_git_success_converges(self):
        self.prepare()
        self.land()
        before = self.record.read_bytes()
        failed = self.reconcile(check=False, env=dict(os.environ, ULTRA_FINALIZATION_FAIL_BEFORE_WRITE='1'))
        self.assertFalse(failed['ok'])
        self.assertEqual(before, self.record.read_bytes())
        self.cleanup()
        self.assertTrue(self.reconcile()['data']['cleanup_done'])
        self.prepare()  # Same immutable input also remains retryable after resource removal.

    def test_partial_cleanup_and_missing_registration(self):
        self.prepare()
        self.land()
        wt = Path(self.member['worktree'])
        import shutil
        shutil.rmtree(wt)
        pending = self.reconcile()['data']
        self.assertEqual(pending['state'], 'merged')
        self.assertFalse(pending['cleanup_done'])
        self.assertIn('registration remains', ' '.join(pending['repositories'][0]['blockers']))
        git(self.repo, 'worktree', 'prune')
        self.assertFalse(self.reconcile()['data']['cleanup_done'])
        git(self.repo, 'branch', '-d', self.member['head'])
        self.assertTrue(self.reconcile()['data']['cleanup_done'])

    def test_missing_historical_evidence_never_means_cleanup_success(self):
        self.land()
        self.cleanup()
        before = self.record.read_bytes()
        result = self.reconcile(check=False)
        self.assertFalse(result['ok'])
        self.assertEqual(before, self.record.read_bytes())
        self.assertEqual(self.call('finalization-plan')['data']['status'], 'pending')

    def test_stale_head_and_wrong_target_are_refused_before_preparation(self):
        self.member['head_sha'] = self.member['base_sha']
        self.write_evidence([self.member])
        before = self.record.read_bytes()
        self.assertFalse(self.call('finalization-record', '--phase', 'prepare', '--evidence', self.evidence, check=False)['ok'])
        self.assertEqual(before, self.record.read_bytes())
        self.member['head_sha'] = git(self.repo, 'rev-parse', self.member['head'])
        git(self.repo, 'branch', 'wrong-target')
        self.member['base'] = 'wrong-target'
        self.write_evidence([self.member])
        self.assertFalse(self.call('finalization-record', '--phase', 'prepare', '--evidence', self.evidence, check=False)['ok'])
        self.assertEqual(before, self.record.read_bytes())

    def test_stale_head_after_preparation_stays_pending(self):
        self.prepare()
        wt = Path(self.member['worktree'])
        (wt / 'app.txt').write_text('unreviewed revision')
        git(wt, 'commit', '-qam', 'unreviewed')
        self.land()
        result = self.reconcile()['data']
        self.assertEqual(result['state'], 'open')
        self.assertIn('stale candidate head', result['repositories'][0]['blockers'])

    def test_dirty_cleanup_keeps_merge_fact(self):
        self.prepare()
        self.land()
        (Path(self.member['worktree']) / 'user.txt').write_text('user work')
        result = self.reconcile()['data']
        self.assertEqual(result['state'], 'merged')
        self.assertFalse(result['cleanup_done'])

    def test_replacement_path_and_branch_drift_never_count_as_removed(self):
        self.prepare()
        self.land()
        self.cleanup()
        Path(self.member['worktree']).mkdir()
        result = self.reconcile()['data']
        self.assertFalse(result['cleanup_done'])
        self.assertTrue(result['repositories'][0]['evidence_conflict'])
        self.assertTrue(Path(self.member['worktree']).exists())

    def test_user_owned_resources_are_retained(self):
        self.member['ownership'] = dict(branch='user-owned', worktree='user-owned')
        self.write_evidence([self.member])
        self.prepare()
        self.land()
        result = self.reconcile()['data']
        self.assertTrue(result['cleanup_done'])
        self.assertTrue(Path(self.member['worktree']).exists())
        self.assertEqual(git(self.repo, 'rev-parse', self.member['head']), self.member['head_sha'])

    def test_scope_retry_conflict_and_read_only_plan(self):
        self.prepare()
        before = self.record.read_bytes()
        self.call('finalization-plan')
        self.dashboard()
        self.assertEqual(before, self.record.read_bytes())
        self.member['landing_sha'] = self.member['base_sha']
        self.write_evidence([self.member])
        result = self.call('finalization-record', '--phase', 'prepare', '--evidence', self.evidence, check=False)
        self.assertFalse(result['ok'])
        self.assertEqual(before, self.record.read_bytes())

    def test_overlapping_wip_and_failed_acceptance_block_preparation(self):
        (self.repo / 'app.txt').write_text('user edits')
        before = self.record.read_bytes()
        result = self.call('finalization-record', '--phase', 'prepare', '--evidence', self.evidence, check=False)
        self.assertFalse(result['ok'])
        self.assertEqual(before, self.record.read_bytes())
        git(self.repo, 'restore', 'app.txt')
        self.record.write_text(self.record.read_text().replace('Checks: passed', 'Checks: stale'))
        result = self.call('finalization-record', '--phase', 'prepare', '--evidence', self.evidence, check=False)
        self.assertFalse(result['ok'])

    def test_prepared_landing_plan_rechecks_wip_for_pending_repo(self):
        _, _, second = fixture(self.root, 'two')
        self.write_evidence([self.member, second])
        self.prepare()
        ready = self.call('landing-plan')['data']
        self.assertEqual(ready['status'], 'ready')
        self.land()
        self.assertFalse(self.call('landing-plan', check=False)['ok'])
        ready = self.call('landing-plan', '--target-repo', second['repo'])['data']
        self.assertEqual(ready['status'], 'ready')
        (Path(second['repo']) / 'app.txt').write_text('user WIP')
        self.assertFalse(self.call('landing-plan', '--target-repo', second['repo'], check=False)['ok'])
        self.assertEqual(git(second['repo'], 'rev-parse', 'main'), second['base_sha'])

    def test_landing_plan_preserves_index_and_wip(self):
        self.prepare()
        (self.repo / 'app.txt').write_text('staged user change')
        git(self.repo, 'add', 'app.txt')
        (self.repo / 'app.txt').write_text('unstaged user change')
        before = (git(self.repo, 'rev-parse', 'main'), git(self.repo, 'diff', '--cached'),
                  git(self.repo, 'diff'), git(self.repo, 'stash', 'list'))
        result = json.loads(run(sys.executable, HELPER, 'landing-plan', '--repo', self.repo,
                                '--record', self.record.relative_to(self.repo), '--json', check=False).stdout)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['dirty_overlap_paths'], ['app.txt'])
        self.assertEqual(before, (git(self.repo, 'rev-parse', 'main'), git(self.repo, 'diff', '--cached'),
                                 git(self.repo, 'diff'), git(self.repo, 'stash', 'list')))

    def test_disjoint_wip_survives_landing(self):
        self.prepare()
        (self.repo / 'notes.txt').write_text('private notes')
        self.assertEqual(self.call('landing-plan')['data']['status'], 'ready')
        self.land()
        self.assertEqual((self.repo / 'notes.txt').read_text(), 'private notes')

    def test_untracked_directory_collision_and_rename_source(self):
        # Real filenames containing tabs and non-ASCII must not be Git-quoted
        # into a different path; rename sources are part of the write surface.
        wt = Path(self.member['worktree'])
        name = '目录\told.txt'
        (self.repo / name).write_text('original')
        git(self.repo, 'add', name)
        git(self.repo, 'commit', '-qm', 'baseline filename')
        git(wt, 'merge', '--no-edit', 'main')
        git(wt, 'mv', name, 'renamed.txt')
        (wt / 'new-directory').write_text('candidate file')
        git(wt, 'add', '.')
        git(wt, 'commit', '-qm', 'rename and file')
        self.record.write_text(self.record.read_text().replace(self.member['head_sha'], git(wt, 'rev-parse', 'HEAD'))
                               .replace(self.member['base_sha'], git(self.repo, 'rev-parse', 'HEAD')))
        (self.repo / name).write_text('user WIP')
        (self.repo / 'new-directory').mkdir()
        (self.repo / 'new-directory' / 'notes.txt').write_text('untracked WIP')
        result = json.loads(run(sys.executable, HELPER, 'landing-plan', '--repo', self.repo,
                                '--record', self.record.relative_to(self.repo), '--json', check=False).stdout)
        self.assertEqual(result['status'], 'blocked')
        self.assertIn(name, result['dirty_overlap_paths'])
        self.assertIn('new-directory/notes.txt', result['untracked_overlap_paths'])
        self.assertEqual((self.repo / name).read_text(), 'user WIP')

    def test_disposable_landing_resources_are_in_cleanup_scope(self):
        (self.repo / 'independent.txt').write_text('target advancement')
        git(self.repo, 'add', 'independent.txt')
        git(self.repo, 'commit', '-qm', 'advance target')
        self.member['base_sha'] = git(self.repo, 'rev-parse', 'HEAD')
        landing = self.root / 'landing'
        git(self.repo, 'worktree', 'add', '-qb', 'solve/landing', landing, 'main')
        git(landing, 'merge', '--no-ff', '-m', 'validated landing', self.member['head'])
        sha = git(landing, 'rev-parse', 'HEAD')
        self.member['landing_sha'] = sha
        self.member['additional_resources'] = [
            dict(kind='worktree', identity=str(landing), head_sha=sha, branch='solve/landing', owner='solve-owned', ownership_evidence='Created disposable landing worktree'),
            dict(kind='branch', identity='solve/landing', head_sha=sha, owner='solve-owned', ownership_evidence='Created disposable landing branch')]
        run(sys.executable, HELPER, 'candidate-gate-record', '--repo', self.repo, '--record', self.record.relative_to(self.repo), '--base', 'main', '--checks', 'passed', '--review', 'passed', '--merge', 'ready', '--rollout-config', 'none', '--json')
        self.write_evidence([self.member])
        self.prepare()
        self.assertEqual(self.call('landing-plan')['data']['landing_sha'], sha)
        self.land()
        self.cleanup()
        result = self.reconcile()['data']
        self.assertEqual(result['state'], 'merged')
        self.assertFalse(result['cleanup_done'])
        git(self.repo, 'worktree', 'remove', landing)
        self.assertFalse(self.reconcile()['data']['cleanup_done'])
        git(self.repo, 'branch', '-d', 'solve/landing')
        self.assertTrue(self.reconcile()['data']['cleanup_done'])
        self.prepare()

    def test_moved_detached_resource_is_not_deleted(self):
        landing = self.root / 'detached-landing'
        relocated = self.root / 'relocated-landing'
        git(self.repo, 'worktree', 'add', '--detach', landing, self.member['head_sha'])
        self.member['additional_resources'] = [dict(kind='worktree', identity=str(landing), head_sha=self.member['head_sha'], branch='', owner='solve-owned', ownership_evidence='Created detached landing environment')]
        self.write_evidence([self.member])
        self.prepare()
        git(self.repo, 'worktree', 'move', landing, relocated)
        self.land()
        self.cleanup()
        result = self.reconcile()['data']
        self.assertFalse(result['cleanup_done'])
        self.assertEqual(result['repositories'][0]['resources']['additional:0:worktree'], 'unverified')
        self.assertTrue(relocated.is_dir())
        git(self.repo, 'worktree', 'remove', relocated)
        self.assertTrue(self.reconcile()['data']['cleanup_done'])

    def test_legacy_receipt_preserves_identity_and_uses_observation_time(self):
        s = self.record.read_text().replace('outcome: candidate\n', '').replace('tickets:', 'issues:')
        fields = f"id: legacy-candidate\nkind: solve_record\nbase: main\nbase_sha: {self.member['base_sha']}\nworktree: {self.member['worktree']}\ncreated_at: 2020-01-01T00:00:00Z\nmerged_at: 2020-01-01T00:00:00Z\ncleanup_done: false\n"
        self.record.write_text(s.replace('state: open\n', 'state: open\n' + fields))
        self.prepare()
        self.land()
        self.cleanup()
        self.reconcile()
        row = self.dashboard()['recent'][0]
        self.assertEqual(row['id'], 'legacy-candidate')
        self.assertNotEqual(row['merged_at'], '2020-01-01T00:00:00Z')
        self.assertEqual(row['created_at'], '2020-01-01T00:00:00Z')
        self.assertTrue(row['legacy_outcome'])

    def test_landing_and_cleanup_update_original_receipt(self):
        original = self.record.read_text()
        self.prepare()
        self.assertEqual(git(self.repo, 'rev-parse', 'main'), self.member['base_sha'])
        self.land()
        landed = self.reconcile()['data']
        self.assertEqual(landed['state'], 'merged')
        self.assertFalse(landed['cleanup_done'])
        self.assertEqual(self.dashboard()['cleanup'][0]['merged_sha'], self.member['head_sha'])
        self.cleanup()
        done = self.reconcile()['data']
        self.assertTrue(done['cleanup_done'])
        self.assertEqual(len(self.dashboard()['recent']), 1)
        self.assertIn('Implemented app change', self.record.read_text())
        self.assertEqual(len(list(self.record.parent.glob('*.md'))), 1)
        before = self.record.read_bytes()
        self.reconcile()
        self.assertEqual(before, self.record.read_bytes())
        self.assertIn('state: open', original)


if __name__ == '__main__':
    unittest.main()
