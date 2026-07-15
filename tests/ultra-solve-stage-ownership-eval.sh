#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PREPARE="$ROOT/tests/evals/ultra-solve-stage-ownership/prepare-fixture.py"
GRADER="$ROOT/tests/evals/ultra-solve-stage-ownership/grade-run.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 -m py_compile "$PREPARE" "$GRADER"
python3 "$PREPARE" --output "$TMP" --run-id fixture --scenario all --treatment-ref working-tree

python3 - "$TMP/fixture" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
expectations = sorted(root.glob("*/repo/EVAL_EXPECTATIONS.json"))
assert [path.parent.parent.name for path in expectations] == [
    "01-direct-all-evidence",
    "02-delegated-unproven",
    "03-preferred-read-only",
    "04-root-read-only-exception",
    "05-dependent-serialized",
    "06-autonomous-repair",
    "07-human-owned-escalation",
]
for path in expectations:
    data = json.loads(path.read_text(encoding="utf-8"))
    repo = path.parent
    assert (repo / data["issue_path"]).is_file()
    assert "stage-evidence.json" in (repo / "EVAL_PROMPT.md").read_text(encoding="utf-8")
    assert "`review_actions` array" in (repo / "EVAL_PROMPT.md").read_text(encoding="utf-8")
    solve = (repo / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")
    assert "## Stage Ownership" in solve
PY

if python3 "$GRADER" "$TMP/fixture"; then
  echo "unexecuted stage-ownership fixtures unexpectedly passed" >&2
  exit 1
fi

echo "ultra solve stage ownership eval harness fixture passed"
