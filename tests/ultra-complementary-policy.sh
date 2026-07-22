#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/test_prospective_policy.py" \
  "$TMP/prospective-policy"

echo "prospective policy authority fixture passed"
