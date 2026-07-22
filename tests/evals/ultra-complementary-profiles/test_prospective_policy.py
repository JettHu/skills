#!/usr/bin/env python3
"""Deterministic contract tests for the Ticket 20 prospective policy runner."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def copy_value(value):
    return json.loads(json.dumps(value))


def expect_rejected(callback, contains: str) -> None:
    try:
        callback()
    except ValueError as exc:
        assert contains in str(exc), str(exc)
    else:
        raise AssertionError(f"expected rejection containing {contains!r}")


def clean_pair(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "conclusion": "attributable-profile-difference",
        "matrix_gate_passed": True,
        "treatment_correct": True,
        "ablation_evidence_valid": True,
        "ablation_profile_failure_codes": [
            "duplicate_evidence_goal", "extra_exploration_call",
        ],
        "mechanical_final_state": {
            "repository": True,
            "artifact": True,
            "validation": True,
            "tracker": True,
            "write_set": True,
        },
    }


def treatment_pass(run_id: str) -> dict:
    return {"run_id": run_id, "treatment_passed": True}


def main(tmp: Path) -> None:
    policy_runner = load_module(HERE / "prospective_policy.py", "prospective_policy")
    policy_path = HERE / "acceptance-policy-v2.json"
    policy = policy_runner.load_policy(policy_path)
    assert policy["policy_id"] == "ticket-20-qoder-prospective-v2"
    assert policy["runtime"]["required"] == "qoder"
    assert policy["gates"]["sentinel_quorum"] == {
        "required": 2,
        "total": 3,
        "applies_per_scenario": True,
        "reference_must_also_pass": True,
    }
    assert policy["evidence"]["v1_evidence"] == "permanently-non-gating"

    treatment = "3a3e22dac7e0fdff508d5dbf4f36963381af2f40"
    manifest = policy_runner.build_canonical_manifest(policy, treatment)
    policy_runner.validate_manifest(policy, manifest)
    assert manifest["schema_version"] == 2
    assert manifest["runtime"] == "qoder"
    assert manifest["refs"] == {
        "treatment": treatment,
        "ablation": "b196b40def10579a17326b3b8a0fbc04cb513907",
    }
    assert manifest["policy"]["file_sha256"] == hashlib.sha256(policy_path.read_bytes()).hexdigest()
    assert manifest["timeout_seconds"] == 1800
    assert list(dict.fromkeys(cell["phase"] for cell in manifest["cells"])) == [
        "reference-architecture-treatment-and-ablation",
        "sentinel-architecture-treatments",
        "reference-and-sentinel-long-stale-treatments",
        "reference-and-sentinel-short-complete-treatments",
        "remaining-reference-core-treatments",
    ]
    assert len(manifest["run_ids"]) == len(set(manifest["run_ids"])) == 15
    assert all(cell["run_id"] in manifest["run_ids"] for cell in manifest["cells"])
    assert all(cell["runtime"] == "qoder" for cell in manifest["cells"])

    wrong_runtime = copy_value(manifest)
    wrong_runtime["runtime"] = "primary"
    expect_rejected(lambda: policy_runner.validate_manifest(policy, wrong_runtime), "runtime")

    missing_run_id = copy_value(manifest)
    missing_run_id["run_ids"].pop()
    expect_rejected(lambda: policy_runner.validate_manifest(policy, missing_run_id), "run_ids")

    wrong_setting = copy_value(manifest)
    wrong_setting["cells"][1]["reasoning_effort"] = "low"
    expect_rejected(lambda: policy_runner.validate_manifest(policy, wrong_setting), "cell plan")

    phase_jump = copy_value(manifest)
    phase_jump["cells"].pop(0)
    expect_rejected(lambda: policy_runner.validate_manifest(policy, phase_jump), "cell plan")

    output = tmp / "run"
    manifest_path = policy_runner.write_canonical_manifest(output, manifest)
    assert manifest_path == output / "canonical-manifest.json"
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest
    expect_rejected(lambda: policy_runner.write_canonical_manifest(output, manifest), "already exists")
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest

    changed = copy_value(manifest)
    changed["refs"]["treatment"] = "f" * 40
    expect_rejected(lambda: policy_runner.ensure_canonical_manifest(output, policy, changed), "already exists")

    no_model_trace = tmp / "no-model.jsonl"
    no_model_trace.write_text('{"type":"system","model":"runtime"}\n', encoding="utf-8")
    model_trace = tmp / "model.jsonl"
    model_trace.write_text(
        '{"type":"assistant","message":{"model":"qmodel_preview","content":[]}}\n',
        encoding="utf-8",
    )
    assert policy_runner.trace_has_model_event(no_model_trace) is False
    assert policy_runner.trace_has_model_event(model_trace) is True

    state = tmp / "state"
    cell = manifest["cells"][0]
    policy_runner.reserve_cell(state, manifest, cell, "treatment", tmp / "attempt-preflight")
    policy_runner.append_attempt_state(
        state, manifest, cell, "treatment", "runtime_preflight_failed", runtime_invoked=False,
        model_started=False,
    )
    assert policy_runner.retry_allowed(state, manifest, cell, "treatment") is True
    assert policy_runner.cell_runtime_invoked(state, manifest, cell, "treatment") is False
    policy_runner.append_attempt_state(
        state, manifest, cell, "treatment", "runtime_invoked", runtime_invoked=True,
        model_started=False,
    )
    assert policy_runner.retry_allowed(state, manifest, cell, "treatment") is False
    assert policy_runner.cell_runtime_invoked(state, manifest, cell, "treatment") is True

    started_state = tmp / "started-state"
    policy_runner.reserve_cell(started_state, manifest, cell, "treatment", tmp / "attempt-started")
    policy_runner.append_attempt_state(
        started_state, manifest, cell, "treatment", "runtime_finished", runtime_invoked=True,
        model_started=policy_runner.trace_has_model_event(model_trace),
    )
    assert policy_runner.retry_allowed(started_state, manifest, cell, "treatment") is False
    expect_rejected(
        lambda: policy_runner.reserve_cell(started_state, manifest, cell, "treatment", tmp / "new-run-id"),
        "already reserved",
    )

    concurrent_state = tmp / "concurrent-state"
    concurrent_cell = manifest["cells"][1]
    barrier = threading.Barrier(2)
    outcomes: list[bool] = []

    def reserve() -> None:
        barrier.wait()
        try:
            policy_runner.reserve_cell(
                concurrent_state, manifest, concurrent_cell, "treatment", tmp / "attempt"
            )
        except ValueError:
            outcomes.append(False)
        else:
            outcomes.append(True)

    threads = [threading.Thread(target=reserve), threading.Thread(target=reserve)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == [False, True]

    allowed = policy["gates"]["architecture_attribution"]
    pair = clean_pair(manifest["cells"][0]["run_id"])
    assert policy_runner.evaluate_architecture_pair(pair, allowed)["passed"] is True
    nonmechanical = clean_pair(manifest["cells"][0]["run_id"])
    nonmechanical["mechanical_final_state"]["write_set"] = False
    assert policy_runner.evaluate_architecture_pair(nonmechanical, allowed)["passed"] is False
    unexpected = clean_pair(manifest["cells"][0]["run_id"])
    unexpected["ablation_profile_failure_codes"].append("required_stage_order")
    assert policy_runner.evaluate_architecture_pair(unexpected, allowed)["passed"] is False

    phase_one = policy_runner.build_phase_verdict(
        manifest,
        policy,
        "reference-architecture-treatment-and-ablation",
        {manifest["cells"][0]["run_id"]: pair},
    )
    assert phase_one["passed"] is True
    phase_path = policy_runner.write_phase_verdict(output, phase_one)
    assert phase_path.is_file()
    expect_rejected(lambda: policy_runner.write_phase_verdict(output, phase_one), "already exists")
    assert policy_runner.phase_may_start(output, manifest, policy, "sentinel-architecture-treatments")

    failed_output = tmp / "failed-phase"
    failed_pair = clean_pair(manifest["cells"][0]["run_id"])
    failed_pair["ablation_profile_failure_codes"] = []
    failed_phase = policy_runner.build_phase_verdict(
        manifest,
        policy,
        "reference-architecture-treatment-and-ablation",
        {manifest["cells"][0]["run_id"]: failed_pair},
    )
    assert failed_phase["passed"] is False
    policy_runner.write_phase_verdict(failed_output, failed_phase)
    expect_rejected(
        lambda: policy_runner.phase_may_start(
            failed_output, manifest, policy, "sentinel-architecture-treatments"
        ),
        "failed phase",
    )

    sentinel_phase = "sentinel-architecture-treatments"
    sentinel_cells = [cell for cell in manifest["cells"] if cell["phase"] == sentinel_phase]
    results = {
        manifest["cells"][0]["run_id"]: pair,
        **{cell["run_id"]: treatment_pass(cell["run_id"]) for cell in sentinel_cells[:2]},
        sentinel_cells[2]["run_id"]: {"run_id": sentinel_cells[2]["run_id"], "treatment_passed": False},
    }
    sentinel_verdict = policy_runner.build_phase_verdict(manifest, policy, sentinel_phase, results)
    assert sentinel_verdict["passed"] is True
    assert sentinel_verdict["quorum"]["architecture-native-ownership"] == {
        "reference_passed": True, "sentinel_passes": 2, "required": 2,
    }

    run_policy = HERE / "run-policy.py"
    result = subprocess.run([sys.executable, str(run_policy), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "canonical-manifest" in result.stdout

    # A real policy invocation that never reaches the model must remain retryable:
    # it creates only $TMP evidence and no phase verdict.
    pre_model_output = tmp / "pre-model-retry"
    policy_runner.write_canonical_manifest(pre_model_output, manifest)
    fake_qoder = tmp / "pre-model-qoder"
    fake_qoder.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('fake-qoder 1.0')\n"
        "    raise SystemExit(0)\n"
        "if 'status' in sys.argv:\n"
        "    print(json.dumps({'logged_in': False}))\n"
        "    raise SystemExit(0)\n"
        "if '-p' in sys.argv:\n"
        "    raise SystemExit('model must not be invoked after preflight failure')\n"
        "raise SystemExit(0)\n",
        encoding="utf-8",
    )
    fake_qoder.chmod(0o755)
    execute = [
        sys.executable, str(run_policy), "--output", str(pre_model_output), "--execute",
        "--qoder-bin", str(fake_qoder),
    ]
    for _ in range(2):
        retry = subprocess.run(execute, capture_output=True, text=True)
        assert retry.returncode != 0
        assert "pre-model infrastructure failure" in retry.stderr
    attempts = sorted((
        pre_model_output / "runs/ticket-20-v2-reference-architecture"
        "/architecture-native-ownership/treatment"
    ).glob("attempt-*"))
    assert [attempt.name for attempt in attempts] == ["attempt-001", "attempt-002"]
    for attempt in attempts:
        invocation = json.loads((attempt / "invocation.json").read_text(encoding="utf-8"))
        assert invocation["runtime_invoked"] is False
        assert invocation["model_started"] is False
    assert not (pre_model_output / "phase-verdicts").exists()


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
