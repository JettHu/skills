#!/usr/bin/env python3
"""Snapshot and detect a review's changes without mutating repository files or index."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


class DetectionError(Exception):
    pass


def git(repo, *args):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True)
    if result.returncode:
        raise DetectionError(result.stderr.decode('utf-8', 'replace').strip() or 'Git read failed')
    return result.stdout


def paths(repo, *args):
    return [os.fsdecode(p) for p in git(repo, *args).split(b'\0') if p]


def digest(repo, name):
    path = repo / name
    if path.is_symlink():
        return hashlib.sha256(b'link\0' + os.fsencode(os.readlink(path))).hexdigest()
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    root = git(args.repo, 'rev-parse', '--show-toplevel')
    if not root.endswith(b'\n'):
        raise DetectionError('Git returned an invalid repository root')
    repo = Path(os.fsdecode(root[:-1])).resolve()
    state_path = Path(args.snapshot).resolve()
    if state_path == repo or repo in state_path.parents:
        raise DetectionError('Keep the snapshot outside the repository so it cannot become a change')
    if args.command == 'snapshot':
        base = git(repo, 'rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
        untracked = paths(repo, 'ls-files', '--others', '--exclude-standard', '-z')
        state = {'version': 1, 'repo': str(repo), 'base_sha': base,
                 'untracked': {name: digest(repo, name) for name in untracked},
                 'starting_dirty': sorted(set(paths(repo, 'diff', '--name-only', '-z', '--'))
                                          | set(paths(repo, 'diff', '--cached', '--name-only', '-z', '--')))}
        # Exclusive creation keeps an accidental retry from replacing the starting inventory.
        with state_path.open('x') as stream:
            json.dump(state, stream, ensure_ascii=True)
        return {'status': 'snapshot', 'base_sha': base, 'snapshot': str(state_path)}

    with state_path.open() as stream:
        state = json.load(stream)
    if (not isinstance(state, dict) or state.get('version') != 1 or state.get('repo') != str(repo)
            or not isinstance(state.get('base_sha'), str) or not state['base_sha']
            or not isinstance(state.get('untracked'), dict)
            or not isinstance(state.get('starting_dirty'), list)):
        raise DetectionError('Invalid or foreign baseline snapshot')
    base = state['base_sha']
    # Pin a commit, never accept a moving branch name from a damaged snapshot.
    resolved = git(repo, 'rev-parse', '--verify', '--end-of-options', base + '^{commit}').decode().strip()
    if resolved != base:
        raise DetectionError('Baseline must be a full commit SHA')
    committed = paths(repo, 'diff', '--name-only', '--no-renames', '-z', base, 'HEAD', '--')
    staged = paths(repo, 'diff', '--cached', '--name-only', '--no-renames', '-z', '--')
    unstaged = paths(repo, 'diff', '--name-only', '--no-renames', '-z', '--')
    current = set(paths(repo, 'ls-files', '--others', '--exclude-standard', '-z'))
    previous = set(state['untracked'])
    for name, old_digest in state['untracked'].items():
        if (not isinstance(name, str) or Path(name).is_absolute() or '..' in Path(name).parts
                or not isinstance(old_digest, str)):
            raise DetectionError('Invalid untracked inventory')
    changed_previous = sorted(name for name in previous if digest(repo, name) != state['untracked'][name])
    new = current - previous
    owned = set(args.owned_untracked)
    excluded = set(args.exclude_untracked)
    if owned & excluded or not (owned | excluded) <= new:
        raise DetectionError('Ownership decisions must name distinct currently new untracked paths')
    unresolved = sorted(new - owned - excluded)
    tracked = sorted((set(committed) | set(staged) | set(unstaged)) - previous)
    required = bool(tracked or owned)
    status = 'needs-ownership' if unresolved or changed_previous else ('review' if required else 'clean')
    return {'status': status, 'base_sha': base, 'head_sha': git(repo, 'rev-parse', 'HEAD').decode().strip(),
            'review_required': required, 'tracked_paths': tracked, 'committed': committed,
            'staged': staged, 'unstaged': unstaged, 'starting_dirty': state['starting_dirty'],
            'owned_untracked': sorted(owned), 'unclassified_untracked': unresolved,
            'excluded_untracked': sorted(excluded), 'preexisting_untracked': sorted(previous),
            'changed_preexisting_untracked': changed_previous}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot', 'detect'])
    parser.add_argument('--repo', required=True)
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--owned-untracked', action='append', default=[])
    parser.add_argument('--exclude-untracked', action='append', default=[])
    args = parser.parse_args()
    try:
        result = run(args)
    except (DetectionError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
