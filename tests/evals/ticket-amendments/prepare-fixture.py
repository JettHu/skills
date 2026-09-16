#!/usr/bin/env python3
"""Prepare a published old contract for real producer/consumer model runs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def prepare(output):
    repo = output / 'repo'
    repo.mkdir(parents=True)
    for skill in ('ultra', 'solve-records'):
        shutil.copytree(ROOT / 'skills/engineering' / skill, repo / '.runtime/skills/engineering' / skill,
                        ignore=shutil.ignore_patterns('__pycache__'))
    spec = importlib.util.spec_from_file_location('fixtures', ROOT / 'tests/tracker-snapshot.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    contract = fixtures.CONTRACT.replace('.tracker/tickets/', '.scratch/policy/issues/')
    fixtures.write(repo, 'docs/agents/ultra-tracker.md', contract)
    fixtures.write(repo, '.scratch/policy/issues/T.md', fixtures.ticket('T', 'review-pending',
        'Publication Run: policy\nSource Spec: approved.md',
        '## What to build\n\nDeletion policy.\n\n## Acceptance criteria\n\n- [ ] Allow deletion without references.'))
    fixtures.write(repo, '.scratch/policy/issues/D.md', fixtures.ticket('D', 'review-pending',
        'Publication Run: policy\nSource Spec: approved.md', '## Acceptance criteria\n\n- [ ] Dependency work.'))
    cli = repo / '.runtime/skills/engineering/ultra/scripts/ultra_tracker.py'
    def run(*args):
        return json.loads(subprocess.check_output([sys.executable, str(cli), *args, '--repo', str(repo)], text=True))['data']
    for action in ('register', 'promote'):
        run('publication', action, '--location', '.scratch/policy/issues', '--run-id', 'policy')
    ticket = repo / '.scratch/policy/issues/T.md'
    ticket.write_text(ticket.read_text().replace('Status: ready-for-agent', 'Status: completed'))
    fixtures.git(repo, 'init', '-q')
    fixtures.git(repo, 'config', 'user.email', 'eval@example.test')
    fixtures.git(repo, 'config', 'user.name', 'Amendment Eval')
    fixtures.write(repo, '.gitignore', '.scratch/\n.runtime/\nREPORT*.json\n')
    fixtures.write(repo, 'approved.md', 'Maintainer approval: forbid every deletion, including unreferenced records. Then add D as an unfinished dependency.\n')
    fixtures.git(repo, 'add', '.')
    fixtures.git(repo, 'commit', '-qm', 'fixture baseline')
    head = fixtures.git(repo, 'rev-parse', 'HEAD')
    branch = fixtures.git(repo, 'branch', '--show-current')
    receipt = fixtures.write(repo, '.scratch/policy/solve-records/old.md',
        f'---\nstate: open\noutcome: candidate\ntickets:\n  - .scratch/policy/issues/T.md\nhead: {branch}\nhead_sha: {head}\n---\n\n# Old candidate\n\n## Summary\nOld deletion policy verified.\n')
    draft = dict(id='DRAFT', ticket='T', status='draft', approval='', predecessor='A2',
                 replaces={'Acceptance criteria': '- [ ] Allow deletion without references.'})
    fixtures.write(repo, '.scratch/policy/issues/.ultra-publications/amendments/policy/DRAFT.json', json.dumps(draft))
    fixtures.write(repo, 'PRODUCER.md', '''Read .runtime/skills/engineering/ultra/references/ticket-amendments.md.
Act as the Ticket producer in this isolated repository. Maintainer authorization in approved.md
changes completed Ticket T: first A1 replaces Acceptance criteria with exactly
`- [ ] Forbid all deletion.`; then A2 replaces Blocked by with exactly `- D`.
Use approval basis `approved.md: maintainer decision`, stable IDs A1/A2 and explicit predecessors.
Apply both via the supported facade, preserve old receipt and original contract, and verify an
identical retry of A2 converges. The DRAFT amendment is unapproved and must remain so.
Only write request inputs and perform supported adapter operations. Do not edit runtime,
Ticket bodies, journal, old receipt or draft by hand. Do not Claim, implement, merge or commit.
Leave final repository state for an independent grader.
''')
    fixtures.write(repo, 'CONSUMER.md', '''Read .runtime/skills/engineering/ultra/references/ticket-amendments.md.
Start from canonical Ticket .scratch/policy/issues/T.md and use supported reads to determine
its effective contract and whether old candidate .scratch/policy/solve-records/old.md satisfies it.
Do not change any tracker, runtime or Git state. Write REPORT-ROLE.json (replace ROLE with your
assigned role) with exactly: role, effective_head, deletion_rule (allow-unreferenced or forbid-all),
blockers (ID array), claimable (bool), current_completed (bool), historical_completion (bool),
old_candidate_satisfies (bool), drafts (ID array). Do not infer completion from old evidence.
''')
    (output / 'baseline.json').write_text(json.dumps({
        'old_receipt': hashlib.sha256(receipt.read_bytes()).hexdigest(),
        'runtime': {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (repo / '.runtime').rglob('*') if p.is_file() and '__pycache__' not in p.parts},
    }, indent=2))
    print(repo)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output.resolve())
