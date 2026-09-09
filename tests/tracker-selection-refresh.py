#!/usr/bin/env python3
"""Selected Snapshot and single-artifact refresh through real owner boundaries."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
base_spec = importlib.util.spec_from_file_location('snapshot_fixture', ROOT / 'tests/tracker-snapshot.py')
base = importlib.util.module_from_spec(base_spec); base_spec.loader.exec_module(base)
query = base.query
spec = importlib.util.spec_from_file_location('board_refresh', ROOT / 'skills/in-progress/maintainer-board/scripts/maintainer-board.py')
board = importlib.util.module_from_spec(spec); spec.loader.exec_module(board)


class SelectionRefreshTests(unittest.TestCase):
    setUp = base.SnapshotTests.setUp
    tearDown = base.SnapshotTests.tearDown
    add = base.SnapshotTests.add
    snapshot = base.SnapshotTests.snapshot

    def test_selection_full_equivalence_and_relationships(self):
        self.add('A', state='completed')
        self.add('B', body='## Blocked by\n- A\n## Solve Records\n- ../solve-records/missing.md')
        full = self.snapshot(); selected = query.snapshot(self.repo, ['B', 'B'])
        self.assertEqual(full['source_fingerprint'], selected['source_fingerprint'])
        b = selected['tickets'][0]; original = next(item for item in full['tickets'] if item['key'] == 'B')
        for field in ('eligibility', 'publication', 'diagnostics', 'claim'): self.assertEqual(b[field], original[field])
        self.assertEqual(b['blockers'][0]['ticket_key'], 'A')
        self.assertEqual(b['blockers'][0]['resolution'], 'resolved')
        self.assertFalse(b['blockers'][0]['returned']); self.assertTrue(b['blockers'][0]['satisfied'])
        self.assertEqual(b['receipt_relations'][0]['resolution'], 'source-missing')
        self.assertEqual(selected['selection']['requested'], ['B'])
        self.assertEqual(query.snapshot(self.repo, [])['tickets'], [])
        missing = query.snapshot(self.repo, ['unknown'])
        self.assertEqual(missing['selection']['missing'], ['unknown']); self.assertFalse(missing['tickets'])
        self.assertEqual(missing['source_fingerprint'], full['source_fingerprint'])
        with patch.object(query, 'SEMANTIC_VERSION', 'test-next-semantics'):
            self.assertNotEqual(self.snapshot()['source_fingerprint'], full['source_fingerprint'])

    def test_global_fatal_cycles_invalid_sources_not_bypassed(self):
        self.add('A', body='## Blocked by\n- B'); self.add('B', body='## Blocked by\n- A')
        full = self.snapshot(); selected = query.snapshot(self.repo, ['B'])
        self.assertEqual(selected['tickets'][0]['eligibility'], next(t for t in full['tickets'] if t['key'] == 'B')['eligibility'])
        self.assertIn('dependency-cycle', selected['tickets'][0]['eligibility']['reasons'])
        (self.repo / '.tracker/tickets/A.md').write_text(base.ticket('A', state='unknown'))
        selected = query.snapshot(self.repo, ['B'])
        self.assertEqual(selected['tickets'][0]['blockers'][0]['resolution'], 'invalid-source')
        malformed = query.snapshot(self.repo, ['A'])
        self.assertFalse(malformed['selection']['missing'])
        self.assertTrue(malformed['tickets'][0]['key'].startswith('malformed:'))
        base.write(self.repo, '.tracker/tickets/duplicate.md', base.ticket('B', state='unknown'))
        for selection in ([], ['unknown'], ['A']):
            with self.assertRaises(query.SnapshotError): query.snapshot(self.repo, selection)

    def test_signatures_effective_options_and_selection(self):
        self.assertEqual(board.render_signature(['B','A','A']), board.render_signature(['A','B'], {'visible_items':5}))
        self.assertNotEqual(board.render_signature(None), board.render_signature([]))
        self.assertNotEqual(board.render_signature(['A']), board.render_signature(['A'], {'visible_items':2}))
        self.add('A')
        output = self.output(); board.write_html(board.build_snapshot(self.repo, ['A']), output)
        self.assertEqual(board.read_artifact(output)[1]['last_success']['selection'], ['A'])
        html = board.render_html(board.build_snapshot(self.repo, ['<missing>']))
        self.assertIn('Exact keys absent from source: &lt;missing&gt;', html)
        before = board.render_signature(['A'])
        with patch.object(board, 'RENDERER_VERSION', 'renderer/next'): self.assertNotEqual(before, board.render_signature(['A']))

    def output(self): return Path(self.tmp.name).resolve() / 'board.html'

    def test_noop_failure_recovery_and_generation_binding(self):
        self.add('A', body='A harmless title <tag>')
        output = self.output(); first = board.refresh(self.repo, output, ['A'])
        self.assertTrue(first['ok']); before = output.read_bytes(); modified = output.stat().st_mtime_ns
        second = board.refresh(self.repo, output, ['A','A'])
        self.assertEqual(second['status'], 'unchanged'); self.assertEqual(output.stat().st_mtime_ns, modified)
        body, state = board.read_artifact(output)
        original_body = body; generation = state['last_success']['generation']
        with patch.object(board, 'build_snapshot', side_effect=RuntimeError('read failed </script><script>bad</script>')):
            failed = board.refresh(self.repo, output, ['B'])
        self.assertFalse(failed['ok']); self.assertTrue(failed['persisted'])
        body, state = board.read_artifact(output)
        self.assertEqual(body, original_body); self.assertEqual(state['latest_refresh']['generation'], generation)
        self.assertEqual(state['last_success']['selection'], ['A']); self.assertEqual(state['latest_refresh']['attempted']['selection'], ['B'])
        self.assertIn('Latest refresh failed', output.read_text()); self.assertNotIn('</script><script>bad', output.read_text())
        recovered = board.refresh(self.repo, output, ['A'])
        self.assertTrue(recovered['ok']); self.assertEqual(output.read_bytes(), before)
        self.assertEqual(recovered['generation'], generation)
        with patch.object(board, 'RENDERER_VERSION', 'renderer/next'):
            changed = board.refresh(self.repo, output, ['A'])
        self.assertTrue(changed['ok']); self.assertNotEqual(changed['generation'], generation)

    def test_query_render_and_persistence_failures_keep_body(self):
        self.add('A'); output = self.output(); self.assertTrue(board.refresh(self.repo, output)['ok'])
        before = output.read_bytes()
        with patch.object(board, 'render_html', side_effect=RuntimeError('render failed')):
            failed = board.refresh(self.repo, output)
        self.assertFalse(failed['ok']); self.assertTrue(failed['persisted'])
        self.assertEqual(board.read_artifact(output)[1]['latest_refresh']['status'], 'failed')
        board.refresh(self.repo, output)
        self.assertEqual(output.read_bytes(), before)
        self.add('B')
        with patch.object(board.os, 'replace', side_effect=OSError('replace denied')):
            result = board.refresh(self.repo, output)
        self.assertEqual(result['error']['code'], 'artifact-replace-failed'); self.assertEqual(output.read_bytes(), before)
        with patch.object(board, 'build_snapshot', side_effect=RuntimeError('query unavailable')), patch.object(board.os, 'write', side_effect=OSError('status write denied')):
            result = board.refresh(self.repo, output)
        self.assertFalse(result['persisted']); self.assertIn('persistence_error', result)
        self.assertEqual(output.read_bytes(), before)
        self.assertFalse(list(output.parent.glob('.board.html.*.tmp')))
        output.write_text(output.read_text().replace('"generation":"', '"generation":"tampered', 1))
        tampered = output.read_bytes()
        with patch.object(board, 'build_snapshot', side_effect=RuntimeError('query unavailable')):
            result = board.refresh(self.repo, output)
        self.assertFalse(result['persisted']); self.assertEqual(output.read_bytes(), tampered)

    def candidate(self):
        self.add('A'); self.add('B')
        read, _, _, _ = base.frontier.frontier(self.repo, [])
        wt = Path(self.tmp.name).resolve() / 'candidate'
        command = [sys.executable, str(base.SCRIPTS / 'ultra_tracker.py')]
        for identity in ['A','B']:
            read, _, _, _ = base.frontier.frontier(self.repo, [])
            subprocess.run(command + ['ticket','claim','--repo',str(self.repo),'--ticket-id',identity,'--expected-snapshot',read['snapshot'],'--branch','candidate','--worktree',str(wt)], check=True, stdout=subprocess.DEVNULL)
        base.git(self.repo, 'worktree', 'add', '-b', 'candidate', str(wt))
        base.write(wt,'result.txt','done\n'); base.git(wt,'add','.'); base.git(wt,'commit','-qm','candidate')
        return command

    def test_real_handoff_barrier_and_group_selection(self):
        self.candidate()
        barrier = Path(self.tmp.name).resolve() / 'written'; release = Path(self.tmp.name).resolve() / 'release'
        script = '''import json,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import local_outcome_handoff as handoff
original=handoff.publication.atomic_write
paused=False
def write(path,text):
 global paused
 original(path,text)
 if 'solve-records' in path.parts and not paused:
  paused=True
  Path(sys.argv[3]).write_text('receipt installed under owner lock')
  deadline=time.monotonic()+10
  while not Path(sys.argv[4]).exists():
   if time.monotonic()>deadline: raise RuntimeError('barrier release timeout')
   time.sleep(.01)
handoff.publication.atomic_write=write
print(json.dumps(handoff.handoff(Path(sys.argv[2]),['A','B'],'barrier','candidate','bounded real handoff','',[])))
'''
        process = subprocess.Popen([sys.executable,'-c',script,str(base.SCRIPTS),str(self.repo),str(barrier),str(release)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline=time.monotonic()+8
            while not barrier.exists() and process.poll() is None and time.monotonic()<deadline: time.sleep(.01)
            self.assertTrue(barrier.exists())
            start=time.monotonic()
            with self.assertRaises(query.SnapshotError) as error: query.snapshot(self.repo,['B'])
            self.assertEqual(error.exception.code,'observation-busy'); self.assertLess(time.monotonic()-start,2)
            release.write_text('continue')
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode,0,stderr); self.assertEqual(json.loads(stdout)['status'],'success')
        finally:
            if process.poll() is None: process.kill(); process.communicate()
        full=self.snapshot(); selected=query.snapshot(self.repo,['B'])
        self.assertEqual(full['source_fingerprint'],selected['source_fingerprint'])
        receipt=selected['receipts'][0]
        self.assertEqual(receipt['handoff_consistency']['status'],'consistent')
        relation=next(r for r in receipt['ticket_relations'] if r['ticket_key']=='A')
        self.assertEqual(relation['resolution'],'resolved'); self.assertFalse(relation['returned'])

    def test_real_interrupted_handoff_same_key_recovery(self):
        command=self.candidate()+['ticket','handoff','--repo',str(self.repo),'--ticket-id','A','--ticket-id','B','--handoff-key','interrupted','--outcome','candidate','--summary','real interrupted fixture']
        result=subprocess.run(command,env={**os.environ,'ULTRA_HANDOFF_FAIL_AFTER_RECEIPT':'1'},capture_output=True,text=True)
        self.assertEqual(result.returncode,6,result.stdout+result.stderr)
        interrupted=query.snapshot(self.repo,['B']); self.assertTrue(interrupted['summary']['incomplete'])
        self.assertEqual(interrupted['receipts'][0]['handoff_consistency']['status'],'inconsistent')
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        recovered=query.snapshot(self.repo,['B']); self.assertFalse(recovered['summary']['incomplete'])
        self.assertEqual(recovered['summary']['receipt_count'],1)
        self.assertNotEqual(interrupted['source_fingerprint'],recovered['source_fingerprint'])


if __name__=='__main__': unittest.main()
