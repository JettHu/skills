#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PREPARE="$ROOT/.evals/ultra-solve-afk-safe-planning/scripts/prepare-fixture.py"
GRADER="$ROOT/.evals/ultra-solve-afk-safe-planning/scripts/grade-run.py"
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

python3 -m py_compile "$PREPARE" "$GRADER"
python3 "$PREPARE" --output "$TMPDIR_ROOT" --run-id fixtures --scenario all --treatment-ref HEAD

python3 - "$TMPDIR_ROOT/fixtures" <<'PY'
import json
import sys
from pathlib import Path

run = Path(sys.argv[1])
expectations = sorted(run.glob("*/repo/EVAL_EXPECTATIONS.json"))
assert [path.parent.parent.name for path in expectations] == [
    "01-simple",
    "02-fanout-preedit",
    "03-first-deviation",
    "04-stale-hint",
    "05-recovery-handoff",
    "06-no-digest-residue",
]
for path in expectations:
    repo = path.parent
    expectation = json.loads(path.read_text(encoding="utf-8"))
    issue_path = expectation["issue_path"]
    issue = (repo / issue_path).read_text(encoding="utf-8")
    prompt = (repo / "EVAL_PROMPT.md").read_text(encoding="utf-8")
    assert issue_path in prompt
    assert "Context:" not in issue
    assert "## Execution Digest" not in issue
    assert (repo / "skills/engineering/solve-records/scripts/solve-records.py").is_file()
PY

STALE="$TMPDIR_ROOT/fixtures/04-stale-hint/repo"
if python3 "$GRADER" "$STALE"; then
  echo "base fixture unexpectedly passed" >&2
  exit 1
fi

echo "ultra solve eval harness fixture passed"
