#!/usr/bin/env python3
"""Prepare, execute, and grade resumable primary/Qoder Ultra profile eval runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREPARE = HERE / "prepare-fixture.py"
GRADER = HERE / "grade-run.py"


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def next_attempt(root: Path) -> int:
    found = [int(path.name.removeprefix("attempt-")) for path in root.glob("attempt-[0-9][0-9][0-9]")]
    return max(found, default=0) + 1


def command_output(args: list[str]) -> str:
    result = subprocess.run(args, text=True, capture_output=True)
    return (result.stdout or result.stderr).strip()


def resolve_ref(ref: str) -> str:
    if ref == "working-tree":
        raise SystemExit(
            "model eval runs require committed treatment/ablation refs; "
            "working-tree is prepare-fixture-only"
        )
    value = ref
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{value}^{{commit}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(f"cannot resolve eval ref {ref}: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--treatment-ref", required=True)
    parser.add_argument("--ablation-ref", required=True)
    parser.add_argument("--runtime", choices=("primary", "qoder"), default="qoder")
    parser.add_argument("--model", required=True)
    parser.add_argument("--context-window", type=int)
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--qoder-bin", default="qodercli")
    parser.add_argument("--primary-bin", default="codex")
    parser.add_argument("--variant", choices=("both", "treatment", "ablation"), default="both")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.runtime == "qoder" and args.context_window is None:
        parser.error("--context-window is required for the Qoder runtime")
    variants = ("treatment", "ablation") if args.variant == "both" else (args.variant,)
    ref_shas = {
        "treatment": resolve_ref(args.treatment_ref),
        "ablation": resolve_ref(args.ablation_ref),
    }

    failed = False
    for variant in variants:
        variant_root = output / args.run_id / args.scenario / variant
        attempt = next_attempt(variant_root)
        prepare = [
            sys.executable, str(PREPARE), "--output", str(output), "--run-id", args.run_id,
            "--scenario", args.scenario, "--variant", variant, "--attempt", str(attempt),
            "--treatment-ref", ref_shas["treatment"], "--ablation-ref", ref_shas["ablation"],
        ]
        subprocess.run(prepare, check=True)
        attempt_root = variant_root / f"attempt-{attempt:03d}"
        repo = attempt_root / "repo"
        prompt = (repo / "EVAL_PROMPT.md").read_text(encoding="utf-8")
        if args.runtime == "qoder":
            command = [
                args.qoder_bin, "-p", "--output-format", "stream-json", "--permission-mode",
                "bypass_permissions", "--cwd", str(repo), "--model", args.model,
                "--context-window", str(args.context_window),
            ]
            if args.reasoning_effort:
                command.extend(["--reasoning-effort", args.reasoning_effort])
            runtime_version = command_output([args.qoder_bin, "--version"])
        else:
            command = [
                args.primary_bin, "--ask-for-approval", "never", "exec", "--json", "--ephemeral",
                "--sandbox", "workspace-write",
                "-C", str(repo),
                "--model", args.model,
            ]
            if args.reasoning_effort:
                command.extend(["-c", f'model_reasoning_effort="{args.reasoning_effort}"'])
            runtime_version = command_output([args.primary_bin, "--version"])
        command.append(prompt)
        contract_ref = args.treatment_ref if variant == "treatment" else args.ablation_ref
        invocation = {
            "argv": command,
            "shell": shlex.join(command),
            "cwd": str(repo),
            "runtime": args.runtime,
            "runtime_version": runtime_version,
            "scenario": args.scenario,
            "variant": variant,
            "model": args.model,
            "context_window": args.context_window,
            "reasoning_effort": args.reasoning_effort or "default",
            "timeout_seconds": args.timeout,
            "refs": {
                "treatment": {"requested": args.treatment_ref, "sha": ref_shas["treatment"]},
                "ablation": {"requested": args.ablation_ref, "sha": ref_shas["ablation"]},
                "selected_contract": {"requested": contract_ref, "sha": ref_shas[variant]},
            },
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        write(attempt_root / "invocation.json", json.dumps(invocation, indent=2) + "\n")
        timed_out = False
        try:
            result = subprocess.run(command, cwd=repo, text=True, capture_output=True, timeout=args.timeout)
            run_exit = result.returncode
            stdout, stderr = result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            run_exit = 124
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        write(attempt_root / "raw-stdout.log", stdout)
        write(attempt_root / "raw-stderr.log", stderr)
        grade = subprocess.run(
            [sys.executable, str(GRADER), str(repo), "--trace", str(attempt_root / "raw-stdout.log"), "--json"],
            text=True,
            capture_output=True,
        )
        write(attempt_root / "grader-stdout.json", grade.stdout)
        write(attempt_root / "grader-stderr.log", grade.stderr)
        try:
            grade_payload = json.loads(grade.stdout)
            grade_result = grade_payload[0]
            invocation["observed_trace"] = grade_result.get("trace")
        except (json.JSONDecodeError, IndexError, AttributeError):
            grade_result = {}
            invocation["observed_trace"] = None
        invocation["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(attempt_root / "invocation.json", json.dumps(invocation, indent=2) + "\n")
        result_record = {
            "variant": variant,
            "attempt": attempt,
            "run_exit_code": run_exit,
            "timed_out": timed_out,
            "grader_exit_code": grade.returncode,
            "final_state_passed": grade_result.get("final_state_grade", {}).get("passed", False),
            "trace_passed": grade_result.get("trace_grade", {}).get("passed", False),
            "passed": run_exit == 0 and grade.returncode == 0,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "recovery": f"rerun the same command; a new attempt directory will be created after attempt-{attempt:03d}",
        }
        write(attempt_root / "result.json", json.dumps(result_record, indent=2) + "\n")
        print(json.dumps(result_record))
        failed = failed or not result_record["passed"]
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
