#!/usr/bin/env python3
"""Prepare isolated final-state model eval fixtures for Ultra Stage Ownership."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL_PATHS = (
    "skills/engineering/ultra/SKILL.md",
    "skills/engineering/ultra/solve.md",
    "skills/engineering/solve-records/references/record-format.md",
    "skills/engineering/solve-records/scripts/solve-records.py",
)


def clean(value: str) -> str:
    return textwrap.dedent(value).strip() + "\n"


def run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    return result.stdout


def read_ref(ref: str, path: str) -> str:
    if ref == "working-tree":
        return (ROOT / path).read_text(encoding="utf-8")
    return run(["git", "show", f"{ref}:{path}"], ROOT)


SCENARIOS = {
    "01-direct-all-evidence": {
        "route": "direct",
        "result": "direct-complete",
        "body": """
            Positive current evidence establishes all six direct properties:
            simple, familiar, local, low-risk, fully specified, and obviously
            verifiable. Change only `app/result.txt` and run the check.
        """,
        "events": ["implement", "validate", "review", "finalize"],
    },
    "02-delegated-unproven": {
        "route": "delegated",
        "result": "delegated-complete",
        "body": """
            The change is local and specified, but familiarity is deliberately
            unproven. Runtime capability declares implementation delegation
            available and the assigned worktree verifiable. Use exactly one
            bounded implementation subagent as writer until handoff.
        """,
        "events": ["writer-acquire", "implement", "validate", "writer-handoff", "root-reread", "finalize"],
    },
    "03-preferred-read-only": {
        "route": "delegated",
        "result": "reviewed-complete",
        "body": """
            A bounded exploration pass and independent review need fresh context.
            Suitable read-only delegation is available; use it before implementation
            and after validation. Implementation familiarity is unproven.
        """,
        "events": ["explore-subagent", "writer-acquire", "implement", "validate", "writer-handoff", "review-subagent", "root-reread", "finalize"],
    },
    "04-root-read-only-exception": {
        "route": "direct",
        "result": "root-exception-complete",
        "body": """
            Positive current evidence establishes every direct property. The bounded
            verification stage is trivial and local, so record that objective
            root-execution exception rather than delegating that read-only stage.
        """,
        "root_exception": "trivial-local",
        "events": ["implement", "root-verify", "review", "finalize"],
    },
    "05-dependent-serialized": {
        "route": "delegated",
        "result": "serialized-complete",
        "body": """
            Familiarity is unproven. Stage B depends on Stage A. Use one bounded
            implementation writer in the assigned worktree, finish and validate A,
            then execute B. Never overlap dependent stages or writers.
        """,
        "events": ["writer-acquire", "stage-a", "validate-a", "stage-b", "validate-b", "writer-handoff", "root-reread", "finalize"],
    },
    "06-autonomous-repair": {
        "route": "delegated",
        "result": "repaired-complete",
        "body": """
            Familiarity is unproven. After the first implementation, apply
            `REVIEW_FINDING.md`: its P3 repair is derivable and acceptance-affecting.
            Repair, revalidate, and re-review without asking the user.
        """,
        "events": ["writer-acquire", "implement", "review-finding", "repair", "revalidate", "rereview", "writer-handoff", "root-reread", "finalize"],
        "review_action": "repair-revalidate-rereview",
    },
    "07-human-owned-escalation": {
        "route": "none",
        "result": "unchanged",
        "body": """
            Choose whether public identity exposes email, internal id, or opaque id.
            Product, security, and data ownership have not approved a choice. Do not
            implement one; route the meaningful Attempt to ready-for-human recovery.
        """,
        "status": "ready-for-human",
        "outcome": "ready-for-human",
        "events": ["assess", "human-owned", "recovery-finalize"],
        "review_action": "human-recovery",
    },
}


def ticket(name: str, scenario: dict) -> str:
    return clean(
        f"""
        Status: ready-for-agent
        Flags:
        Ticket ID: {name}

        # Stage ownership scenario {name}

        ## What to build

        {clean(scenario['body']).strip()}

        ## Acceptance criteria

        - Leave `app/result.txt` equal to `{scenario['result']}`.
        - Run `python3 scripts/check.py` when implementation is allowed.
        - Preserve `main`; do not merge, push, land, or clean up.
        - Record eval-only stage evidence at `eval/stage-evidence.json`.
        """
    )


def create(repo: Path, name: str, scenario: dict, ref: str) -> None:
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    for path in SKILL_PATHS:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(read_ref(ref, path), encoding="utf-8")

    issue_path = f".scratch/stage-ownership/issues/{name}.md"
    files = {
        "AGENTS.md": clean("""
            # Eval guidance

            Embedded Ultra files are authoritative. `main` is the landing branch.
            Work only in this disposable repository. Eval-only stage evidence is
            required final-state evidence, not a production Ultra artifact.
        """),
        issue_path: ticket(name, scenario),
        "app/result.txt": "unchanged\n",
        "scripts/check.py": clean(f"""
            from pathlib import Path
            actual = (Path(__file__).resolve().parents[1] / "app/result.txt").read_text().strip()
            assert actual == {scenario['result']!r}, (actual, {scenario['result']!r})
            print("stage ownership check passed")
        """),
        "RUNTIME_CAPABILITIES.md": clean("""
            Implementation delegation: available
            Read-only delegation: available
            Assigned-worktree verification: available
            Concurrent non-namespaced shared-state mutation: not required
        """),
        "REVIEW_FINDING.md": clean("""
            P3: The first-pass value is not the Ticket's required final value.
            The repair is fully derivable from the Ticket and local check.
        """),
        "EVAL_PROMPT.md": clean(f"""
            Read AGENTS.md, RUNTIME_CAPABILITIES.md, the embedded Ultra runbook,
            its linked Solve Record format, and the authoritative Ticket at
            `{issue_path}`. Execute `/ultra solve {issue_path}` exactly.

            Do not merge, push, land, or clean up. Leave final repository, Ticket,
            validation, receipt, candidate worktree, and `eval/stage-evidence.json`
            state for the grader. The evidence JSON must record `implementation_route`,
            optional `root_exception`, ordered `events`, exclusive writer acquire and
            handoff events with worktree/actor fields when delegated, and review
            actions when applicable. Do not edit EVAL_EXPECTATIONS.json.
        """),
    }
    for path, value in files.items():
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding="utf-8")

    expectation = {
        "scenario": name,
        "issue_path": issue_path,
        "expected": {
            "route": scenario["route"],
            "result": scenario["result"],
            "status": scenario.get("status", "completed"),
            "outcome": scenario.get("outcome", "candidate"),
            "events": scenario["events"],
            "root_exception": scenario.get("root_exception"),
            "review_action": scenario.get("review_action"),
        },
    }
    (repo / "EVAL_EXPECTATIONS.json").write_text(json.dumps(expectation, indent=2) + "\n", encoding="utf-8")
    run(["git", "init", "-q", "-b", "main"], repo)
    run(["git", "config", "user.name", "Stage Ownership Eval"], repo)
    run(["git", "config", "user.email", "stage-ownership@example.invalid"], repo)
    run(["git", "add", "-A", "-f"], repo)
    run(["git", "commit", "-qm", f"fixture: {name}"], repo)
    run(["git", "tag", "eval-base"], repo)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--treatment-ref", default="HEAD")
    args = parser.parse_args()
    selected = SCENARIOS.items() if args.scenario == "all" else ((args.scenario, SCENARIOS[args.scenario]),)
    for name, scenario in selected:
        create(args.output / args.run_id / name / "repo", name, scenario, args.treatment_ref)
    print(args.output / args.run_id)


if __name__ == "__main__":
    main()
