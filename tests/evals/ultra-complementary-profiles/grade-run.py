#!/usr/bin/env python3
"""Grade Ultra profile runs from final repository and artifact state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def status(text: str) -> str:
    for line in text.splitlines():
        if line.lower().startswith("status:"):
            return line.split(":", 1)[1].strip()
    return ""


def grade(repo: Path) -> dict:
    expected = read_json(repo / "EVAL_EXPECTATIONS.json")
    failures: list[str] = []
    checks: list[str] = []

    def check(condition: bool, message: str) -> None:
        (checks if condition else failures).append(message)

    evidence_path = repo / "artifacts/stage-evidence.json"
    try:
        evidence = read_json(evidence_path)
    except (FileNotFoundError, json.JSONDecodeError):
        evidence = {}
    events = evidence.get("events", [])
    valid_events = isinstance(events, list) and all(
        isinstance(event, dict) and set(event) == {"name", "owner", "goal", "evidence"}
        and all(isinstance(event[key], str) and event[key].strip() for key in event)
        for event in events
    )
    check(valid_events, "stage evidence has the required final-state schema")
    names = [event.get("name") for event in events if isinstance(event, dict)]
    required = expected["required_events"]
    check(all(names.count(name) == 1 for name in required), "each required evidence goal runs exactly once")
    cursor = 0
    ordered = True
    for name in required:
        try:
            cursor = names.index(name, cursor) + 1
        except ValueError:
            ordered = False
            break
    check(ordered, "required stage order is preserved")
    check(not set(names) & set(expected["forbidden_events"]), "forbidden or duplicate-ownership stages are absent")
    goals = [event.get("goal") for event in events if isinstance(event, dict)]
    check(len(goals) == len(set(goals)), "evidence goals have a single owner and execution")

    artifact = repo / expected["artifact"]
    artifact_text = artifact.read_text(encoding="utf-8") if artifact.is_file() else ""
    check(artifact.is_file(), f"artifact exists: {expected['artifact']}")
    for token in expected["artifact_tokens"]:
        check(token.casefold() in artifact_text.casefold(), f"artifact covers: {token}")

    validation = subprocess.run(
        [sys.executable, "scripts/check.py"], cwd=repo, text=True, capture_output=True
    )
    check(validation.returncode == 0, "repository validation passes now")
    actual_result = (repo / "app/result.txt").read_text(encoding="utf-8").strip()
    check(actual_result == expected["expected_result"], "repository result matches the scenario outcome")
    tracker = (repo / ".scratch/eval/issues/01-order-routing.md").read_text(encoding="utf-8")
    check(status(tracker) == expected["expected_tracker_status"], "tracker state matches the scenario contract")

    for relative, digest in expected["contract_hashes"].items():
        supplied = repo / "skill-input" / relative
        check(
            supplied.is_file() and hashlib.sha256(supplied.read_bytes()).hexdigest() == digest,
            f"supplied contract remains unchanged: {relative}",
        )
    check((repo / "EVAL_PROMPT.md").is_file(), "eval prompt remains present")
    return {
        "scenario": expected["scenario"],
        "variant": expected["variant"],
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "validation": {
            "command": "python3 scripts/check.py",
            "exit_code": validation.returncode,
            "stdout": validation.stdout,
            "stderr": validation.stderr,
        },
    }


def find_repos(paths: list[Path]) -> list[Path]:
    repos = []
    for path in paths:
        if (path / "EVAL_EXPECTATIONS.json").is_file():
            repos.append(path)
        else:
            repos.extend(item.parent for item in path.glob("**/repo/EVAL_EXPECTATIONS.json"))
    return sorted(set(repo.resolve() for repo in repos))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = [grade(repo) for repo in find_repos(args.paths)]
    if not results:
        raise SystemExit("no prepared eval repositories found")
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            print("PASS" if result["passed"] else "FAIL", result["scenario"], result["variant"])
            for failure in result["failures"]:
                print("  FAIL:", failure)
    raise SystemExit(0 if all(result["passed"] for result in results) else 1)


if __name__ == "__main__":
    main()
