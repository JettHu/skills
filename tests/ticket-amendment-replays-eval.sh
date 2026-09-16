#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FIXTURE="$TMP/fixture"
python3 "$ROOT/tests/evals/ticket-amendment-replays/fixture.py" prepare "$FIXTURE"
if python3 "$ROOT/tests/evals/ticket-amendment-replays/fixture.py" grade "$FIXTURE" >"$TMP/untouched.log" 2>&1; then
  echo 'unexecuted replay fixture unexpectedly passed' >&2
  exit 1
fi
CLI="$FIXTURE/runtime/skills/engineering/ultra/scripts/ultra_tracker.py"
python3 "$CLI" solve-record landing-plan --repo "$FIXTURE/canonical" \
  --record .scratch/feature/solve-records/candidate.md --target-repo "$FIXTURE/companion" >"$FIXTURE/landing.json"
if python3 "$CLI" ticket handoff --repo "$FIXTURE/recovery" --ticket-id T --handoff-key old-contract \
  --outcome blocked --summary 'Recover after inspection.' --recovery-next-action inspect >"$FIXTURE/old.json"; then
  echo 'old recovery key unexpectedly succeeded' >&2
  exit 1
fi
python3 "$CLI" ticket handoff --repo "$FIXTURE/recovery" --ticket-id T --handoff-key current-contract \
  --outcome blocked --summary 'Recover after inspection.' --recovery-next-action inspect >"$FIXTURE/current.json"
python3 "$ROOT/tests/evals/ticket-amendment-replays/fixture.py" grade "$FIXTURE"
