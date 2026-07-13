#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PREPARE="$REPO_ROOT/.evals/ultra-local-ticket-publication/scripts/prepare-fixture.py"
GRADER="$REPO_ROOT/.evals/ultra-local-ticket-publication/scripts/grade-run.py"
TMPDIR_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ultra-local-publication-eval.XXXXXX")"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

RUN="$TMPDIR_ROOT/run"
python3 "$PREPARE" --source "$REPO_ROOT" --output "$RUN" >/dev/null

python3 - "$RUN" <<'PY'
from pathlib import Path
import json
import subprocess
import sys

run = Path(sys.argv[1])
manifest = json.loads((run / "contract-manifest.json").read_text(encoding="utf-8"))
adapter = run / "skill-input/skills/engineering/ultra/scripts/local_ticket_publication.py"
root = run / "scenarios/01-derivable-review-fix"
repo = root / "repo"
(repo / ".scratch/feature/tickets.md").write_text("""# Formal Tickets

<!-- ultra-ticket:begin id=RECOVERY-BACKEND -->
Status: review-pending
Ticket ID: RECOVERY-BACKEND
Publication Run: derivable-run
Source Spec: APPROVED_SPEC.md
Blocked By:
Flags:

## Ticket RECOVERY-BACKEND
Backend token rotation unit test coverage.
Validation: pytest tests/test_token_rotation.py
<!-- ultra-ticket:end -->

<!-- ultra-ticket:begin id=RECOVERY-FRONTEND -->
Status: review-pending
Ticket ID: RECOVERY-FRONTEND
Publication Run: derivable-run
Source Spec: APPROVED_SPEC.md
Blocked By:
Flags:

## Ticket RECOVERY-FRONTEND
Frontend recovery UI component test coverage.
Validation: pnpm test -- recovery-ui
<!-- ultra-ticket:end -->
""", encoding="utf-8")
base = [sys.executable, str(adapter), "--repo", str(repo), "--representation", "tickets-file", "--location", ".scratch/feature/tickets.md", "--run-id", "derivable-run"]
subprocess.run([sys.executable, str(adapter), "register", "--repo", str(repo), "--representation", "tickets-file", "--location", ".scratch/feature/tickets.md", "--run-id", "derivable-run", "--allow-membership-change"], check=True, stdout=subprocess.DEVNULL)
subprocess.run([sys.executable, str(adapter), "promote", "--repo", str(repo), "--representation", "tickets-file", "--location", ".scratch/feature/tickets.md", "--run-id", "derivable-run"], check=True, stdout=subprocess.DEVNULL)
(root / "run-decision.json").write_text(json.dumps({
    "scenario": "01-derivable-review-fix",
    "action": "fixed-and-promoted",
    "human_choice": False,
    "review_iterations": 2,
    "contract_sha256": manifest["contract_sha256"],
    "evidence": "The main Agent fixes every finding derivable from approved context and current code in those same artifacts: factual drift, canonical Spec/Ticket terminology (use `Ticket`, not `Issue`), acceptance or validation gaps, sizing and split/merge repairs, blocker-edge corrections, and formatting or backlink defects.",
}, indent=2) + "\n", encoding="utf-8")

second = run / "scenarios/02-human-owned-choice"
(second / "run-decision.json").write_text(json.dumps({
    "scenario": "02-human-owned-choice",
    "action": "stopped-for-human",
    "human_choice": True,
    "review_iterations": 1,
    "contract_sha256": manifest["contract_sha256"],
    "evidence": "Ask the user only for an unresolved scope, product-semantic, ownership, release-policy, data/security-policy, architecture, significant UX, or missing-core-requirement choice.",
}, indent=2) + "\n", encoding="utf-8")
(second / "escalation.json").write_text(json.dumps({"choice": "release owner"}) + "\n", encoding="utf-8")
PY

python3 "$GRADER" --output "$RUN" --json >"$TMPDIR_ROOT/pass.json"
grep -Fq '"passed": true' "$TMPDIR_ROOT/pass.json"

python3 - "$RUN/scenarios.json" <<'PY'
from pathlib import Path
import json, sys
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
path.write_text(json.dumps(data[:1], indent=2) + "\n", encoding="utf-8")
PY
if python3 "$GRADER" --output "$RUN" --json >/dev/null 2>&1; then
  echo "grader accepted a missing model scenario" >&2
  exit 1
fi

python3 -m py_compile "$PREPARE" "$GRADER"
echo "ultra Local Markdown publication eval harness passed"
