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


def run(*command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
    ([sys.executable, str(facade), "publication", "--help"], ("register", "inspect", "promote", "cleanup")),
    ([sys.executable, str(facade), "ticket", "--help"], ("frontier", "claim")),
    ([sys.executable, str(facade), "solve-record", "--help"], ("dashboard", "merge-gate", "landing-plan", "cleanup-plan")),
):
    output = run(*command).stdout
    assert all(word in output for word in words), output

# Publication success and refusal preserve the owning adapter result while facade config is discovered once.
pub_direct = fixture("publication-direct", "review-pending", "run-1")
pub_facade = fixture("publication-facade", "review-pending", "run-1")
direct = json.loads(run(sys.executable, str(publication), "register", "--repo", str(pub_direct), "--representation", "file-per-ticket", "--location", ".scratch/feature/issues", "--run-id", "run-1").stdout)
actual = facade_data(run(sys.executable, str(facade), "publication", "register", "--repo", str(pub_facade), "--location", ".scratch/feature/issues", "--run-id", "run-1"), "publication.register")
assert direct == actual
refusal = run(sys.executable, str(facade), "publication", "cleanup", "--repo", str(pub_facade), "--location", ".scratch/feature/issues", "--run-id", "run-1", check=False)
assert refusal.returncode == 3
assert json.loads(refusal.stdout)["error"]["code"] == "not-allowed"

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

# Solve Record inspection remains the standalone helper's data, including an empty dashboard.
records = fixture("records", "ready-for-agent")
direct_dashboard = json.loads(run(sys.executable, str(solve_records), "dashboard", "--repo", str(records), "--json").stdout)
facade_dashboard = facade_data(run(sys.executable, str(facade), "solve-record", "dashboard", "--repo", str(records)), "solve-record.dashboard")
assert direct_dashboard == facade_dashboard
malformed = run(sys.executable, str(facade), "solve-record", "merge-gate", "--repo", str(records), "--record", "missing", check=False)
assert malformed.returncode == 4 and json.loads(malformed.stdout)["error"]["code"] == "invalid-input-or-state"

# Missing bundled helpers are explicit unavailability, not copied behavior.
isolated = root / "isolated/scripts"
isolated.mkdir(parents=True)
shutil.copy2(facade, isolated / "ultra_tracker.py")
missing = run(sys.executable, str(isolated / "ultra_tracker.py"), "ticket", "frontier", "--repo", str(records), check=False)
assert missing.returncode == 5
assert json.loads(missing.stdout)["error"]["code"] == "helper-unavailable"
PY

echo "ultra tracker facade fixture passed"
