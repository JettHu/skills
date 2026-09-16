#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT
python3 "$ROOT/tests/evals/ticket-amendments/prepare-fixture.py" --output "$FIXTURE"
if python3 "$ROOT/tests/evals/ticket-amendments/grade-run.py" "$FIXTURE" >"$FIXTURE/grade.log" 2>&1; then
  echo 'unamended fixture unexpectedly passed' >&2
  exit 1
fi
python3 - "$FIXTURE" <<'PY'
import json
from pathlib import Path
import subprocess
import sys
root = Path(sys.argv[1]); repo = root / 'repo'
cli = repo / '.runtime/skills/engineering/ultra/scripts/ultra_tracker.py'
def run(*args):
    return json.loads(subprocess.check_output([sys.executable, str(cli), *args, '--repo', str(repo)], text=True))['data']
for identity, predecessor, replacements in (
    ('A1', None, {'Acceptance criteria': '- [ ] Forbid all deletion.'}),
    ('A2', 'A1', {'Blocked by': '- D'}),
):
    ticket = next(t for t in run('snapshot')['tickets'] if t['key'] == 'T')
    request = root / (identity + '.json')
    request.write_text(json.dumps(dict(id=identity, ticket='T', status='approved',
        approval='approved.md: maintainer decision', predecessor=predecessor, replaces=replacements)))
    run('publication', 'amend', '--location', '.scratch/policy/issues', '--run-id', 'policy',
        '--ticket-id', 'T', '--expected-digest', ticket['publication']['current_digest'], '--amendment', str(request))
PY
python3 "$ROOT/tests/evals/ticket-amendments/grade-run.py" "$FIXTURE"
