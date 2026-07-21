#!/usr/bin/env python3
"""Exercise the Primary collaboration canary with a token-free fake Codex CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[3]
RUNNER = Path(__file__).resolve().parent / "run-canary.py"
PROFILE_RUNNER = ROOT / "tests/evals/ultra-complementary-profiles/run-eval.py"
MARKER = "[eval-stage:primary-collaboration-canary]"


FAKE = r'''#!/usr/bin/env python3
import json, os
from pathlib import Path
import subprocess
import sys, time

case = os.environ.get("PRIMARY_CANARY_FAKE_CASE", "happy")
MARKER = "[eval-stage:primary-collaboration-canary]"
log_path = os.environ.get("PRIMARY_CANARY_FAKE_LOG")
if log_path:
    with open(log_path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps({
            "argv": sys.argv[1:], "cwd": str(Path.cwd()),
            "HOME": os.environ.get("HOME"), "CODEX_HOME": os.environ.get("CODEX_HOME"),
        }) + "\n")
if "--version" in sys.argv:
    print("codex-cli 0.fake")
    raise SystemExit(0)
if sys.argv[1:3] == ["features", "list"]:
    if case == "feature-nonzero":
        raise SystemExit(17)
    if case == "feature-unknown":
        print("unknown protocol")
    elif case == "feature-short":
        print("multi_agent true")
    elif case == "feature-nonsense":
        print("multi_agent nonsense true")
    elif case == "feature-unknown-lifecycle":
        print("multi_agent       future            true")
    elif case == "feature-extra-field":
        print("multi_agent experimental unexpected true")
    elif case == "feature-duplicate":
        print("multi_agent experimental true\nmulti_agent experimental true")
    elif case == "feature-no-exact-target":
        print("multi_agent_mode  removed            false")
        print("multi_agent_v2    under development  false")
    elif case == "feature-false":
        print("multi_agent       stable             false")
        print("multi_agent_mode  removed            false")
        print("multi_agent_v2    under development  false")
    else:
        print("multi_agent       stable             true")
        print("multi_agent_mode  removed            false")
        print("multi_agent_v2    under development  false")
        print("use_legacy_landlock    deprecated false")
        print("web_search_cached      deprecated false")
        print("web_search_request     deprecated false")
    raise SystemExit(0)

codex_home = Path(os.environ["CODEX_HOME"])
(codex_home / "threads").mkdir(exist_ok=True)
(codex_home / "threads" / "runtime-thread.json").write_text("temporary thread")
cwd = Path.cwd()
if case == "runtime-timeout":
    time.sleep(5)
if case == "runtime-nonzero":
    print(json.dumps({"type": "error", "message": "fake failure"}))
    raise SystemExit(9)
if case == "runtime-repo-missing":
    import shutil
    shutil.rmtree(cwd)
    raise SystemExit(0)
if case == "tracked-write":
    (cwd / "CANARY_INPUT.md").write_text("modified")
if case == "committed-write":
    (cwd / "CANARY_INPUT.md").write_text("committed modification")
    subprocess.run(["git", "add", "CANARY_INPUT.md"], cwd=cwd, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "forbidden"], cwd=cwd, check=True)
if case == "untracked-write":
    (cwd / "UNTRACKED.md").write_text("forbidden")
if case == "symlink-write":
    (cwd / "FORBIDDEN_LINK").symlink_to("CANARY_INPUT.md")

def event(event_type, call_id, marker=MARKER, outer="completed", states=None, receivers=None):
    return {
        "type": event_type,
        "item": {
            "id": call_id,
            "type": "collab_tool_call",
            "tool": "spawn_agent",
            "prompt": marker,
            "receiver_thread_ids": receivers or [],
            "agents_states": states or {},
            "status": outer,
        },
    }

if case in {"no-spawn", "prose-only"}:
    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "I delegated successfully"}}))
    raise SystemExit(0)

if case == "malformed-jsonl":
    print("{malformed")
if case == "nonobject-jsonl":
    print(json.dumps(["not", "an", "event"]))

marker = "[eval-stage:wrong]" if case == "wrong-marker" else MARKER
terminal_type = "item.failed" if case == "outer-failed" else "item.completed"
outer = "failed" if case == "outer-failed" else "completed"
states = {"child-1": {"status": "completed"}}
receivers = ["child-1"]
if case == "child-failed": states = {"child-1": {"status": "failed"}}
if case == "child-running": states = {"child-1": {"status": "running"}}
if case == "child-cancelled": states = {"child-1": {"status": "cancelled"}}
if case == "child-timed-out": states = {"child-1": {"status": "timed-out"}}
if case == "multiple-child":
    states = {"child-1": {"status": "completed"}, "child-2": {"status": "completed"}}
    receivers = ["child-1", "child-2"]
print(json.dumps(event("item.started", "spawn-1", marker, "in_progress")))
if case == "duplicate-start-same-id":
    print(json.dumps(event("item.started", "spawn-1", marker, "in_progress")))
if case == "item-failed-completed-payload": terminal_type, outer = "item.failed", "completed"
print(json.dumps(event(terminal_type, "spawn-1", marker, outer, states, receivers)))
if case == "multiple-spawn":
    print(json.dumps(event("item.completed", "spawn-2", marker, "completed", {"child-2": {"status": "completed"}}, ["child-2"])))
'''


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def invoke(
    root: Path,
    fake: Path,
    case: str,
    *,
    run_id: str | None = None,
    timeout: int = 2,
    ambient_codex_home: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    run_id = run_id or case
    env = os.environ.copy()
    env["PRIMARY_CANARY_FAKE_CASE"] = case
    if ambient_codex_home is not None:
        env["CODEX_HOME"] = str(ambient_codex_home)
    env.update(extra_env or {})
    result = subprocess.run(
        [
            sys.executable, str(RUNNER), "--output", str(root), "--run-id", run_id,
            "--model", "fake-primary", "--reasoning-effort", "medium",
            "--timeout", str(timeout), "--primary-bin", str(fake),
        ],
        text=True,
        capture_output=True,
        env=env,
    )
    attempts = sorted((root / run_id).glob("attempt-*"))
    return result, attempts[-1]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="primary-canary-fixture-") as temp:
        root = Path(temp)
        fake = root / "fake-codex"
        fake.write_text(FAKE, encoding="utf-8")
        fake.chmod(0o755)

        result, happy = invoke(root / "evidence", fake, "happy")
        assert result.returncode == 0, (
            result.stdout, result.stderr, (happy / "stderr.log").read_text(encoding="utf-8")
        )
        assert load(happy / "result.json")["verdict"] == "PASS"
        grade = load(happy / "grader-output.json")
        assert grade["spawn_count"] == 1
        assert grade["child_identities"] == ["child-1"]
        assert grade["child_terminal_states"] == ["completed"]
        feature = load(happy / "feature-preflight.json")
        assert feature["multi_agent_stage"] == "stable"
        assert feature["multi_agent_enabled"] is True
        invocation = load(happy / "invocation.json")
        argv = invocation["argv"]
        assert argv[1:5] == ["--ask-for-approval", "never", "exec", "--json"]
        assert argv[5:7] == ["--sandbox", "workspace-write"]
        assert "--ephemeral" not in argv
        assert argv[argv.index("-C") + 1] == invocation["cwd"]
        assert not Path(invocation["cwd"]).exists()
        assert not Path(invocation["runtime_isolation"]["temporary_home"]).exists()
        assert not Path(invocation["runtime_isolation"]["temporary_codex_home"]).exists()

        expected = {
            "feature-nonzero": "primary_feature_probe_failed",
            "feature-unknown": "primary_feature_protocol_unrecognized",
            "feature-false": "primary_multi_agent_unavailable",
            "feature-short": "primary_feature_protocol_unrecognized",
            "feature-nonsense": "primary_feature_protocol_unrecognized",
            "feature-unknown-lifecycle": "primary_feature_protocol_unrecognized",
            "feature-extra-field": "primary_feature_protocol_unrecognized",
            "feature-duplicate": "primary_feature_protocol_unrecognized",
            "feature-no-exact-target": "primary_feature_protocol_unrecognized",
            "no-spawn": "primary_spawn_count_invalid",
            "wrong-marker": "primary_spawn_marker_invalid",
            "outer-failed": "primary_outer_collaboration_incomplete",
            "child-failed": "primary_child_terminal_state_invalid",
            "child-running": "primary_child_terminal_state_invalid",
            "child-cancelled": "primary_child_terminal_state_invalid",
            "child-timed-out": "primary_child_terminal_state_invalid",
            "multiple-child": "primary_child_identity_invalid",
            "multiple-spawn": "primary_spawn_count_invalid",
            "prose-only": "primary_spawn_count_invalid",
            "runtime-nonzero": "runtime_exit_nonzero",
            "runtime-timeout": "runtime_timeout",
            "malformed-jsonl": "primary_trace_protocol_unrecognized",
            "nonobject-jsonl": "primary_trace_protocol_unrecognized",
            "item-failed-completed-payload": "primary_outer_collaboration_incomplete",
            "duplicate-start-same-id": "primary_trace_protocol_unrecognized",
            "tracked-write": "primary_repository_write_set_nonempty",
            "committed-write": "primary_repository_write_set_nonempty",
            "untracked-write": "primary_repository_write_set_nonempty",
            "symlink-write": "primary_repository_write_set_nonempty",
            "runtime-repo-missing": "runtime_workspace_restore_failed",
        }
        for case, expected_code in expected.items():
            result, attempt = invoke(
                root / "evidence", fake, case, timeout=1 if case == "runtime-timeout" else 2
            )
            assert result.returncode == 1, (case, result.stdout, result.stderr)
            payload = load(attempt / "result.json")
            assert payload["verdict"] == "FAIL", case
            assert expected_code in payload["failure_codes"], (case, payload)

        repo_keys = {
            "tracked-write": "tracked_write_set",
            "committed-write": "committed_write_set",
            "untracked-write": "untracked_write_set",
            "symlink-write": "symlink_write_set",
        }
        for case, key in repo_keys.items():
            attempt = root / "evidence" / case / "attempt-001"
            evidence = load(attempt / "repository-evidence.json")
            assert evidence[key], (case, evidence)

        missing_result, missing_attempt = invoke(
            root / "evidence", root / "missing-codex", "happy", run_id="binary-missing"
        )
        assert missing_result.returncode == 1
        assert "runtime_version_failed" in load(missing_attempt / "result.json")["failure_codes"]

        missing_repo_attempt = root / "evidence/runtime-repo-missing/attempt-001"
        assert (missing_repo_attempt / "grader-output.json").is_file()
        assert (missing_repo_attempt / "result.json").is_file()
        assert (missing_repo_attempt / "fixture/CANARY_INPUT.md").is_file()

        secret_auth = "AUTH_SECRET_MUST_NOT_ENTER_EVIDENCE"
        secret_config = "CONFIG_SECRET_MUST_NOT_ENTER_EVIDENCE"
        ambient = root / "ambient-codex"
        ambient.mkdir()
        (ambient / "auth.json").write_text(secret_auth, encoding="utf-8")
        (ambient / "config.toml").write_text(secret_config, encoding="utf-8")
        result, sanitized = invoke(
            root / "evidence", fake, "happy", run_id="sanitized", ambient_codex_home=ambient
        )
        assert result.returncode == 0
        evidence_bytes = b"\n".join(
            path.read_bytes() for path in sanitized.rglob("*") if path.is_file()
        )
        assert secret_auth.encode() not in evidence_bytes
        assert secret_config.encode() not in evidence_bytes
        isolation = load(sanitized / "invocation.json")["runtime_isolation"]
        assert isolation["initial_codex_home_entries"] == ["auth.json"]
        assert isolation["cleanup_succeeded"] is True

        result, second = invoke(root / "evidence", fake, "happy", run_id="happy")
        assert result.returncode == 0
        assert second.name == "attempt-002"
        assert (root / "evidence/happy/attempt-001/result.json").is_file()

        shared_log = root / "shared-adapter-invocations.jsonl"
        result, shared_canary = invoke(
            root / "evidence", fake, "happy", run_id="shared-adapter",
            extra_env={"PRIMARY_CANARY_FAKE_LOG": str(shared_log)},
        )
        assert result.returncode == 0
        profile_output = root / "profile-evidence"
        profile_env = os.environ.copy()
        profile_env.update({
            "PRIMARY_CANARY_FAKE_CASE": "happy",
            "PRIMARY_CANARY_FAKE_LOG": str(shared_log),
        })
        profile = subprocess.run(
            [
                sys.executable, str(PROFILE_RUNNER), "--output", str(profile_output),
                "--run-id", "shared-adapter", "--scenario", "architecture-native-ownership",
                "--treatment-ref", "HEAD", "--ablation-ref", "HEAD", "--runtime", "primary",
                "--model", "fake-primary", "--reasoning-effort", "medium", "--timeout", "2",
                "--primary-bin", str(fake), "--variant", "treatment",
            ],
            cwd=ROOT, env=profile_env, text=True, capture_output=True,
        )
        assert profile.returncode == 1
        profile_attempt = profile_output / "shared-adapter/architecture-native-ownership/treatment/attempt-001"
        canary_argv = load(shared_canary / "invocation.json")["argv"]
        profile_argv = load(profile_attempt / "invocation.json")["argv"]

        def normalized_command(argv):
            value = list(argv[:-1])
            value[value.index("-C") + 1] = "<opaque-fixture>"
            return value

        assert normalized_command(canary_argv) == normalized_command(profile_argv)
        model_records = [
            json.loads(line) for line in shared_log.read_text(encoding="utf-8").splitlines()
            if "exec" in json.loads(line)["argv"]
        ]
        assert len(model_records) == 2
        for record in model_records:
            assert Path(record["HOME"]).name == "home"
            assert Path(record["CODEX_HOME"]).name == "codex-home"
            assert Path(record["cwd"]).name.startswith("workspace-")
            assert Path(record["HOME"]).parent == Path(record["CODEX_HOME"]).parent

        def run_with_start_failure(module_path: Path, argv: list[str], expected_result: Path) -> None:
            import contextlib
            import importlib.util
            import io
            module_name = "startup_failure_" + module_path.stem.replace("-", "_")
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            original = module.PrimaryRuntimeAdapter.start
            original_argv = sys.argv
            def fail_start(_self):
                raise OSError("deterministic startup failure")
            module.PrimaryRuntimeAdapter.start = fail_start
            sys.argv = [str(module_path), *argv]
            try:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    try:
                        module.main()
                    except SystemExit as exc:
                        assert exc.code == 1
            finally:
                module.PrimaryRuntimeAdapter.start = original
                sys.argv = original_argv
            assert expected_result.is_file(), expected_result
            result = load(expected_result)
            codes = result.get("failure_codes", result.get("error_codes", []))
            assert "primary_runtime_start_failed" in codes

        startup_root = root / "startup-failure"
        run_with_start_failure(
            RUNNER,
            ["--output", str(startup_root), "--run-id", "canary", "--model", "fake",
             "--timeout", "2", "--primary-bin", str(fake)],
            startup_root / "canary/attempt-001/result.json",
        )
        run_with_start_failure(
            PROFILE_RUNNER,
            ["--output", str(startup_root), "--run-id", "profile",
             "--scenario", "architecture-native-ownership", "--treatment-ref", "HEAD",
             "--ablation-ref", "HEAD", "--runtime", "primary", "--model", "fake",
             "--timeout", "2", "--primary-bin", str(fake), "--variant", "treatment"],
            startup_root / "profile/architecture-native-ownership/treatment/attempt-001/result.json",
        )

        sys.path.insert(0, str(PROFILE_RUNNER.parent))
        from primary_runtime import PrimaryRuntimeAdapter
        missing_repo_adapter = PrimaryRuntimeAdapter(
            evidence_repo=root / "does-not-exist",
            primary_bin=str(fake), model="fake", reasoning_effort=None, timeout=2,
        ).start()
        assert missing_repo_adapter.start_error_code == "primary_runtime_start_failed"
        assert missing_repo_adapter.cleanup_succeeded is True
        if missing_repo_adapter.runtime_root is not None:
            assert not missing_repo_adapter.runtime_root.exists()
        if missing_repo_adapter.workspace_root is not None:
            assert not missing_repo_adapter.workspace_root.exists()

        restore_repo = root / "restore-failure-fixture"
        subprocess.run(["git", "init", "-q", str(restore_repo)], check=True)
        (restore_repo / "CANARY_INPUT.md").write_text("baseline\n", encoding="utf-8")
        restore_adapter = PrimaryRuntimeAdapter(
            evidence_repo=restore_repo,
            primary_bin=str(fake), model="fake", reasoning_effort=None, timeout=2,
        ).start()
        assert restore_adapter.started is True
        restore_repo.write_text("blocks normal restore", encoding="utf-8")
        cleanup_codes = restore_adapter.cleanup()
        assert "runtime_workspace_restore_failed" in cleanup_codes
        recovery_path = Path(restore_adapter.preserved_workspace_path)
        assert recovery_path.parent == restore_repo.parent
        assert (recovery_path / "CANARY_INPUT.md").is_file()
        baseline_recovery = Path(restore_adapter.preserved_baseline_path)
        assert baseline_recovery.parent == restore_repo.parent
        assert (baseline_recovery / "CANARY_INPUT.md").is_file()
        assert restore_adapter.workspace_root is not None
        assert not restore_adapter.workspace_root.exists()

    print("primary collaboration canary deterministic fixture: PASS")


if __name__ == "__main__":
    main()
