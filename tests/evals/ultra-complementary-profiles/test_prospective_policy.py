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
    policy_path = HERE / "acceptance-policy-v4.json"
    policy = policy_runner.load_policy(policy_path)
    assert policy["policy_id"] == "ticket-20-qoder-prospective-v4"
    assert policy["runtime"]["required"] == "qoder"
    assert policy["gates"]["sentinel_quorum"] == {
        "required": 2,
        "total": 3,
        "applies_per_scenario": True,
        "reference_must_also_pass": True,
    }
    assert policy["evidence"]["v1_evidence"] == "permanently-non-gating"

    authority_mutations = (
        ("prospective-only", ("effective_scope", "mode"), "retroactive"),
        ("historical attempts", ("effective_scope", "historical_attempts"), "gating"),
        ("v1 evidence", ("effective_scope", "v1_evidence"), "gating"),
        ("v2 evidence", ("effective_scope", "v2_evidence"), "gating"),
        ("v3 evidence", ("effective_scope", "v3_evidence"), "gating"),
        ("v1", ("evidence", "v1_evidence"), "gating"),
        ("v2", ("evidence", "v2_evidence"), "gating"),
        ("v3", ("evidence", "v3_evidence"), "gating"),
        ("v2 Phase 1", ("effective_scope", "v2_phase_1_verdict"), "retryable"),
        ("new version", ("effective_scope", "change_rule"), "edit-in-place"),
        ("historical attempts", ("evidence", "historical_attempts_may_satisfy_gate"), True),
    )
    for expected_error, path, replacement in authority_mutations:
        weakened = copy_value({
            key: value for key, value in policy.items() if not key.startswith("_")
        })
        weakened[path[0]][path[1]] = replacement
        expect_rejected(
            lambda value=weakened: policy_runner.validate_policy_authority(value),
            expected_error,
        )

    # The runner may load only the tracked, canonical v4 authority.  A byte-for-byte
    # copy elsewhere cannot inherit its run IDs or commit identity.
    foreign_policy = tmp / "acceptance-policy-v4.json"
    foreign_policy.parent.mkdir(parents=True, exist_ok=True)
    foreign_policy.write_text(policy_path.read_text(encoding="utf-8"), encoding="utf-8")
    expect_rejected(
        lambda: policy_runner.load_policy(foreign_policy),
        "canonical",
    )

    treatment = "3a3e22dac7e0fdff508d5dbf4f36963381af2f40"
    manifest = policy_runner.build_canonical_manifest(policy, treatment)
    policy_runner.validate_manifest(policy, manifest)
    assert manifest["schema_version"] == 4
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
    expect_rejected(
        lambda: policy_runner.build_canonical_manifest(policy, "f" * 40),
        "cannot resolve",
    )

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

    interrupted_publish = tmp / "interrupted-publish"
    original_link = policy_runner.os.link

    def fail_publish(source, destination):
        raise OSError("simulated interrupted publish")

    policy_runner.os.link = fail_publish
    try:
        try:
            policy_runner.write_canonical_manifest(interrupted_publish, manifest)
        except OSError as exc:
            assert "interrupted publish" in str(exc)
        else:
            raise AssertionError("manifest publication unexpectedly succeeded")
    finally:
        policy_runner.os.link = original_link
    assert not (interrupted_publish / "canonical-manifest.json").exists()
    assert not list(interrupted_publish.glob(".canonical-manifest.json.*.tmp"))

    changed = copy_value(manifest)
    changed["refs"]["treatment"] = "f" * 40
    expect_rejected(lambda: policy_runner.ensure_canonical_manifest(output, policy, changed), "cannot resolve")

    no_model_trace = tmp / "no-model.jsonl"
    no_model_trace.write_text('{"type":"system","model":"runtime"}\n', encoding="utf-8")
    model_trace = tmp / "model.jsonl"
    model_trace.write_text(
        '{"type":"assistant","message":{"model":"qmodel_preview","content":[]}}\n',
        encoding="utf-8",
    )
    assert policy_runner.trace_has_model_event(no_model_trace) is False
    assert policy_runner.trace_has_model_event(model_trace) is True

    state_authority = tmp / "state-authority"
    policy_runner.write_canonical_manifest(state_authority, manifest)
    state = state_authority / "attempt-state"
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

    started_authority = tmp / "started-authority"
    policy_runner.write_canonical_manifest(started_authority, manifest)
    started_state = started_authority / "attempt-state"
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

    concurrent_authority = tmp / "concurrent-authority"
    policy_runner.write_canonical_manifest(concurrent_authority, manifest)
    concurrent_state = concurrent_authority / "attempt-state"
    concurrent_cell = cell
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

    pair_verdict = load_module(HERE / "pair_verdict.py", "pair_verdict")
    no_model_treatment = {
        "result": {"run_exit_code": 0},
        "invocation": {"runtime_invoked": False, "model_started": False},
        "grade": {"repository_grade": {"passed": True}, "profile_grade": {"passed": True}},
    }
    no_model_ablation = {
        "result": {"run_exit_code": 0},
        "invocation": {"runtime_invoked": False, "model_started": False},
        "grade": {
            "repository_grade": {"passed": True, "failure_codes": []},
            "profile_grade": {"failure_codes": ["duplicate_evidence_goal"]},
            "trace_grade": {"failure_codes": ["extra_exploration_call"]},
        },
    }
    no_model_pair = pair_verdict.classify_pair(
        no_model_treatment,
        no_model_ablation,
        allowed["allowed_ablation_failure_codes"],
        [allowed["required_difference"]],
    )
    assert no_model_pair["treatment_correct"] is False
    assert no_model_pair["ablation_evidence_valid"] is False

    trace_spoof_treatment = copy_value(no_model_treatment)
    trace_spoof_ablation = copy_value(no_model_ablation)
    for attempt in (trace_spoof_treatment, trace_spoof_ablation):
        attempt["invocation"] = {"runtime_invoked": True, "model_started": True}
        attempt["trace_model_event"] = False
    trace_spoof_pair = pair_verdict.classify_pair(
        trace_spoof_treatment,
        trace_spoof_ablation,
        allowed["allowed_ablation_failure_codes"],
        [allowed["required_difference"]],
    )
    assert trace_spoof_pair["treatment_correct"] is False
    assert trace_spoof_pair["ablation_evidence_valid"] is False

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
    assert policy_runner.first_unfinished_phase(output, manifest, policy) == "sentinel-architecture-treatments"

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
        pre_model_output / "runs/ticket-20-v4-reference-architecture"
        "/architecture-native-ownership/treatment"
    ).glob("attempt-*"))
    assert [attempt.name for attempt in attempts] == ["attempt-001", "attempt-002"]
    for attempt in attempts:
        invocation = json.loads((attempt / "invocation.json").read_text(encoding="utf-8"))
        result = json.loads((attempt / "result.json").read_text(encoding="utf-8"))
        assert invocation["runtime_invoked"] is False
        assert invocation["model_started"] is False
        assert result["recovery"].startswith("pre-runtime-retry-allowed")
    assert not (pre_model_output / "phase-verdicts").exists()

    # A completed Phase 1 is reused.  The first new pre-runtime failure stops the
    # phase before later sentinel cells can consume their one permitted invocation.
    resumed_output = tmp / "resumed-policy"
    policy_runner.write_canonical_manifest(resumed_output, manifest)
    policy_runner.write_phase_verdict(resumed_output, phase_one)
    resumed_pair_root = (
        resumed_output / "runs/ticket-20-v4-reference-architecture"
        "/architecture-native-ownership"
    )
    resumed_pair_root.mkdir(parents=True)
    (resumed_pair_root / "pair-verdict-resumed.json").write_text(
        json.dumps(pair),
        encoding="utf-8",
    )
    resumed = subprocess.run(
        [
            sys.executable, str(run_policy), "--output", str(resumed_output), "--execute",
            "--qoder-bin", str(fake_qoder),
        ],
        capture_output=True,
        text=True,
    )
    assert resumed.returncode != 0
    assert "pre-model infrastructure failure" in resumed.stderr
    phase_one_attempts = list((
        resumed_output / "runs/ticket-20-v4-reference-architecture"
        "/architecture-native-ownership/treatment"
    ).glob("attempt-*"))
    assert not phase_one_attempts
    sentinel_attempts = [
        sorted((resumed_output / "runs" / cell["run_id"] / cell["scenario"] / "treatment").glob("attempt-*"))
        for cell in sentinel_cells
    ]
    assert [len(attempts) for attempts in sentinel_attempts] == [1, 0, 0]

    # Direct generic-runner calls carry the same reservation authority: neither a
    # Phase 2 cell nor the Phase 1 ablation may cross into the runtime first.
    marker = tmp / "generic-runtime-marker"
    direct_qoder = tmp / "direct-qoder"
    direct_qoder.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "from pathlib import Path\n"
        "import sys\n"
        f"marker = Path({str(marker)!r})\n"
        "if '--version' in sys.argv:\n"
        "    print('fake-qoder 1.0')\n"
        "elif 'status' in sys.argv:\n"
        "    print(json.dumps({'logged_in': True}))\n"
        "elif 'agents' in sys.argv:\n"
        "    print('2 active agents\\n\\nBuilt-in:\\n  Explore · Builtin\\n  general-purpose · Builtin')\n"
        "elif 'skills' in sys.argv:\n"
        "    print('No skills discovered.')\n"
        "elif '-p' in sys.argv:\n"
        "    marker.write_text('invoked', encoding='utf-8')\n"
        "    print(json.dumps({'type': 'assistant', 'message': {'model': 'fake', 'content': []}}))\n"
        "else:\n"
        "    raise SystemExit(2)\n",
        encoding="utf-8",
    )
    direct_qoder.chmod(0o755)

    def direct_command(authority: Path, direct_cell: dict, variant: str) -> list[str]:
        return [
            sys.executable, str(HERE / "run-eval.py"),
            "--output", str(authority / "runs"),
            "--run-id", direct_cell["run_id"],
            "--scenario", direct_cell["scenario"],
            "--treatment-ref", manifest["refs"]["treatment"],
            "--ablation-ref", manifest["refs"]["ablation"],
            "--runtime", direct_cell["runtime"],
            "--model", direct_cell["model"],
            "--reasoning-effort", direct_cell["reasoning_effort"],
            "--context-window", str(direct_cell["context_window"]),
            "--timeout", str(manifest["timeout_seconds"]),
            "--qoder-bin", str(direct_qoder),
            "--variant", variant,
            "--policy-state", str(authority / "attempt-state"),
            "--canonical-manifest", str(authority / "canonical-manifest.json"),
        ]

    phase_two_authority = tmp / "phase-two-direct"
    policy_runner.write_canonical_manifest(phase_two_authority, manifest)
    phase_two_cell = next(cell for cell in manifest["cells"] if cell["phase"] == sentinel_phase)
    phase_two = subprocess.run(
        direct_command(phase_two_authority, phase_two_cell, "treatment"),
        capture_output=True,
        text=True,
    )
    assert phase_two.returncode != 0
    assert not marker.exists()

    ablation_authority = tmp / "ablation-direct"
    policy_runner.write_canonical_manifest(ablation_authority, manifest)
    ablation = subprocess.run(
        direct_command(ablation_authority, manifest["cells"][0], "ablation"),
        capture_output=True,
        text=True,
    )
    assert ablation.returncode != 0
    assert not marker.exists()

    treatment_authority = tmp / "treatment-direct"
    policy_runner.write_canonical_manifest(treatment_authority, manifest)
    treatment_run = subprocess.run(
        direct_command(treatment_authority, manifest["cells"][0], "treatment"),
        capture_output=True,
        text=True,
    )
    assert treatment_run.returncode != 0
    treatment_result = json.loads(next((
        treatment_authority / "runs/ticket-20-v4-reference-architecture"
        "/architecture-native-ownership/treatment"
    ).glob("attempt-*/result.json")).read_text(encoding="utf-8"))
    assert treatment_result["recovery"].startswith("cell-consumed-no-retry")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
