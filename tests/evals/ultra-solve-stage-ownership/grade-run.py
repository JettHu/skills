#!/usr/bin/env python3
"""Grade Ultra Stage Ownership model runs from final state, never prose."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Grade:
    scenario: str
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def check(self, condition: bool, message: str) -> None:
        (self.passed if condition else self.failed).append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True)


def receipt_helper(repo: Path):
    path = repo / "skills/engineering/solve-records/scripts/solve-records.py"
    spec = importlib.util.spec_from_file_location("stage_ownership_records", path)
    if not spec or not spec.loader:
        raise SystemExit(f"missing receipt helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def status(ticket: str) -> str:
    for line in ticket.splitlines():
        if line.lower().startswith("status:"):
            return line.split(":", 1)[1].strip().lower()
    return ""


def candidate_dir(repo: Path, receipt: dict | None) -> Path:
    if receipt and receipt.get("worktree"):
        path = Path(receipt["worktree"])
        return path if path.is_absolute() else (repo / path).resolve()
    return repo


def evidence_file(repo: Path, candidate: Path) -> Path:
    for path in (candidate / "eval/stage-evidence.json", repo / "eval/stage-evidence.json"):
        if path.is_file():
            return path
    return candidate / "eval/stage-evidence.json"


def exclusive_writers(events: list[dict]) -> bool:
    active = {}
    for event in events:
        kind = event.get("event") or event.get("name")
        worktree = event.get("worktree")
        actor = event.get("actor")
        if kind == "writer-acquire":
            if not worktree or not actor or worktree in active:
                return False
            active[worktree] = actor
        elif kind == "writer-handoff":
            if active.get(worktree) != actor:
                return False
            active.pop(worktree)
    return not active


def names(events: list[dict | str]) -> list[str]:
    return [event if isinstance(event, str) else event.get("event", event.get("name", "")) for event in events]


def grade(repo: Path) -> Grade:
    config = json.loads(read(repo / "EVAL_EXPECTATIONS.json"))
    expected = config["expected"]
    result = Grade(config["scenario"])
    ticket = read(repo / config["issue_path"])
    result.check(status(ticket) == expected["status"], f"Ticket status is {expected['status']}")

    helper = receipt_helper(repo)
    receipts = [record for record in helper.discover(repo) if config["issue_path"] in record.get("issues", [])]
    result.check(len(receipts) == 1, "exactly one linked receipt exists")
    receipt = receipts[0] if len(receipts) == 1 else None
    if receipt:
        result.check(not receipt.get("malformed"), "receipt passes canonical parser")
        result.check(receipt.get("outcome") == expected["outcome"], f"receipt outcome is {expected['outcome']}")
        if expected["outcome"] == "candidate":
            result.check(receipt.get("base") == "main", "candidate landing branch remains main")
        else:
            result.check(not any(receipt.get(key) for key in ("base", "base_sha", "head", "head_sha")), "recovery has no candidate refs")

    candidate = candidate_dir(repo, receipt)
    evidence_path = evidence_file(repo, candidate)
    try:
        evidence = json.loads(read(evidence_path))
    except json.JSONDecodeError:
        evidence = {}
    result.check(bool(evidence), "structured stage evidence exists")
    result.check(evidence.get("implementation_route") == expected["route"], f"implementation route is {expected['route']}")
    result.check(evidence.get("root_exception") == expected["root_exception"], "root exception matches fixture")
    actual_events = evidence.get("events", [])
    actual_names = names(actual_events)
    cursor = 0
    for expected_event in expected["events"]:
        try:
            cursor = actual_names.index(expected_event, cursor) + 1
        except ValueError:
            result.check(False, f"ordered event exists: {expected_event}")
            break
    else:
        result.check(True, "required stage events are ordered")
    result.check(exclusive_writers([event for event in actual_events if isinstance(event, dict)]), "writer evidence is exclusive and handed off")

    if expected["route"] == "delegated":
        acquires = [event for event in actual_events if isinstance(event, dict) and (event.get("event") or event.get("name")) == "writer-acquire"]
        result.check(len(acquires) == 1 and acquires[0].get("actor") != "root", "one bounded implementation subagent acquired the worktree")
    if expected["review_action"]:
        actions = evidence.get("review_actions", [])
        result.check(expected["review_action"] in actions, f"review action includes {expected['review_action']}")

    result.check(git(repo, "rev-parse", "main").stdout.strip() == git(repo, "rev-parse", "eval-base").stdout.strip(), "landing branch was not advanced")
    actual = read(candidate / "app/result.txt").strip()
    result.check(actual == expected["result"], f"repository result is {expected['result']}")
    if expected["outcome"] == "candidate":
        check = subprocess.run(["python3", "scripts/check.py"], cwd=candidate, text=True, capture_output=True)
        result.check(check.returncode == 0, "candidate validation passes")
        result.check(git(candidate, "status", "--porcelain").stdout.strip() == "", "candidate worktree is clean")
    else:
        result.check(git(repo, "diff", "eval-base", "--", "app/result.txt").stdout == "", "human-owned stop did not implement a choice")
    return result


def expectation_files(paths: list[Path]) -> list[Path]:
    found = []
    for path in paths:
        if (path / "EVAL_EXPECTATIONS.json").is_file():
            found.append(path / "EVAL_EXPECTATIONS.json")
        else:
            found.extend(path.glob("**/repo/EVAL_EXPECTATIONS.json"))
    return sorted(set(found))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    grades = [grade(path.parent) for path in expectation_files(args.paths)]
    if not grades:
        raise SystemExit("no eval fixtures found")
    if args.json:
        print(json.dumps([grade.__dict__ for grade in grades], indent=2))
    else:
        for item in grades:
            print("PASS" if not item.failed else "FAIL", item.scenario)
            for failure in item.failed:
                print("  FAIL:", failure)
    if any(item.failed for item in grades):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
