#!/usr/bin/env python3
"""Grade Ultra profile runs from final repository and artifact state."""

from __future__ import annotations

import argparse
import ast
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


def safe_text(path: Path) -> tuple[str, bool]:
    try:
        return path.read_text(encoding="utf-8"), True
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return "", False


def git_output(repo: Path, args: list[str]) -> tuple[str, bool]:
    try:
        result = subprocess.run(
            ["git", *args], cwd=repo, text=True, capture_output=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return "", False
    return result.stdout, result.returncode == 0


def load_authority(
    repo: Path, control_path: Optional[Path]
) -> tuple[dict, str, str, list[str]]:
    """Load model-invisible authority, falling back to the fixture's root commit."""
    errors: list[str] = []
    control = control_path or repo.parent / "control.json"
    if control.is_file():
        try:
            payload = read_json(control)
            expected = payload["expectations"]
            baseline = payload["baseline_commit"]
            digest = payload["expectations_sha256"]
            workspace_digest = payload.get("workspace_expectations_sha256", digest)
            if (
                not isinstance(expected, dict)
                or not isinstance(baseline, str)
                or not isinstance(digest, str)
                or not isinstance(workspace_digest, str)
            ):
                raise ValueError("invalid control types")
            canonical = json.dumps(expected, indent=2) + "\n"
            if hashlib.sha256(canonical.encode()).hexdigest() != digest:
                raise ValueError("control digest mismatch")
            return expected, baseline, workspace_digest, errors
        except (KeyError, ValueError, json.JSONDecodeError, OSError, UnicodeDecodeError):
            errors.append("authoritative control record is missing or malformed")
            return {}, "", "", errors

    roots, ok = git_output(repo, ["rev-list", "--max-parents=0", "HEAD"])
    baseline = roots.splitlines()[0].strip() if ok and roots.splitlines() else ""
    raw, ok = (
        git_output(repo, ["show", f"{baseline}:EVAL_EXPECTATIONS.json"])
        if baseline
        else ("", False)
    )
    if not ok:
        errors.append("authoritative expectations are unavailable")
        return {}, baseline, "", errors
    try:
        expected = json.loads(raw)
    except json.JSONDecodeError:
        errors.append("authoritative expectations are malformed")
        return {}, baseline, "", errors
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return expected, baseline, digest, errors


def status(text: str) -> str:
    for line in text.splitlines():
        if line.lower().startswith("status:"):
            return line.split(":", 1)[1].strip()
    return ""


def normalize_event_name(name: object, aliases: dict[str, str]) -> object:
    return aliases.get(name, name) if isinstance(name, str) else name


def check_required_sequence(
    names: list[object], required: list[str], check, once_message: str, order_message: str,
    precedence: Optional[list[list[str]]] = None,
) -> None:
    check(
        all(names.count(name) == 1 for name in required),
        once_message,
        "required_events_once",
    )
    pairs = precedence if precedence is not None else [
        [before, after] for before, after in zip(required, required[1:])
    ]
    ordered = all(
        isinstance(pair, list)
        and len(pair) == 2
        and all(isinstance(name, str) and name in names for name in pair)
        and names.index(pair[0]) < names.index(pair[1])
        for pair in pairs
    )
    check(ordered, order_message, "required_stage_order")


def schema_v4_precedence(expected: dict, required: list[str]) -> list[list[str]]:
    configured = expected.get("required_event_precedence")
    if configured is not None:
        return configured if isinstance(configured, list) else [["__invalid__", "__invalid__"]]
    scenario = expected.get("scenario")
    if scenario in {"spec-independent-code-trigger", "long-stale-context"}:
        portable = [
            "ultra-independent-code", "target-native-explore", "target-artifact",
            "ultra-fresh-review", "validation",
        ]
        return [[before, after] for before, after in zip(portable, portable[1:])]
    if scenario == "tickets-review-publication":
        return [
            ["target-native-explore", "target-draft"],
            ["target-draft", "ultra-complete-set-review"],
            ["ultra-complete-set-review", "ultra-publication"],
            ["ultra-complete-set-review", "validation"],
        ]
    return [[before, after] for before, after in zip(required, required[1:])]


def changed_paths(repo: Path, baseline: str) -> tuple[set[str], bool]:
    tracked, tracked_ok = git_output(
        repo, ["-c", "core.safecrlf=false", "diff", "--no-ext-diff", "--name-only", baseline, "--"]
    )
    # Do not honor model-writable ignore configuration when enforcing the write set.
    untracked, untracked_ok = git_output(repo, ["ls-files", "--others"])
    return set(tracked.splitlines()) | set(untracked.splitlines()), tracked_ok and untracked_ok


def section_body(text: str, heading: str) -> str:
    lines = text.splitlines()
    wanted = f"## {heading}".casefold()
    start = next(
        (index for index, line in enumerate(lines) if line.strip().casefold() == wanted),
        None,
    )
    if start is None:
        return ""
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body).strip()


def validate_diagnosis_router(path: Path) -> tuple[bool, str]:
    """Validate the fixture fix structurally without executing model-authored code."""
    source, readable = safe_text(path)
    if not readable:
        return False, "app/router.py is missing or unreadable"
    wanted = "def route_order(order):\n    return 'priority' if order == 'priority' else 'standard'\n"
    try:
        actual_tree = ast.parse(source)
        wanted_tree = ast.parse(wanted)
    except SyntaxError as exc:
        return False, str(exc)
    valid = ast.dump(actual_tree, include_attributes=False) == ast.dump(
        wanted_tree, include_attributes=False
    )
    error = "" if valid else "route_order does not implement the required routing expression"
    return valid, error


def grade(
    repo: Path,
    trace: Optional[Path] = None,
    control: Optional[Path] = None,
    workflow_runtime_root: Optional[Path] = None,
) -> dict:
    (
        expected,
        baseline,
        workspace_expected_digest,
        authority_errors,
    ) = load_authority(repo, control)
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

    check_repository(
        not authority_errors,
        "authoritative expectations are available",
        "expectations_authority",
    )
    required_expectation_keys = {
        "scenario", "variant", "required_events", "artifact", "expected_result",
        "expected_tracker_status", "contract_hashes",
    }
    expectations_valid = (
        isinstance(expected, dict) and required_expectation_keys <= set(expected)
    )
    check_repository(
        expectations_valid,
        "authoritative expectation schema is complete",
        "expectations_schema",
    )
    workspace_expectations, workspace_expectations_present = safe_text(
        repo / "EVAL_EXPECTATIONS.json"
    )
    workspace_digest = hashlib.sha256(workspace_expectations.encode()).hexdigest()
    check_repository(
        workspace_expectations_present
        and bool(workspace_expected_digest)
        and workspace_digest == workspace_expected_digest,
        "workspace expectations match the model-invisible authority",
        "expectations_tampered",
    )

    evidence_path = repo / "artifacts/stage-evidence.json"
    try:
        evidence = read_json(evidence_path)
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
        evidence = {}
    if not isinstance(evidence, dict):
        evidence = {}
    events = evidence.get("events", [])
    schema_version = expected.get("schema_version")
    if schema_version == 4:
        event_keys = {"name", "evidence"}
    elif schema_version == 3:
        event_keys = {"name", "owner", "evidence"}
    else:
        event_keys = {"name", "owner", "goal", "evidence"}
    valid_events = (
        evidence_path.is_file()
        and not evidence_path.is_symlink()
        and isinstance(events, list)
        and all(
            isinstance(event, dict)
            and set(event) == event_keys
            and all(isinstance(event[key], str) and event[key].strip() for key in event)
            for event in events
        )
    )
    check_profile(valid_events, "stage evidence has the required final-state schema", "stage_schema")
    grading_events = events if valid_events else []
    aliases = expected.get("event_aliases", {}) if isinstance(expected.get("event_aliases", {}), dict) else {}
    raw_names = [event["name"] for event in grading_events]
    names = [normalize_event_name(name, aliases) for name in raw_names]
    stage_vocabulary = expected.get("stage_vocabulary")
    if schema_version in {2, 3, 4}:
        normalized_vocabulary = {
            normalize_event_name(name, aliases) for name in (stage_vocabulary or [])
        }
        check_profile(
            all(name in normalized_vocabulary for name in names),
            "recorded stages use the published stable vocabulary",
            "stage_vocabulary",
        )
        required = expected.get("required_events", [])
        check_required_sequence(
            names,
            required,
            check_profile,
            "each scenario-required completed stage is recorded exactly once",
            "scenario-required stages preserve their contract-relative order",
            schema_v4_precedence(expected, required) if schema_version == 4 else None,
        )
        if schema_version in {2, 3}:
            owners = expected.get("event_owners", {})
            owner_ok = all(
                owners.get(normalize_event_name(event.get("name"), aliases)) == event.get("owner")
                for event in grading_events
            )
            check_profile(owner_ok, "recorded stage owners match the hidden ownership contract", "stage_owner")
        if schema_version in {3, 4}:
            goal_identities = expected.get("event_goal_identities", {})
            stable_goal_ids = [goal_identities.get(name) for name in names]
            check_profile(
                all(isinstance(goal_id, str) and goal_id for goal_id in stable_goal_ids),
                "completed stages resolve to evaluator-owned stable goal identities",
                "stable_goal_identity",
            )
            check_profile(
                len(stable_goal_ids) == len(set(stable_goal_ids)),
                "completed stages have distinct stable evidence-goal identities",
                "duplicate_evidence_goal",
            )
        else:
            goals = [event.get("goal") for event in grading_events]
            check_profile(
                len(goals) == len(set(goals)),
                "completed stages have distinct evidence goals",
                "unique_evidence_goals",
            )
    elif stage_vocabulary is not None:
        normalized_vocabulary = {normalize_event_name(name, aliases) for name in stage_vocabulary}
        check_profile(
            all(name in normalized_vocabulary for name in names),
            "recorded stages use the published stable vocabulary",
            "stage_vocabulary",
        )
        if "required_events" in expected:
            required = expected.get("required_events", [])
            check_required_sequence(
                names, required, check_profile,
                "each scenario-required completed stage is recorded exactly once",
                "scenario-required stages preserve their contract-relative order",
            )
        else:
            for name in expected.get("required_recorded_events", []):
                check_profile(
                    names.count(name) == 1,
                    f"completed public stage is recorded exactly once: {name}",
                    f"recorded_event:{name}",
                )
    else:
        # Historical fixtures predate actual-stage ledgers. Preserve their literal
        # regrade behavior without imposing that treatment sequence on new runs.
        required = expected.get("required_events", [])
        check_required_sequence(
            names,
            required,
            check_profile,
            "each required evidence goal runs exactly once",
            "required stage order is preserved",
        )
        check_profile(
            not set(names) & set(expected.get("forbidden_events", [])),
            "forbidden or duplicate-ownership stages are absent",
            "forbidden_events_absent",
        )
        goals = [event.get("goal") for event in grading_events]
        check_profile(
            len(goals) == len(set(goals)),
            "evidence goals have a single owner and execution",
            "unique_evidence_goals",
        )

    artifact_relative = expected.get("artifact", "")
    artifact = repo / artifact_relative if artifact_relative else repo / "__missing_artifact__"
    artifact_text, artifact_readable = safe_text(artifact)
    check_repository(
        artifact.is_file() and not artifact.is_symlink(),
        f"artifact is a regular file: {artifact_relative}",
        "artifact_exists",
    )
    check_repository(artifact_readable, "artifact is readable UTF-8 text", "artifact_readable")
    for token in expected.get("artifact_tokens", []):
        check_repository(
            token.casefold() in artifact_text.casefold(),
            f"artifact covers: {token}",
            f"artifact_token:{token}",
        )
    for heading in expected.get("artifact_sections", []):
        check_repository(
            len(section_body(artifact_text, heading).split()) >= 4,
            f"artifact has substantive section: {heading}",
            f"artifact_section:{heading}",
        )
    for source in expected.get("artifact_sources", []):
        check_repository(
            source in artifact_text and (repo / source).is_file(),
            f"artifact cites existing repository evidence: {source}",
            f"artifact_source:{source}",
        )

    actual_result_text, result_present = safe_text(repo / "app/result.txt")
    actual_result = actual_result_text.strip()
    check_repository(
        result_present
        and not (repo / "app/result.txt").is_symlink()
        and actual_result == expected.get("expected_result"),
        "immutable validator confirms the scenario result",
        "repository_result",
    )
    validation_exit = 0 if result_present and actual_result == expected.get("expected_result") else 1
    validation_stdout = ""
    validation_stderr = ""
    if expected.get("scenario") == "diagnosis-feedback-loop-first":
        router_valid, validation_stderr = validate_diagnosis_router(repo / "app/router.py")
        validation_exit = 0 if router_valid and validation_exit == 0 else 1
    check_repository(validation_exit == 0, "immutable external validator passes", "repository_validation")

    tracker, tracker_present = safe_text(repo / ".scratch/eval/issues/01-order-routing.md")
    check_repository(
        tracker_present
        and not (repo / ".scratch/eval/issues/01-order-routing.md").is_symlink()
        and status(tracker) == expected.get("expected_tracker_status"),
        "tracker state matches the scenario contract",
        "tracker_status",
    )

    unexpected_paths: list[str] = []
    if schema_version in {2, 3, 4}:
        paths, paths_ok = changed_paths(repo, baseline)
        write_set_violations = paths - set(expected.get("allowed_changes", []))
        # Exclude bound Workflow runtime paths from write-set violations.
        # Only .qoder/sessions/<session>/workflows/<workflow>/ paths that
        # match a Workflow detected in the runtime trace are allowed.
        # All other .qoder/** paths remain violations.
        # trace_summary is not yet computed at this point; the exclusion
        # is deferred to after trace summarization below.
        unexpected_paths = sorted(write_set_violations)
        check_repository(paths_ok, "initial fixture baseline is available", "baseline_unavailable")
        check_repository(
            not unexpected_paths,
            "repository changes stay within the scenario write set",
            "scenario_write_set",
        )

    if expected.get("scenario") == "tickets-review-publication":
        try:
            receipt = read_json(repo / "artifacts/publication-receipt.json")
        except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeDecodeError):
            receipt = {}
        check_repository(
            not (repo / "artifacts/publication-receipt.json").is_symlink()
            and receipt == {"adapter": "local-publication", "status": "promoted"},
            "publication adapter receipt is valid",
            "publication_receipt",
        )

    for relative, digest in expected.get("contract_hashes", {}).items():
        supplied = repo / "skill-input" / relative
        try:
            supplied_digest = hashlib.sha256(supplied.read_bytes()).hexdigest()
        except OSError:
            supplied_digest = ""
        check_repository(
            supplied.is_file() and not supplied.is_symlink() and supplied_digest == digest,
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
            trace_summary = summarize_trace(trace, workflow_runtime_root=workflow_runtime_root)
            trace_checks, trace_failures, trace_failure_codes = grade_trace(trace_summary, trace_expected)
            trace_checks.insert(0, "runtime trace is supplied for delegation grading")
            marker_to_event = {
                marker: name
                for name, marker in trace_expected.get("known_stage_markers", {}).items()
            }
            traced_names = [
                marker_to_event[marker]
                for call in trace_summary.get("agent_calls", [])
                for marker in call.get("stage_markers", [])
                if marker in marker_to_event
            ]
            reconciled = set(trace_expected.get("reconcile_events", []))
            ledger_sequence = [name for name in names if name in reconciled]
            trace_sequence = [name for name in traced_names if name in reconciled]
            mismatched = [
                name for name in trace_expected.get("reconcile_events", [])
                if names.count(name) != traced_names.count(name)
            ]
            if mismatched or ledger_sequence != trace_sequence:
                detail = ", ".join(mismatched) if mismatched else "relative order"
                trace_failures.append(
                    "stage ledger and completed runtime calls do not agree for: " + detail
                )
                trace_failure_codes.append("stage_trace_mismatch")
            else:
                trace_checks.append("stage ledger agrees with completed runtime stage markers")

    # Deferred write-set correction: if the trace summary reveals Workflow
    # sessions, exclude bound runtime paths from the write-set check.
    if trace_summary is not None and schema_version in {2, 3, 4}:
        from trace_evidence import classify_workflow_write_set
        for wf_session in trace_summary.get("workflow_sessions", []):
            session_id = wf_session.get("session_id", "")
            workflow_id = wf_session.get("workflow_id", "")
            if session_id and workflow_id:
                bound = classify_workflow_write_set(
                    set(unexpected_paths), session_id, workflow_id,
                )
                if bound:
                    unexpected_paths = sorted(set(unexpected_paths) - bound)
                    # Re-evaluate the write-set check
                    if "scenario_write_set" in repository_failure_codes:
                        repository_failure_codes.remove("scenario_write_set")
                        repository_failures[:] = [
                            f for f in repository_failures
                            if "scenario write set" not in f
                        ]
                    if not unexpected_paths:
                        repository_checks[:] = [
                            c for c in repository_checks
                            if "scenario write set" not in c
                        ]
                        repository_checks.append(
                            "repository changes stay within the scenario write set"
                            " (Workflow runtime paths excluded)"
                        )

    profile_checks.extend(trace_checks)
    profile_failures.extend(trace_failures)
    profile_failure_codes.extend(trace_failure_codes)
    checks = repository_checks + profile_checks
    failures = repository_failures + profile_failures
    final_state_checks = repository_checks + [check for check in profile_checks if check not in trace_checks]
    final_state_failures = repository_failures + [failure for failure in profile_failures if failure not in trace_failures]
    return {
        "scenario": expected.get("scenario", "unknown"),
        "variant": expected.get("variant", "unknown"),
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
            "command": "immutable grade-run.py validator",
            "exit_code": validation_exit,
            "stdout": validation_stdout,
            "stderr": validation_stderr,
        },
        "unexpected_changes": unexpected_paths,
    }


def find_repos(paths: list[Path]) -> list[Path]:
    repos = []
    for path in paths:
        if path.is_dir() and (
            (path / ".git").exists() or (path.parent / "control.json").is_file()
        ):
            repos.append(path)
        else:
            repos.extend(item for item in path.glob("**/repo") if item.is_dir())
    return sorted(set(repo.resolve() for repo in repos))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--control", type=Path)
    parser.add_argument(
        "--workflow-runtime-root",
        type=Path,
        help="Root directory for Qoder Workflow runtime artifacts (.qoder/sessions/...)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    repos = find_repos(args.paths)
    if args.trace and len(repos) != 1:
        raise SystemExit("--trace requires exactly one prepared eval repository")
    results = [
        grade(repo, args.trace, args.control, workflow_runtime_root=args.workflow_runtime_root)
        for repo in repos
    ]
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
