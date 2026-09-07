#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
FACADE="$ROOT/skills/engineering/ultra/scripts/ultra_tracker.py"
PUBLICATION="$ROOT/skills/engineering/ultra/scripts/local_ticket_publication.py"
FRONTIER="$ROOT/skills/engineering/ultra/scripts/local_ticket_frontier.py"
SOLVE_RECORDS="$ROOT/skills/engineering/solve-records/scripts/solve-records.py"
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

python3 - "$TMPDIR_ROOT" "$FACADE" "$PUBLICATION" "$FRONTIER" "$SOLVE_RECORDS" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

root, facade, publication, frontier, solve_records = map(Path, sys.argv[1:])


def run(
    *command: str, check: bool = True, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if check and result.returncode:
        raise AssertionError(f"{command}: {result.stderr or result.stdout}")
    return result


def contract() -> str:
    return """Publication strategy: local-review-pending
Local Ticket representation: file-per-ticket
Local Ticket path: .scratch/feature/issues/<ticket-file>.md
Cancellation policy: retain-until-explicit-cleanup
Frontier adapter: bundled-local-markdown-v1
Ticket ID field aliases: Ticket ID, ID
Publication Run field aliases: Publication Run
Source field aliases: Source Spec, Parent
Ticket state fields: Status, State
Ticket state values: review-pending, ready-for-agent, completed, ready-for-human, needs-info
Ready state: ready-for-agent
Completed state: completed
Human-blocked states: ready-for-human, needs-info
Blocker metadata fields: Blocked By, Blockers
Blocker body heading: Blocked by
Claim field: Flags
Claim field aliases: Flags, Labels
Claim value: solve-in-progress
Solve branch field: Solve Branch
Solve branch field aliases: Solve Branch, Branch
Solve worktree field: Solve Worktree
Solve worktree field aliases: Solve Worktree, Worktree
"""


def fixture(name: str, status: str, run_id: str = "") -> Path:
    repo = root / name
    run("git", "init", "-q", str(repo))
    (repo / "docs/agents").mkdir(parents=True)
    (repo / "docs/agents/ultra-tracker.md").write_text(contract(), encoding="utf-8")
    tickets = repo / ".scratch/feature/issues"
    tickets.mkdir(parents=True)
    publication_fields = f"Publication Run: {run_id}\nSource Spec: docs/spec.md\n" if run_id else ""
    (tickets / "A.md").write_text(
        f"Status: {status}\nTicket ID: A\n{publication_fields}Blocked By:\nFlags:\n\n# Ticket A\n",
        encoding="utf-8",
    )
    return repo


def facade_data(result: subprocess.CompletedProcess[str], operation: str) -> dict:
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "ultra-tracker/v1"
    assert payload["operation"] == operation
    assert payload["ok"] is True
    return payload["data"]


# Canonical help reaches every delegated domain surface without relying on PATH.
for command, words in (
    ([sys.executable, str(facade), "--help"], ("publication", "ticket", "solve-record", "Ticket", "Claim", "Attempt", "Solve Record")),
    ([sys.executable, str(facade), "publication", "--help"], ("register", "inspect", "promote", "cleanup", "terminal-repair")),
    ([sys.executable, str(facade), "ticket", "--help"], ("frontier", "claim", "handoff")),
    ([sys.executable, str(facade), "solve-record", "--help"], ("dashboard", "merge-gate", "landing-plan", "cleanup-plan")),
):
    output = run(*command).stdout
    assert all(word in output for word in words), output
facade_help = " ".join(run(sys.executable, str(facade), "--help").stdout.split())
assert "selected adapter capability document" in facade_help
handoff_help = run(sys.executable, str(facade), "ticket", "handoff", "--help").stdout
normalized_handoff_help = " ".join(handoff_help.split())
assert "Only success returns ok=true and exits 0" in normalized_handoff_help
assert "retryable (6), conflict (3), and unavailable (5)" in normalized_handoff_help

# Publication success and refusal preserve the owning adapter result while facade config is discovered once.
pub_direct = fixture("publication-direct", "review-pending", "run-1")
pub_facade = fixture("publication-facade", "review-pending", "run-1")
direct = json.loads(run(sys.executable, str(publication), "register", "--repo", str(pub_direct), "--representation", "file-per-ticket", "--location", ".scratch/feature/issues", "--run-id", "run-1").stdout)
actual = facade_data(run(sys.executable, str(facade), "publication", "register", "--repo", str(pub_facade), "--location", ".scratch/feature/issues", "--run-id", "run-1"), "publication.register")
assert direct == actual
refusal = run(sys.executable, str(facade), "publication", "cleanup", "--repo", str(pub_facade), "--location", ".scratch/feature/issues", "--run-id", "run-1", check=False)
assert refusal.returncode == 3
assert json.loads(refusal.stdout)["error"]["code"] == "not-allowed"
missing_contract = root / "missing-contract"
missing_contract.mkdir()
malformed_contract = run(sys.executable, str(facade), "publication", "register", "--repo", str(missing_contract), "--run-id", "run-1", check=False)
assert malformed_contract.returncode == 4
assert json.loads(malformed_contract.stdout)["error"]["code"] == "invalid-input-or-state"

# Inspect is the public diagnosis seam and must fail closed when the current
# Ticket body no longer matches the registered publication digest.
inspect_drift = fixture("publication-inspect-drift", "review-pending", "run-drift")
run(
    sys.executable,
    str(facade),
    "publication",
    "register",
    "--repo",
    str(inspect_drift),
    "--location",
    ".scratch/feature/issues",
    "--run-id",
    "run-drift",
)
drifted_ticket = inspect_drift / ".scratch/feature/issues/A.md"
drifted_ticket.write_text(
    drifted_ticket.read_text(encoding="utf-8") + "\nSemantic correction after registration.\n",
    encoding="utf-8",
)
drift = run(
    sys.executable,
    str(facade),
    "publication",
    "inspect",
    "--repo",
    str(inspect_drift),
    "--location",
    ".scratch/feature/issues",
    "--run-id",
    "run-drift",
    check=False,
)
assert drift.returncode == 4
drift_payload = json.loads(drift.stdout)
assert drift_payload["error"]["code"] == "invalid-input-or-state"
assert "Ticket content changed after review registration" in drift_payload["error"]["detail"]

# Frontier snapshots and Claim assignments are delegated unchanged on separate identical repositories.
frontier_direct = fixture("frontier-direct", "ready-for-agent")
frontier_facade = fixture("frontier-facade", "ready-for-agent")
direct_frontier = json.loads(run(sys.executable, str(frontier), "frontier", "--repo", str(frontier_direct), "--ticket-id", "A").stdout)
actual_frontier = facade_data(run(sys.executable, str(facade), "ticket", "frontier", "--repo", str(frontier_facade), "--ticket-id", "A"), "ticket.frontier")
assert {key: value for key, value in direct_frontier.items() if key != "snapshot"} == {key: value for key, value in actual_frontier.items() if key != "snapshot"}
claim_args = ("--ticket-id", "A", "--branch", "solve/a", "--worktree", "/tmp/facade-a")
direct_claim = json.loads(run(sys.executable, str(frontier), "claim", "--repo", str(frontier_direct), "--expected-snapshot", direct_frontier["snapshot"], *claim_args).stdout)
facade_claim = facade_data(run(sys.executable, str(facade), "ticket", "claim", "--repo", str(frontier_facade), "--expected-snapshot", actual_frontier["snapshot"], *claim_args), "ticket.claim")
assert {key: value for key, value in direct_claim.items() if key not in {"snapshot", "previous_snapshot"}} == {key: value for key, value in facade_claim.items() if key not in {"snapshot", "previous_snapshot"}}
stale = run(sys.executable, str(facade), "ticket", "claim", "--repo", str(frontier_facade), "--expected-snapshot", actual_frontier["snapshot"], *claim_args, check=False)
assert stale.returncode == 3 and json.loads(stale.stdout)["error"]["code"] == "not-allowed"
invalid_claim = run(sys.executable, str(facade), "ticket", "claim", "--repo", str(frontier_facade), "--ticket-id", "A", "--expected-snapshot", "snapshot", "--branch", "solve/a", check=False)
assert invalid_claim.returncode == 4
invalid_claim_payload = json.loads(invalid_claim.stdout)
assert invalid_claim_payload["operation"] == "parse"
assert invalid_claim_payload["error"]["code"] == "invalid-input-or-state"

# Solve Record inspection remains the standalone helper's data, including an empty dashboard.
records = fixture("records", "ready-for-agent")
direct_dashboard = json.loads(run(sys.executable, str(solve_records), "dashboard", "--repo", str(records), "--json").stdout)
facade_dashboard = facade_data(run(sys.executable, str(facade), "solve-record", "dashboard", "--repo", str(records)), "solve-record.dashboard")
assert direct_dashboard == facade_dashboard
malformed = run(sys.executable, str(facade), "solve-record", "merge-gate", "--repo", str(records), "--record", "missing", check=False)
assert malformed.returncode == 4 and json.loads(malformed.stdout)["error"]["code"] == "invalid-input-or-state"

# A successful helper process can still return a non-eligible gate; preserve
# that non-allowed outcome in the facade's exit and envelope contract.
layout = root / "facade-layout/skills/engineering"
layout.joinpath("ultra/scripts").mkdir(parents=True)
layout.joinpath("solve-records/scripts").mkdir(parents=True)
shutil.copy2(facade, layout / "ultra/scripts/ultra_tracker.py")
(layout / "solve-records/scripts/solve-records.py").write_text(
    "import json\nprint(json.dumps({'eligible': False, 'reasons': ['manual gate']}))\n",
    encoding="utf-8",
)
ineligible_gate = run(
    sys.executable, str(layout / "ultra/scripts/ultra_tracker.py"),
    "solve-record", "merge-gate", "--repo", str(records), "--record", "fixture", check=False,
)
assert ineligible_gate.returncode == 3
ineligible_payload = json.loads(ineligible_gate.stdout)
assert ineligible_payload["error"]["code"] == "not-allowed"

# Handoff is successful only when its complete postcondition is successful.
# Expected retry and conflict results retain adapter data while the facade's
# top-level success bit and process exit fail closed for simple callers.
(layout / "ultra/scripts/local_outcome_handoff.py").write_text(
    """import json, sys
def value(name):
    return sys.argv[sys.argv.index(name) + 1]
status = {"candidate": "success", "blocked": "retryable", "abandoned": "conflict"}[value("--outcome")]
print(json.dumps({
    "schema": "ultra-local-outcome-handoff/v1",
    "status": status,
    "handoff_key": value("--handoff-key"),
    "repo": value("--repo"),
    "reason": "fixture " + status if status != "success" else "",
    "next_action": "retry same key" if status == "retryable" else "manual inspection" if status == "conflict" else "",
}))
""",
    encoding="utf-8",
)
handoff_command = (
    sys.executable,
    str(layout / "ultra/scripts/ultra_tracker.py"),
    "ticket",
    "handoff",
    "--ticket-id",
    "A",
    "--handoff-key",
    "facade-status-key",
    "--summary",
    "Facade status projection fixture.",
)
handoff_success = run(*handoff_command, "--outcome", "candidate", cwd=records)
success_data = facade_data(handoff_success, "ticket.handoff")
assert success_data["status"] == "success"
assert success_data["repo"] == str(records.resolve())
for outcome, status, returncode in (
    ("blocked", "retryable", 6),
    ("abandoned", "conflict", 3),
):
    handoff_result = run(
        *handoff_command, "--outcome", outcome, cwd=records, check=False
    )
    assert handoff_result.returncode == returncode, handoff_result
    handoff_payload = json.loads(handoff_result.stdout)
    assert handoff_payload["ok"] is False
    assert handoff_payload["data"]["status"] == status
    assert handoff_payload["data"]["handoff_key"] == "facade-status-key"
    assert handoff_payload["error"]["code"] == f"handoff-{status}"

# Missing bundled helpers are explicit unavailability, not copied behavior.
isolated = root / "isolated/scripts"
isolated.mkdir(parents=True)
shutil.copy2(facade, isolated / "ultra_tracker.py")
missing = run(sys.executable, str(isolated / "ultra_tracker.py"), "ticket", "frontier", "--repo", str(records), check=False)
assert missing.returncode == 5
assert json.loads(missing.stdout)["error"]["code"] == "helper-unavailable"
PY

echo "ultra tracker facade fixture passed"
