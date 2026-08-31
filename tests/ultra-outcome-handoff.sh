#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
FACADE="$ROOT/skills/engineering/ultra/scripts/ultra_tracker.py"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

python3 - "$TMP_ROOT" "$FACADE" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root, facade = map(Path, sys.argv[1:])


def run(*command: str, check: bool = True, env: dict[str, str] | None = None):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if check and result.returncode:
        raise AssertionError(f"{command}: {result.stderr or result.stdout}")
    return result


repo = root / "repo"
run("git", "init", "-q", "-b", "solve/A", str(repo))
run("git", "-C", str(repo), "config", "user.email", "handoff@example.test")
run("git", "-C", str(repo), "config", "user.name", "Handoff Fixture")
(repo / "docs/agents").mkdir(parents=True)
(repo / "docs/agents/ultra-tracker.md").write_text("""Frontier adapter: bundled-local-markdown-v1
Local Ticket representation: file-per-ticket
Local Ticket path: .scratch/<feature>/issues/<ticket-file>.md
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
""", encoding="utf-8")
ticket = repo / ".scratch/feature/issues/A.md"
ticket.parent.mkdir(parents=True)
ticket.write_text(f"""Status: ready-for-agent
Ticket ID: A
Flags: solve-in-progress
Solve Branch: solve/A
Solve Worktree: {repo}
Blocked By:

# Ticket A
""", encoding="utf-8")
(repo / "candidate.txt").write_text("candidate\n", encoding="utf-8")
run("git", "-C", str(repo), "add", ".")
run("git", "-C", str(repo), "commit", "-qm", "candidate")
head_sha = run("git", "-C", str(repo), "rev-parse", "HEAD").stdout.strip()


def handoff(key: str, summary: str = "Implemented and validated the candidate.", check: bool = True):
    return run(
        sys.executable, str(facade), "ticket", "handoff",
        "--repo", str(repo), "--ticket-id", "A", "--handoff-key", key,
        "--outcome", "candidate", "--summary", summary,
        check=check,
    )


# Missing semantic input refuses before any side effect.
missing = run(
    sys.executable, str(facade), "ticket", "handoff", "--repo", str(repo),
    "--ticket-id", "A", "--handoff-key", "", "--outcome", "candidate",
    "--summary", "Implemented.", check=False,
)
missing_data = json.loads(missing.stdout)["data"]
assert missing.returncode == 0
assert missing_data["status"] == "conflict" and missing_data["handoff_key"] == ""
assert not list((repo / ".scratch/feature/solve-records").glob("*.md"))

# A missing active Claim is refused before receipt or backlink creation.
claimed_text = ticket.read_text(encoding="utf-8")
ticket.write_text(claimed_text.replace("Flags: solve-in-progress", "Flags:"), encoding="utf-8")
unclaimed = handoff("unclaimed-key", check=False)
unclaimed_data = json.loads(unclaimed.stdout)["data"]
assert unclaimed_data["status"] == "conflict" and unclaimed_data["handoff_key"] == "unclaimed-key"
assert not list((repo / ".scratch/feature/solve-records").glob("*.md"))
assert "Solve Records" not in ticket.read_text(encoding="utf-8")
ticket.write_text(claimed_text, encoding="utf-8")

key = "opaque retry key / A"
fault_env = dict(os.environ, ULTRA_HANDOFF_FAIL_AFTER_RECEIPT="1")
partial = run(
    sys.executable, str(facade), "ticket", "handoff",
    "--repo", str(repo), "--ticket-id", "A", "--handoff-key", key,
    "--outcome", "candidate", "--summary", "Implemented and validated the candidate.",
    env=fault_env,
)
partial_data = json.loads(partial.stdout)["data"]
assert partial_data["status"] == "retryable" and partial_data["handoff_key"] == key
expected_name = hashlib.sha256(key.encode()).hexdigest() + ".md"
partial_receipt = repo / ".scratch/feature/solve-records" / expected_name
partial_text = partial_receipt.read_text(encoding="utf-8")
assert partial_text.startswith("---\n") and partial_text.endswith("validated the candidate.\n")
assert "Status: ready-for-agent" in ticket.read_text(encoding="utf-8")
assert "solve-in-progress" in ticket.read_text(encoding="utf-8")

ticket_failure_env = dict(os.environ, ULTRA_HANDOFF_FAIL_BEFORE_TICKET_WRITE="1")
ticket_failure = run(
    sys.executable, str(facade), "ticket", "handoff",
    "--repo", str(repo), "--ticket-id", "A", "--handoff-key", key,
    "--outcome", "candidate", "--summary", "Implemented and validated the candidate.",
    env=ticket_failure_env,
)
ticket_failure_data = json.loads(ticket_failure.stdout)["data"]
assert ticket_failure_data["status"] == "retryable"
assert "Ticket transition failed" in ticket_failure_data["reason"]

# A prose path mention is not mistaken for the canonical backlink entry.
ticket.write_text(ticket.read_text(encoding="utf-8").rstrip() + f"\n\nMention: ../solve-records/{expected_name}\n", encoding="utf-8")

first = json.loads(handoff(key).stdout)
data = first["data"]
assert data["status"] == "success" and data["handoff_key"] == key
assert data["receipt"] == f".scratch/feature/solve-records/{expected_name}"
receipt = repo / data["receipt"]
text = receipt.read_text(encoding="utf-8")
assert "outcome: candidate" in text
assert "state: open" in text
assert "tickets:\n  - .scratch/feature/issues/A.md" in text
assert "\nissues:" not in text
assert "\nid:" not in text
assert "\nkind:" not in text
assert "\ncleanup_done:" not in text
assert "  - .scratch/feature/issues/A.md" in text
assert "head: solve/A" in text and f"head_sha: {head_sha}" in text
assert "## Summary\nImplemented and validated the candidate." in text
ticket_text = ticket.read_text(encoding="utf-8")
assert "Status: completed" in ticket_text
assert "solve-in-progress" not in ticket_text
assert ticket_text.count(f"- `../solve-records/{expected_name}`") == 1

# A new process converges on the same postcondition without duplicates.
second = json.loads(handoff(key).stdout)["data"]
assert second == data
assert len(list(receipt.parent.glob("*.md"))) == 1
assert ticket.read_text(encoding="utf-8").count(f"- `../solve-records/{expected_name}`") == 1

# A later incompatible Ticket state is a conflict, not a guessed partial transition.
successful_ticket_text = ticket.read_text(encoding="utf-8")
ticket.write_text(successful_ticket_text.replace("Status: completed", "Status: needs-info"), encoding="utf-8")
state_conflict = json.loads(handoff(key, check=False).stdout)["data"]
assert state_conflict["status"] == "conflict"
assert state_conflict["next_action"] == "inspect Ticket state, Claim, and backlink manually; do not retry unchanged"
assert "Status: needs-info" in ticket.read_text(encoding="utf-8")
ticket.write_text(successful_ticket_text, encoding="utf-8")

# Summary is canonical receipt content, not immutable binding identity.
summary_retry = json.loads(handoff(key, "Changed summary.").stdout)["data"]
assert summary_retry == data
assert receipt.read_text(encoding="utf-8") == text

# The same key cannot create a second receipt for another feature/Ticket scope.
other_ticket = repo / ".scratch/other/issues/B.md"
other_ticket.parent.mkdir(parents=True)
other_ticket.write_text(f"""Status: ready-for-agent
Ticket ID: B
Flags: solve-in-progress
Solve Branch: solve/A
Solve Worktree: {repo}
Blocked By:

# Ticket B
""", encoding="utf-8")
membership_conflict = run(
    sys.executable, str(facade), "ticket", "handoff", "--repo", str(repo),
    "--ticket-id", "B", "--handoff-key", key, "--outcome", "candidate",
    "--summary", "Another Ticket.", check=False,
)
membership_data = json.loads(membership_conflict.stdout)["data"]
assert membership_data["status"] == "conflict"
assert membership_data["next_action"] == "use a new handoff key for changed immutable facts"
assert not list((repo / ".scratch/other/solve-records").glob("*.md"))
other_ticket.unlink()

# Complete reread detects canonical receipt tampering and never repairs it silently.
receipt.write_text(text.replace("state: open", "state: closed"), encoding="utf-8")
tampered = json.loads(handoff(key, check=False).stdout)["data"]
assert tampered["status"] == "conflict" and "complete verification" in tampered["reason"]
assert tampered["next_action"] == "inspect the canonical receipt manually; do not retry unchanged"
receipt.write_text(text, encoding="utf-8")

binding_line = next(line for line in text.splitlines() if line.startswith("binding_digest: "))
receipt.write_text(text.replace(binding_line, "binding_digest: " + "0" * 64), encoding="utf-8")
binding_tampered = json.loads(handoff(key, check=False).stdout)["data"]
assert binding_tampered["status"] == "conflict"
assert binding_tampered["next_action"] == "inspect the canonical receipt manually; do not retry unchanged"
receipt.write_text(text, encoding="utf-8")

receipt.write_text(text.replace(f"head_sha: {head_sha}", "head_sha: 0000000"), encoding="utf-8")
identity_tampered = json.loads(handoff(key, check=False).stdout)["data"]
assert identity_tampered["status"] == "conflict"
assert identity_tampered["next_action"]
receipt.write_text(text, encoding="utf-8")

# Candidate-only scope still reports a keyed semantic conflict for another outcome.
outcome_conflict = run(
    sys.executable, str(facade), "ticket", "handoff", "--repo", str(repo),
    "--ticket-id", "A", "--handoff-key", key, "--outcome", "blocked",
    "--summary", "Changed outcome.", check=False,
)
outcome_data = json.loads(outcome_conflict.stdout)["data"]
assert outcome_data["status"] == "conflict" and outcome_data["handoff_key"] == key
assert outcome_data["next_action"]

# Candidate identity is immutable even when the same branch advances.
run("git", "-C", str(repo), "add", ".")
run("git", "-C", str(repo), "commit", "-qm", "advance candidate")
head_conflict = json.loads(handoff(key, check=False).stdout)["data"]
assert head_conflict["status"] == "conflict"
assert head_conflict["next_action"]
assert receipt.read_text(encoding="utf-8") == text

print("ultra outcome handoff fixture passed")
PY

EXISTING_OUTPUT="$TMP_ROOT/existing-eval-output"
mkdir -p "$EXISTING_OUTPUT"
touch "$EXISTING_OUTPUT/do-not-delete"
if python3 "$ROOT/tests/evals/ultra-outcome-handoff/prepare-fixture.py" --output "$EXISTING_OUTPUT" >/dev/null 2>&1; then
  echo "prepare fixture unexpectedly accepted an existing output directory" >&2
  exit 1
fi
test -f "$EXISTING_OUTPUT/do-not-delete"
