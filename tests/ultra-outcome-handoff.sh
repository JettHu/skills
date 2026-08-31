#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
FACADE="$ROOT/skills/engineering/ultra/scripts/ultra_tracker.py"
BOARD="$ROOT/skills/in-progress/maintainer-board/scripts/maintainer-board.py"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMP_ROOT"' EXIT

python3 - "$TMP_ROOT" "$FACADE" "$BOARD" <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

root, facade, board = map(Path, sys.argv[1:])


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
Resumable Claims: supported
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


def grouped_handoff(key: str, *ticket_ids: str, check: bool = True, env=None):
    command = [
        sys.executable, str(facade), "ticket", "handoff", "--repo", str(repo),
        "--handoff-key", key, "--outcome", "candidate",
        "--summary", "Implemented and validated the grouped candidate.",
    ]
    for ticket_id in ticket_ids:
        command.extend(["--ticket-id", ticket_id])
    return run(*command, check=check, env=env)


def recovery(
    key: str,
    outcome: str,
    next_action: str,
    *resources: str,
    check: bool = True,
):
    command = [
        sys.executable, str(facade), "ticket", "handoff",
        "--repo", str(repo), "--ticket-id", "A", "--handoff-key", key,
        "--outcome", outcome, "--summary", f"Recovery handoff for {outcome}.",
        "--recovery-next-action", next_action,
    ]
    for resource in resources:
        command.extend(["--retained-resource", resource])
    return run(*command, check=check)


def terminal(key: str, outcome: str):
    return run(
        sys.executable, str(facade), "ticket", "handoff",
        "--repo", str(repo), "--ticket-id", "A", "--handoff-key", key,
        "--outcome", outcome, "--summary", f"Terminal handoff for {outcome}.",
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

# Equivalent grouped Ticket scopes normalize independently of caller ordering.
group_a = repo / ".scratch/group/issues/A.md"
group_b = repo / ".scratch/group/issues/B.md"
group_a.parent.mkdir(parents=True)
for group_ticket, group_id in ((group_a, "GROUP-A"), (group_b, "GROUP-B")):
    group_ticket.write_text(f"""Status: ready-for-agent
Ticket ID: {group_id}
Flags: solve-in-progress
Solve Branch: solve/A
Solve Worktree: {repo}
Blocked By:

# Ticket {group_id}
""", encoding="utf-8")
run("git", "-C", str(repo), "add", ".scratch/group")
run("git", "-C", str(repo), "commit", "-qm", "add grouped Tickets")

group_key = "grouped-order-independent"
group_partial = json.loads(grouped_handoff(
    group_key, "GROUP-B", "GROUP-A",
    env=dict(os.environ, ULTRA_HANDOFF_FAIL_AFTER_MEMBER="1"),
).stdout)["data"]
assert group_partial["status"] == "retryable", group_partial
group_name = hashlib.sha256(group_key.encode()).hexdigest() + ".md"
group_receipt = repo / ".scratch/group/solve-records" / group_name
group_text = group_receipt.read_text(encoding="utf-8")
assert "tickets:\n  - .scratch/group/issues/A.md\n  - .scratch/group/issues/B.md" in group_text
assert sum("Status: completed" in p.read_text(encoding="utf-8") for p in (group_a, group_b)) == 1

group_success = json.loads(grouped_handoff(group_key, "GROUP-A", "GROUP-B").stdout)["data"]
assert group_success["status"] == "success", group_success
for group_ticket in (group_a, group_b):
    final_group_text = group_ticket.read_text(encoding="utf-8")
    assert "Status: completed" in final_group_text
    assert "solve-in-progress" not in final_group_text
    assert final_group_text.count(f"- `../solve-records/{group_name}`") == 1
assert json.loads(grouped_handoff(group_key, "GROUP-B", "GROUP-A").stdout)["data"] == group_success
assert len(list(group_receipt.parent.glob(f"{group_name}"))) == 1

# A changed grouped membership is an immutable same-key conflict.
changed_group = json.loads(grouped_handoff(group_key, "GROUP-A", check=False).stdout)["data"]
assert changed_group["status"] == "conflict"
assert changed_group["next_action"] == "use a new handoff key for changed immutable facts"
run("git", "-C", str(repo), "add", ".scratch/group")
run("git", "-C", str(repo), "commit", "-qm", "record grouped handoff")

# Every cross-surface interruption remains the same retryable operation, projects
# handoff attention, and converges on restart without duplicate actions.
boundary_faults = (
    ("member", "ULTRA_HANDOFF_FAIL_AFTER_MEMBER", "2"),
    ("backlink", "ULTRA_HANDOFF_FAIL_AFTER_BACKLINK", "2"),
    ("claim", "ULTRA_HANDOFF_FAIL_DURING_CLAIM", "2"),
)
for boundary, fault_name, fault_value in boundary_faults:
    boundary_a = repo / f".scratch/{boundary}/issues/A.md"
    boundary_b = repo / f".scratch/{boundary}/issues/B.md"
    boundary_c = repo / f".scratch/{boundary}/issues/C.md"
    boundary_a.parent.mkdir(parents=True)
    boundary_members = (
        (boundary_a, f"{boundary}-A"),
        (boundary_b, f"{boundary}-B"),
        (boundary_c, f"{boundary}-C"),
    )
    for boundary_ticket, boundary_id in boundary_members:
        boundary_ticket.write_text(f"""Status: ready-for-agent
Ticket ID: {boundary_id}
Flags: solve-in-progress
Solve Branch: solve/A
Solve Worktree: {repo}
Blocked By:

# Ticket {boundary_id}
""", encoding="utf-8")
    run("git", "-C", str(repo), "add", f".scratch/{boundary}")
    run("git", "-C", str(repo), "commit", "-qm", f"add {boundary} boundary Tickets")
    boundary_key = f"grouped-{boundary}-boundary"
    boundary_result = json.loads(grouped_handoff(
        boundary_key, f"{boundary}-C", f"{boundary}-B", f"{boundary}-A",
        env=dict(os.environ, **{fault_name: fault_value}),
    ).stdout)["data"]
    assert boundary_result["status"] == "retryable", (boundary, boundary_result)
    boundary_board = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
    boundary_records = [item for bucket in boundary_board["solve_records"]["buckets"].values() for item in bucket]
    boundary_record = next(item for item in boundary_records if item["path"] == boundary_result["receipt"])
    assert boundary_record["handoff_projection"] == "inconsistent_handoff_attention", boundary
    converged = json.loads(grouped_handoff(
        boundary_key, f"{boundary}-A", f"{boundary}-B", f"{boundary}-C"
    ).stdout)["data"]
    assert converged["status"] == "success", (boundary, converged)
    final_board = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
    final_records = [item for bucket in final_board["solve_records"]["buckets"].values() for item in bucket]
    final_record = next(item for item in final_records if item["path"] == converged["receipt"])
    assert final_record["handoff_projection"] == "normal_candidate", boundary
    for boundary_ticket in (boundary_a, boundary_b, boundary_c):
        boundary_text = boundary_ticket.read_text(encoding="utf-8")
        assert boundary_text.count(f"- `../solve-records/{Path(converged['receipt']).name}`") == 1
    run("git", "-C", str(repo), "add", f".scratch/{boundary}")
    run("git", "-C", str(repo), "commit", "-qm", f"record {boundary} boundary handoff")

# Whole-group preflight refuses an incompatible or disappeared later member
# before changing any still-compatible member.
preflight_a = repo / ".scratch/preflight/issues/A.md"
preflight_b = repo / ".scratch/preflight/issues/B.md"
preflight_a.parent.mkdir(parents=True)
for preflight_ticket, preflight_id in ((preflight_a, "preflight-A"), (preflight_b, "preflight-B")):
    preflight_ticket.write_text(f"""Status: ready-for-agent
Ticket ID: {preflight_id}
Flags: solve-in-progress
Solve Branch: solve/A
Solve Worktree: {repo}
Blocked By:

# Ticket {preflight_id}
""", encoding="utf-8")
run("git", "-C", str(repo), "add", ".scratch/preflight")
run("git", "-C", str(repo), "commit", "-qm", "add preflight Tickets")
preflight_key = "grouped-preflight"
installed = json.loads(grouped_handoff(
    preflight_key, "preflight-A", "preflight-B",
    env=dict(os.environ, ULTRA_HANDOFF_FAIL_AFTER_RECEIPT="1"),
).stdout)["data"]
assert installed["status"] == "retryable"
untouched_a = preflight_a.read_text(encoding="utf-8")
canonical_b = preflight_b.read_text(encoding="utf-8")
preflight_b.write_text(canonical_b.replace("Status: ready-for-agent", "Status: needs-info"), encoding="utf-8")
incompatible = json.loads(grouped_handoff(preflight_key, "preflight-B", "preflight-A").stdout)["data"]
assert incompatible["status"] == "conflict", incompatible
assert preflight_a.read_text(encoding="utf-8") == untouched_a
preflight_b.unlink()
missing_member = json.loads(grouped_handoff(preflight_key, "preflight-A", "preflight-B").stdout)["data"]
assert missing_member["status"] == "conflict", missing_member
assert "unavailable" in missing_member["reason"]
assert preflight_a.read_text(encoding="utf-8") == untouched_a
preflight_b.write_text(canonical_b, encoding="utf-8")
assert json.loads(grouped_handoff(preflight_key, "preflight-A", "preflight-B").stdout)["data"]["status"] == "success"

# Recovery outcomes use the same facade while keeping Ticket state and Claim
# disposition as separate postconditions.
recovery_cases = [
    ("blocked", "ready-for-human", "open"),
    ("needs-info", "needs-info", "open"),
    ("ready-for-human", "ready-for-human", "open"),
    ("abandoned", "ready-for-agent", "closed"),
    ("superseded", "ready-for-agent", "closed"),
]
for recovery_outcome, expected_status, expected_state in recovery_cases:
    ticket.write_text(claimed_text, encoding="utf-8")
    recovery_key = f"recovery-{recovery_outcome}"
    invocation = terminal(recovery_key, recovery_outcome) if recovery_outcome in {"abandoned", "superseded"} else recovery(recovery_key, recovery_outcome, "inspect")
    recovery_data = json.loads(invocation.stdout)["data"]
    assert recovery_data["status"] == "success", recovery_data
    recovery_text = (repo / recovery_data["receipt"]).read_text(encoding="utf-8")
    assert f"outcome: {recovery_outcome}" in recovery_text
    assert f"state: {expected_state}" in recovery_text
    if recovery_outcome not in {"abandoned", "superseded"}:
        assert 'recovery_next_action: "inspect"' in recovery_text
    else:
        assert "recovery_next_action:" not in recovery_text
    final_ticket = ticket.read_text(encoding="utf-8")
    assert f"Status: {expected_status}" in final_ticket
    assert "solve-in-progress" not in final_ticket
    projection_data = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
    projection_records = [item for bucket in projection_data["solve_records"]["buckets"].values() for item in bucket]
    projected = next(item for item in projection_records if item["path"] == recovery_data["receipt"])
    expected_projection = "closed_terminal_history" if expected_state == "closed" else "normal_active_recovery"
    assert projected["handoff_projection"] == expected_projection
    if expected_state == "closed":
        inconsistent_ticket = final_ticket.replace("Flags:", "Flags: solve-in-progress")
        ticket.write_text(inconsistent_ticket, encoding="utf-8")
        inconsistent_data = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
        inconsistent_records = [item for bucket in inconsistent_data["solve_records"]["buckets"].values() for item in bucket]
        inconsistent = next(item for item in inconsistent_records if item["path"] == recovery_data["receipt"])
        assert inconsistent["handoff_projection"] == "inconsistent_handoff_attention"
        ticket.write_text(final_ticket, encoding="utf-8")
        terminal_receipt_path = repo / recovery_data["receipt"]
        canonical_terminal_text = terminal_receipt_path.read_text(encoding="utf-8")
        terminal_tampers = {
            "recovery action": 'recovery_next_action: "resume"\n',
            "retained resources": (
                "retained_resources:\n"
                '  - "solve-owned:branch:solve/A"\n'
                f'  - "solve-owned:worktree:{repo}"\n'
            ),
        }
        for tamper_name, injected_fields in terminal_tampers.items():
            terminal_receipt_path.write_text(
                canonical_terminal_text.replace("---\n\n# Solve Record", injected_fields + "---\n\n# Solve Record"),
                encoding="utf-8",
            )
            tamper_data = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
            tamper_records = [item for bucket in tamper_data["solve_records"]["buckets"].values() for item in bucket]
            tampered_terminal = next(item for item in tamper_records if item["path"] == recovery_data["receipt"])
            assert tampered_terminal["handoff_projection"] == "inconsistent_handoff_attention", tamper_name
        terminal_receipt_path.write_text(canonical_terminal_text, encoding="utf-8")

# Creation-time superseded preserves an already actionable Ticket state.
ticket.write_text(claimed_text.replace("Status: ready-for-agent", "Status: needs-info"), encoding="utf-8")
preserved = json.loads(terminal("superseded-needs-info", "superseded").stdout)["data"]
assert preserved["status"] == "success", preserved
assert "Status: needs-info" in ticket.read_text(encoding="utf-8")

# Resume retains ownership only for the complete, aligned, solve-owned Claim
# resource set. The actively claimed blocked Ticket remains outside frontier.
ticket.write_text(claimed_text, encoding="utf-8")
retained = json.loads(recovery(
    "retained-recovery", "blocked", "resume",
    "solve-owned:branch:solve/A", f"solve-owned:worktree:{repo}",
).stdout)["data"]
assert retained["status"] == "success", retained
retained_text = (repo / retained["receipt"]).read_text(encoding="utf-8")
assert "retained_resources:" in retained_text
assert "solve-owned:branch:solve/A" in retained_text
assert f"solve-owned:worktree:{repo}" in retained_text
retained_ticket = ticket.read_text(encoding="utf-8")
assert "Status: ready-for-human" in retained_ticket
assert "Flags: solve-in-progress" in retained_ticket
frontier_result = run(
    sys.executable, str(facade), "ticket", "frontier", "--repo", str(repo),
    "--ticket-id", "A",
)
assert json.loads(frontier_result.stdout)["data"]["claimable"] == []
board_data = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
board_records = [item for bucket in board_data["solve_records"]["buckets"].values() for item in bucket]
retained_projection = next(item for item in board_records if item["path"] == retained["receipt"])
assert retained_projection["handoff_projection"] == "retained_recovery_ownership"
retained_receipt_path = repo / retained["receipt"]
canonical_retained_text = retained_receipt_path.read_text(encoding="utf-8")
retained_receipt_path.write_text(canonical_retained_text.replace("state: open", "state: closed"), encoding="utf-8")
state_tamper_data = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
state_tamper_records = [item for bucket in state_tamper_data["solve_records"]["buckets"].values() for item in bucket]
state_tamper = next(item for item in state_tamper_records if item["path"] == retained["receipt"])
assert state_tamper["handoff_projection"] == "inconsistent_handoff_attention"
retained_receipt_path.write_text(canonical_retained_text, encoding="utf-8")
ticket.write_text(retained_ticket.replace("Solve Branch: solve/A", "Solve Branch: solve/other"), encoding="utf-8")
attention_data = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
attention_records = [item for bucket in attention_data["solve_records"]["buckets"].values() for item in bucket]
attention = next(item for item in attention_records if item["path"] == retained["receipt"])
assert attention["handoff_projection"] == "inconsistent_handoff_attention"
ticket.write_text(retained_ticket, encoding="utf-8")

# Every unsafe retain/release combination refuses before creating a receipt.
unsafe_cases = [
    ("resume-without-resources", "resume", []),
    ("resources-without-resume", "inspect", ["solve-owned:branch:solve/A", f"solve-owned:worktree:{repo}"]),
    ("partial-declaration", "resume", ["solve-owned:branch:solve/A"]),
    ("missing-resource", "resume", ["solve-owned:branch:missing", f"solve-owned:worktree:{repo}"]),
    ("user-owned-resource", "resume", ["user-owned:branch:solve/A", f"solve-owned:worktree:{repo}"]),
    ("branch-worktree-mismatch", "resume", ["solve-owned:branch:solve/A", f"solve-owned:worktree:{root}"]),
    ("stale-identity", "resume", ["solve-owned:branch:refs/heads/solve/A", f"solve-owned:worktree:{repo}"]),
    ("ambiguous-ownership", "resume", ["solve-owned:branch:solve/A", "user-owned:branch:solve/A", f"solve-owned:worktree:{repo}"]),
]
for unsafe_key, next_action, resources in unsafe_cases:
    ticket.write_text(claimed_text, encoding="utf-8")
    unsafe = json.loads(recovery(unsafe_key, "blocked", next_action, *resources).stdout)["data"]
    assert unsafe["status"] == "conflict", (unsafe_key, unsafe)
    assert unsafe["next_action"]
    unsafe_name = hashlib.sha256(unsafe_key.encode()).hexdigest() + ".md"
    assert not (repo / ".scratch/feature/solve-records" / unsafe_name).exists()

# A tracker that does not declare resumable Claim support fails closed.
ticket.write_text(claimed_text, encoding="utf-8")
contract_path = repo / "docs/agents/ultra-tracker.md"
contract_text = contract_path.read_text(encoding="utf-8")
contract_path.write_text(contract_text.replace("Resumable Claims: supported", "Resumable Claims: unsupported"), encoding="utf-8")
unsupported = json.loads(recovery(
    "unsupported-resume", "blocked", "resume",
    "solve-owned:branch:solve/A", f"solve-owned:worktree:{repo}",
).stdout)["data"]
assert unsupported["status"] == "conflict"
assert "resumable Claims" in unsupported["reason"]
contract_path.write_text(contract_text, encoding="utf-8")

# A resumed Attempt creates a distinct successor receipt. The predecessor stays
# open until the successor's primary handoff succeeds and the relation converges.
ticket.write_text(claimed_text, encoding="utf-8")
predecessor = json.loads(recovery(
    "successor-predecessor", "blocked", "inspect",
).stdout)["data"]
assert predecessor["status"] == "success", predecessor
predecessor_path = repo / predecessor["receipt"]
original_predecessor = predecessor_path.read_text(encoding="utf-8")
assert "state: open" in original_predecessor
assert "outcome: blocked" in original_predecessor

# Model the resumed Claim after the inspectable recovery handoff.
ticket.write_text(
    ticket.read_text(encoding="utf-8")
    .replace("Status: ready-for-human", "Status: ready-for-agent")
    .replace("Flags:", "Flags: solve-in-progress", 1),
    encoding="utf-8",
)
run("git", "-C", str(repo), "add", ".scratch")
run("git", "-C", str(repo), "commit", "-qm", "resume from recovery predecessor")
successor_key = "successor-candidate"
successor_command = [
    sys.executable, str(facade), "ticket", "handoff",
    "--repo", str(repo), "--ticket-id", "A", "--handoff-key", successor_key,
    "--outcome", "candidate", "--summary", "Resumed work completed successfully.",
    "--supersedes", predecessor["receipt"],
]
relation_failure = run(
    *successor_command,
    env=dict(os.environ, ULTRA_HANDOFF_FAIL_BEFORE_PREDECESSOR_CLOSE="1"),
)
relation_failure_data = json.loads(relation_failure.stdout)["data"]
assert relation_failure_data["status"] == "retryable", relation_failure_data
successor_path = repo / relation_failure_data["receipt"]
assert successor_path.is_file()
assert predecessor_path.read_text(encoding="utf-8") == original_predecessor

relation_read_failure = run(
    *successor_command,
    env=dict(os.environ, ULTRA_HANDOFF_FAIL_BEFORE_PREDECESSOR_RELATION_READ="1"),
)
relation_read_failure_data = json.loads(relation_read_failure.stdout)["data"]
assert relation_read_failure_data["status"] == "retryable", relation_read_failure_data
assert "predecessor relation read failed" in relation_read_failure_data["reason"]
assert predecessor_path.read_text(encoding="utf-8") == original_predecessor

closure_failure = run(
    *successor_command,
    env=dict(os.environ, ULTRA_HANDOFF_FAIL_DURING_PREDECESSOR_CLOSE="1"),
)
closure_failure_data = json.loads(closure_failure.stdout)["data"]
assert closure_failure_data["status"] == "retryable", closure_failure_data
assert "predecessor closure failed" in closure_failure_data["reason"]
assert predecessor_path.read_text(encoding="utf-8") == original_predecessor

verification_failure = run(
    *successor_command,
    env=dict(os.environ, ULTRA_HANDOFF_FAIL_AFTER_PREDECESSOR_CLOSE="1"),
)
verification_failure_data = json.loads(verification_failure.stdout)["data"]
assert verification_failure_data["status"] == "retryable", verification_failure_data
assert "predecessor closure failed" in verification_failure_data["reason"]
assert "state: closed" in predecessor_path.read_text(encoding="utf-8")

successor_read_failure = run(
    *successor_command,
    env=dict(os.environ, ULTRA_HANDOFF_FAIL_BEFORE_SUCCESSOR_RELATION_READ="1"),
)
successor_read_failure_data = json.loads(successor_read_failure.stdout)["data"]
assert successor_read_failure_data["status"] == "retryable", successor_read_failure_data
assert "successor relation read failed" in successor_read_failure_data["reason"]

converged_successor = json.loads(run(*successor_command).stdout)["data"]
assert converged_successor["status"] == "success", converged_successor
assert converged_successor["receipt"] == relation_failure_data["receipt"]
assert len(list(predecessor_path.parent.glob("*.md"))) >= 2
predecessor_text = predecessor_path.read_text(encoding="utf-8")
successor_text = successor_path.read_text(encoding="utf-8")
assert "state: closed" in predecessor_text
assert "outcome: blocked" in predecessor_text
assert f"superseded_by: {json.dumps(converged_successor['receipt'])}" in predecessor_text
assert "closed_at:" in predecessor_text
assert f"supersedes: {json.dumps(predecessor['receipt'])}" in successor_text
assert "\npredecessor:" not in successor_text
assert "\nsuccessor:" not in predecessor_text
ticket_text = ticket.read_text(encoding="utf-8")
assert ticket_text.count(f"- `../solve-records/{predecessor_path.name}`") == 1
assert ticket_text.count(f"- `../solve-records/{successor_path.name}`") == 1

successor_board = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
successor_records = [item for bucket in successor_board["solve_records"]["buckets"].values() for item in bucket]
projected_predecessor = next(item for item in successor_records if item["path"] == predecessor["receipt"])
projected_successor = next(item for item in successor_records if item["path"] == converged_successor["receipt"])
assert projected_predecessor["handoff_projection"] == "closed_predecessor_history", projected_predecessor
assert projected_predecessor["superseded_by"] == converged_successor["receipt"]
assert projected_successor["supersedes"] == predecessor["receipt"]
assert projected_successor["handoff_projection"] == "normal_candidate", projected_successor
assert predecessor["receipt"] not in {
    item["path"] for item in successor_board["solve_records"]["buckets"]["recovery"]
}

# Exact retry stays successful, while invalid predecessor identities conflict
# without rewriting either side of the established relation.
assert json.loads(run(*successor_command).stdout)["data"]["status"] == "success"
stable_predecessor = predecessor_path.read_text(encoding="utf-8")
stable_successor = successor_path.read_text(encoding="utf-8")

def predecessor_conflict(key: str, predecessor_value: str):
    command = [
        sys.executable, str(facade), "ticket", "handoff",
        "--repo", str(repo), "--ticket-id", "A", "--handoff-key", key,
        "--outcome", "candidate", "--summary", "Must conflict.",
        "--supersedes", predecessor_value,
    ]
    data = json.loads(run(*command).stdout)["data"]
    assert data["status"] == "conflict", (key, data)
    return data

predecessor_conflict("missing-predecessor", ".scratch/feature/solve-records/missing.md")
predecessor_conflict("closed-predecessor", predecessor["receipt"])
predecessor_conflict("candidate-predecessor", converged_successor["receipt"])
predecessor_conflict(successor_key, converged_successor["receipt"])

malformed_key = "malformed-predecessor"
malformed_path = predecessor_path.parent / (hashlib.sha256(malformed_key.encode()).hexdigest() + ".md")
malformed_path.write_text("---\nstate: open\n---\n", encoding="utf-8")
malformed_before = malformed_path.read_text(encoding="utf-8")
predecessor_conflict("malformed-successor", malformed_path.relative_to(repo).as_posix())
assert malformed_path.read_text(encoding="utf-8") == malformed_before

cross_ticket = repo / ".scratch/other/issues/B.md"
cross_ticket.parent.mkdir(parents=True, exist_ok=True)
cross_ticket.write_text(claimed_text.replace("Ticket ID: A", "Ticket ID: cross-B"), encoding="utf-8")
cross_predecessor = json.loads(run(
    sys.executable, str(facade), "ticket", "handoff",
    "--repo", str(repo), "--ticket-id", "cross-B",
    "--handoff-key", "cross-predecessor", "--outcome", "blocked",
    "--summary", "Cross-membership recovery.", "--recovery-next-action", "inspect",
).stdout)["data"]
assert cross_predecessor["status"] == "success", cross_predecessor
predecessor_conflict("cross-membership-successor", cross_predecessor["receipt"])
predecessor_conflict(successor_key, cross_predecessor["receipt"])
assert predecessor_path.read_text(encoding="utf-8") == stable_predecessor
assert successor_path.read_text(encoding="utf-8") == stable_successor

# A relation missing closure time is attention on both sides, never a normal
# successor or closed-predecessor projection.
predecessor_path.write_text(
    re.sub(r"(?m)^closed_at:.*\n", "", stable_predecessor), encoding="utf-8"
)
partial_board = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
partial_records = [item for bucket in partial_board["solve_records"]["buckets"].values() for item in bucket]
partial_predecessor = next(item for item in partial_records if item["path"] == predecessor["receipt"])
partial_successor = next(item for item in partial_records if item["path"] == converged_successor["receipt"])
assert partial_predecessor["handoff_projection"] == "inconsistent_handoff_attention"
assert partial_successor["handoff_projection"] == "inconsistent_handoff_attention"
predecessor_path.write_text(stable_predecessor, encoding="utf-8")

missing_successor_backlink = ticket.read_text(encoding="utf-8").replace(
    f"- `../solve-records/{successor_path.name}`\n", ""
)
ticket.write_text(missing_successor_backlink, encoding="utf-8")
backlink_board = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
backlink_records = [item for bucket in backlink_board["solve_records"]["buckets"].values() for item in bucket]
backlink_predecessor = next(item for item in backlink_records if item["path"] == predecessor["receipt"])
backlink_successor = next(item for item in backlink_records if item["path"] == converged_successor["receipt"])
assert backlink_predecessor["handoff_projection"] == "inconsistent_handoff_attention"
assert backlink_successor["handoff_projection"] == "inconsistent_handoff_attention"
ticket.write_text(ticket_text, encoding="utf-8")

# Recovery outcomes can also be successors and use the same reciprocal board gate.
cross_ticket.write_text(
    cross_ticket.read_text(encoding="utf-8")
    .replace("Status: ready-for-human", "Status: ready-for-agent")
    .replace("Flags:", "Flags: solve-in-progress", 1),
    encoding="utf-8",
)
recovery_successor = json.loads(run(
    sys.executable, str(facade), "ticket", "handoff",
    "--repo", str(repo), "--ticket-id", "cross-B",
    "--handoff-key", "cross-recovery-successor", "--outcome", "needs-info",
    "--summary", "A later recovery outcome remains meaningful.",
    "--recovery-next-action", "inspect", "--supersedes", cross_predecessor["receipt"],
).stdout)["data"]
assert recovery_successor["status"] == "success", recovery_successor
recovery_board = json.loads(run(sys.executable, str(board), "--repo", str(repo), "--json").stdout)
recovery_records = [item for bucket in recovery_board["solve_records"]["buckets"].values() for item in bucket]
projected_recovery_successor = next(item for item in recovery_records if item["path"] == recovery_successor["receipt"])
assert projected_recovery_successor["handoff_projection"] == "normal_active_recovery"

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
