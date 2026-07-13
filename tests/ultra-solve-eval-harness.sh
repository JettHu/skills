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
    "07-failed-check-retained",
    "08-resume-reuse",
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
    assert (repo / "skills/engineering/solve-records/references/edge-cases.md").is_file()

failed = run / "07-failed-check-retained/repo"
failed_expectation = json.loads((failed / "EVAL_EXPECTATIONS.json").read_text(encoding="utf-8"))["expected"]
assert failed_expectation["outcome"] == "blocked"
assert failed_expectation["required_check_fails"] is True

resume = run / "08-resume-reuse/repo"
resume_expectation = json.loads((resume / "EVAL_EXPECTATIONS.json").read_text(encoding="utf-8"))["expected"]
initial_receipt = resume / resume_expectation["initial_receipt_path"]
assert "outcome: blocked" in initial_receipt.read_text(encoding="utf-8")
assert resume_expectation["receipt_count"] == 1
assert (run / "08-resume-reuse/resume-worktree").is_dir()
PY

for BASE in \
  "$TMPDIR_ROOT/fixtures/04-stale-hint/repo" \
  "$TMPDIR_ROOT/fixtures/07-failed-check-retained/repo" \
  "$TMPDIR_ROOT/fixtures/08-resume-reuse/repo"
do
  if python3 "$GRADER" "$BASE"; then
    echo "base fixture unexpectedly passed: $BASE" >&2
    exit 1
  fi
done

echo "ultra solve eval harness fixture passed"
