#!/usr/bin/env python3
"""Prepare/grade an isolated setup skill forward run; never uses live Vaults."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / 'skills/in-progress/setup-obsidian-workspace'


def prepare(path):
    path.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('fixture', ROOT / 'tests/tracker-snapshot.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    case = module.SnapshotTests(); case.setUp(); case.add('A')
    try:
        shutil.copytree(case.repo, path / 'repo')
    finally:
        case.tearDown()
    for name in ('Selected Vault', 'Open Experiment'):
        plugin = path / name / '.obsidian/plugins/obsidian-kanban'
        plugin.mkdir(parents=True)
        (plugin / 'manifest.json').write_text('{"version":"2.0.51"}')
        (plugin.parents[1] / 'community-plugins.json').write_text('["obsidian-kanban"]')
    (path / 'registry.json').write_text(json.dumps({'vaults': {'a': {'path': str(path / 'Selected Vault')}, 'b': {'path': str(path / 'Open Experiment'), 'open': True}}}))
    for name, source in [('setup-obsidian-workspace', SKILL), ('ultra', ROOT / 'skills/engineering/ultra'), ('solve-records', ROOT / 'skills/engineering/solve-records')]:
        shutil.copytree(source, path / 'skills' / name, ignore=shutil.ignore_patterns('__pycache__'))
    print(json.dumps({'root': str(path), 'skill': str(path / 'skills/setup-obsidian-workspace/SKILL.md')}))


def grade(path, selected):
    config = path / 'repo/.scratch/obsidian-workspace.json'
    assert not (path / 'Open Experiment/tracker-generated').exists(), 'open experiment was modified'
    if selected:
        data = json.loads(config.read_text())
        assert data['vault'] == str(path / 'Selected Vault')
        assert data['projects'][0]['repository'] == str(path / 'repo')
        assert (path / 'Selected Vault' / data['generated'] / 'Home.md').is_file()
        assert (path / 'repo/.tracker/tickets/A.md').read_text().startswith('Status: ready-for-agent')
    else:
        assert not config.exists(), 'unselected target was configured'
        assert not (path / 'Selected Vault/tracker-generated').exists()
    print(json.dumps({'ok': True, 'selected': selected, 'evidence': 'filesystem invariants; UI and response require separate review'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['prepare', 'grade']); parser.add_argument('path', type=Path); parser.add_argument('--selected', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare': prepare(args.path.resolve())
    else: grade(args.path.resolve(), args.selected)
