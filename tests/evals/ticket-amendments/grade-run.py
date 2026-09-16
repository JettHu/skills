#!/usr/bin/env python3
"""Grade final tracker bytes and independent consumer artifacts, not chat prose."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def grade(output, consumers):
    repo = output / 'repo'
    baseline = json.loads((output / 'baseline.json').read_text())
    for relative, digest in baseline['runtime'].items():
        assert hashlib.sha256((repo / relative).read_bytes()).hexdigest() == digest, relative
    old = repo / '.scratch/policy/solve-records/old.md'
    assert hashlib.sha256(old.read_bytes()).hexdigest() == baseline['old_receipt']
    cli = repo / '.runtime/skills/engineering/ultra/scripts/ultra_tracker.py'
    payload = json.loads(subprocess.check_output([sys.executable, str(cli), 'snapshot', '--repo', str(repo)], text=True))['data']
    ticket = next(t for t in payload['tickets'] if t['key'] == 'T')
    amendment = ticket['contract']['amendment']
    assert amendment['head'] == 'A2'
    assert [a['id'] for a in amendment['chain']] == ['A1', 'A2']
    assert amendment['historical_completion'] is True
    assert [d['id'] for d in amendment['drafts']] == ['DRAFT']
    assert ticket['contract']['completed'] is False
    assert ticket['eligibility']['claimable'] is False
    assert ticket['blockers'][0]['ticket_key'] == 'D' and not ticket['blockers'][0]['satisfied']
    assert 'Forbid all deletion.' in ticket['contract']['effective_text']
    first = json.loads((repo / amendment['chain'][0]['path']).read_text())
    assert 'Allow deletion without references.' in first['original_text']
    assert first['approval'] == 'approved.md: maintainer decision'
    if consumers:
        for role in ('executor', 'reviewer', 'acceptor'):
            actual = json.loads((repo / f'REPORT-{role}.json').read_text())
            assert actual == dict(role=role, effective_head='A2', deletion_rule='forbid-all', blockers=['D'],
                                  claimable=False, current_completed=False, historical_completion=True,
                                  old_candidate_satisfies=False, drafts=['DRAFT']), actual
    print('PASS approved amendments' + (' and three independent consumers' if consumers else ' producer'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('--consumers', action='store_true')
    args = parser.parse_args()
    grade(args.output.resolve(), args.consumers)
