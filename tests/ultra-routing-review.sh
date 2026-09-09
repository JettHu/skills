#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
python3 - "$ROOT" <<'PY'
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
root=Path(sys.argv[1])
profiles=(root/'skills/engineering/ultra/PROFILES.md').read_text()
section=profiles.split('## Skill aliases\n',1)[1].split('## Pre-target',1)[0]
rows=[tuple(c.strip() for c in line.strip('|').split('|')[:2]) for line in section.splitlines() if line.startswith('| ')][1:]
assert len(dict(rows)) == len(rows), 'alias names must be unique'
assert dict(rows) == {'diagnose':'diagnosing-bugs','write-a-skill':'writing-for-agents','writing-great-skills':'writing-for-agents'}
for requested, canonical in rows:
    assert canonical not in dict(rows), 'aliases must resolve in one step'
for name in ('ultra-solve','ultra-diagnose','ultra-to-spec','ultra-to-tickets'):
    skill=(root/f'skills/engineering/{name}/SKILL.md').read_text()
    metadata=(root/f'skills/engineering/{name}/agents/openai.yaml').read_text()
    assert 'disable-model-invocation: true' in skill
    assert 'allow_implicit_invocation: false' in metadata
    assert 'Delegate to the `ultra` skill' in skill
spec=importlib.util.spec_from_file_location('fixture', root/'tests/evals/ultra-routing-review/fixture.py')
fixture=importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
with tempfile.TemporaryDirectory() as tmp:
    output=Path(tmp)/'cases'; fixture.prepare(root,output)
    transcript=Path(tmp)/'run.jsonl'
    transcript.write_text(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'cost.py charges an empty batch 3 instead of 0.'}})+'\n')
    for case in fixture.CASES:
        try: fixture.grade(output/case)
        except AssertionError: pass
        else: raise AssertionError('unexecuted fixture passed')
    # Behavioral graders must reject a report-only implementation and a mutated review.
    try: fixture.grade(output/'implementation',transcript)
    except subprocess.CalledProcessError: pass
    else: raise AssertionError('unrepaired implementation passed')
    (output/'implementation/cost.py').write_text('def cost(items):\n    return len(items) * 3\n')
    fixture.grade(output/'implementation',transcript)
    fixture.grade(output/'review-only',transcript)
    (output/'implementation/check.py').write_text('pass\n')
    try: fixture.grade(output/'implementation',transcript)
    except AssertionError: pass
    else: raise AssertionError('modified validation passed')
    (output/'review-only/cost.py').write_text('changed\n')
    try: fixture.grade(output/'review-only',transcript)
    except AssertionError: pass
    else: raise AssertionError('mutated review passed')
print('Ultra routing metadata and behavioral grader checks passed')
PY
