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
for scenario in 01-github-remote-review-fix 02-gitlab-remote-review-fix; do
  provider="${scenario#??-}"; provider="${provider%%-*}"
  if python3 "$ADAPTER" publish --provider "$provider" --strategy remote-review-pending --run-id "$scenario" --spec "$TMPROOT/runs/$scenario/SPEC.json" --remote-state "$TMPROOT/runs/$scenario/REMOTE.json" --reviewed --fail-at verify >/dev/null 2>&1; then
    echo "remote review-fix fixture unexpectedly skipped partial failure" >&2; exit 1
  fi
  cp "$TMPROOT/runs/$scenario/REMOTE.json" "$TMPROOT/runs/$scenario/PARTIAL_STATE.json"
  python3 - "$TMPROOT/runs/$scenario/REMOTE.json" <<'PY'
import json, sys
path = sys.argv[1]
state = json.load(open(path))
state["tickets"][0]["body"] = state["tickets"][0]["body"].replace("Parent", "Reviewer-fixed Parent", 1)
json.dump(state, open(path, "w"))
PY
  python3 "$ADAPTER" publish --provider "$provider" --strategy remote-review-pending --run-id "$scenario" --spec "$TMPROOT/runs/$scenario/SPEC.json" --remote-state "$TMPROOT/runs/$scenario/REMOTE.json" --reviewed >/dev/null
done
for scenario in 03-github-staging-partial-resume 04-gitlab-staging-partial-resume; do
  provider="${scenario#??-}"; provider="${provider%%-*}"
  root="$TMPROOT/runs/$scenario"
  if python3 "$ADAPTER" publish --provider "$provider" --strategy local-staging --run-id "$scenario" --spec "$root/SPEC.json" --remote-state "$root/REMOTE.json" --staging-root "$root/.scratch/.ultra-staging" --reviewed --fail-at wire >/dev/null 2>&1; then
    echo "staging fixture unexpectedly skipped partial failure" >&2; exit 1
  fi
  cp "$root/.scratch/.ultra-staging/$scenario/manifest.json" "$root/PARTIAL_MANIFEST.json"
  python3 "$ADAPTER" publish --provider "$provider" --strategy local-staging --run-id "$scenario" --spec "$root/SPEC.json" --remote-state "$root/REMOTE.json" --staging-root "$root/.scratch/.ultra-staging" --reviewed >/dev/null
done
printf 'Release owner unresolved.\n' >"$TMPROOT/runs/05-gitlab-remote-human/ESCALATION.md"
python3 "$GRADER" "$TMPROOT/runs" | grep -Fq '"passed": true'
echo "ultra remote publication eval fixture passed"
