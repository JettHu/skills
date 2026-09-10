#!/usr/bin/env python3
"""Installed skill and repository CLI use one renderer from unrelated cwd."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/in-progress/setup-obsidian-workspace'
spec = importlib.util.spec_from_file_location('snapshot_fixture', ROOT / 'tests/tracker-snapshot.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class InstalledWorkspaceTests(unittest.TestCase):
    setUp = base.SnapshotTests.setUp
    tearDown = base.SnapshotTests.tearDown
    add = base.SnapshotTests.add

    def prepare(self):
        root = Path(self.tmp.name).resolve()
        installed = root / 'installed skills'
        for source in (SKILL, ROOT / 'skills/engineering/ultra', ROOT / 'skills/engineering/solve-records'):
            shutil.copytree(source, installed / source.name, ignore=shutil.ignore_patterns('__pycache__'))
        vault = root / 'selected vault'
        vault.mkdir()
        config = root / 'workspace.json'
        config.write_text(json.dumps(dict(vault=str(vault), generated='generated',
                                          projects=[dict(id='one', repository=str(self.repo))])))
        self.add('A')
        return installed, config, vault / 'generated/Home.md'

    def run_cli(self, script, config, **overrides):
        env = dict(os.environ)
        env.pop('JETT_ULTRA_SKILL_DIR', None)
        env.pop('PYTHONPATH', None)
        env.update(overrides)
        result = subprocess.run([sys.executable, str(script), '--config', str(config)],
                                cwd=self.repo, env=env, text=True, capture_output=True)
        self.assertNotIn('Traceback', result.stderr, result.stderr)
        return result.returncode, json.loads(result.stdout)

    def test_flat_install_and_compatibility_cli_share_output(self):
        installed, config, home = self.prepare()
        entry = installed / 'setup-obsidian-workspace/scripts/obsidian-workspace.py'
        code, result = self.run_cli(entry, config)
        self.assertEqual(code, 0, result)
        original, mtime = home.read_bytes(), home.stat().st_mtime_ns
        code, result = self.run_cli(ROOT / 'scripts/obsidian-workspace.py', config)
        self.assertEqual(code, 0, result)
        self.assertEqual((home.read_bytes(), home.stat().st_mtime_ns), (original, mtime))
        for alias in home.parent.glob('generations/*/one/sources/*.md'):
            self.assertTrue(alias.is_symlink())
            self.assertTrue(alias.resolve().is_relative_to(self.repo))

    def test_missing_dependency_preserves_existing_output(self):
        installed, config, home = self.prepare()
        entry = installed / 'setup-obsidian-workspace/scripts/obsidian-workspace.py'
        self.assertEqual(self.run_cli(entry, config)[0], 0)
        original = home.read_bytes()
        shutil.rmtree(installed / 'solve-records')
        code, result = self.run_cli(entry, config)
        self.assertEqual(code, 2)
        self.assertFalse(result['persisted'])
        self.assertIn('solve-records', result['error'])
        self.assertEqual(home.read_bytes(), original)

    def test_explicit_dependency_is_not_silently_replaced(self):
        installed, config, home = self.prepare()
        entry = installed / 'setup-obsidian-workspace/scripts/obsidian-workspace.py'
        code, result = self.run_cli(entry, config, JETT_ULTRA_SKILL_DIR=str(installed / 'missing'))
        self.assertEqual(code, 2)
        self.assertFalse(home.exists())
        self.assertIn('missing', result['error'])
        # Move this skill outside the dependency root, then select the dependency set.
        relocated = installed.parent / 'standalone'
        shutil.move(str(installed / 'setup-obsidian-workspace'), relocated)
        code, result = self.run_cli(relocated / 'scripts/obsidian-workspace.py', config,
                                    JETT_ULTRA_SKILL_DIR=str(installed / 'ultra'))
        self.assertEqual(code, 0, result)

    def test_incompatible_snapshot_fails_before_output(self):
        installed, config, home = self.prepare()
        source = installed / 'ultra/scripts/tracker_snapshot.py'
        source.write_text(source.read_text().replace('tracker-snapshot/v1', 'tracker-snapshot/v999'))
        code, result = self.run_cli(installed / 'setup-obsidian-workspace/scripts/obsidian-workspace.py', config)
        self.assertEqual(code, 2)
        self.assertIn('Unsupported Tracker Snapshot', result['error'])
        self.assertFalse(home.exists())


if __name__ == '__main__':
    unittest.main()
