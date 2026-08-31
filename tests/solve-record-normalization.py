#!/usr/bin/env python3
"""Focused fixtures for compact and legacy Solve Record normalization."""

import importlib.util
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/engineering/solve-records/scripts/solve-records.py"
spec = importlib.util.spec_from_file_location("solve_records", TOOL)
solve_records = importlib.util.module_from_spec(spec)
spec.loader.exec_module(solve_records)

BOARD = ROOT / "skills/in-progress/maintainer-board/scripts/maintainer-board.py"
board_spec = importlib.util.spec_from_file_location("maintainer_board", BOARD)
maintainer_board = importlib.util.module_from_spec(board_spec)
board_spec.loader.exec_module(maintainer_board)


def record(repo, name, frontmatter, body):
    path = repo / ".scratch/feature/solve-records" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return solve_records.parse_record(repo, path)


with tempfile.TemporaryDirectory() as tmp:
    repo = Path(tmp)
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, stdout=subprocess.DEVNULL)
    common = """id: compact
kind: solve_record
state: open
outcome: candidate
issues:
  - .scratch/feature/issues/01.md
created_at: 2026-08-31T10:00:00+08:00
cleanup_done: false
head: solve/compact
head_sha: abc1234"""
    compact = record(
        repo,
        "compact",
        common,
        """# Solve Record: Compact candidate

## Summary
Implemented the normalized parser and its focused fixtures.""",
    )
    assert "malformed" not in compact, compact
    assert compact["issues"] == [".scratch/feature/issues/01.md"]
    assert compact["outcome"] == "candidate"
    assert compact["summary"].startswith("Implemented")
    assert compact["base"] is None and compact["worktree"] is None

    alias = record(
        repo,
        "alias",
        common.replace("id: compact", "id: alias").replace(
            "issues:\n  - .scratch/feature/issues/01.md",
            "tickets:\n  - .scratch/feature/issues/01.md",
        ),
        """# Solve Record: Membership alias

## Ticket
Linked Ticket: .scratch/feature/issues/01.md

## Outcome
Result: candidate

## Outcome
Result: candidate

## Summary
The mirrors agree.""",
    )
    assert "malformed" not in alias, alias
    assert alias["issues"] == compact["issues"]

    conflict = record(
        repo,
        "conflict",
        common.replace("id: compact", "id: conflict"),
        """# Solve Record: Conflict

## Ticket
Linked Ticket: .scratch/feature/issues/02.md

## Outcome
Result: blocked

## Summary
Contradictory mirrors must fail closed.""",
    )
    assert conflict["malformed"] == (
        "conflicting representations: outcome frontmatter=candidate body=blocked; "
        "membership frontmatter=.scratch/feature/issues/01.md "
        "body=.scratch/feature/issues/02.md"
    )

    identity_conflict = record(
        repo,
        "identity-conflict",
        common.replace("id: compact", "id: identity-conflict"),
        """# Solve Record: Identity conflict

## Summary
The body carries a contradictory historical identity mirror.

## Resources
Head: `solve/compact`

## Resources
Head: `solve/other`""",
    )
    assert identity_conflict["malformed"] == (
        "conflicting representations: identity head "
        "frontmatter=solve/compact body=solve/other"
    )

    state_conflict = record(
        repo,
        "state-conflict",
        common.replace("id: compact", "id: state-conflict"),
        """# Solve Record: State conflict

## Summary
Status: open

## Summary
Status: closed""",
    )
    assert state_conflict["malformed"] == (
        "conflicting representations: state frontmatter=open body=closed"
    )

    body_identity_conflict = record(
        repo,
        "body-identity-conflict",
        common.replace("id: compact", "id: body-identity-conflict")
        .replace("outcome: candidate", "outcome: blocked")
        .replace("head: solve/compact\nhead_sha: abc1234", ""),
        """# Solve Record: Body identity conflict

## Summary
The historical mirrors disagree.

## Resources
Head: `solve/one`

## Resources
Head: `solve/two`""",
    )
    assert body_identity_conflict["malformed"] == (
        "conflicting representations: identity head body=solve/one,solve/two"
    )

    body_identity = record(
        repo,
        "body-identity",
        common.replace("id: compact", "id: body-identity")
        .replace("outcome: candidate", "outcome: blocked")
        .replace("head: solve/compact\nhead_sha: abc1234", ""),
        """# Solve Record: Body identity

## Summary
One historical mirror is unambiguous.

## Resources
Head: `solve/retained`""",
    )
    assert "malformed" not in body_identity, body_identity
    assert body_identity["head"] == "solve/retained"

    body_candidate_identity = record(
        repo,
        "body-candidate-identity",
        common.replace("id: compact", "id: body-candidate-identity").replace(
            "head: solve/compact\nhead_sha: abc1234", ""
        ),
        """# Solve Record: Historical candidate identity

## Summary
Historical identifiers remain readable.

## Resources
Head: `solve/historical`
Head SHA: `def5678`""",
    )
    assert "malformed" not in body_candidate_identity, body_candidate_identity
    assert body_candidate_identity["head"] == "solve/historical"
    assert body_candidate_identity["head_sha"] == "def5678"

    recovery = record(
        repo,
        "recovery",
        common.replace("id: compact", "id: recovery")
        .replace("outcome: candidate", "outcome: blocked")
        .replace("head: solve/compact\nhead_sha: abc1234", "")
        .replace("created_at: 2026-08-31T10:00:00+08:00\n", "")
        .replace("cleanup_done: false\n", ""),
        """# Solve Record: Compact recovery

## Summary
The environment is unavailable; retry after access is restored.""",
    )
    assert "malformed" not in recovery, recovery
    assert recovery["cleanup_done"] is None
    assert recovery["created_at"] is None
    refusal = solve_records.merge_gate(repo, recovery)
    assert refusal["eligible"] is False
    assert refusal["reasons"] == [
        "outcome is blocked; candidate-only operations are unavailable"
    ]

    incomplete_candidate = record(
        repo,
        "incomplete",
        common.replace("id: compact", "id: incomplete"),
        """# Solve Record: Initial candidate

## Summary
Ready for acceptance review; merge evidence is not recorded yet.""",
    )
    gate = solve_records.merge_gate(repo, incomplete_candidate)
    assert gate["eligible"] is False
    assert "base is unavailable for merge gate" in gate["reasons"]
    assert "worktree is unavailable for merge gate" in gate["reasons"]

    historical = record(
        repo,
        "historical",
        common.replace("id: compact", "id: historical")
        .replace("state: open", "state: closed")
        .replace("outcome: candidate", "outcome: superseded")
        .replace("head: solve/compact\nhead_sha: abc1234", "")
        .replace("cleanup_done: false", "cleanup_done: true"),
        """# Solve Record: Historical superseded attempt

## Summary
The later candidate replaced this attempt without rewriting its outcome.""",
    )
    assert "malformed" not in historical, historical

    dashboard = maintainer_board.load_solve_records_dashboard(repo)
    buckets = {
        name: {item["id"] for item in items}
        for name, items in dashboard["buckets"].items()
    }
    assert "recovery" in buckets["recovery"]
    assert "historical" in buckets["historical"]
    assert "conflict" in buckets["stale_or_malformed"]
    assert "identity-conflict" in buckets["stale_or_malformed"]
    assert "state-conflict" in buckets["stale_or_malformed"]
    assert "body-identity-conflict" in buckets["stale_or_malformed"]
    assert "compact" in buckets["manual"] or "compact" in buckets["stale_or_malformed"]
    assert solve_records.cleanup_plan(repo, historical) == {
        "id": "historical",
        "path": ".scratch/feature/solve-records/historical.md",
        "status": "done",
        "reason": "",
    }
    historical["cleanup_done"] = None
    assert solve_records.cleanup_plan(repo, historical)["reason"] == (
        "recovery cleanup facts are unavailable"
    )

print("solve-record normalization fixture passed")
