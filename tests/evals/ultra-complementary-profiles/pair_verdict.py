#!/usr/bin/env python3
"""Generate immutable treatment/ablation verdicts from completed eval attempts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


def _variant_ref(invocation: dict[str, Any], variant: str) -> dict[str, str]:
    refs = invocation.get("refs")
    if not isinstance(refs, dict) or not isinstance(refs.get(variant), dict):
        raise ValueError(f"{variant} invocation is missing immutable refs")
    ref = refs[variant]
    if not isinstance(ref.get("requested"), str) or not ref["requested"]:
        raise ValueError(f"{variant} invocation has malformed refs")
    if not isinstance(ref.get("sha"), str) or not re.fullmatch(r"[0-9a-f]{40}", ref["sha"]):
        raise ValueError(f"{variant} invocation has malformed refs")
    return {"requested": ref["requested"], "sha": ref["sha"]}


def _identity_for(invocation: dict[str, Any], variant: str) -> dict[str, Any]:
    if invocation.get("variant") != variant:
        raise ValueError(f"expected {variant} invocation")
    treatment_ref = _variant_ref(invocation, "treatment")
    ablation_ref = _variant_ref(invocation, "ablation")
    selected = invocation.get("refs", {}).get("selected_contract")
    if selected != (treatment_ref if variant == "treatment" else ablation_ref):
        raise ValueError(f"{variant} selected contract does not match its immutable ref")
    runtime = invocation.get("runtime")
    runtime_version = invocation.get("runtime_version")
    model = invocation.get("model")
    scenario = invocation.get("scenario")
    reasoning_effort = invocation.get("reasoning_effort")
    timeout_seconds = invocation.get("timeout_seconds")
    context_window = invocation.get("context_window")
    if runtime not in {"primary", "qoder"}:
        raise ValueError(f"{variant} runtime identity is missing")
    if not isinstance(runtime_version, str) or not runtime_version:
        raise ValueError(f"{variant} runtime version identity is missing")
    if not isinstance(model, str) or not model:
        raise ValueError(f"{variant} model identity is missing")
    if not isinstance(scenario, str) or not scenario:
        raise ValueError(f"{variant} scenario identity is missing")
    if not isinstance(reasoning_effort, str) or not reasoning_effort:
        raise ValueError(f"{variant} reasoning setting is missing")
    if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or timeout_seconds < 1:
        raise ValueError(f"{variant} timeout setting is invalid")
    if runtime == "qoder" and (
        not isinstance(context_window, int)
        or isinstance(context_window, bool)
        or context_window < 1
    ):
        raise ValueError(f"{variant} context-window setting is invalid")
    if runtime == "primary" and context_window is not None and (
        not isinstance(context_window, int)
        or isinstance(context_window, bool)
        or context_window < 1
    ):
        raise ValueError(f"{variant} context-window setting is invalid")
    return {
        "pair_id": invocation.get("pair_id"),
        "runtime": {
            "name": runtime,
            "version": runtime_version,
        },
        "model": model,
        "settings": {
            "context_window": context_window,
            "reasoning_effort": reasoning_effort,
            "timeout_seconds": timeout_seconds,
        },
        "scenario": scenario,
        "refs": {
            "treatment": treatment_ref,
            "ablation": ablation_ref,
        },
    }


def build_pair_identity(
    treatment_invocation: dict[str, Any], ablation_invocation: dict[str, Any]
) -> dict[str, Any]:
    treatment = _identity_for(treatment_invocation, "treatment")
    ablation = _identity_for(ablation_invocation, "ablation")
    if treatment != ablation:
        raise ValueError("treatment/ablation pair identity mismatch")
    return treatment


def classify_pair(
    treatment: dict[str, Any],
    ablation: dict[str, Any],
    allowed_ablation_failure_codes: list[str],
    required_ablation_difference_codes: list[str],
) -> dict[str, Any]:
    treatment_grade = treatment.get("grade", {})
    ablation_grade = ablation.get("grade", {})
    treatment_correct = (
        treatment.get("result", {}).get("run_exit_code") == 0
        and treatment_grade.get("repository_grade", {}).get("passed") is True
        and treatment_grade.get("profile_grade", {}).get("passed") is True
    )
    ablation_evidence_valid = (
        ablation.get("result", {}).get("run_exit_code") == 0
        and ablation_grade.get("repository_grade", {}).get("passed") is True
    )
    ablation_failure_codes = ablation_grade.get(
        "profile_grade", {}
    ).get("failure_codes", [])
    attributable_difference = (
        treatment_correct
        and ablation_evidence_valid
        and bool(ablation_failure_codes)
        and set(ablation_failure_codes) <= set(allowed_ablation_failure_codes)
        and set(required_ablation_difference_codes) <= set(ablation_failure_codes)
    )
    if not treatment_correct:
        conclusion = "treatment-invalid"
    elif not ablation_evidence_valid:
        conclusion = "ablation-evidence-invalid"
    elif not ablation_failure_codes:
        conclusion = "no-observed-attributable-difference"
    elif attributable_difference:
        conclusion = "attributable-profile-difference"
    else:
        conclusion = "ablation-non-attributable-profile-failure"
    return {
        "treatment_correct": treatment_correct,
        "ablation_evidence_valid": ablation_evidence_valid,
        "ablation_profile_failure_codes": ablation_failure_codes,
        "allowed_ablation_failure_codes": allowed_ablation_failure_codes,
        "required_ablation_difference_codes": required_ablation_difference_codes,
        "attributable_difference": attributable_difference,
        "conclusion": conclusion,
        "matrix_gate_passed": attributable_difference,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read pair evidence: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"pair evidence is not an object: {path.name}")
    return value


def _read_grade(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read literal grader output") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ValueError("literal grader output must contain exactly one result")
    return value[0]


def load_attempt(path: Path, variant: str) -> dict[str, Any]:
    invocation = _read_json(path / "invocation.json")
    result = _read_json(path / "result.json")
    control = _read_json(path / "grader-control.json")
    manifest = _read_json(path / "fixture-manifest.json")
    grade = _read_grade(path / "grader-stdout.json")
    if invocation.get("variant") != variant or result.get("variant") != variant:
        raise ValueError(f"expected {variant} attempt evidence")
    attempt = result.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise ValueError(f"{variant} attempt number is invalid")
    if manifest.get("variant") != variant:
        raise ValueError(f"{variant} fixture manifest has wrong arm")
    if manifest.get("scenario") != invocation.get("scenario"):
        raise ValueError(f"{variant} fixture scenario does not match invocation")
    selected = invocation.get("refs", {}).get("selected_contract", {})
    if manifest.get("contract_ref") not in {selected.get("requested"), selected.get("sha")}:
        raise ValueError(f"{variant} fixture ref does not match invocation")
    expectations = control.get("expectations")
    if not isinstance(expectations, dict) or expectations.get("variant") != variant:
        raise ValueError(f"{variant} grader authority has wrong arm")
    if expectations.get("scenario") != invocation.get("scenario"):
        raise ValueError(f"{variant} grader authority has wrong scenario")
    return {
        "path": path,
        "invocation": invocation,
        "result": result,
        "grade": grade,
        "control": control,
        "manifest": manifest,
    }


def build_verdict(treatment: dict[str, Any], ablation: dict[str, Any]) -> dict[str, Any]:
    identity = build_pair_identity(
        treatment["invocation"], ablation["invocation"]
    )
    if treatment["path"].parents[1] != ablation["path"].parents[1]:
        raise ValueError("treatment/ablation attempts do not share one run/scenario root")
    if treatment["manifest"].get("common_hashes") != ablation["manifest"].get(
        "common_hashes"
    ):
        raise ValueError("treatment/ablation fixtures are not pair-equivalent")
    treatment_expectations = treatment["control"]["expectations"]
    ablation_expectations = ablation["control"]["expectations"]
    allowed = treatment_expectations.get("ablation_attributable_failure_codes", [])
    required = treatment_expectations.get("ablation_required_difference_codes", [])
    if (
        allowed != ablation_expectations.get("ablation_attributable_failure_codes", [])
        or required != ablation_expectations.get("ablation_required_difference_codes", [])
    ):
        raise ValueError("treatment/ablation attribution authority mismatch")
    classification = classify_pair(treatment, ablation, allowed, required)
    return {
        "verdict_schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pair_identity": identity,
        "pair_instance": {
            "treatment": {
                "attempt": treatment["result"]["attempt"],
                "started_at": treatment["invocation"].get("started_at"),
            },
            "ablation": {
                "attempt": ablation["result"]["attempt"],
                "started_at": ablation["invocation"].get("started_at"),
            },
        },
        "repository_evidence": {
            "treatment_passed": treatment["grade"].get("repository_grade", {}).get("passed"),
            "treatment_failure_codes": treatment["grade"].get("repository_grade", {}).get("failure_codes", []),
            "ablation_passed": ablation["grade"].get("repository_grade", {}).get("passed"),
            "ablation_failure_codes": ablation["grade"].get("repository_grade", {}).get("failure_codes", []),
        },
        **classification,
    }


def _verdict_token(verdict: dict[str, Any]) -> str:
    pair_id = verdict["pair_identity"].get("pair_id")
    if isinstance(pair_id, str) and pair_id:
        return "".join(character if character.isalnum() or character in "-_" else "-" for character in pair_id)
    material = {
        "identity": verdict["pair_identity"],
        "instance": verdict["pair_instance"],
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()[:16]
    return f"legacy-{digest}"


def write_verdict(output: Path, verdict: dict[str, Any]) -> Path:
    treatment_attempt = verdict["pair_instance"]["treatment"]["attempt"]
    ablation_attempt = verdict["pair_instance"]["ablation"]["attempt"]
    name = (
        f"pair-verdict-{_verdict_token(verdict)}"
        f"-treatment-{treatment_attempt:03d}-ablation-{ablation_attempt:03d}.json"
    )
    verdict = {**verdict, "verdict_file": name}
    output.mkdir(parents=True, exist_ok=True)
    path = output / name
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(verdict, handle, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise ValueError(f"refusing to overwrite existing verdict: {name}") from exc
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--treatment-attempt", type=Path, required=True)
    parser.add_argument("--ablation-attempt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        treatment = load_attempt(args.treatment_attempt.resolve(), "treatment")
        ablation = load_attempt(args.ablation_attempt.resolve(), "ablation")
        verdict = build_verdict(treatment, ablation)
        path = write_verdict(args.output.resolve(), verdict)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(path)


if __name__ == "__main__":
    main()
