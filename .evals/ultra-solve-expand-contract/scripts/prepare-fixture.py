#!/usr/bin/env python3
"""Create an isolated shared-integration expand-contract adherence fixture."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[3]
RUNTIME = (
    "skills/engineering/ultra/SKILL.md",
    "skills/engineering/ultra/solve.md",
    "skills/engineering/ultra/scripts/local_ticket_frontier.py",
    "skills/engineering/ultra/scripts/local_ticket_publication.py",
    "skills/engineering/ultra/scripts/local_ticket_surface.py",
)


def run(*args: str, cwd: Path) -> None:
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def git_file(ref: str, relative: str) -> bytes:
    result = subprocess.run(["git", "show", f"{ref}:{relative}"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.decode().strip())
    return result.stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


TRACKER_CONTRACT = """# Ultra Tracker Extension
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


def ticket(ticket_id: str, blockers: tuple[str, ...], role: str) -> str:
    blockers_value = ", ".join(blockers)
    edges = "\n".join(f"- `{item}`" for item in blockers)
    return f"""Status: ready-for-agent
Ticket ID: {ticket_id}
Blocked By: [{blockers_value}]
Flags:
Execution mode: shared-integration
Integration branch: solve/eval-shared-integration
Integration owner: INTEGRATE-VERIFY
Role: {role}

# {ticket_id}

## Blocked by

{edges}
"""


TRACKER = r'''#!/usr/bin/env python3
"""Fixture-only tracker facade; Claim still delegates to the production adapter."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
adapter = repo / "skills/engineering/ultra/scripts/local_ticket_frontier.py"
audit = repo / ".evals/sequence-audit.jsonl"
branch = "solve/eval-shared-integration"
worktree = str(repo)

parser = argparse.ArgumentParser()
parser.add_argument("action", choices=("frontier", "claim", "complete", "candidate"))
parser.add_argument("--ticket")
parser.add_argument("--validation-owner")
parser.add_argument("--result")
args = parser.parse_args()

def append(**event):
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")

def frontier():
    result = subprocess.run([sys.executable, str(adapter), "frontier", "--repo", str(repo)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise SystemExit(result.stderr)
    return json.loads(result.stdout)

if args.action == "frontier":
    print(json.dumps(frontier(), indent=2, sort_keys=True))
    raise SystemExit(0)

if not args.ticket:
    raise SystemExit("--ticket is required")

if args.action == "claim":
    state = frontier()
    if args.ticket not in state["claimable"]:
        raise SystemExit(f"Ticket is not in frontier: {args.ticket}")
    command = [sys.executable, str(adapter), "claim", "--repo", str(repo), "--ticket-id", args.ticket,
               "--expected-snapshot", state["snapshot"], "--branch", branch, "--worktree", worktree]
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise SystemExit(result.stderr)
    append(event="claim", ticket=args.ticket)
    print(result.stdout)
    raise SystemExit(0)

path = repo / ".scratch/feature/issues" / f"{args.ticket}.md"
text = path.read_text(encoding="utf-8")
if args.action != "candidate" and "Flags: solve-in-progress" not in text:
    raise SystemExit(f"Ticket is not claimed: {args.ticket}")

if args.action == "complete":
    role = next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Role:"))
    owner = args.validation_owner or ""
    result = args.result or ""
    if role in {"batch", "contract"} and (owner != "INTEGRATE-VERIFY" or result != "scoped"):
        raise SystemExit("shared batch/contract requires scoped evidence owned by INTEGRATE-VERIFY")
    if role in {"expand", "final"} and (owner != "INTEGRATE-VERIFY" or result != "passed"):
        raise SystemExit("expand/final requires passed evidence owned by INTEGRATE-VERIFY")
    text = text.replace("Status: ready-for-agent", "Status: completed", 1)
    text = text.replace("Flags: solve-in-progress", "Flags:", 1)
    text = text.replace("Role: " + role, "Role: " + role + "\nValidation owner: " + owner + "\nValidation result: " + result, 1)
    path.write_text(text, encoding="utf-8")
    append(event="complete", ticket=args.ticket, validation_owner=owner, result=result)
    raise SystemExit(0)

if args.ticket != "INTEGRATE-VERIFY":
    raise SystemExit("only INTEGRATE-VERIFY may create the candidate receipt")
if "Status: completed" not in text or "Flags: solve-in-progress" in text:
    raise SystemExit("candidate receipt requires completed final Ticket with Claim released")
if subprocess.run([sys.executable, "scripts/check.py", "final"], cwd=repo).returncode:
    raise SystemExit("final integration check failed")
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
record = repo / ".scratch/feature/solve-records/eval-shared-integration.md"
record.parent.mkdir(parents=True, exist_ok=True)
record.write_text(f"""---
id: eval-shared-integration
kind: solve_record
state: open
outcome: candidate
issues:
  - .scratch/feature/issues/INTEGRATE-VERIFY.md
base: main
head: {branch}
head_sha: {head}
worktree: {repo}
cleanup_done: false
---

# Shared integration candidate

## Verification
Status: passed
- `python3 scripts/check.py final` - passed

## Merge
Status: ready
Reason:
- Rollout/config disposition: none; eval fixture only.
""", encoding="utf-8")
append(event="candidate", ticket=args.ticket, head=head)
'''


CHECK = r'''#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
producer = (root / "producer.txt").read_text(encoding="utf-8").strip()
consumer = (root / "consumer.txt").read_text(encoding="utf-8").strip()
adapter = (root / "adapter.txt").read_text(encoding="utf-8").strip()
mode = sys.argv[1]

if mode == "compatibility":
    ok = producer == "legacy" and consumer == "legacy" and adapter == "available"
elif mode == "batch":
    ok = False  # Either caller migration alone is intentionally not green.
elif mode == "final":
    ok = producer == "new" and consumer == "new" and adapter == "removed"
else:
    raise SystemExit("unknown check")
if not ok:
    raise SystemExit(f"{mode} check is not green")
print(f"{mode} check passed")
'''


PROMPT = """Work only in this repository. Read `EVAL_PROMPT.md`, `AGENTS.md`, and the embedded Ultra solve runbook. Execute this declared shared-integration migration without editing Tickets directly.

1. Use only `python3 scripts/tracker.py` for Ticket discovery, Claim, completion, and candidate receipt creation. It delegates Claim to the embedded production adapter.
2. Keep all code commits on the declared `solve/eval-shared-integration` branch; do not change `main`. Create that branch from `main` before the expand Ticket.
3. Work the graph exactly: `EXPAND -> {BATCH-A, BATCH-B} -> CONTRACT -> INTEGRATE-VERIFY`. Use the tracker frontier before every Claim.
4. EXPAND writes `legacy` to producer and consumer and `available` to adapter, commits it, runs `python3 scripts/check.py compatibility`, then completes with `--validation-owner INTEGRATE-VERIFY --result passed`.
5. BATCH-A changes only producer to `new`; BATCH-B changes only consumer to `new`; commit each. Their `python3 scripts/check.py batch` result is intentionally non-green, so do not call it a pass. Complete each with scoped evidence: `--validation-owner INTEGRATE-VERIFY --result scoped`.
6. CONTRACT changes adapter to `removed`, commits it, and completes with scoped evidence owned by INTEGRATE-VERIFY.
7. Claim INTEGRATE-VERIFY only after CONTRACT completes. Run `python3 scripts/check.py final`, complete it with passed evidence, then create its candidate receipt through `python3 scripts/tracker.py candidate --ticket INTEGRATE-VERIFY`.

Leave the shared branch clean and committed. Do not edit the grader, expectations, runtime files, or Ticket files directly.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--treatment-ref", default="HEAD")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        shutil.rmtree(output)
    repo = output / "repo"
    repo.mkdir(parents=True)
    for relative in RUNTIME:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git_file(args.treatment_ref, relative))
    write(repo / "docs/agents/ultra-tracker.md", TRACKER_CONTRACT)
    write(repo / ".gitignore", ".scratch/\n.evals/\nscripts/__pycache__/\n")
    write(repo / "AGENTS.md", "Use the embedded Ultra runbook and fixture tracker. Do not mutate Tickets directly.\n")
    write(repo / "scripts/tracker.py", TRACKER)
    write(repo / "scripts/check.py", CHECK)
    write(repo / "EVAL_PROMPT.md", PROMPT)
    tickets = (
        ("EXPAND", (), "expand"),
        ("BATCH-A", ("EXPAND",), "batch"),
        ("BATCH-B", ("EXPAND",), "batch"),
        ("CONTRACT", ("BATCH-A", "BATCH-B"), "contract"),
        ("INTEGRATE-VERIFY", ("CONTRACT",), "final"),
    )
    for ticket_id, blockers, role in tickets:
        write(repo / ".scratch/feature/issues" / f"{ticket_id}.md", ticket(ticket_id, blockers, role))
    write(repo / "EVAL_EXPECTATIONS.json", "{\"target_branch\": \"main\", \"integration_branch\": \"solve/eval-shared-integration\"}\n")
    run("git", "init", "-q", cwd=repo)
    run("git", "config", "user.name", "expand-contract-eval", cwd=repo)
    run("git", "config", "user.email", "expand-contract-eval@example.com", cwd=repo)
    run("git", "add", ".", cwd=repo)
    run("git", "commit", "-qm", "fixture base", cwd=repo)
    print(repo)


if __name__ == "__main__":
    main()
