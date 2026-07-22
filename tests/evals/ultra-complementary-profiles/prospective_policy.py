#!/usr/bin/env python3
"""Fail-closed authority and evidence state for Ticket 20 policy v2."""

from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST_NAME = "canonical-manifest.json"
_SHA = re.compile(r"[0-9a-f]{40}")


def _canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _policy_commit(path: Path) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", str(path.relative_to(ROOT))],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    commit = result.stdout.strip()
    if not _SHA.fullmatch(commit):
        raise ValueError("policy file must be committed before a canonical manifest can be created")
    return commit


def load_policy(path: Path) -> dict[str, Any]:
    """Load a tracked policy, retaining its immutable identity out of band."""
    path = path.resolve()
    policy = _read_object(path, "acceptance policy")
    if policy.get("schema_version") != 2:
        raise ValueError("acceptance policy schema_version must be 2")
    if policy.get("policy_id") != "ticket-20-qoder-prospective-v2":
        raise ValueError("unrecognized prospective acceptance policy")
    if policy.get("runtime", {}).get("required") != "qoder":
        raise ValueError("policy must require the qoder runtime")
    if policy.get("evidence", {}).get("v1_evidence") != "permanently-non-gating":
        raise ValueError("policy must permanently exclude v1 evidence from gating")
    return {
        **policy,
        "_path": path,
        "_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "_commit_sha": _policy_commit(path),
    }


def _models(policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
    matrix = policy.get("matrix")
    if not isinstance(matrix, dict):
        raise ValueError("policy matrix is missing")
    reference = matrix.get("reference")
    sentinels = matrix.get("sentinels")
    if not isinstance(reference, dict) or not isinstance(sentinels, list):
        raise ValueError("policy model matrix is malformed")
    models = {"reference": reference}
    for index, sentinel in enumerate(sentinels, start=1):
        if not isinstance(sentinel, dict):
            raise ValueError("policy sentinel is malformed")
        models[f"sentinel-{index}"] = sentinel
    return models


def _phase_plan(policy: dict[str, Any]) -> list[dict[str, Any]]:
    phases = policy.get("phases")
    order = policy.get("execution_order")
    models = _models(policy)
    if not isinstance(phases, list) or not isinstance(order, list):
        raise ValueError("policy phase plan is missing")
    if [phase.get("name") for phase in phases if isinstance(phase, dict)] != order:
        raise ValueError("policy phase order is malformed")
    result: list[dict[str, Any]] = []
    for phase in phases:
        if not isinstance(phase, dict) or not isinstance(phase.get("cells"), list):
            raise ValueError("policy phase cells are malformed")
        for source in phase["cells"]:
            if not isinstance(source, dict):
                raise ValueError("policy cell is malformed")
            model_key = source.get("model_key")
            model = models.get(model_key)
            variants = source.get("variants")
            if (
                not isinstance(model, dict)
                or not isinstance(source.get("run_id"), str)
                or not isinstance(source.get("scenario"), str)
                or not isinstance(variants, list)
                or variants not in (["treatment"], ["treatment", "ablation"])
            ):
                raise ValueError("policy cell is malformed")
            if not all(isinstance(model.get(field), (str, int)) for field in ("model", "reasoning_effort", "context_window")):
                raise ValueError("policy model settings are malformed")
            result.append({
                "phase": phase["name"],
                "run_id": source["run_id"],
                "runtime": policy["runtime"]["required"],
                "model": model["model"],
                "reasoning_effort": model["reasoning_effort"],
                "context_window": model["context_window"],
                "scenario": source["scenario"],
                "variants": variants,
            })
    if len({cell["run_id"] for cell in result}) != len(result):
        raise ValueError("policy run IDs must be unique")
    return result


def build_canonical_manifest(policy: dict[str, Any], treatment_ref: str) -> dict[str, Any]:
    """Materialize the only authority allowed to launch a v2 model cell."""
    if not _SHA.fullmatch(treatment_ref):
        raise ValueError("treatment ref must be a committed SHA")
    cells = _phase_plan(policy)
    return {
        "schema_version": 2,
        "manifest_id": "ticket-20-qoder-prospective-v2",
        "policy": {
            "id": policy["policy_id"],
            "commit_sha": policy["_commit_sha"],
            "file_sha256": policy["_file_sha256"],
        },
        "runtime": policy["runtime"]["required"],
        "refs": {
            "treatment": treatment_ref,
            "ablation": policy["refs"]["ablation"],
        },
        "run_ids": [cell["run_id"] for cell in cells],
        "timeout_seconds": policy["timeout_seconds"],
        "execution_order": policy["execution_order"],
        "cells": cells,
    }


def validate_manifest(policy: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Reject every partial, stale, or policy-external manifest before runtime use."""
    if not isinstance(manifest, dict):
        raise ValueError("canonical manifest must be an object")
    refs = manifest.get("refs")
    if not isinstance(refs, dict) or not _SHA.fullmatch(refs.get("treatment", "")):
        raise ValueError("canonical manifest treatment ref is malformed")
    expected = build_canonical_manifest(policy, refs["treatment"])
    if manifest == expected:
        return
    if manifest.get("runtime") != expected["runtime"]:
        raise ValueError("canonical manifest runtime is not policy-authorized")
    if manifest.get("run_ids") != expected["run_ids"]:
        raise ValueError("canonical manifest run_ids are incomplete or policy-external")
    if manifest.get("cells") != expected["cells"]:
        raise ValueError("canonical manifest cell plan is incomplete or policy-external")
    if manifest.get("execution_order") != expected["execution_order"]:
        raise ValueError("canonical manifest phase order is not policy-authorized")
    raise ValueError("canonical manifest does not match the frozen policy authority")


def _write_exclusive(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    except FileExistsError as exc:
        raise ValueError(f"append-only evidence already exists: {path}") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def write_canonical_manifest(output: Path, manifest: dict[str, Any]) -> Path:
    path = output / MANIFEST_NAME
    try:
        _write_exclusive(path, _canonical_json(manifest))
    except ValueError as exc:
        raise ValueError("canonical manifest already exists and cannot be overwritten") from exc
    return path


def ensure_canonical_manifest(output: Path, policy: dict[str, Any], manifest: dict[str, Any]) -> Path:
    """Return an existing byte-authoritative manifest only if it exactly validates."""
    validate_manifest(policy, manifest)
    path = output / MANIFEST_NAME
    if not path.exists():
        return write_canonical_manifest(output, manifest)
    existing = _read_object(path, "canonical manifest")
    validate_manifest(policy, existing)
    if existing != manifest:
        raise ValueError("canonical manifest already exists with inconsistent authority")
    return path


def _cell_token(manifest: dict[str, Any], cell: dict[str, Any], variant: str) -> str:
    material = {
        "manifest": _digest(manifest),
        "run_id": cell["run_id"],
        "scenario": cell["scenario"],
        "variant": variant,
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()


def _cell_state_path(state_root: Path, manifest: dict[str, Any], cell: dict[str, Any], variant: str) -> Path:
    return state_root / "cells" / f"{_cell_token(manifest, cell, variant)}.jsonl"


def reserve_cell(
    state_root: Path,
    manifest: dict[str, Any],
    cell: dict[str, Any],
    variant: str,
    attempt_path: Path,
) -> Path:
    """Reserve the model cell at the last safe point before invoking the runtime."""
    if variant not in cell.get("variants", []):
        raise ValueError("variant is not authorized by the canonical cell")
    token = _cell_token(manifest, cell, variant)
    path = state_root / "reservations" / f"{token}.json"
    receipt = {
        "schema_version": 2,
        "kind": "cell_reserved",
        "manifest_sha256": _digest(manifest),
        "run_id": cell["run_id"],
        "scenario": cell["scenario"],
        "variant": variant,
        "attempt_path": str(attempt_path),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        _write_exclusive(path, _canonical_json(receipt))
    except ValueError as exc:
        raise ValueError("policy cell already reserved; a new run ID cannot retry it") from exc
    return path


def append_attempt_state(
    state_root: Path,
    manifest: dict[str, Any],
    cell: dict[str, Any],
    variant: str,
    event: str,
    *,
    runtime_invoked: bool,
    model_started: bool,
) -> Path:
    """Append one fsync'd, lock-protected state receipt without rewriting history."""
    if model_started and not runtime_invoked:
        raise ValueError("model_started requires runtime_invoked")
    path = _cell_state_path(state_root, manifest, cell, variant)
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 2,
        "event": event,
        "manifest_sha256": _digest(manifest),
        "run_id": cell["run_id"],
        "scenario": cell["scenario"],
        "variant": variant,
        "runtime_invoked": runtime_invoked,
        "model_started": model_started,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    line = json.dumps(receipt, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return path


def _state_receipts(state_root: Path, manifest: dict[str, Any], cell: dict[str, Any], variant: str) -> list[dict[str, Any]]:
    path = _cell_state_path(state_root, manifest, cell, variant)
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("attempt state is malformed") from exc


def retry_allowed(state_root: Path, manifest: dict[str, Any], cell: dict[str, Any], variant: str) -> bool:
    """Only an observed pre-runtime failure may receive a fresh attempt directory."""
    receipts = _state_receipts(state_root, manifest, cell, variant)
    return not any(
        receipt.get("runtime_invoked") is True or receipt.get("model_started") is True
        for receipt in receipts
    )


def text_has_model_event(text: str) -> bool:
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        if (
            isinstance(event, dict)
            and event.get("type") == "assistant"
            and isinstance(message, dict)
            and isinstance(message.get("model"), str)
            and message["model"].strip()
        ):
            return True
    return False


def trace_has_model_event(path: Path) -> bool:
    try:
        return text_has_model_event(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return False


def evaluate_architecture_pair(pair: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    mechanical = pair.get("mechanical_final_state")
    if not isinstance(mechanical, dict):
        mechanical = {}
    mechanical_valid = all(
        mechanical.get(field) is True
        for field in ("repository", "artifact", "validation", "tracker", "write_set")
    )
    codes = pair.get("ablation_profile_failure_codes")
    if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
        codes = []
    allowed = gate.get("allowed_ablation_failure_codes", [])
    required = [gate.get("required_difference")]
    profile_only = bool(codes) and set(codes) <= set(allowed) and set(required) <= set(codes)
    passed = (
        pair.get("treatment_correct") is True
        and pair.get("ablation_evidence_valid") is True
        and mechanical_valid
        and profile_only
        and pair.get("matrix_gate_passed") is True
    )
    return {
        "passed": passed,
        "mechanical_final_state": {
            field: mechanical.get(field) is True
            for field in ("repository", "artifact", "validation", "tracker", "write_set")
        },
        "allowed_ablation_failure_codes": allowed,
        "observed_ablation_failure_codes": codes,
    }


def _run_result_passed(result: object) -> bool:
    return isinstance(result, dict) and (
        result.get("treatment_passed") is True or result.get("treatment_correct") is True
    )


def build_phase_verdict(
    manifest: dict[str, Any],
    policy: dict[str, Any],
    phase_name: str,
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Make the stop-rule decision durable from exact cell evidence, never prose."""
    cells = _phase_plan(policy)
    phase_cells = [cell for cell in cells if cell["phase"] == phase_name]
    if not phase_cells:
        raise ValueError("phase is not authorized by the policy")
    phase_index = policy["execution_order"].index(phase_name)
    quorum: dict[str, dict[str, Any]] = {}
    if phase_index == 0:
        pair = results.get(phase_cells[0]["run_id"], {})
        architecture = evaluate_architecture_pair(pair, policy["gates"]["architecture_attribution"])
        passed = architecture["passed"]
        cells_out = {phase_cells[0]["run_id"]: architecture}
    elif phase_name in {
        "sentinel-architecture-treatments",
        "reference-and-sentinel-long-stale-treatments",
        "reference-and-sentinel-short-complete-treatments",
    }:
        scenario = phase_cells[0]["scenario"]
        reference = next(
            cell for cell in cells
            if cell["scenario"] == scenario and cell["model"] == policy["matrix"]["reference"]["model"]
        )
        sentinels = [cell for cell in phase_cells if cell["model"] != reference["model"]]
        sentinel_passes = sum(_run_result_passed(results.get(cell["run_id"])) for cell in sentinels)
        required = policy["gates"]["sentinel_quorum"]["required"]
        reference_passed = (
            _run_result_passed(results.get(reference["run_id"]))
            if reference["run_id"] != phase_cells[0]["run_id"] or reference["model"] == policy["matrix"]["reference"]["model"]
            else False
        )
        quorum[scenario] = {
            "reference_passed": reference_passed,
            "sentinel_passes": sentinel_passes,
            "required": required,
        }
        passed = reference_passed and sentinel_passes >= required
        cells_out = {
            cell["run_id"]: {"treatment_passed": _run_result_passed(results.get(cell["run_id"]))}
            for cell in phase_cells
        }
    else:
        passed = all(_run_result_passed(results.get(cell["run_id"])) for cell in phase_cells)
        cells_out = {
            cell["run_id"]: {"treatment_passed": _run_result_passed(results.get(cell["run_id"]))}
            for cell in phase_cells
        }
    return {
        "schema_version": 2,
        "kind": "phase_verdict",
        "manifest_sha256": _digest(manifest),
        "phase": phase_name,
        "phase_index": phase_index,
        "passed": passed,
        "cells": cells_out,
        "quorum": quorum,
        "stop_after_failed_phase": policy["stop_after_failed_phase"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _phase_file(output: Path, phase: str) -> Path:
    safe_phase = re.sub(r"[^a-z0-9-]", "-", phase)
    return output / "phase-verdicts" / f"phase-verdict-{safe_phase}.json"


def write_phase_verdict(output: Path, verdict: dict[str, Any]) -> Path:
    path = _phase_file(output, verdict["phase"])
    try:
        _write_exclusive(path, _canonical_json(verdict))
    except ValueError as exc:
        raise ValueError("phase verdict already exists and cannot be overwritten") from exc
    return path


def phase_may_start(output: Path, manifest: dict[str, Any], policy: dict[str, Any], phase_name: str) -> bool:
    index = policy["execution_order"].index(phase_name)
    if index == 0:
        return True
    previous = _read_object(_phase_file(output, policy["execution_order"][index - 1]), "previous phase verdict")
    if previous.get("manifest_sha256") != _digest(manifest):
        raise ValueError("previous phase verdict belongs to another manifest")
    if previous.get("passed") is not True:
        raise ValueError("policy stop rule blocks this phase after a failed phase")
    return True
