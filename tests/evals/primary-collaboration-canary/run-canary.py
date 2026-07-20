#!/usr/bin/env python3
"""Run and externally grade one isolated Primary collaboration runtime canary."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


HERE = Path(__file__).resolve().parent
PROFILE_EVAL = HERE.parent / "ultra-complementary-profiles"
sys.path.insert(0, str(PROFILE_EVAL))
from primary_runtime import PrimaryRuntimeAdapter  # noqa: E402


MARKER = "[eval-stage:primary-collaboration-canary]"
PROMPT = f"""You are the Root Agent in an isolated Primary collaboration runtime canary.

This task is self-contained. Do exactly the following:
1. Call the real spawn_agent/collaboration tool exactly once. Do not simulate delegation.
2. Include the stable marker {MARKER} in the child Agent prompt.
3. Tell that single child Agent to work read-only and read CANARY_INPUT.md.
4. Wait until that child Agent has completed before ending your own turn.

Do not modify any file. Do not claim the Agent ran unless the collaboration tool actually
ran. Do not invoke a Skill, slash command, Ticket 20 workflow, profile workflow, treatment,
or ablation. The child must also make no file changes. Keep the final response brief.
"""


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def next_attempt(run_root: Path) -> int:
    attempts = []
    for path in run_root.glob("attempt-[0-9][0-9][0-9]"):
        if path.is_dir():
            attempts.append(int(path.name.removeprefix("attempt-")))
    return max(attempts, default=0) + 1


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=True
    )
    return result.stdout


def prepare_fixture(repo: Path) -> dict[str, object]:
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Primary Canary Evaluator")
    git(repo, "config", "user.email", "primary-canary@example.invalid")
    input_text = "PRIMARY_COLLABORATION_CANARY_INPUT_V1\nRead-only child input.\n"
    (repo / "CANARY_INPUT.md").write_text(input_text, encoding="utf-8")
    git(repo, "add", "CANARY_INPUT.md")
    git(repo, "commit", "-q", "-m", "primary collaboration canary baseline")
    baseline = git(repo, "rev-parse", "HEAD").strip()
    return {
        "baseline_commit": baseline,
        "input_sha256": hashlib.sha256(input_text.encode()).hexdigest(),
        "tracked_entries": git(repo, "ls-files", "-s").splitlines(),
    }


def symlinks(repo: Path) -> list[str]:
    found: list[str] = []
    for root, dirs, files in os.walk(repo, followlinks=False):
        root_path = Path(root)
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in [*dirs, *files]:
            path = root_path / name
            if path.is_symlink():
                found.append(path.relative_to(repo).as_posix())
    return sorted(set(found))


def repository_evidence(repo: Path, baseline: str) -> dict[str, object]:
    committed = git(repo, "diff", "--name-status", baseline, "HEAD").splitlines()
    tracked = list(dict.fromkeys(
        git(repo, "diff", "--name-status").splitlines()
        + git(repo, "diff", "--cached", "--name-status").splitlines()
    ))
    untracked = git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    link_writes = symlinks(repo)
    return {
        "baseline_commit": baseline,
        "final_head": git(repo, "rev-parse", "HEAD").strip(),
        "tracked_write_set": tracked,
        "committed_write_set": committed,
        "untracked_write_set": untracked,
        "symlink_write_set": link_writes,
        "clean": not (tracked or committed or untracked or link_writes),
    }


def classify_features(exit_code: int, stdout: str) -> dict[str, object]:
    result: dict[str, object] = {
        "exit_code": exit_code,
        "multi_agent_recognized": False,
        "multi_agent_enabled": None,
        "passed": False,
        "error_code": None,
    }
    if exit_code != 0:
        result["error_code"] = "primary_feature_probe_failed"
        return result
    candidates = []
    for line in stdout.splitlines():
        fields = re.split(r"\s+", line.strip())
        if fields and fields[0] == "multi_agent":
            candidates.append(fields)
    if len(candidates) != 1 or not candidates[0] or candidates[0][-1] not in {"true", "false"}:
        result["error_code"] = "primary_feature_protocol_unrecognized"
        return result
    result["multi_agent_recognized"] = True
    result["multi_agent_enabled"] = candidates[0][-1] == "true"
    if result["multi_agent_enabled"] is not True:
        result["error_code"] = "primary_multi_agent_unavailable"
        return result
    result["passed"] = True
    return result


def _tool_name(item: dict[str, object]) -> str:
    return str(item.get("tool") or item.get("name") or item.get("tool_name") or "")


def _is_spawn(item: dict[str, object]) -> bool:
    name = _tool_name(item)
    return name == "spawn_agent" or name.endswith(".spawn_agent") or name.endswith("__spawn_agent")


def _child_status(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("status") or value.get("state")
    return str(value or "unknown").casefold()


def grade_trace(raw_path: Path) -> dict[str, object]:
    merged: dict[str, dict[str, object]] = {}
    anonymous: list[dict[str, object]] = []
    for index, line in enumerate(raw_path.read_text(encoding="utf-8").splitlines()):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict) and event.get("type") == "collab_tool_call":
            item = event
        if not isinstance(item, dict) or item.get("type") != "collab_tool_call" or not _is_spawn(item):
            continue
        call_id = item.get("id") or item.get("call_id")
        call = merged.setdefault(str(call_id), {}) if call_id else {}
        for key, value in item.items():
            if value not in (None, "", [], {}):
                call[key] = value
        call["trace_index"] = index
        event_type = str(event.get("type") or "")
        if event_type in {"item.completed", "item.failed"}:
            call["terminal_event"] = True
        if not call_id:
            anonymous.append(call)
    calls = list(merged.values()) + anonymous
    marker_calls = []
    for call in calls:
        arguments = call.get("arguments") or call.get("input") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}
        prompt = call.get("prompt")
        if not prompt and isinstance(arguments, dict):
            prompt = arguments.get("prompt") or arguments.get("message")
        if MARKER in str(prompt or ""):
            marker_calls.append(call)

    selected = calls[0] if len(calls) == 1 else {}
    states = selected.get("agents_states") if isinstance(selected.get("agents_states"), dict) else {}
    receiver_ids = selected.get("receiver_thread_ids")
    identities = set(str(value) for value in states if str(value))
    if isinstance(receiver_ids, list):
        identities.update(str(value) for value in receiver_ids if str(value))
    child_states = [_child_status(value) for value in states.values()]
    outer_status = str(selected.get("status") or "unknown").casefold()
    failure_codes = []
    if len(calls) != 1:
        failure_codes.append("primary_spawn_count_invalid")
    if len(marker_calls) != 1 or len(calls) != 1:
        failure_codes.append("primary_spawn_marker_invalid")
    if not selected.get("terminal_event") or outer_status != "completed":
        failure_codes.append("primary_outer_collaboration_incomplete")
    if len(identities) != 1:
        failure_codes.append("primary_child_identity_invalid")
    if len(states) != 1 or child_states != ["completed"]:
        failure_codes.append("primary_child_terminal_state_invalid")
    return {
        "passed": not failure_codes,
        "failure_codes": failure_codes,
        "spawn_count": len(calls),
        "marked_spawn_count": len(marker_calls),
        "outer_status": outer_status,
        "child_identities": sorted(identities),
        "child_terminal_states": child_states,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--primary-bin", default="codex", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", args.run_id):
        parser.error("--run-id must be one immutable path component")
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    run_root = args.output.resolve() / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    attempt_number = next_attempt(run_root)
    attempt_root = run_root / f"attempt-{attempt_number:03d}"
    attempt_root.mkdir()
    evidence_repo = attempt_root / "fixture"
    control = prepare_fixture(evidence_repo)
    control.update({"marker": MARKER, "expected_spawn_count": 1, "expected_child_count": 1})
    write_json(attempt_root / "grader-control.json", control)

    errors: list[str] = []
    started_at = datetime.now(timezone.utc).isoformat()
    adapter = PrimaryRuntimeAdapter(
        evidence_repo=evidence_repo,
        primary_bin=args.primary_bin,
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        timeout=args.timeout,
    ).start()
    invocation = {
        "argv": adapter.command(PROMPT),
        "shell": shlex.join(adapter.command(PROMPT)),
        "cwd": str(adapter.runtime_repo),
        "runtime": "primary",
        "model": args.model,
        "reasoning_effort": args.reasoning_effort or "default",
        "timeout_seconds": args.timeout,
        "run_id": args.run_id,
        "attempt": attempt_number,
        "started_at": started_at,
        "runtime_isolation": {
            "temporary_home": str(adapter.runtime_home),
            "temporary_codex_home": str(adapter.codex_home),
            "auth_json_only_bridge": True,
            "auth_bridge_present": adapter.auth_bridge_present,
            "initial_codex_home_entries": adapter.initial_codex_home_entries,
            "neutral_opaque_git_cwd": True,
            "primary_session_persistence": "temporary-codex-home",
            "cleanup_succeeded": None,
        },
    }
    write_json(attempt_root / "invocation.json", invocation)
    raw_path = attempt_root / "raw-stdout.jsonl"
    stderr_path = attempt_root / "stderr.log"
    raw_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    runtime_exit = 125
    timed_out = False
    feature = {
        "exit_code": None,
        "multi_agent_recognized": False,
        "multi_agent_enabled": None,
        "passed": False,
        "error_code": "primary_feature_probe_failed",
    }
    try:
        version = adapter.probe(adapter.version_command())
        (attempt_root / "runtime-version.txt").write_text(
            (version.stdout or version.stderr).strip() + "\n", encoding="utf-8"
        )
        if version.exit_code != 0:
            errors.append("runtime_version_failed")
        else:
            feature_probe = adapter.probe(adapter.feature_command())
            (attempt_root / "feature-stdout.log").write_text(
                feature_probe.stdout, encoding="utf-8"
            )
            (attempt_root / "feature-stderr.log").write_text(
                feature_probe.stderr, encoding="utf-8"
            )
            feature = classify_features(feature_probe.exit_code, feature_probe.stdout)
            feature["command"] = adapter.feature_command()
            feature["cwd"] = str(adapter.runtime_repo)
            feature["environment"] = "same-as-model-invocation"
            if feature["error_code"]:
                errors.append(str(feature["error_code"]))
            if feature["passed"]:
                execution = adapter.execute(
                    PROMPT, stdout_path=raw_path, stderr_path=stderr_path
                )
                runtime_exit = execution.exit_code
                timed_out = execution.timed_out
                if execution.error_code:
                    errors.append(execution.error_code)
                elif runtime_exit != 0:
                    errors.append("runtime_exit_nonzero")
    finally:
        cleanup_codes = adapter.cleanup()
        errors.extend(cleanup_codes)

    write_json(attempt_root / "feature-preflight.json", feature)
    repository = repository_evidence(evidence_repo, str(control["baseline_commit"]))
    write_json(attempt_root / "repository-evidence.json", repository)
    trace = grade_trace(raw_path)
    grade = {
        **trace,
        "feature_preflight_passed": feature["passed"],
        "runtime_exit_code": runtime_exit,
        "runtime_timed_out": timed_out,
        "repository_clean": repository["clean"],
        "cleanup_succeeded": adapter.cleanup_succeeded,
    }
    grade["failure_codes"] = list(dict.fromkeys(
        [*grade["failure_codes"], *errors]
        + ([] if repository["clean"] else ["primary_repository_write_set_nonempty"])
        + ([] if adapter.cleanup_succeeded else ["primary_cleanup_failed"])
    ))
    grade["passed"] = (
        not grade["failure_codes"]
        and feature["passed"] is True
        and runtime_exit == 0
        and repository["clean"] is True
        and adapter.cleanup_succeeded is True
    )
    write_json(attempt_root / "grader-output.json", grade)
    invocation["finished_at"] = datetime.now(timezone.utc).isoformat()
    invocation["runtime_isolation"]["cleanup_succeeded"] = adapter.cleanup_succeeded
    write_json(attempt_root / "invocation.json", invocation)
    result = {
        "run_id": args.run_id,
        "attempt": attempt_number,
        "verdict": "PASS" if grade["passed"] else "FAIL",
        "passed": grade["passed"],
        "failure_codes": grade["failure_codes"],
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(attempt_root / "result.json", result)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if grade["passed"] else 1)


if __name__ == "__main__":
    main()
