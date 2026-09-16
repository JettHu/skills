#!/usr/bin/env python3
"""Prepare/grade a real-model continuation using the production facade."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

SOURCE = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('fixture_support', SOURCE / 'tests/candidate-finalization.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    catalog = root / 'catalog'
    for skill in ('ultra', 'solve-records'):
        shutil.copytree(SOURCE / 'skills/engineering' / skill, catalog / 'skills/engineering' / skill,
                        ignore=shutil.ignore_patterns('__pycache__'))
    first, record, a = support.fixture(root, 'one')
    second, _, b = support.fixture(root, 'two')
    facade = catalog / 'skills/engineering/ultra/scripts/ultra_tracker.py'
    evidence = root / 'evidence.json'
    evidence.write_text(json.dumps(dict(authorization='User authorized landing and cleanup of both selected repositories.',
                                       scope_evidence='One selected Ticket spans these two repository candidates.', repositories=[a, b]), indent=2))
    support.run(sys.executable, facade, 'solve-record', 'finalization-record', '--repo', first,
                '--record', record.relative_to(first), '--phase', 'prepare', '--evidence', evidence)
    support.git(first, 'merge', '--ff-only', a['landing_sha'])
    support.git(first, 'worktree', 'remove', a['worktree'])
    # Original record is still open; one branch remains, the second repo has not landed.
    state = dict(repositories=[a, b], record=str(record), facade=str(facade), before=record.read_text())
    (root / 'expected.json').write_text(json.dumps(state, indent=2))
    prompt = f'''Finish the interrupted landing and cleanup of this one selected candidate, covering BOTH repositories.
User authorization for both landing and solve-owned cleanup remains valid. Do not push or deploy.
Read {catalog}/skills/engineering/solve-records/SKILL.md and its applicable candidate/finalization references.
Canonical receipt: {record}
Production Tracker Facade: {facade}
The exact approved and already prepared full scope is in {evidence} and the canonical receipt.
The first target was advanced and its worktree removed, but the receipt write was interrupted.
Use current Git evidence to determine remaining work; finish the second target and safe cleanup,
then persist all verified facts on the original receipt through the supported facade writer.
Preserve original history and identity. Do not create replacement receipts or edit lifecycle fields by hand.
All fixture checks, audit, dependencies and acceptance were passed against the prepared identities.
Independently recheck current refs, worktree and WIP safety before any remaining Git operation.
Operate only under {root}. This is a bounded local continuation eval, not a request for upstream implementation.
'''
    (root / 'PROMPT.md').write_text(prompt)
    return dict(root=str(root), prompt=str(root / 'PROMPT.md'))


def grade(root):
    state = json.loads((root / 'expected.json').read_text())
    record = Path(state['record'])
    p = support.run(sys.executable, state['facade'], 'solve-record', 'dashboard', '--repo', state['repositories'][0]['repo'])
    dashboard = json.loads(p.stdout)['data']
    recent = dashboard['buckets']['recent']
    checks = dict(original_receipt=record.exists(), one_receipt=len(list(record.parent.glob('*.md'))) == 1,
                  terminal_projection=len(recent) == 1 and recent[0]['state'] == 'merged' and recent[0]['cleanup_done'] == 'true',
                  summary_preserved='Implemented app change; validation and requirement audit passed.' in record.read_text(),
                  supported_evidence='## Finalization' in record.read_text())
    for index, member in enumerate(state['repositories']):
        repo = member['repo']
        checks[f'target_{index}'] = support.git(repo, 'rev-parse', member['base']) == member['landing_sha']
        checks[f'worktree_{index}'] = not Path(member['worktree']).exists() and member['worktree'] not in support.git(repo, 'worktree', 'list', '--porcelain')
        checks[f'branch_{index}'] = support.run('git', '-C', repo, 'show-ref', '--verify', f"refs/heads/{member['head']}", check=False).returncode != 0
        checks[f'clean_{index}'] = not support.git(repo, 'status', '--porcelain')
    return dict(passed=all(checks.values()), checks=checks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('prepare', 'grade'))
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = globals()[args.operation](args.directory.resolve())
    print(json.dumps(result, indent=2))
    if result.get('passed') is False:
        sys.exit(1)
