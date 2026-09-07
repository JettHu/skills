#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PREPARE="$ROOT/tests/evals/ultra-solve-context-routing/prepare-fixture.py"
GRADER="$ROOT/tests/evals/ultra-solve-context-routing/grade-run.py"
FIXTURE_ROOT="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_ROOT"' EXIT

python3 -m py_compile "$PREPARE" "$GRADER"
python3 "$PREPARE" --output "$FIXTURE_ROOT"

for repo in "$FIXTURE_ROOT"/*/repo; do
  if python3 "$GRADER" "$repo"; then
    echo "untouched context-routing fixture unexpectedly passed: $repo" >&2
    exit 1
  fi
done

echo "ultra solve context-routing eval harness fixture passed"
