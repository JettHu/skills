#!/usr/bin/env python3
"""Create isolated claimable-frontier model-adherence fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_FILES = (
    "skills/engineering/ultra/SKILL.md",
    "skills/engineering/ultra/solve.md",
    "skills/engineering/ultra/scripts/local_ticket_frontier.py",
    "skills/engineering/ultra/scripts/local_ticket_publication.py",
    "skills/engineering/ultra/scripts/local_ticket_surface.py",
)


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "command failed")
    return result.stdout


def git_file(ref: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode().strip() or f"missing {relative} at {ref}")
    return result.stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def contract(safe: bool = True) -> str:
    claim = "Claim value: solve-in-progress\n" if safe else ""
    return f"""# Ultra Tracker Extension
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
{claim}Solve branch field: Solve Branch
Solve branch field aliases: Solve Branch, Branch
Solve worktree field: Solve Worktree
Solve worktree field aliases: Solve Worktree, Worktree
"""


def ticket(ticket_id: str, status: str = "ready-for-agent", blockers: tuple[str, ...] = ()) -> str:
    edges = "\n".join(f"- `{item}`" for item in blockers)
    return f"""Status: {status}
Ticket ID: {ticket_id}
Flags:

# Eval Ticket {ticket_id}

## Acceptance criteria

- [ ] Exercise only the configured discovery and Claim transition for this eval.

## Blocked by

{edges}
"""


TRACKER = r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
adapter = repo / "skills/engineering/ultra/scripts/local_ticket_frontier.py"
audit = repo / ".evals/claim-audit.jsonl"

def append(event, ticket):
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event": event, "ticket": ticket}, sort_keys=True) + "\n")

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=("frontier", "claim", "complete"))
parser.add_argument("--ticket-id", action="append", default=[])
parser.add_argument("--snapshot")
args = parser.parse_args()

if args.action == "frontier":
    command = [sys.executable, str(adapter), "frontier", "--repo", str(repo)]
    for ticket_id in args.ticket_id:
        command += ["--ticket-id", ticket_id]
    raise SystemExit(subprocess.run(command).returncode)

if len(args.ticket_id) != 1:
    raise SystemExit("claim/complete requires one --ticket-id")
ticket_id = args.ticket_id[0]
path = repo / ".scratch/feature/issues" / f"{ticket_id}.md"
if args.action == "claim":
    command = [
        sys.executable, str(adapter), "claim", "--repo", str(repo),
        "--ticket-id", ticket_id, "--expected-snapshot", args.snapshot or "",
        "--branch", f"solve/eval-{ticket_id.lower()}",
        "--worktree", str(repo.parent / f"worktree-{ticket_id.lower()}"),
    ]
    result = subprocess.run(command)
    if result.returncode == 0:
        append("claim", ticket_id)
    raise SystemExit(result.returncode)

text = path.read_text(encoding="utf-8")
if "Flags: solve-in-progress" not in text:
    raise SystemExit(f"Ticket is not claimed: {ticket_id}")
text = text.replace("Status: ready-for-agent", "Status: completed", 1)
text = text.replace("Flags: solve-in-progress", "Flags:", 1)
path.write_text(text, encoding="utf-8")
append("complete", ticket_id)
'''


def create_fixture(root: Path, scenario: str, treatment: str) -> None:
    repo = root / scenario / "repo"
    repo.mkdir(parents=True)
    for relative in RUNTIME_FILES:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git_file(treatment, relative))
    write(repo / "docs/agents/issue-tracker.md", "# Eval tracker\n")
    write(repo / "AGENTS.md", "Use the embedded Ultra skill and the configured tracker adapter. Do not edit Ticket state directly.\n")
    write(repo / "scripts/tracker.py", TRACKER)
    if scenario == "01-explicit":
        write(repo / "docs/agents/ultra-tracker.md", contract())
        write(repo / ".scratch/feature/issues/A.md", ticket("A"))
        write(repo / ".scratch/feature/issues/B.md", ticket("B", blockers=("A",)))
        write(repo / ".scratch/feature/issues/P.md", ticket("P", status="review-pending"))
        prompt = """Use the embedded `/ultra solve` discovery and Claim rules for the explicit set A, B, P. This eval stops after the initial frontier generation: use only `python3 scripts/tracker.py` to discover, Claim, and complete initially claimable Tickets. Do not rediscover or advance the explicit set. Do not edit Ticket files directly.\n"""
        expected = {"scenario": "explicit", "completed": ["A"], "unchanged": ["B", "P"]}
    elif scenario == "02-all":
        write(repo / "docs/agents/ultra-tracker.md", contract())
        write(repo / ".scratch/feature/issues/A.md", ticket("A"))
        write(repo / ".scratch/feature/issues/B.md", ticket("B", blockers=("A",)))
        write(repo / ".scratch/feature/issues/C.md", ticket("C", blockers=("A",)))
        write(repo / ".scratch/feature/issues/D.md", ticket("D", blockers=("B", "C")))
        prompt = """Use the embedded `/ultra solve --all` discovery and Claim rules. Repeatedly use only `python3 scripts/tracker.py` to discover the current frontier, Claim each returned Ticket with the current snapshot, complete it, then re-read until the frontier is empty. Do not edit Ticket files directly or preselect downstream Tickets.\n"""
        expected = {"scenario": "all", "completed": ["A", "B", "C", "D"]}
    else:
        write(repo / "docs/agents/ultra-tracker.md", contract(safe=False))
        write(repo / ".scratch/feature/issues/A.md", ticket("A"))
        prompt = """Use the embedded `/ultra solve --all` discovery rules. Attempt discovery only through `python3 scripts/tracker.py frontier`. The configured Claim contract is unsafe, so fail closed without editing the Ticket. After observing the refusal, write `.evals/EVAL_ATTEMPTED.json` containing `{"result":"unsafe-contract-refused"}` and stop.\n"""
        expected = {"scenario": "unsafe", "completed": [], "unchanged": ["A"]}
    write(repo / "EVAL_PROMPT.md", prompt)
    write(repo / "EVAL_EXPECTATIONS.json", json.dumps(expected, indent=2, sort_keys=True) + "\n")
    run("git", "init", "-q", cwd=repo)
    run("git", "config", "user.name", "frontier-eval", cwd=repo)
    run("git", "config", "user.email", "frontier-eval@example.com", cwd=repo)
    run("git", "add", ".", cwd=repo)
    run("git", "commit", "-qm", "fixture base", cwd=repo)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--treatment-ref", default="HEAD")
    parser.add_argument("--scenario", choices=("all", "01-explicit", "02-all", "03-unsafe"), default="all")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    scenarios = ("01-explicit", "02-all", "03-unsafe") if args.scenario == "all" else (args.scenario,)
    for scenario in scenarios:
        create_fixture(output, scenario, args.treatment_ref)
    print(output)


if __name__ == "__main__":
    main()
