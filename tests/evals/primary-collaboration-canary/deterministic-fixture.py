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
if "--version" in sys.argv:
    print("codex-cli 0.fake")
    raise SystemExit(0)
if sys.argv[1:3] == ["features", "list"]:
    if case == "feature-nonzero":
        raise SystemExit(17)
    if case == "feature-unknown":
        print("unknown protocol")
    elif case == "feature-false":
        print("multi_agent experimental false")
    else:
        print("multi_agent experimental true")
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

marker = "[eval-stage:wrong]" if case == "wrong-marker" else MARKER
terminal_type = "item.failed" if case == "outer-failed" else "item.completed"
outer = "failed" if case == "outer-failed" else "completed"
states = {"child-1": {"status": "completed"}}
receivers = ["child-1"]
if case == "child-failed": states = {"child-1": {"status": "failed"}}
if case == "child-running": states = {"child-1": {"status": "running"}}
if case == "multiple-child":
    states = {"child-1": {"status": "completed"}, "child-2": {"status": "completed"}}
    receivers = ["child-1", "child-2"]
print(json.dumps(event("item.started", "spawn-1", marker, "in_progress")))
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
) -> tuple[subprocess.CompletedProcess[str], Path]:
    run_id = run_id or case
    env = os.environ.copy()
    env["PRIMARY_CANARY_FAKE_CASE"] = case
    if ambient_codex_home is not None:
        env["CODEX_HOME"] = str(ambient_codex_home)
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
            "no-spawn": "primary_spawn_count_invalid",
            "wrong-marker": "primary_spawn_marker_invalid",
            "outer-failed": "primary_outer_collaboration_incomplete",
            "child-failed": "primary_child_terminal_state_invalid",
            "child-running": "primary_child_terminal_state_invalid",
            "multiple-child": "primary_child_identity_invalid",
            "multiple-spawn": "primary_spawn_count_invalid",
            "prose-only": "primary_spawn_count_invalid",
            "runtime-nonzero": "runtime_exit_nonzero",
            "runtime-timeout": "runtime_timeout",
            "tracked-write": "primary_repository_write_set_nonempty",
            "committed-write": "primary_repository_write_set_nonempty",
            "untracked-write": "primary_repository_write_set_nonempty",
            "symlink-write": "primary_repository_write_set_nonempty",
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

        profile_source = PROFILE_RUNNER.read_text(encoding="utf-8")
        assert "from primary_runtime import PrimaryRuntimeAdapter" in profile_source
        assert "primary_adapter.command(prompt)" in profile_source
        adapter_source = (PROFILE_RUNNER.parent / "primary_runtime.py").read_text(encoding="utf-8")
        assert adapter_source.count('"--ask-for-approval"') == 1
        assert adapter_source.count('"workspace-write"') == 1

    print("primary collaboration canary deterministic fixture: PASS")


if __name__ == "__main__":
    main()
