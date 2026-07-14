#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$ROOT" <<'PY'
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


root = Path(sys.argv[1])
adapter = root / "skills/engineering/ultra/scripts/local_ticket_frontier.py"
solve = (root / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")

for predicate in (
    "Ordinary work remains tracer-bullet execution",
    "one mechanical representation change",
    "adds the new form beside the old one",
    "Every **migration batch** is sized by blast radius",
    "contract** Ticket declares every migration batch as a blocker",
    "`Execution mode: shared-integration`",
    "**final integrate-and-verify** Ticket",
    "final integrate-and-verify declares contract as its blocker",
    "final integrate-and-verify Ticket alone owns the full green guarantee",
    "A completed blocker is a Claim predicate, not proof that its code exists",
    "only the final integrate-and-verify Ticket can create the candidate receipt",
):
    assert predicate in solve, f"expand-contract runbook predicate missing: {predicate}"


CONTRACT = """# Ultra Tracker Extension
Publication strategy: local-review-pending
Local Ticket representation: file-per-ticket
Local Ticket path: .scratch/<feature>/issues/<ticket-file>.md
Cancellation policy: retain-until-explicit-cleanup
Frontier adapter: bundled-local-markdown-v1
Ticket state fields: Status, State
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


def run(*args, cwd):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    return result.stdout


def write_ticket(repo, ticket_id, blockers=(), extra=""):
    edges = ", ".join(blockers)
    bullets = "\n".join(f"- `{blocker}`" for blocker in blockers)
    text = f"""Status: ready-for-agent
Ticket ID: {ticket_id}
Blocked By: [{edges}]
Flags:
{extra}
# Ticket {ticket_id}

## Blocked by

{bullets}
"""
    (repo / ".scratch/feature/issues" / f"{ticket_id}.md").write_text(text, encoding="utf-8")


def frontier(repo):
    return json.loads(run(sys.executable, str(adapter), "frontier", "--repo", str(repo), cwd=repo))


def complete(repo, ticket_id):
    path = repo / ".scratch/feature/issues" / f"{ticket_id}.md"
    path.write_text(path.read_text(encoding="utf-8").replace("Status: ready-for-agent", "Status: completed", 1), encoding="utf-8")


def scenario(name, tickets, expected):
    temp = Path(tempfile.mkdtemp(prefix=f"ultra-expand-contract-{name}-"))
    try:
        (temp / "docs/agents").mkdir(parents=True)
        (temp / ".scratch/feature/issues").mkdir(parents=True)
        (temp / "docs/agents/ultra-tracker.md").write_text(CONTRACT, encoding="utf-8")
        run("git", "init", "-q", cwd=temp)
        for ticket_id, blockers, extra in tickets:
            write_ticket(temp, ticket_id, blockers, extra)

        assert frontier(temp)["claimable"] == ["EXPAND"]
        complete(temp, "EXPAND")
        assert frontier(temp)["claimable"] == expected["batches"]
        complete(temp, expected["batches"][0])
        blocked = frontier(temp)["non_frontier"]
        assert expected["next"] in blocked
        assert f"blocked-by:{expected['batches'][1]}:ready-for-agent" in blocked[expected["next"]]
        complete(temp, expected["batches"][1])
        assert frontier(temp)["claimable"] == [expected["next"]]
        complete(temp, expected["next"])
        assert frontier(temp)["claimable"] == expected["after_next"]

        for ticket_id, blockers, _extra in tickets:
            text = (temp / ".scratch/feature/issues" / f"{ticket_id}.md").read_text(encoding="utf-8")
            for blocker in blockers:
                assert f"Blocked By: [{', '.join(blockers)}]" in text
                assert f"- `{blocker}`" in text
    finally:
        shutil.rmtree(temp)


scenario(
    "independently-green",
    (
        ("EXPAND", (), ""),
        ("MIGRATE-A", ("EXPAND",), ""),
        ("MIGRATE-B", ("EXPAND",), ""),
        ("CONTRACT", ("MIGRATE-A", "MIGRATE-B"), ""),
    ),
    {"batches": ["MIGRATE-A", "MIGRATE-B"], "next": "CONTRACT", "after_next": []},
)

scenario(
    "shared-integration",
    (
        ("EXPAND", (), ""),
        ("BATCH-A", ("EXPAND",), "Execution mode: shared-integration\nIntegration branch: solve/eval-shared-integration\nIntegration owner: INTEGRATE-VERIFY\n"),
        ("BATCH-B", ("EXPAND",), "Execution mode: shared-integration\nIntegration branch: solve/eval-shared-integration\nIntegration owner: INTEGRATE-VERIFY\n"),
        ("CONTRACT", ("BATCH-A", "BATCH-B"), "Execution mode: shared-integration\nIntegration branch: solve/eval-shared-integration\nIntegration owner: INTEGRATE-VERIFY\n"),
        ("INTEGRATE-VERIFY", ("CONTRACT",), "Execution mode: shared-integration\nIntegration branch: solve/eval-shared-integration\nIntegration owner: INTEGRATE-VERIFY\n"),
    ),
    {"batches": ["BATCH-A", "BATCH-B"], "next": "CONTRACT", "after_next": ["INTEGRATE-VERIFY"]},
)

print("ultra solve expand-contract fixture passed")
PY
