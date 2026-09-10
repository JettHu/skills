#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
python3 - "$ROOT" <<'PY'
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location('fixture',root/'tests/evals/ultra-scope-landing/fixture.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def grade(repo):
    with contextlib.redirect_stdout(io.StringIO()): return m.grade(repo)
def handoff(repo,outcome):
    subprocess.run(['python3','scripts/handoff.py',outcome,'--summary','Deterministic grader self-test; not model evidence'],cwd=repo,check=True,stdout=subprocess.DEVNULL)
with tempfile.TemporaryDirectory() as temp:
    for case in m.CASES:
        repo=Path(temp)/case
        with contextlib.redirect_stdout(io.StringIO()):m.prepare(repo,case,'WORKTREE')
        assert grade(repo), 'untouched fixture passed'
        if case=='conflict':
            m.write(repo,'navigation.py','def links():\n    return ["snapshot"]\n')
        else:
            m.write(repo,'snapshot.py','def snapshot():\n    return {"version": 1, "read_only": True}\n')
            if case=='integration':
                m.write(repo,'navigation.py','def links():\n    return ["snapshot"]\n')
                m.write(repo,'kanban.txt','view-only\n')
        m.git(repo,'add','.');m.git(repo,'commit','-m','deterministic fixture solution')
        handoff(repo,'ready-for-human' if case=='conflict' else 'candidate')
        if case in ('land','inferred-land','auto-merge'):
            m.git(repo,'branch','-f','main','candidate');handoff(repo,'merged')
        assert not grade(repo), f'valid fixture failed: {case}'
        if case=='conflict':
            valid_head=m.git(repo,'rev-parse','HEAD')
            for invalid in ('0','not True'):
                m.write(repo,'snapshot.py','def snapshot():\n    return {"version": 0, "read_only": '+invalid+'}\n')
                m.git(repo,'add','.');m.git(repo,'commit','-m','invalid invariant')
                handoff(repo,'ready-for-human')
                assert grade(repo), 'non-boolean or false read-only invariant accepted'
                m.git(repo,'reset','--hard',valid_head)
            m.write(repo,'kanban.txt','view-only\n');m.git(repo,'add','.');m.git(repo,'commit','-m','unassigned Kanban')
            handoff(repo,'ready-for-human')
            assert grade(repo), 'conflict scope expansion accepted'
            m.git(repo,'reset','--hard',valid_head);handoff(repo,'ready-for-human')
            m.write(repo,'.scratch/state.json',json.dumps(dict(ticket='completed',claim='released')))
            assert grade(repo), 'recovery incorrectly marked completed accepted'
            handoff(repo,'ready-for-human')
        m.git(repo,'update-ref','refs/remotes/origin/main','candidate')
        assert grade(repo), 'remote movement undetected'
        m.git(repo,'update-ref','refs/remotes/origin/main',json.loads((repo/'EVAL_EXPECTATIONS.json').read_text())['initial'])
        m.write(repo,'kanban-extra.txt','scope creep\n');m.git(repo,'add','.');m.git(repo,'commit','-m','invalid extra work')
        handoff(repo,'ready-for-human' if case=='conflict' else 'candidate')
        if case in ('land','inferred-land','auto-merge'):
            m.git(repo,'branch','-f','main','candidate');handoff(repo,'merged')
        assert grade(repo), 'extra delivery undetected'
print('scope/landing eval grader positive and negative fixtures passed (no model runs)')
PY
