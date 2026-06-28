#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

find "$REPO/skills" \
  -name SKILL.md \
  -not -path '*/node_modules/*' \
  -not -path '*/deprecated/*' \
  -print0 |
  while IFS= read -r -d '' skill_md; do
    dir="$(dirname "$skill_md")"
    rel="${dir#"$REPO"/}"
    name="$(basename "$dir")"
    printf '%s\t%s\n' "$name" "$rel"
  done |
  sort
