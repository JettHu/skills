#!/usr/bin/env python3
"""Setup behavior through the installed CLI; all Vaults and plugins are fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from argparse import Namespace

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installed_fixture', ROOT / 'tests/obsidian-workspace-install.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class SetupTests(unittest.TestCase):
    setUp = base.InstalledWorkspaceTests.setUp
    tearDown = base.InstalledWorkspaceTests.tearDown
    add = base.InstalledWorkspaceTests.add
    prepare = base.InstalledWorkspaceTests.prepare
    def setup_case(self):
        installed, config, home = self.prepare()
        self.entry = installed / 'setup-obsidian-workspace/scripts/setup-workspace.py'
        self.config = config
        self.vault = home.parent.parent
        self.other = self.vault.parent / 'open experiment'
        for vault in (self.vault, self.other):
            plugin = vault / '.obsidian/plugins/obsidian-kanban'
            plugin.mkdir(parents=True)
            (plugin / 'manifest.json').write_text(json.dumps({'version': '2.0.51'}))
            (vault / '.obsidian/community-plugins.json').write_text('["obsidian-kanban"]')
        self.registry = self.vault.parent / 'registry.json'
        self.registry.write_text(json.dumps({'vaults': {'a': {'path': str(self.vault)}, 'b': {'path': str(self.other), 'open': True}}}))
        self.config.unlink()

    def cli(self, action, *extra):
        command = [sys.executable, str(self.entry), action, '--config', str(self.config)]
        if action != 'verify':
            command += ['--repo', str(self.repo)]
        env = dict(os.environ)
        env.pop('JETT_ULTRA_SKILL_DIR', None)
        result = subprocess.run(command + list(extra), text=True, capture_output=True, env=env, cwd=self.repo)
        self.assertNotIn('Traceback', result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0 if data.get('ok') else 2, data)
        return data

    def test_registry_never_selects_open_vault(self):
        self.setup_case()
        result = self.cli('inspect', '--registry', str(self.registry))
        self.assertTrue(result['ok'], result)
        self.assertIsNone(result['vault'])
        self.assertEqual(result['next_action'], 'select-vault')
        self.assertEqual(len(result['vault_candidates']), 2)
        self.assertFalse(self.config.exists())
        self.assertFalse(self.cli('configure')['ok'])

    def test_pinned_target_idempotence_and_compact_navigation(self):
        self.setup_case()
        first = self.cli('configure', '--vault', str(self.vault))
        self.assertTrue(first['ok'], first)
        content = self.config.read_bytes()
        home = Path(first['home']); mtime = home.stat().st_mtime_ns
        second = self.cli('configure')
        self.assertFalse(second['configuration_changed'])
        self.assertIsNone(second['backup'])
        self.assertEqual(home.stat().st_mtime_ns, mtime)
        mismatch = self.cli('verify', '--active-vault', str(self.other))
        self.assertFalse(mismatch['ok'])
        self.assertEqual(mismatch['next_action'], 'open-selected-vault')
        self.assertFalse(self.cli('configure', '--vault', str(self.other))['ok'])
        self.assertEqual(self.config.read_bytes(), content)
        self.assertFalse((self.other / 'tracker-generated').exists())
        result = self.cli('verify', '--active-vault', str(self.vault))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['ui_verification'], 'pending')
        self.assertEqual(Path(result['projects'][0]['sample_source']['source']), self.repo / '.tracker/tickets/A.md')
        self.assertNotIn('manifest', result['projects'][0])
        refreshed = subprocess.run(result['refresh_command'], capture_output=True, text=True)
        self.assertEqual(refreshed.returncode, 0, refreshed.stdout)

    def test_merge_preserves_selection_backup_and_output_owner(self):
        self.setup_case()
        self.assertTrue(self.cli('configure', '--vault', str(self.vault), '--no-tickets')['ok'])
        old = self.config.read_bytes()
        repo2 = self.repo.parent / 'second'; shutil.copytree(self.repo, repo2)
        result = self.cli('configure', '--repo', str(repo2))
        self.assertTrue(result['ok'], result)
        data = json.loads(self.config.read_text())
        self.assertEqual(data['projects'][0]['selection'], [])
        self.assertNotIn('selection', data['projects'][1])
        self.assertEqual(Path(result['backup']).read_bytes(), old)
        self.assertFalse(self.cli('configure', '--repo', str(repo2), '--project-id', 'repo')['ok'])
        other_config = self.repo.parent / 'other.json'
        inspected = self.cli('inspect', '--config', str(other_config), '--vault', str(self.vault), '--registry', str(self.registry))
        self.assertEqual(inspected['config'], str(self.config))
        self.assertFalse(self.cli('configure', '--config', str(other_config), '--vault', str(self.vault))['ok'])
        self.assertFalse(other_config.exists())

    def test_unknown_output_plugin_and_symlink_are_preserved(self):
        self.setup_case()
        generated = self.vault / 'tracker-generated/workspace'; generated.mkdir(parents=True)
        note = generated / 'personal.md'; note.write_text('personal')
        self.assertFalse(self.cli('configure', '--vault', str(self.vault))['ok'])
        self.assertEqual(note.read_text(), 'personal')
        self.assertFalse(self.config.exists())
        note.unlink()
        (generated / '.setup.lock').symlink_to(self.registry)
        self.assertFalse(self.cli('configure', '--vault', str(self.vault))['ok'])
        (generated / '.setup.lock').unlink()
        (self.vault / '.obsidian/community-plugins.json').write_text('[]')
        self.assertFalse(self.cli('configure', '--vault', str(self.vault))['ok'])
        self.assertFalse(self.config.exists())

    def test_stale_config_and_failed_first_setup_retry(self):
        self.setup_case()
        generated = self.vault / 'tracker-generated/workspace'; generated.mkdir(parents=True)
        (generated / '.setup.lock').touch()
        self.assertTrue(self.cli('configure', '--vault', str(self.vault))['ok'])
        data = json.loads(self.config.read_text()); data['projects'][0]['selection'] = []
        self.config.write_text(json.dumps(data))
        self.assertFalse(self.cli('verify')['ok'])
        self.assertTrue(self.cli('configure')['ok'])
        self.assertTrue(self.cli('verify')['ok'])

    def test_atomic_config_failure_preserves_bytes_and_retry(self):
        self.setup_case()
        self.assertTrue(self.cli('configure', '--vault', str(self.vault))['ok'])
        old = self.config.read_bytes()
        spec = importlib.util.spec_from_file_location('setup_helper', ROOT / 'skills/in-progress/setup-obsidian-workspace/scripts/setup-workspace.py')
        helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        tool = helper.renderer()
        args = Namespace(repo=str(self.repo), config=str(self.config), vault=None, generated=None, all_tickets=False, no_tickets=True, ticket_id=None, project_id=None)
        with patch.object(tool, 'atomic_write', side_effect=OSError('fixture write failure')):
            with self.assertRaisesRegex(OSError, 'fixture write failure'):
                helper.configure(args, tool)
        self.assertEqual(self.config.read_bytes(), old)
        self.assertTrue(self.cli('configure', '--no-tickets')['ok'])

    def test_exact_ignore_rule_also_covers_backup_and_lock(self):
        self.setup_case()
        self.config = self.repo / 'machine.json'
        with (self.repo / '.gitignore').open('a') as handle:
            handle.write('/machine.json\n')
        self.assertTrue(self.cli('configure', '--vault', str(self.vault))['ok'])
        result = self.cli('configure', '--no-tickets')
        self.assertTrue(result['ok'], result)
        for path in (result['backup'], str(self.config) + '.lock'):
            check = subprocess.run(['git', '-C', str(self.repo), 'check-ignore', '--quiet', path])
            self.assertEqual(check.returncode, 0)

    def test_missing_dependency_fails_before_configuration(self):
        self.setup_case()
        shutil.rmtree(self.entry.parents[2] / 'solve-records')
        result = self.cli('configure', '--vault', str(self.vault))
        self.assertFalse(result['ok'])
        self.assertIn('solve-records', result['error'])
        self.assertFalse(self.config.exists())


if __name__ == '__main__':
    unittest.main()
