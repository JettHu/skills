#!/usr/bin/env python3
"""Grade Ultra profile runs from final repository and artifact state."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Optional

from trace_evidence import grade as grade_trace
from trace_evidence import summarize as summarize_trace


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def status(text: str) -> str:
    for line in text.splitlines():
        if line.lower().startswith("status:"):
            return line.split(":", 1)[1].strip()
    return ""


def normalize_event_name(name: object, aliases: dict[str, str]) -> object:
    return aliases.get(name, name) if isinstance(name, str) else name


def grade(repo: Path, trace: Optional[Path] = None) -> dict:
    expected = read_json(repo / "EVAL_EXPECTATIONS.json")
    profile_failures: list[str] = []
    profile_failure_codes: list[str] = []
    profile_checks: list[str] = []
    repository_failures: list[str] = []
    repository_failure_codes: list[str] = []
    repository_checks: list[str] = []

    def check_profile(condition: bool, message: str, code: str) -> None:
        (profile_checks if condition else profile_failures).append(message)
        if not condition:
            profile_failure_codes.append(code)

    def check_repository(condition: bool, message: str, code: str) -> None:
        (repository_checks if condition else repository_failures).append(message)
        if not condition:
            repository_failure_codes.append(code)

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
    check_profile(valid_events, "stage evidence has the required final-state schema", "stage_schema")
    aliases = expected.get("event_aliases", {})
    raw_names = [event.get("name") for event in events if isinstance(event, dict)]
    names = [normalize_event_name(name, aliases) for name in raw_names]
    stage_vocabulary = expected.get("stage_vocabulary")
    if stage_vocabulary is not None:
        normalized_vocabulary = {
            normalize_event_name(name, aliases) for name in stage_vocabulary
        }
        check_profile(
            all(name in normalized_vocabulary for name in names),
            "recorded stages use the published stable vocabulary",
            "stage_vocabulary",
        )
        required = expected["required_events"]
        check_profile(
            all(names.count(name) == 1 for name in required),
            "each scenario-required completed stage is recorded exactly once",
            "required_events_once",
        )
        cursor = 0
        ordered = True
        for name in required:
            try:
                cursor = names.index(name, cursor) + 1
            except ValueError:
                ordered = False
                break
        check_profile(
            ordered,
            "scenario-required stages preserve their contract-relative order",
            "required_stage_order",
        )
    else:
        # Historical fixtures predate actual-stage ledgers. Preserve their literal
        # regrade behavior without imposing that treatment sequence on new runs.
        required = expected["required_events"]
        check_profile(
            all(names.count(name) == 1 for name in required),
            "each required evidence goal runs exactly once",
            "required_events_once",
        )
        cursor = 0
        ordered = True
        for name in required:
            try:
                cursor = names.index(name, cursor) + 1
            except ValueError:
                ordered = False
                break
        check_profile(ordered, "required stage order is preserved", "required_stage_order")
        check_profile(
            not set(names) & set(expected["forbidden_events"]),
            "forbidden or duplicate-ownership stages are absent",
            "forbidden_events_absent",
        )
        goals = [event.get("goal") for event in events if isinstance(event, dict)]
        check_profile(
            len(goals) == len(set(goals)),
            "evidence goals have a single owner and execution",
            "unique_evidence_goals",
        )

    artifact = repo / expected["artifact"]
    artifact_text = artifact.read_text(encoding="utf-8") if artifact.is_file() else ""
    check_repository(artifact.is_file(), f"artifact exists: {expected['artifact']}", "artifact_exists")
    for token in expected["artifact_tokens"]:
        check_repository(
            token.casefold() in artifact_text.casefold(),
            f"artifact covers: {token}",
            f"artifact_token:{token}",
        )

    validation = subprocess.run(
        [sys.executable, "scripts/check.py"], cwd=repo, text=True, capture_output=True
    )
    check_repository(validation.returncode == 0, "repository validation passes now", "repository_validation")
    actual_result = (repo / "app/result.txt").read_text(encoding="utf-8").strip()
    check_repository(
        actual_result == expected["expected_result"],
        "repository result matches the scenario outcome",
        "repository_result",
    )
    tracker = (repo / ".scratch/eval/issues/01-order-routing.md").read_text(encoding="utf-8")
    check_repository(
        status(tracker) == expected["expected_tracker_status"],
        "tracker state matches the scenario contract",
        "tracker_status",
    )

    for relative, digest in expected["contract_hashes"].items():
        supplied = repo / "skill-input" / relative
        check_repository(
            supplied.is_file() and hashlib.sha256(supplied.read_bytes()).hexdigest() == digest,
            f"supplied contract remains unchanged: {relative}",
            f"supplied_contract:{relative}",
        )
    check_repository((repo / "EVAL_PROMPT.md").is_file(), "eval prompt remains present", "eval_prompt_present")
    trace_summary = None
    trace_expected = expected.get("trace_expectations")
    trace_checks: list[str] = []
    trace_failures: list[str] = []
    trace_failure_codes: list[str] = []
    if trace_expected:
        if trace is None or not trace.is_file():
            trace_failures.append("runtime trace is supplied for delegation grading")
            trace_failure_codes.append("runtime_trace_supplied")
        else:
            trace_checks.append("runtime trace is supplied for delegation grading")
            trace_summary = summarize_trace(trace)
            trace_checks, trace_failures, trace_failure_codes = grade_trace(trace_summary, trace_expected)
            trace_checks.insert(0, "runtime trace is supplied for delegation grading")
    profile_checks.extend(trace_checks)
    profile_failures.extend(trace_failures)
    profile_failure_codes.extend(trace_failure_codes)
    checks = repository_checks + profile_checks
    failures = repository_failures + profile_failures
    final_state_checks = repository_checks + [check for check in profile_checks if check not in trace_checks]
    final_state_failures = repository_failures + [failure for failure in profile_failures if failure not in trace_failures]
    return {
        "scenario": expected["scenario"],
        "variant": expected["variant"],
        "passed": not failures,
        "checks": checks,
        "failures": failures,
        "failure_codes": repository_failure_codes + profile_failure_codes,
        "final_state_grade": {
            "passed": not final_state_failures,
            "checks": final_state_checks,
            "failures": final_state_failures,
        },
        "repository_grade": {
            "passed": not repository_failures,
            "checks": repository_checks,
            "failures": repository_failures,
            "failure_codes": repository_failure_codes,
        },
        "profile_grade": {
            "passed": not profile_failures,
            "checks": profile_checks,
            "failures": profile_failures,
            "failure_codes": profile_failure_codes,
        },
        "trace_grade": {
            "required": bool(trace_expected),
            "passed": not trace_failures,
            "checks": trace_checks,
            "failures": trace_failures,
            "failure_codes": trace_failure_codes,
        },
        "trace": trace_summary,
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
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    repos = find_repos(args.paths)
    if args.trace and len(repos) != 1:
        raise SystemExit("--trace requires exactly one prepared eval repository")
    results = [grade(repo, args.trace) for repo in repos]
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
