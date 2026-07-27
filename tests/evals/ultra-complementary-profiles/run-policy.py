#!/usr/bin/env python3
"""Execute the frozen Ticket 20 prospective policy from one canonical manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from prospective_policy import (
    MANIFEST_NAME,
    build_canonical_manifest,
    build_phase_verdict,
    cell_runtime_invoked,
    ensure_canonical_manifest,
    first_unfinished_phase,
    load_policy,
    phase_may_start,
    validate_manifest,
    write_phase_verdict,
)


HERE = Path(__file__).resolve().parent
EVAL_RUNNER = HERE / "run-eval.py"
PAIR_VERDICT = HERE / "pair_verdict.py"


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _latest_attempt(output: Path, cell: dict, variant: str) -> Path:
    root = output / "runs" / cell["run_id"] / cell["scenario"] / variant
    attempts = sorted(root.glob("attempt-[0-9][0-9][0-9]"))
    if not attempts:
        raise ValueError(f"missing {variant} attempt for policy cell {cell['run_id']}")
    return attempts[-1]


def _treatment_result(output: Path, cell: dict) -> dict:
    attempt = _latest_attempt(output, cell, "treatment")
    invocation = _read_json(attempt / "invocation.json")
    result = _read_json(attempt / "result.json")
    grade = json.loads((attempt / "grader-stdout.json").read_text(encoding="utf-8"))[0]
    return {
        "run_id": cell["run_id"],
        "treatment_passed": (
            result.get("run_exit_code") == 0
            and invocation.get("runtime_invoked") is True
            and invocation.get("model_started") is True
            and grade.get("passed") is True
        ),
    }


def _pair_result(output: Path, cell: dict) -> dict:
    root = output / "runs" / cell["run_id"] / cell["scenario"]
    verdicts = sorted(root.glob("pair-verdict-*.json"))
    if len(verdicts) != 1:
        raise ValueError("phase 1 requires exactly one durable pair verdict")
    return {"run_id": cell["run_id"], **_read_json(verdicts[0])}


def _write_pair_verdict(output: Path, cell: dict) -> None:
    root = output / "runs" / cell["run_id"] / cell["scenario"]
    command = [
        sys.executable, str(PAIR_VERDICT),
        "--treatment-attempt", str(_latest_attempt(output, cell, "treatment")),
        "--ablation-attempt", str(_latest_attempt(output, cell, "ablation")),
        "--output", str(root),
    ]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr or result.stdout or "cannot write phase 1 pair verdict")


def _completed_phase_results(output: Path, cells: list[dict]) -> dict[str, dict]:
    """Rehydrate the exact durable evidence needed by subsequent phase gates."""
    results: dict[str, dict] = {}
    for cell in cells:
        if cell["variants"] == ["treatment", "ablation"]:
            results[cell["run_id"]] = _pair_result(output, cell)
        else:
            results[cell["run_id"]] = _treatment_result(output, cell)
    return results


def _run_variant(args: argparse.Namespace, manifest_path: Path, cell: dict, variant: str) -> None:
    command = [
        sys.executable, str(EVAL_RUNNER),
        "--output", str(args.output / "runs"),
        "--run-id", cell["run_id"],
        "--scenario", cell["scenario"],
        "--treatment-ref", args.manifest["refs"]["treatment"],
        "--ablation-ref", args.manifest["refs"]["ablation"],
        "--runtime", cell["runtime"],
        "--model", cell["model"],
        "--reasoning-effort", cell["reasoning_effort"],
        "--context-window", str(cell["context_window"]),
        "--timeout", str(args.manifest["timeout_seconds"]),
        "--qoder-bin", args.qoder_bin,
        "--variant", variant,
        "--policy-state", str(args.output / "attempt-state"),
        "--canonical-manifest", str(manifest_path),
    ]
    subprocess.run(command, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"The only pre-run authority is output/{MANIFEST_NAME}.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=HERE / "acceptance-policy-v3.json")
    parser.add_argument("--treatment-ref")
    parser.add_argument("--create-manifest", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--qoder-bin", default="qodercli")
    args = parser.parse_args()
    if args.create_manifest == args.execute:
        parser.error("choose exactly one of --create-manifest or --execute")
    policy = load_policy(args.policy)
    args.output = args.output.resolve()
    manifest_path = args.output / MANIFEST_NAME
    if args.create_manifest:
        if not args.treatment_ref:
            parser.error("--create-manifest requires --treatment-ref")
        manifest = build_canonical_manifest(policy, args.treatment_ref)
        ensure_canonical_manifest(args.output, policy, manifest)
        print(manifest_path)
        return
    if args.treatment_ref:
        parser.error("--treatment-ref is only valid with --create-manifest")
    args.manifest = _read_json(manifest_path)
    validate_manifest(policy, args.manifest)
    results: dict[str, dict] = {}
    resume_from = first_unfinished_phase(args.output, args.manifest, policy)
    completed_phases = (
        policy["execution_order"]
        if resume_from is None
        else policy["execution_order"][:policy["execution_order"].index(resume_from)]
    )
    for phase in policy["execution_order"]:
        phase_cells = [cell for cell in args.manifest["cells"] if cell["phase"] == phase]
        if phase in completed_phases:
            results.update(_completed_phase_results(args.output, phase_cells))
            continue
        phase_may_start(args.output, args.manifest, policy, phase)
        for cell in phase_cells:
            for variant in cell["variants"]:
                if cell_runtime_invoked(
                    args.output / "attempt-state", args.manifest, cell, variant,
                ):
                    continue
                _run_variant(args, manifest_path, cell, variant)
                if not cell_runtime_invoked(
                    args.output / "attempt-state", args.manifest, cell, variant,
                ):
                    raise SystemExit(
                        "pre-model infrastructure failure; retry with the same canonical manifest: "
                        f"{cell['run_id']}/{variant}"
                    )
        for cell in phase_cells:
            if cell["variants"] == ["treatment", "ablation"]:
                _write_pair_verdict(args.output, cell)
                results[cell["run_id"]] = _pair_result(args.output, cell)
            else:
                results[cell["run_id"]] = _treatment_result(args.output, cell)
        verdict = build_phase_verdict(args.manifest, policy, phase, results)
        write_phase_verdict(args.output, verdict)
        if not verdict["passed"]:
            raise SystemExit(f"policy phase failed: {phase}")


if __name__ == "__main__":
    main()
