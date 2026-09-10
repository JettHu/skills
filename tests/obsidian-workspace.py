#!/usr/bin/env python3
"""Real Snapshot -> generated workspace contract fixtures."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import os
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('snapshot_fixture', ROOT / 'tests/tracker-snapshot.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
spec = importlib.util.spec_from_file_location('workspace', ROOT / 'scripts/obsidian-workspace.py')
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


class WorkspaceTests(unittest.TestCase):
    setUp = base.SnapshotTests.setUp
    tearDown = base.SnapshotTests.tearDown
    add = base.SnapshotTests.add

    def config(self):
        vault = Path(self.tmp.name) / '中文 Vault # [x]'
        vault.mkdir(exist_ok=True)
        return {'vault': str(vault), 'generated': 'tracker-generated',
                'projects': [{'id': 'one', 'repository': str(self.repo)}]}

    def test_same_ticket_ids_have_exact_project_links(self):
        source = self.add('A', body='PRIVATE CONTRACT BODY')
        second = Path(self.tmp.name) / 'second'
        shutil.copytree(self.repo, second)
        config = self.config()
        config['projects'].append({'id': 'two', 'repository': str(second)})
        result = workspace.refresh(config)
        self.assertTrue(result['ok'], result)
        home = Path(config['vault']) / 'tracker-generated/Home.md'
        self.assertIn('one', home.read_text())
        self.assertIn('two', home.read_text())
        state = workspace.read_state(home)
        targets = []
        for identity in ('one', 'two'):
            good = state['projects'][identity]['last_success']
            board = home.parent / good['views']['Work']
            self.assertNotIn('PRIVATE CONTRACT BODY', board.read_text())
            links = re.findall(r'\]\((sources/[^)]+)\)', board.read_text())
            self.assertTrue(links)
            targets.append((board.parent / unquote(links[0])).resolve())
        self.assertEqual(targets, [source, (second / '.tracker/tickets/A.md').resolve()])

    def test_refresh_partial_failure_selection_versions_and_generated_edits(self):
        self.add('A')
        self.add('B', body='## Blocked by\n- A')
        second = Path(self.tmp.name).resolve() / 'second'
        shutil.copytree(self.repo, second)
        config = self.config()
        config['projects'].append({'id': 'two', 'repository': str(second)})
        self.assertTrue(workspace.refresh(config)['ok'])
        home = Path(config['vault']) / 'tracker-generated/Home.md'
        initial = home.read_bytes()
        state = workspace.read_state(home)
        board = home.parent / state['projects']['one']['last_success']['views']['Work']
        content = board.read_bytes()
        self.assertTrue(workspace.refresh(config)['ok'])
        self.assertEqual(home.read_bytes(), initial)
        board.write_text(board.read_text() + '\n## USER DRAG EDIT\n')
        self.assertTrue(workspace.refresh(config)['ok'])
        state = workspace.read_state(home)
        restored = home.parent / state['projects']['one']['last_success']['views']['Work']
        self.assertEqual(restored.read_bytes(), content)
        old_two = state['projects']['two']['last_success']
        old_two_board = (home.parent / old_two['views']['Work']).read_bytes()
        (second / 'docs/agents/ultra-tracker.md').unlink()
        config['projects'][0]['selection'] = ['B']
        result = workspace.refresh(config)
        self.assertFalse(result['ok'])
        self.assertTrue(result['persisted'])
        self.assertIn('partial failure', home.read_text())
        state = workspace.read_state(home)
        self.assertEqual(state['projects']['two']['last_success'], old_two)
        self.assertEqual((home.parent / old_two['views']['Work']).read_bytes(), old_two_board)
        good = state['projects']['one']['last_success']
        self.assertEqual(good['selection'], ['B'])
        self.assertNotEqual(good['render_signature'], old_two['render_signature'])
        selected_board = (home.parent / good['views']['Work']).read_text()
        self.assertIn('returned', selected_board)
        with patch.object(workspace, 'RENDERER_VERSION', 'next'):
            workspace.refresh(config)
        upgraded = workspace.read_state(home)['projects']['one']['last_success']
        self.assertNotEqual(upgraded['render_signature'], good['render_signature'])


    def test_home_publication_barrier_and_persistence_failure(self):
        self.add('A')
        config = self.config()
        self.assertTrue(workspace.refresh(config)['ok'])
        home = Path(config['vault']) / 'tracker-generated/Home.md'
        before = home.read_bytes()
        self.add('B')
        replace = os.replace
        def barrier(source, target):
            self.assertEqual(home.read_bytes(), before)
            pending = workspace.read_state(Path(source))
            for entry in pending['projects'].values():
                for path in entry['last_success']['views'].values():
                    self.assertTrue((home.parent / path).is_file())
            raise OSError('controlled commit-point failure')
        with patch.object(os, 'replace', side_effect=barrier):
            result = workspace.refresh(config)
        self.assertFalse(result['persisted'])
        self.assertEqual(home.read_bytes(), before)
        (self.repo / 'docs/agents/ultra-tracker.md').unlink()
        with patch.object(os, 'fsync', side_effect=OSError('status persistence denied')):
            result = workspace.refresh(config)
        self.assertFalse(result['persisted'])
        self.assertEqual(home.read_bytes(), before)
        self.assertFalse(list(home.parent.glob('.refresh-*')))

    def test_special_characters_missing_links_and_plain_markdown(self):
        source = base.write(self.repo, '.tracker/tickets/中文 空格 # | [x].md',
                            base.ticket('A', body='PRIVATE BODY'))
        context = base.write(self.repo, 'docs/中文 # | [x].md', 'FULL SOURCE')
        source.write_text(source.read_text().replace('Ticket ID: A', 'Ticket ID: A\nSource Spec: docs/中文 # | [x].md'))
        config = self.config()
        self.assertTrue(workspace.refresh(config)['ok'])
        home = Path(config['vault']) / 'tracker-generated/Home.md'
        state = workspace.read_state(home)
        board = home.parent / state['projects']['one']['last_success']['views']['Work']
        content = board.read_text()
        targets = [(board.parent / unquote(path)).resolve() for path in re.findall(r'\]\((sources/[^)]+)\)', content)]
        self.assertIn(source, targets)
        self.assertIn(context, targets)
        self.assertIn('## Claimable', content)
        self.assertNotIn('PRIVATE BODY', content)
        self.assertIn('&#35;', content)
        self.assertIn('&#124;', content)
        context.unlink()
        self.assertTrue(workspace.refresh(config)['ok'])
        board = home.parent / workspace.read_state(home)['projects']['one']['last_success']['views']['Work']
        self.assertIn('source unavailable', board.read_text())

    def test_candidate_recovery_publication_and_resource_attention(self):
        self.add('A')
        self.add('B', state='ready-for-human')
        self.add('C', state='review-pending', extra='Publication Run: unpublished')
        self.add('D', extra='Flags: solve-in-progress\nSolve Branch: missing-branch\nSolve Worktree: missing-worktree')
        self.add('E', body='## Blocked by\n- C')
        command = [sys.executable, str(base.SCRIPTS / 'ultra_tracker.py')]
        frontier, _, _, _ = base.frontier.frontier(self.repo, [])
        wt = Path(self.tmp.name).resolve() / 'candidate'
        subprocess.run(command + ['ticket', 'claim', '--repo', str(self.repo), '--ticket-id', 'A',
                                 '--expected-snapshot', frontier['snapshot'], '--branch', 'candidate', '--worktree', str(wt)], check=True, stdout=subprocess.DEVNULL)
        base.git(self.repo, 'worktree', 'add', '-b', 'candidate', str(wt))
        base.write(wt, 'result.txt', 'complete')
        base.git(wt, 'add', '.')
        base.git(wt, 'commit', '-qm', 'candidate')
        subprocess.run(command + ['ticket', 'handoff', '--repo', str(self.repo), '--ticket-id', 'A',
                                 '--handoff-key', 'projection', '--outcome', 'candidate', '--summary', 'finished'], check=True, stdout=subprocess.DEVNULL)
        # Canonical recovery and historical parser fixtures, no display-side parser.
        base.write(self.repo, '.scratch/old/solve-records/recovery.md',
                   '---\nid: recovery\nstate: open\noutcome: blocked\nrecovery_action: decide\n---\n# Recovery\n')
        base.write(self.repo, '.scratch/old/solve-records/history.md',
                   '---\nid: history\nstate: closed\noutcome: abandoned\n---\n# History\n')
        config = self.config()
        self.assertTrue(workspace.refresh(config)['ok'])
        home = Path(config['vault']) / 'tracker-generated/Home.md'
        good = workspace.read_state(home)['projects']['one']['last_success']
        views = {name: (home.parent / path).read_text() for name, path in good['views'].items()}
        self.assertIn('## Completed Tickets', views['Work'])
        for text in ('Outcome: candidate', 'Human acceptance:', 'Landing evidence:', 'Cleanup evidence:', '## Recovery', '## Closed and historical'):
            self.assertIn(text, views['Delivery'])
        for text in ('missing&#95;solve&#95;branch', 'Publication', 'Dependency', 'Diagnostic', 'Operation observations'):
            self.assertIn(text, views['Attention'])



if __name__ == '__main__': unittest.main()
