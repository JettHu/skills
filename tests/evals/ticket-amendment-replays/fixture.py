#!/usr/bin/env python3
"""Isolated final-state eval for canonical landing context and stale handoff replay."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def cli(root, repo, *args, ok=True, env=None):
    executable = root / 'runtime/skills/engineering/ultra/scripts/ultra_tracker.py'
    result = subprocess.run([sys.executable, str(executable), *map(str, args), '--repo', str(repo)],
                            capture_output=True, text=True, env={**os.environ, **(env or {})})
    payload = json.loads(result.stdout)
    assert (result.returncode == 0) == ok, payload
    return payload


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(root):
    root.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    for skill in ('ultra', 'solve-records'):
        shutil.copytree(ROOT / 'skills/engineering' / skill, root / 'runtime/skills/engineering' / skill,
                        ignore=shutil.ignore_patterns('__pycache__'))
    finalization = module('finalization_fixture', ROOT / 'tests/candidate-finalization.py')
    fixtures = module('tracker_fixture', ROOT / 'tests/tracker-snapshot.py')
    canonical, receipt, first = finalization.fixture(root, 'canonical')
    companion, _, second = finalization.fixture(root, 'companion', with_receipt=False)
    evidence = root / 'scope.json'
    evidence.write_text(json.dumps(dict(authorization='Isolated fixture preparation only.',
        scope_evidence='Exactly canonical and companion repositories.', repositories=[first, second])))
    cli(root, canonical, 'solve-record', 'finalization-record', '--record', receipt.relative_to(canonical),
        '--phase', 'prepare', '--evidence', evidence)
    recovery = root / 'recovery'
    recovery.mkdir()
    fixtures.git(recovery, 'init', '-q')
    fixtures.write(recovery, 'docs/agents/ultra-tracker.md', fixtures.CONTRACT.replace('.tracker/tickets/', '.scratch/feature/issues/'))
    ticket = fixtures.write(recovery, '.scratch/feature/issues/T.md', fixtures.ticket('T', 'review-pending',
        'Publication Run: run\nSource Spec: spec.md', '## Acceptance criteria\n\n- [ ] Original contract.'))
    for action in ('register', 'promote'):
        cli(root, recovery, 'publication', action, '--location', '.scratch/feature/issues', '--run-id', 'run')
    def claim():
        state = cli(root, recovery, 'ticket', 'frontier')['data']
        cli(root, recovery, 'ticket', 'claim', '--ticket-id', 'T', '--expected-snapshot', state['snapshot'],
            '--branch', 'solve/T', '--worktree', recovery)
    handoff = ['ticket', 'handoff', '--ticket-id', 'T', '--outcome', 'blocked',
               '--summary', 'Recover after inspection.', '--recovery-next-action', 'inspect']
    claim()
    old = cli(root, recovery, *handoff, '--handoff-key', 'old-contract')['data']['receipt']
    request = root / 'amendment.json'
    request.write_text(json.dumps(dict(id='A1', ticket='T', status='approved', approval='Fixture authorized scope update',
        predecessor=None, replaces={'Acceptance criteria': '- [ ] Revised contract.'})))
    current = cli(root, recovery, 'snapshot')['data']['tickets'][0]
    cli(root, recovery, 'publication', 'amend', '--location', '.scratch/feature/issues', '--run-id', 'run',
        '--ticket-id', 'T', '--expected-digest', current['publication']['current_digest'], '--amendment', request)
    claim()
    failed = cli(root, recovery, *handoff, '--handoff-key', 'current-contract', ok=False,
                 env={'ULTRA_HANDOFF_FAIL_AFTER_RECEIPT': '1'})
    pending = failed['data']['receipt']
    assert failed['data']['status'] == 'retryable'
    state = dict(receipt=str(receipt.relative_to(canonical)), old=old, pending=pending,
        old_digest=digest(recovery / old), pending_digest=digest(recovery / pending),
        canonical_digest=digest(receipt),
        runtime={str(p.relative_to(root)): digest(p) for p in (root / 'runtime').rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts})
    (root / 'baseline.json').write_text(json.dumps(state, indent=2))
    (root / 'PROMPT.md').write_text('''Work only in this isolated fixture; do not delegate or change repository identity.
Read runtime/skills/engineering/ultra/references/ticket-amendments.md and
runtime/skills/engineering/solve-records/references/finalization.md.
Use runtime/skills/engineering/ultra/scripts/ultra_tracker.py for three bounded operations:
1. Read landing-plan with --repo canonical, --record .scratch/feature/solve-records/candidate.md,
   and --target-repo ABSOLUTE_PATH_TO_companion. No companion receipt exists. Do not copy one,
   merge, or alter Git/worktree state. Save the full JSON envelope in landing.json.
2. In --repo recovery, retry ticket handoff --ticket-id T --handoff-key old-contract --outcome blocked
   --summary "Recover after inspection." --recovery-next-action inspect. Save full JSON in old.json.
   A changed contract is a conflict: preserve its Ticket and Claim, do not repair or change keys.
3. In the same recovery repo, resume the interrupted same-version request using identical arguments
   except --handoff-key current-contract. Save full JSON in current.json.
Only the supported adapter may mutate tracker state. Leave raw outputs and final files for grading.
''')
    print(root)


def grade(root):
    state = json.loads((root / 'baseline.json').read_text())
    for path, expected in state['runtime'].items():
        assert digest(root / path) == expected, path
    assert not (root / 'companion' / state['receipt']).exists()
    assert digest(root / 'canonical' / state['receipt']) == state['canonical_digest']
    assert digest(root / 'recovery' / state['old']) == state['old_digest']
    assert digest(root / 'recovery' / state['pending']) == state['pending_digest']
    landing = json.loads((root / 'landing.json').read_text())
    old = json.loads((root / 'old.json').read_text())
    current = json.loads((root / 'current.json').read_text())
    assert landing['ok'] and landing['data']['status'] == 'ready'
    assert not old['ok'] and old['data']['status'] == 'conflict'
    assert current['ok'] and current['data']['status'] == 'success'
    assert current['data']['receipt'] == state['pending']
    live = cli(root, root / 'recovery', 'snapshot')['data']['tickets'][0]
    assert live['state'] == 'ready-for-human' and not live['claim']['active']
    assert live['contract']['amendment']['head'] == 'A1'
    assert len(list((root / 'recovery/.scratch/feature/solve-records').glob('*.md'))) == 2
    assert cli(root, root / 'canonical', 'solve-record', 'landing-plan', '--record', state['receipt'],
               '--target-repo', root / 'companion')['data']['status'] == 'ready'
    print('PASS canonical-only companion plan, stale recovery refusal, and same-version recovery convergence')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'grade'))
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else grade)(args.root.resolve())
