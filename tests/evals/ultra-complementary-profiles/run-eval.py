#!/usr/bin/env python3
"""Prepare, execute, and grade resumable Qoder Ultra profile eval runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys


HERE = Path(__file__).resolve().parent
PREPARE = HERE / "prepare-fixture.py"
GRADER = HERE / "grade-run.py"


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def next_attempt(root: Path) -> int:
    found = [int(path.name.removeprefix("attempt-")) for path in root.glob("attempt-[0-9][0-9][0-9]")]
    return max(found, default=0) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--treatment-ref", required=True)
    parser.add_argument("--ablation-ref", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--context-window", type=int, required=True)
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--qoder-bin", default="qodercli")
    parser.add_argument("--variant", choices=("both", "treatment", "ablation"), default="both")
    args = parser.parse_args()
    output = args.output.resolve()
    variants = ("treatment", "ablation") if args.variant == "both" else (args.variant,)

    failed = False
    for variant in variants:
        variant_root = output / args.run_id / args.scenario / variant
        attempt = next_attempt(variant_root)
        prepare = [
            sys.executable, str(PREPARE), "--output", str(output), "--run-id", args.run_id,
            "--scenario", args.scenario, "--variant", variant, "--attempt", str(attempt),
            "--treatment-ref", args.treatment_ref, "--ablation-ref", args.ablation_ref,
        ]
        subprocess.run(prepare, check=True)
        attempt_root = variant_root / f"attempt-{attempt:03d}"
        repo = attempt_root / "repo"
        prompt = (repo / "EVAL_PROMPT.md").read_text(encoding="utf-8")
        command = [
            args.qoder_bin, "-p", "--output-format", "stream-json", "--permission-mode",
            "bypass_permissions", "--cwd", str(repo), "--model", args.model,
            "--context-window", str(args.context_window),
        ]
        if args.reasoning_effort:
            command.extend(["--reasoning-effort", args.reasoning_effort])
        command.append(prompt)
        invocation = {
            "argv": command,
            "shell": shlex.join(command),
            "cwd": str(repo),
            "model": args.model,
            "context_window": args.context_window,
            "reasoning_effort": args.reasoning_effort or "default",
            "timeout_seconds": args.timeout,
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
            [sys.executable, str(GRADER), str(repo), "--json"], text=True, capture_output=True
        )
        write(attempt_root / "grader-stdout.json", grade.stdout)
        write(attempt_root / "grader-stderr.log", grade.stderr)
        result_record = {
            "variant": variant,
            "attempt": attempt,
            "run_exit_code": run_exit,
            "timed_out": timed_out,
            "grader_exit_code": grade.returncode,
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
