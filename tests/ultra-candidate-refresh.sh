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
repo = root / "repo"
worktree = root / "candidate"


def run(*command: str, check: bool = True, env=None):
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    if check and result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result


run("git", "init", "-q", "-b", "main", str(repo))
run("git", "-C", str(repo), "config", "user.email", "refresh@example.test")
run("git", "-C", str(repo), "config", "user.name", "Refresh Fixture")
(repo / "base.txt").write_text("base\n", encoding="utf-8")
run("git", "-C", str(repo), "add", "base.txt")
run("git", "-C", str(repo), "commit", "-qm", "base")
run("git", "-C", str(repo), "worktree", "add", "-qb", "solve/refresh", str(worktree))
(worktree / "candidate.txt").write_text("one\n", encoding="utf-8")
run("git", "-C", str(worktree), "add", "candidate.txt")
run("git", "-C", str(worktree), "commit", "-qm", "candidate one")
first = run("git", "-C", str(worktree), "rev-parse", "HEAD").stdout.strip()

(repo / "docs/agents").mkdir(parents=True)
(repo / "docs/agents/ultra-tracker.md").write_text(f"""Frontier adapter: bundled-local-markdown-v1
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
ticket.write_text(f"""Status: completed
Ticket ID: A
Flags:
Solve Branch: solve/refresh
Solve Worktree: {worktree}

# Ticket A
""", encoding="utf-8")
record_name = hashlib.sha256(b"refresh-key").hexdigest() + ".md"
record = repo / ".scratch/feature/solve-records" / record_name
record.parent.mkdir(parents=True)


def binding(sha: str):
    value = {
        "repo": str(repo.resolve()),
        "handoff_key": "refresh-key",
        "tickets": [".scratch/feature/issues/A.md"],
        "outcome": "candidate",
        "head": "solve/refresh",
        "head_sha": sha,
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


record.write_text(f"""---
state: open
outcome: candidate
tickets:
  - .scratch/feature/issues/A.md
handoff_key: "refresh-key"
binding_digest: {binding(first)}
head: solve/refresh
head_sha: {first}
---

# Solve Record: Candidate

## Summary
Candidate ready for review.

## Gate Evidence
Base: `main`
Base SHA: `deadbeef`
Worktree: `{worktree}`
Checks: passed
Review: passed
Merge: ready
Landing: fast-forward, `{first}`
""", encoding="utf-8")
ticket.write_text(
    ticket.read_text(encoding="utf-8")
    + f"\n## Solve Records\n\n- `../solve-records/{record_name}`\n",
    encoding="utf-8",
)


def refresh(path: Path, observed: str, ticket_id: str = "A", check: bool = True, env=None):
    result = run(
        sys.executable, str(facade), "ticket", "refresh-candidate",
        "--repo", str(repo), "--record", str(path.relative_to(repo)),
        "--ticket-id", ticket_id, "--observed-head-sha", observed,
        check=False,
        env=env,
    )
    payload = json.loads(result.stdout)
    if check and (result.returncode or not payload["ok"]):
        raise AssertionError(payload)
    return result.returncode, payload


# Same-head retry is idempotent and preserves current evidence.
before = record.read_text(encoding="utf-8")
_, same = refresh(record, first)
assert same["data"]["status"] == "unchanged"
assert record.read_text(encoding="utf-8") == before

# A descendant head refreshes the same receipt and clears snapshot evidence.
(worktree / "candidate.txt").write_text("two\n", encoding="utf-8")
run("git", "-C", str(worktree), "add", "candidate.txt")
run("git", "-C", str(worktree), "commit", "-qm", "candidate two")
second = run("git", "-C", str(worktree), "rev-parse", "HEAD").stdout.strip()
tree = run("git", "-C", str(repo), "rev-parse", f"{second}^{{tree}}").stdout.strip()
concurrent = run(
    "git", "-C", str(repo), "commit-tree", tree, "-p", second, "-m", "concurrent candidate"
).stdout.strip()
concurrent_snapshot = record.read_text(encoding="utf-8")
code, concurrent_result = refresh(
    record,
    second,
    check=False,
    env=dict(os.environ, ULTRA_REFRESH_ADVANCE_HEAD_TO=concurrent),
)
assert code == 3 and concurrent_result["data"]["status"] == "conflict"
assert record.read_text(encoding="utf-8") == concurrent_snapshot
run("git", "-C", str(repo), "update-ref", "refs/heads/solve/refresh", second, concurrent)
precommit_snapshot = record.read_text(encoding="utf-8")
code, interrupted = refresh(
    record,
    second,
    check=False,
    env=dict(os.environ, ULTRA_REFRESH_FAIL_AFTER_RECEIPT="1"),
)
assert code == 6 and interrupted["data"]["status"] == "retryable"
assert record.read_text(encoding="utf-8") != precommit_snapshot
assert run("git", "-C", str(worktree), "rev-parse", "HEAD").stdout.strip() == second
_, changed = refresh(record, second)
assert changed["data"]["status"] == "unchanged"
updated = record.read_text(encoding="utf-8")
assert f"head_sha: {second}" in updated
assert "## Gate Evidence" not in updated
assert "refresh-key" in updated and record.exists()

# Retry stays idempotent; stale and non-current observations fail without writes.
_, retry = refresh(record, second)
assert retry["data"]["status"] == "unchanged"
snapshot = record.read_text(encoding="utf-8")
code, stale = refresh(record, first, check=False)
assert code == 3 and stale["data"]["status"] == "conflict"
assert record.read_text(encoding="utf-8") == snapshot
run("git", "-C", str(repo), "commit", "--allow-empty", "-qm", "unrelated")
unrelated = run("git", "-C", str(repo), "rev-parse", "HEAD").stdout.strip()
code, conflict = refresh(record, unrelated, check=False)
assert code == 3 and conflict["data"]["status"] == "conflict"
assert record.read_text(encoding="utf-8") == snapshot

# Exact Ticket scope and retained ownership are fail-closed.
code, scope = refresh(record, second, ticket_id="missing", check=False)
assert code == 3 and scope["data"]["status"] == "conflict"
ticket_text = ticket.read_text(encoding="utf-8")
ticket.write_text(ticket_text.replace("Solve Branch: solve/refresh", "Solve Branch: solve/other"), encoding="utf-8")
code, owner = refresh(record, second, check=False)
assert code == 3 and owner["data"]["status"] == "conflict"
assert record.read_text(encoding="utf-8") == snapshot
ticket.write_text(ticket_text, encoding="utf-8")

# Complete legacy records remain refreshable without schema migration.
legacy = repo / ".scratch/feature/solve-records/legacy.md"
legacy.write_text(f"""---
id: legacy
kind: solve_record
state: open
base: main
base_sha: {unrelated}
head: solve/refresh
head_sha: {second}
issues:
  - .scratch/feature/issues/A.md
worktree: {worktree}
created_at: 2026-09-07T00:00:00Z
cleanup_done: false
---

# Solve Record: Legacy

## Issues
- `.scratch/feature/issues/A.md`

## Changes
- Legacy candidate.

## Checks
Status: passed

## Review
Post-Execution Review: passed

## Merge
Status: ready
- Landing: fast-forward, `{second}`

## Resources
Base: `main`
Base SHA: `{unrelated}`
Head: `solve/refresh`
Head SHA: `{second}`
Worktree: `{worktree}`
Cleanup: pending
""", encoding="utf-8")
ticket.write_text(
    ticket.read_text(encoding="utf-8") + "- `../solve-records/legacy.md`\n",
    encoding="utf-8",
)
_, legacy_same = refresh(legacy, second)
assert legacy_same["data"]["status"] == "unchanged"
assert "kind: solve_record" in legacy.read_text(encoding="utf-8")
(worktree / "candidate.txt").write_text("three\n", encoding="utf-8")
run("git", "-C", str(worktree), "add", "candidate.txt")
run("git", "-C", str(worktree), "commit", "-qm", "candidate three")
third = run("git", "-C", str(worktree), "rev-parse", "HEAD").stdout.strip()
_, legacy_changed = refresh(legacy, third)
assert legacy_changed["data"]["status"] == "refreshed"
legacy_text = legacy.read_text(encoding="utf-8")
assert f"head_sha: {third}" in legacy_text and f"Head SHA: `{third}`" in legacy_text
assert "## Checks" not in legacy_text
assert "## Review" not in legacy_text
assert "## Merge" not in legacy_text
assert "Landing:" not in legacy_text
assert "kind: solve_record" in legacy_text
_, legacy_retry = refresh(legacy, third)
assert legacy_retry["data"]["status"] == "unchanged"

print("ultra candidate refresh fixture passed")
PY
