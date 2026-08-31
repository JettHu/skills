#!/usr/bin/env python3
"""Create an isolated candidate-handoff model-adherence fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_FILES = (
    "skills/engineering/ultra/scripts/ultra_tracker.py",
    "skills/engineering/ultra/scripts/local_outcome_handoff.py",
    "skills/engineering/ultra/scripts/local_ticket_frontier.py",
    "skills/engineering/ultra/scripts/local_ticket_publication.py",
    "skills/engineering/ultra/scripts/local_ticket_surface.py",
)


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "command failed")
    return result.stdout.strip()


def git_file(ref: str, relative: str) -> bytes:
    result = subprocess.run(["git", "show", f"{ref}:{relative}"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.decode().strip() or f"missing {relative} at {ref}")
    return result.stdout


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--treatment-ref", default="HEAD")
    args = parser.parse_args()
    repo = Path(args.output).resolve()
    if repo.exists():
        raise RuntimeError(f"fixture output must not already exist: {repo}")
    repo.mkdir(parents=True)
    for relative in RUNTIME_FILES:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(git_file(args.treatment_ref, relative))
    write(repo / "AGENTS.md", "Use only `python3 scripts/tracker.py` for the requested outcome handoff. Do not edit Ticket or receipt files directly.\n")
    write(repo / "docs/agents/ultra-tracker.md", """Frontier adapter: bundled-local-markdown-v1
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
""")
    write(repo / "scripts/tracker.py", """#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[1]
facade = repo / 'skills/engineering/ultra/scripts/ultra_tracker.py'
result = subprocess.run([sys.executable, str(facade), *sys.argv[1:]], text=True)
if result.returncode == 0:
    audit = repo / '.evals/handoff-audit.jsonl'
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'argv': sys.argv[1:]}) + '\\n')
raise SystemExit(result.returncode)
""")
    run("git", "init", "-q", "-b", "solve/eval-A", cwd=repo)
    run("git", "config", "user.name", "handoff-eval", cwd=repo)
    run("git", "config", "user.email", "handoff-eval@example.test", cwd=repo)
    ticket = repo / ".scratch/outcome/issues/A.md"
    write(ticket, f"""Status: ready-for-agent
Ticket ID: A
Flags: solve-in-progress
Solve Branch: solve/eval-A
Solve Worktree: {repo}
Blocked By:

# Eval Ticket A
""")
    write(repo / "candidate.txt", "candidate\n")
    write(repo / "EVAL_PROMPT.md", """Finalize Ticket A's candidate outcome using only `python3 scripts/tracker.py ticket handoff` and the configured facade. Use handoff key `model-eval-candidate-A` and Summary `Candidate behavior and deterministic validation are complete.` Do not edit lifecycle artifacts directly. Stop after the facade reports success.
""")
    write(repo / "EVAL_EXPECTATIONS.json", json.dumps({"key": "model-eval-candidate-A", "ticket": "A"}, indent=2) + "\n")
    run("git", "add", ".", cwd=repo)
    run("git", "commit", "-qm", "candidate fixture", cwd=repo)
    print(repo)


if __name__ == "__main__":
    main()
