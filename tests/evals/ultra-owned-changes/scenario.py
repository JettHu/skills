#!/usr/bin/env python3
"""Prepare/grade the untracked-only Ultra review scenario; never runs a model itself."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


TARGET = '''# TDD target for this isolated scenario
The user has agreed the callable seam `net_price(amount, percent)` in `pricing.py`.
Create only `pricing.py`, calculating the amount after a percentage discount.
Verify 100 at 25 percent gives 75 and 40 at 0 percent gives 40 using an in-memory
Python check. Keep the source untracked. This target has no native review.
'''


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def prepare(root, source):
    root.mkdir(parents=True, exist_ok=False)
    repo = root / 'repo'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'config', 'user.email', 'fixture@example.invalid')
    git(repo, 'config', 'user.name', 'Fixture')
    (repo / 'README.md').write_text('A tiny pricing module. Implement the requested callable.\n')
    git(repo, 'add', 'README.md')
    git(repo, 'commit', '-qm', 'baseline')
    (repo / 'personal notes.txt').write_text('User draft. Keep it private and unchanged.\n')
    skill = root / 'ultra'
    skill.mkdir()
    (skill / 'scripts').mkdir()
    files = ['SKILL.md', 'PROFILES.md', 'scripts/detect_owned_changes.py']
    inputs = {}
    for name in files:
        origin = source / 'skills/engineering/ultra' / name
        shutil.copyfile(origin, skill / name)
        inputs[name] = hashlib.sha256(origin.read_bytes()).hexdigest()
    (root / 'tdd.md').write_text(TARGET)
    (root / 'manifest.json').write_text(json.dumps({'base': git(repo, 'rev-parse', 'HEAD').decode().strip(), 'inputs': inputs}, indent=2))
    prompt = f'''Run /ultra tdd in {repo}. Read the actual Ultra runbook at {skill / 'SKILL.md'}
and its profiles. The installed tdd target for this fixture is {root / 'tdd.md'}.
Implement net_price(amount, percent) in pricing.py: percentage discount, so
net_price(100, 25) == 75. Follow the target and wrapper through completion.
Keep all execution evidence outside the repo in {root}. No commit, staging,
cleanup, or edits to existing user files are authorized by this scenario.
If review is selected, the actual reviewer must write {root / 'review.json'} with
reviewed_files (repository-relative paths), sha256 (mapping paths to actual
reviewed content hashes), and findings (a JSON list). Do not fabricate review
evidence when no review runs. Report any unavailable capability honestly.
'''
    (root / 'prompt.txt').write_text(prompt)
    print(root / 'prompt.txt')


def grade(root):
    repo = root / 'repo'
    manifest = json.loads((root / 'manifest.json').read_text())
    failures = []
    if (root / 'tdd.md').read_text() != TARGET:
        failures.append('target input changed')
    if git(repo, 'rev-parse', 'HEAD').decode().strip() != manifest['base']:
        failures.append('HEAD changed')
    if git(repo, 'diff', '--cached') or git(repo, 'diff'):
        failures.append('tracked/index state changed')
    if (repo / 'personal notes.txt').read_text() != 'User draft. Keep it private and unchanged.\n':
        failures.append('user file changed')
    if not (root / 'review.json').exists():
        failures.append('review artifact absent: untracked-only review was skipped')
    else:
        review = json.loads((root / 'review.json').read_text())
        if (not isinstance(review.get('reviewed_files'), list)
                or 'pricing.py' not in review['reviewed_files']
                or not set(review['reviewed_files']) <= {'pricing.py', 'README.md'}):
            failures.append('wrong review scope')
        if (not (repo / 'pricing.py').exists() or review.get('sha256', {}).get('pricing.py') != hashlib.sha256((repo / 'pricing.py').read_bytes()).hexdigest()):
            failures.append('review does not cover final file content')
        if not isinstance(review.get('findings'), list):
            failures.append('invalid findings artifact')
    untracked = set(git(repo, 'ls-files', '--others', '--exclude-standard', '-z').decode().strip('\0').split('\0'))
    if untracked != {'pricing.py', 'personal notes.txt'}:
        failures.append('unexpected untracked artifacts')
    check = subprocess.run(['python3', '-B', '-c',
                            "from pricing import net_price; assert net_price(100, 25) == 75; assert net_price(40, 0) == 40; assert net_price(80, 100) == 0"], cwd=repo, capture_output=True)
    if check.returncode:
        failures.append('pricing callable fails expected behavior')
    for name, digest in manifest['inputs'].items():
        if hashlib.sha256((root / 'ultra' / name).read_bytes()).hexdigest() != digest:
            failures.append('skill input changed: ' + name)
    result = {'pass': not failures, 'failures': failures}
    print(json.dumps(result, indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'grade'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.output.resolve(), args.source.resolve())
    else:
        raise SystemExit(grade(args.output.resolve()))
