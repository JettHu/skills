#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PREPARE="$ROOT/.evals/ultra-remote-ticket-publication/scripts/prepare-fixture.py"
GRADER="$ROOT/.evals/ultra-remote-ticket-publication/scripts/grade-run.py"
ADAPTER="$ROOT/skills/engineering/ultra/scripts/remote_ticket_publication.py"
TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

python3 -m py_compile "$PREPARE" "$GRADER"
python3 "$PREPARE" --output "$TMPROOT/runs"
for scenario in 01-github-remote 03-github-staging-resume 04-gitlab-staging-resume; do
  provider="${scenario#??-}"; provider="${provider%%-*}"
  if [[ "$scenario" == *staging* ]]; then
    python3 "$ADAPTER" publish --provider "$provider" --strategy local-staging --run-id "$scenario" --spec "$TMPROOT/runs/$scenario/SPEC.json" --remote-state "$TMPROOT/runs/$scenario/REMOTE.json" --staging-root "$TMPROOT/runs/$scenario/.scratch/.ultra-staging" --reviewed >/dev/null
  else
    python3 "$ADAPTER" publish --provider "$provider" --strategy remote-review-pending --run-id "$scenario" --spec "$TMPROOT/runs/$scenario/SPEC.json" --remote-state "$TMPROOT/runs/$scenario/REMOTE.json" --reviewed >/dev/null
  fi
done
printf 'Release owner unresolved.\n' >"$TMPROOT/runs/02-gitlab-remote-human/ESCALATION.md"
python3 "$GRADER" "$TMPROOT/runs" | grep -Fq '"passed": true'
echo "ultra remote publication eval fixture passed"
