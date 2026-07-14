#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PREPARE="$ROOT/.evals/ultra-solve-expand-contract/scripts/prepare-fixture.py"
GRADER="$ROOT/.evals/ultra-solve-expand-contract/scripts/grade-run.py"
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

python3 -m py_compile "$PREPARE" "$GRADER"
python3 "$PREPARE" --output "$TMPDIR_ROOT/fixture" --treatment-ref HEAD >/dev/null

if python3 "$GRADER" "$TMPDIR_ROOT/fixture/repo"; then
  echo "untouched shared-integration fixture unexpectedly passed" >&2
  exit 1
fi

echo "ultra solve expand-contract eval harness fixture passed"
