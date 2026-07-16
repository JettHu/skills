#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$REPO_ROOT" <<'PY'
from pathlib import Path
import importlib.util
import sys

repo = Path(sys.argv[1])
core = (repo / "skills/engineering/ultra/SKILL.md").read_text(encoding="utf-8")
profiles = (repo / "skills/engineering/ultra/PROFILES.md").read_text(encoding="utf-8")
prepare_path = repo / "tests/evals/ultra-complementary-profiles/prepare-fixture.py"
prepare_source = prepare_path.read_text(encoding="utf-8")
spec = importlib.util.spec_from_file_location("complementary_prepare", prepare_path)
prepare = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prepare)
assert "def stage_marker" in prepare_source
assert "[target-native:architecture-candidate-discovery]" not in prepare_source
assert "historical_forbidden_events" not in prepare_source
assert "delegation_marker" not in prepare.SCENARIOS["architecture-native-ownership"]
assert set(prepare.SCENARIOS) == {
    "architecture-native-ownership", "diagnosis-feedback-loop-first",
    "spec-independent-code-trigger", "tickets-review-publication",
    "short-evidence-complete", "long-stale-context", "triage-native-exploration",
}

for target in (
    "improve-codebase-architecture", "to-spec", "diagnosing-bugs", "to-tickets",
    "triage", "tdd", "prototype", "grill-me", "grill-with-docs", "handoff",
):
    assert f"| {target} |" in profiles, f"missing ownership profile: {target}"

for text in (
    "A goal may have only one owner and must run at most once",
    "This sufficiency check never suppresses an unconditional target-native stage",
    "Missing evidence in conversation context is not, by itself, a trigger",
    "Target-native delegation is outside this cap and remains intact",
    "invoke the target first so it can build and run its red-capable feedback loop",
):
    assert text in core, f"missing complementary routing rule: {text}"

for text in (
    "No Ultra pre-exploration",
    "Always review the complete Ticket set once",
    "publication/promotion",
    "Proportional review after actual code changes",
    "A short current artifact names affected modules and contracts",
    "A long prior discussion covers architecture but predates a changed contract",
):
    assert text in profiles, f"missing profile contract: {text}"

for proxy in ("20+ messages", "completely unfamiliar area", "already traced the code path"):
    assert proxy not in core + profiles, f"proxy heuristic returned: {proxy}"
assert "`unavailable` = neither the target nor Ultra has a stage for that capability" in profiles
for contradictory in (
    "to-spec | Repository exploration is conditional `target-native`; the target runs it when current codebase understanding is absent. Research and code review are `unavailable`",
    "to-tickets | Context gathering and repository exploration are conditional `target-native`; drafting and blocker assignment are `target-native`. Research and code review are `unavailable`",
):
    assert contradictory not in profiles, f"target-native absence is mislabeled unavailable: {contradictory}"
PY

python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/prepare-fixture.py" \
  --output "$TMP" --run-id authority-fixtures --scenario all --variant treatment \
  --treatment-ref working-tree --ablation-ref HEAD >/dev/null

python3 - "$REPO_ROOT" "$TMP/authority-fixtures" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

repo_root = Path(sys.argv[1])
root = Path(sys.argv[2])
grader = repo_root / "tests/evals/ultra-complementary-profiles/grade-run.py"

for repo in sorted(root.glob("*/treatment/attempt-001/repo")):
    expected = json.loads((repo.parent / "control.json").read_text(encoding="utf-8"))["expectations"]
    scenario = expected["scenario"]
    artifact = repo / expected["artifact"]
    artifact.parent.mkdir(parents=True, exist_ok=True)
    coverage = " ".join(expected["artifact_tokens"] + expected["artifact_sources"])
    artifact.write_text(
        "# Evidence artifact\n\n" + "\n\n".join(
            f"## {heading}\n\nEvidence for {heading} is grounded in {coverage} and records concrete validation risk."
            for heading in expected["artifact_sections"]
        ) + "\n",
        encoding="utf-8",
    )
    events = [
        {
            "name": name,
            "owner": expected["event_owners"][name],
            "goal": f"goal-{index}-{name}",
            "evidence": expected["artifact"],
        }
        for index, name in enumerate(expected["required_events"])
    ]
    (repo / "artifacts/stage-evidence.json").write_text(
        json.dumps({"events": events}, indent=2) + "\n", encoding="utf-8"
    )
    if scenario == "diagnosis-feedback-loop-first":
        (repo / "app/router.py").write_text(
            "def route_order(order):\n    return 'priority' if order == 'priority' else 'standard'\n",
            encoding="utf-8",
        )
        (repo / "app/result.txt").write_text("fixed\n", encoding="utf-8")
    if scenario == "tickets-review-publication":
        tracker = repo / ".scratch/eval/issues/01-order-routing.md"
        tracker.write_text(
            tracker.read_text(encoding="utf-8").replace("Status: review-pending", "Status: ready-for-agent"),
            encoding="utf-8",
        )
        subprocess.run([sys.executable, "scripts/publish.py"], cwd=repo, check=True)

    trace_events = [{
        "type": "system", "subtype": "init", "tools": ["Agent", "Bash"],
        "agents": ["general-purpose"], "model": "root-model",
    }]
    for index, name in enumerate(expected["trace_expectations"]["required_marker_events"]):
        call_id = f"agent-{index}"
        marker = expected["trace_expectations"]["known_stage_markers"][name]
        trace_events.extend((
            {"type": "assistant", "message": {"content": [{
                "type": "tool_use", "id": call_id, "name": "Agent",
                "input": {"subagent_type": "general-purpose", "prompt": f"Do stage {marker}"},
            }]}},
            {"type": "assistant", "parent_tool_use_id": call_id, "message": {"model": "delegated", "content": []}},
            {"type": "user", "message": {"content": [{
                "type": "tool_result", "tool_use_id": call_id, "is_error": False,
            }]}, "tool_use_result": {"state": "completed"}},
        ))
    command_index = 0
    for requirement in expected["trace_expectations"]["command_calls"]:
        for occurrence in range(requirement["min"]):
            call_id = f"command-{command_index}"
            command_index += 1
            failed = scenario == "diagnosis-feedback-loop-first" and occurrence == 0
            trace_events.extend((
                {"type": "assistant", "message": {"content": [{
                    "type": "tool_use", "id": call_id, "name": "Bash",
                    "input": {"command": requirement["command"]},
                }]}},
                {"type": "user", "message": {"content": [{
                    "type": "tool_result", "tool_use_id": call_id, "is_error": failed,
                }]}, "tool_use_result": {
                    "state": "failed" if failed else "completed",
                    "exit_code": 1 if failed else 0,
                }},
            ))
    trace = repo.parent / "authority-trace.jsonl"
    trace.write_text("\n".join(json.dumps(event) for event in trace_events) + "\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(grader), str(repo), "--trace", str(trace), "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"{scenario}: {result.stdout}{result.stderr}"
    if scenario == "diagnosis-feedback-loop-first":
        sentinel = repo.parent / "model-code-executed"
        (repo / "app/router.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(sentinel)!r}).write_text('executed')\n"
            "def route_order(order):\n"
            "    return 'priority' if order == 'priority' else 'standard'\n",
            encoding="utf-8",
        )
        malicious = subprocess.run(
            [sys.executable, str(grader), str(repo), "--trace", str(trace), "--json"],
            capture_output=True, text=True,
        )
        assert malicious.returncode != 0
        assert not sentinel.exists(), "grader executed model-authored diagnosis code"
        malicious_grade = json.loads(malicious.stdout)[0]
        assert "repository_validation" in malicious_grade["repository_grade"]["failure_codes"]
PY

python3 - "$TMP/fake-qoder" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text(
    "#!/usr/bin/env python3\n"
    "import pathlib, sys\n"
    "if '--cwd' in sys.argv:\n"
    "    repo = pathlib.Path(sys.argv[sys.argv.index('--cwd') + 1])\n"
    "    (repo.parent / 'control.json').write_text('{}\\n', encoding='utf-8')\n"
    "raise SystemExit(9)\n",
    encoding="utf-8",
)
path.chmod(0o755)
PY

runner=(python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/run-eval.py"
  --output "$TMP/runner" --run-id failure-record --scenario architecture-native-ownership
  --treatment-ref HEAD --ablation-ref HEAD --model fake --context-window 1000000
  --timeout 5 --qoder-bin "$TMP/fake-qoder" --variant treatment)
if "${runner[@]}" >/dev/null 2>&1; then
  echo "runner unexpectedly passed a failed model run" >&2
  exit 1
fi
if "${runner[@]}" >/dev/null 2>&1; then
  echo "runner unexpectedly passed a failed rerun" >&2
  exit 1
fi
test -f "$TMP/runner/failure-record/architecture-native-ownership/treatment/attempt-001/result.json"
test -f "$TMP/runner/failure-record/architecture-native-ownership/treatment/attempt-002/result.json"
test -f "$TMP/runner/failure-record/architecture-native-ownership/treatment/attempt-001/grader-control.json"
python3 - "$TMP/runner/failure-record/architecture-native-ownership/treatment/attempt-001" <<'PY'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
assert json.loads((root / "control.json").read_text()) == {}
snapshot = json.loads((root / "grader-control.json").read_text())
assert snapshot["expectations"]["required_events"]
invocation = json.loads((root / "invocation.json").read_text())
argv = invocation["argv"]
assert argv[argv.index("--setting-sources") + 1] == "project"
assert "--disable-builtin-skills" in argv
config_dir = Path(argv[argv.index("--config-dir") + 1])
assert not config_dir.exists()
assert invocation["runtime_isolation"] == {
    "contract_only_prompt": True,
    "slash_and_skill_invocation_forbidden": True,
    "global_skill_use_trace_graded": True,
    "ephemeral_user_config": True,
    "user_and_local_setting_sources_disabled": True,
    "builtin_skills_disabled": True,
    "ambient_home_isolated": False,
}
PY

canary_runner=(python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/run-eval.py"
  --output "$TMP/runner" --run-id verdict-history --scenario architecture-native-ownership
  --treatment-ref HEAD --ablation-ref HEAD --model fake --context-window 1000000
  --timeout 5 --qoder-bin "$TMP/fake-qoder" --canary-gate)
if "${canary_runner[@]}" >/dev/null 2>&1; then
  echo "failed canary unexpectedly passed" >&2
  exit 1
fi
if "${canary_runner[@]}" >/dev/null 2>&1; then
  echo "failed canary rerun unexpectedly passed" >&2
  exit 1
fi
test -f "$TMP/runner/verdict-history/architecture-native-ownership/canary-verdict-treatment-001-ablation-001.json"
test -f "$TMP/runner/verdict-history/architecture-native-ownership/canary-verdict-treatment-002-ablation-002.json"
python3 - "$TMP/runner/verdict-history/architecture-native-ownership" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
first = json.loads((root / "canary-verdict-treatment-001-ablation-001.json").read_text(encoding="utf-8"))
second = json.loads((root / "canary-verdict-treatment-002-ablation-002.json").read_text(encoding="utf-8"))
assert (first["treatment_attempt"], first["ablation_attempt"]) == (1, 1)
assert (second["treatment_attempt"], second["ablation_attempt"]) == (2, 2)
assert first["verdict_file"] != second["verdict_file"]
PY

if python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/run-eval.py" \
  --output "$TMP/runner" --run-id uncommitted-ref --scenario architecture-native-ownership \
  --treatment-ref working-tree --ablation-ref HEAD --model fake --context-window 1000000 \
  --timeout 5 --qoder-bin "$TMP/fake-qoder" --variant treatment >/dev/null 2>&1; then
  echo "model runner accepted an uncommitted working-tree contract" >&2
  exit 1
fi
test ! -e "$TMP/runner/uncommitted-ref"

if python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/run-eval.py" \
  --output "$TMP/runner" --run-id primary-entry --scenario architecture-native-ownership \
  --treatment-ref HEAD --ablation-ref HEAD --runtime primary --model fake-primary \
  --timeout 5 --primary-bin "$TMP/fake-qoder" --variant treatment >/dev/null 2>&1; then
  echo "primary runner unexpectedly passed a failed model run" >&2
  exit 1
fi
python3 - "$TMP/runner/primary-entry/architecture-native-ownership/treatment/attempt-001/invocation.json" <<'PY'
import json
from pathlib import Path
import sys
invocation = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert invocation["runtime"] == "primary"
assert invocation["argv"][1:4] == ["--ask-for-approval", "never", "exec"]
assert invocation["argv"][4:6] == ["--json", "--ephemeral"]
assert "--dangerously-bypass-approvals-and-sandbox" not in invocation["argv"]
assert ["--sandbox", "workspace-write"] == invocation["argv"][6:8]
assert invocation["context_window"] is None
assert len(invocation["refs"]["treatment"]["sha"]) == 40
expectations = json.loads((Path(invocation["cwd"]) / "EVAL_EXPECTATIONS.json").read_text(encoding="utf-8"))
assert expectations["contract_ref"] == invocation["refs"]["selected_contract"]["sha"]
assert invocation["refs"]["selected_contract"]["requested"] == "HEAD"
assert invocation["scenario"] == "architecture-native-ownership"
assert invocation["variant"] == "treatment"
assert invocation["runtime_isolation"]["contract_only_prompt"] is True
assert invocation["runtime_isolation"]["ephemeral_user_config"] is True
assert invocation["runtime_isolation"]["user_and_local_setting_sources_disabled"] is False
assert invocation["runtime_isolation"]["ambient_home_isolated"] is True
assert invocation["authority"]["snapshotted_before_model_run"] is True
assert len(invocation["authority"]["baseline_commit"]) == 40
prompt = invocation["argv"][-1]
assert "Execute `/ultra" not in prompt
assert "Do not invoke any slash command or Skill tool" in prompt
PY

python3 - "$TMP/sleep-qoder" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n", encoding="utf-8")
path.chmod(0o755)
PY
if python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/run-eval.py" \
  --output "$TMP/runner" --run-id timeout-record --scenario architecture-native-ownership \
  --treatment-ref HEAD --ablation-ref HEAD --model fake --context-window 1000000 \
  --timeout 1 --qoder-bin "$TMP/sleep-qoder" --variant ablation >/dev/null 2>&1; then
  echo "runner unexpectedly passed a timed-out model run" >&2
  exit 1
fi
python3 - "$TMP/runner/timeout-record/architecture-native-ownership/ablation/attempt-001/result.json" <<'PY'
import json
from pathlib import Path
import sys
result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["timed_out"] is True and result["run_exit_code"] == 124
PY

python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/prepare-fixture.py" \
  --output "$TMP" --run-id all-fixtures --scenario all \
  --treatment-ref working-tree --ablation-ref HEAD >/dev/null

python3 - "$REPO_ROOT" "$TMP/all-fixtures" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv[1])
root = Path(sys.argv[2])
grader = repo / "tests/evals/ultra-complementary-profiles/grade-run.py"
fixtures = sorted(root.glob("*/*/attempt-001/repo"))
assert len(fixtures) == 14
for scenario_root in sorted(path for path in root.iterdir() if path.is_dir()):
    treatment_prompt = (
        scenario_root / "treatment/attempt-001/repo/EVAL_PROMPT.md"
    ).read_text(encoding="utf-8")
    ablation_prompt = (
        scenario_root / "ablation/attempt-001/repo/EVAL_PROMPT.md"
    ).read_text(encoding="utf-8")
    assert treatment_prompt == ablation_prompt, (
        f"treatment and ablation prompts differ: {scenario_root.name}"
    )
for fixture in fixtures:
    public = json.loads((fixture / "EVAL_EXPECTATIONS.json").read_text(encoding="utf-8"))
    control = json.loads((fixture.parent / "control.json").read_text(encoding="utf-8"))
    expected = control["expectations"]
    prompt = (fixture / "EVAL_PROMPT.md").read_text(encoding="utf-8")
    assert f"exact status `{expected['expected_tracker_status']}`" in prompt
    assert f"`{expected['artifact']}`" in prompt
    expected_vocabulary = {
        *expected["required_events"],
        *expected["event_aliases"],
        *expected["recordable_extra_events"],
    }
    assert set(expected["stage_vocabulary"]) == expected_vocabulary
    for name in expected_vocabulary:
        assert f"`{name}`" in prompt
    assert "required stages exactly once" not in prompt
    assert "Record these required stages" not in prompt
    assert "Extra stages are allowed only" not in prompt
    assert "Every goal must be distinct" not in prompt
    assert "[target-native:" not in prompt
    assert " -> " not in prompt
    assert "Execute `/ultra" not in prompt
    assert "Do not invoke any slash command or Skill tool" in prompt
    assert expected["schema_version"] == 2
    assert expected["trace_expectations"] is not None
    assert "required_events" not in public
    assert "event_owners" not in public
    assert "trace_expectations" not in public
    assert "allowed_changes" not in public
    assert (fixture.parent / "control.json").is_file()
    if expected["scenario"] == "architecture-native-ownership":
        assert expected_vocabulary == {
            "target-native-explore", "target-native-candidate", "target-native-report",
            "ultra-code-explore", "ultra-post-review", "validation",
        }
        assert "`ultra-research`" not in prompt
        assert "`target-feedback-loop-red`" not in prompt
        assert "`ultra-complete-set-review`" not in prompt
    observability = expected["trace_expectations"]
    scenario = expected["scenario"]
    if scenario == "diagnosis-feedback-loop-first":
        assert observability["command_sequence"] == [
            {"command": "python3 scripts/check.py", "status": "failed"},
            {"command": "python3 scripts/check.py", "status": "completed"},
        ]
        assert observability["required_marker_events"] == ["ultra-code-review"]
    elif scenario == "tickets-review-publication":
        assert any(
            item["command"] == "python3 scripts/publish.py"
            for item in observability["command_calls"]
        )
        assert observability["required_marker_events"] == [
            "target-native-explore", "ultra-complete-set-review",
        ]
    elif scenario == "short-evidence-complete":
        assert observability["max_total_agent_calls"] == 0
    elif scenario in {"spec-independent-code-trigger", "long-stale-context"}:
        assert observability["required_marker_events"] == [
            "target-native-explore", "ultra-independent-code", "ultra-fresh-review",
        ]
    elif scenario == "triage-native-exploration":
        assert observability["required_marker_events"] == ["target-native-explore"]
    assert subprocess.run(
        [sys.executable, str(grader), str(fixture)], capture_output=True
    ).returncode != 0, f"untouched fixture unexpectedly passed: {fixture}"

# 82842f6-capability shape dispatches without KeyError.
legacy_fixture = fixtures[0]
legacy_control_path = legacy_fixture.parent / "control.json"
legacy_control = json.loads(legacy_control_path.read_text(encoding="utf-8"))
legacy_expected = legacy_control["expectations"]
legacy_expected.pop("schema_version", None)
legacy_expected.pop("required_events", None)
legacy_expected.pop("event_owners", None)
legacy_expected["required_recorded_events"] = ["validation"]
legacy_text = json.dumps(legacy_expected, indent=2) + "\n"
import hashlib
legacy_control["expectations_sha256"] = hashlib.sha256(legacy_text.encode()).hexdigest()
legacy_control["workspace_expectations_sha256"] = hashlib.sha256(legacy_text.encode()).hexdigest()
legacy_control_path.write_text(json.dumps(legacy_control, indent=2) + "\n", encoding="utf-8")
(legacy_fixture / "EVAL_EXPECTATIONS.json").write_text(legacy_text, encoding="utf-8")
legacy_result = subprocess.run(
    [sys.executable, str(grader), str(legacy_fixture), "--json"],
    capture_output=True, text=True,
)
assert legacy_result.stdout.strip().startswith("[")
json.loads(legacy_result.stdout)
PY

python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/prepare-fixture.py" \
  --output "$TMP" --run-id fixture --scenario architecture-native-ownership \
  --treatment-ref working-tree --ablation-ref HEAD >/dev/null

python3 - "$REPO_ROOT" "$TMP" <<'PY'
import json
import importlib.util
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv[1])
tmp = Path(sys.argv[2])
base = tmp / "fixture/architecture-native-ownership"
treatment = base / "treatment/attempt-001/repo"
ablation = base / "ablation/attempt-001/repo"
grader = repo / "tests/evals/ultra-complementary-profiles/grade-run.py"

t_manifest = json.loads((treatment.parent / "fixture-manifest.json").read_text())
a_manifest = json.loads((ablation.parent / "fixture-manifest.json").read_text())
assert t_manifest["common_hashes"] == a_manifest["common_hashes"], "pair fixtures are not equivalent"
prompt = (treatment / "EVAL_PROMPT.md").read_text(encoding="utf-8")
ablation_prompt = (ablation / "EVAL_PROMPT.md").read_text(encoding="utf-8")
assert prompt == ablation_prompt, "treatment and ablation must receive the same eval prompt"
assert "exact status `ready-for-agent`" in prompt
assert "Runtime execution and live repository state are graded" in prompt
assert "the primary artifact does not need to repeat the command" in prompt
assert "[eval-stage:target-native-explore]" not in prompt
assert "target-native-explore` -> `target-native-candidate" not in prompt
assert "required stages exactly once" not in prompt
assert "Record these required stages" not in prompt
assert "Extra stages are allowed only" not in prompt
assert "do not repeat a required goal" not in prompt
target_contract = (treatment / "TARGET_SKILL.md").read_text(encoding="utf-8")
assert target_contract == (ablation / "TARGET_SKILL.md").read_text(encoding="utf-8")
assert "[eval-stage:target-native-explore]" in target_contract
assert subprocess.run([sys.executable, str(grader), str(treatment)], capture_output=True).returncode != 0

artifact = treatment / "artifacts/architecture-report.md"
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text(
    """# Architecture report

## Candidate

The Order Router route_order boundary should absorb routing policy and decision context.

## Source Evidence

The implementation in app/router.py is shallow and exposes the policy branch directly.

## ADR and Risk Review

The ordering rule in docs/adr/ADR-0001.md creates an audit sequencing risk to preserve.
""",
    encoding="utf-8",
)
events = [
    {"name": "target-native-explore", "owner": "target", "goal": "discover-candidates", "evidence": "app/router.py"},
    {"name": "target-native-report", "owner": "target", "goal": "produce-report", "evidence": "artifacts/architecture-report.md"},
    {"name": "ultra-post-review", "owner": "ultra", "goal": "risk-and-adr-review", "evidence": "docs/adr/ADR-0001.md"},
    {"name": "validation", "owner": "root", "goal": "validate-repository", "evidence": "python3 scripts/check.py"},
]
(treatment / "artifacts/stage-evidence.json").write_text(json.dumps({"events": events}, indent=2) + "\n")
missing_delegation = treatment.parent / "missing-delegation.jsonl"
missing_delegation.write_text(json.dumps({
    "type": "system", "subtype": "init", "tools": ["Agent"],
    "agents": ["Explore"], "model": "root-model",
}) + "\n")
assert subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(missing_delegation)],
    capture_output=True,
).returncode != 0, "self-reported target-native exploration must not replace a real delegation call"

valid_trace = treatment.parent / "valid-trace.jsonl"
valid_trace.write_text("\n".join(json.dumps(event) for event in (
    {"type": "system", "subtype": "init", "tools": ["Agent"], "agents": ["Explore"], "model": "root-model"},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "agent-1", "name": "Agent", "input": {"subagent_type": "general-purpose", "description": "target-native explore", "prompt": "Explore repository [eval-stage:target-native-explore]"}}]}},
    {"type": "assistant", "parent_tool_use_id": "agent-1", "message": {"model": "delegated-model", "content": []}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "agent-1", "is_error": False}]}, "tool_use_result": {"state": "completed"}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "bash-1", "name": "Bash", "input": {"command": "python3 scripts/check.py"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "bash-1", "is_error": False}]}, "tool_use_result": {"stdout": "", "stderr": "", "interrupted": False}},
)) + "\n")
assert subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(valid_trace)],
    capture_output=True,
).returncode == 0

def grade_json(repo_path=treatment, trace_path=valid_trace):
    result = subprocess.run(
        [sys.executable, str(grader), str(repo_path), "--trace", str(trace_path), "--json"],
        capture_output=True, text=True,
    )
    return result, json.loads(result.stdout)[0]


# Token stuffing cannot replace structured evidence-backed artifact content.
artifact_original = artifact.read_text(encoding="utf-8")
artifact.write_text("Order Router route_order ADR-0001\n", encoding="utf-8")
thin_artifact_result, thin_artifact_grade = grade_json()
assert thin_artifact_result.returncode != 0
assert any(
    code.startswith("artifact_section:")
    for code in thin_artifact_grade["repository_grade"]["failure_codes"]
)
artifact.write_text(artifact_original, encoding="utf-8")

# Workspace expectations are untrusted; the external control remains authoritative.
expectations_path = treatment / "EVAL_EXPECTATIONS.json"
expectations_original = expectations_path.read_text(encoding="utf-8")
tampered = json.loads(expectations_original)
tampered["stage_vocabulary"] = []
tampered["contract_hashes"] = {}
expectations_path.write_text(json.dumps(tampered, indent=2) + "\n", encoding="utf-8")
tampered_result, tampered_grade = grade_json()
assert tampered_result.returncode != 0
assert "expectations_tampered" in tampered_grade["repository_grade"]["failure_codes"]
expectations_path.write_text(expectations_original, encoding="utf-8")

# The model-owned checker and architecture source are outside the write set.
checker = treatment / "scripts/check.py"
checker_original = checker.read_text(encoding="utf-8")
checker.write_text("raise SystemExit(0)\n", encoding="utf-8")
checker_result, checker_grade = grade_json()
assert checker_result.returncode != 0
assert "scenario_write_set" in checker_grade["repository_grade"]["failure_codes"]
checker.write_text(checker_original, encoding="utf-8")

router = treatment / "app/router.py"
router_original = router.read_text(encoding="utf-8")
router.write_text(router_original + "# unauthorized architecture edit\n", encoding="utf-8")
router_result, router_grade = grade_json()
assert router_result.returncode != 0
assert "scenario_write_set" in router_grade["repository_grade"]["failure_codes"]
router.write_text(router_original, encoding="utf-8")

# Missing/malformed model-writable state yields stable JSON failures, not crashes.
tracker_path = treatment / ".scratch/eval/issues/01-order-routing.md"
tracker_original = tracker_path.read_text(encoding="utf-8")
tracker_path.unlink()
missing_tracker_result, missing_tracker_grade = grade_json()
assert missing_tracker_result.returncode != 0
assert "tracker_status" in missing_tracker_grade["repository_grade"]["failure_codes"]
tracker_path.parent.mkdir(parents=True, exist_ok=True)
tracker_path.write_text(tracker_original, encoding="utf-8")

result_path = treatment / "app/result.txt"
result_original = result_path.read_text(encoding="utf-8")
result_path.unlink()
missing_result_run, missing_result_grade = grade_json()
assert missing_result_run.returncode != 0
assert "repository_result" in missing_result_grade["repository_grade"]["failure_codes"]
result_path.write_text(result_original, encoding="utf-8")

expectations_path.write_text("{malformed", encoding="utf-8")
malformed_result, malformed_grade = grade_json()
assert malformed_result.returncode != 0
assert "expectations_tampered" in malformed_grade["repository_grade"]["failure_codes"]
expectations_path.write_text(expectations_original, encoding="utf-8")

skill_trace = treatment.parent / "global-skill-trace.jsonl"
skill_trace.write_text(valid_trace.read_text() + json.dumps({
    "type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "skill-1", "name": "Skill",
        "input": {"skill": "ultra"},
    }]},
}) + "\n")
skill_result, skill_grade = grade_json(trace_path=skill_trace)
assert skill_result.returncode != 0
assert "forbidden_runtime_tool" in skill_grade["trace_grade"]["failure_codes"]

def assert_required_stage_failure(missing_name):
    incomplete_events = [
        event for event in events
        if event["name"] != missing_name
        and not (missing_name == "target-native-candidate" and event["name"] == "target-native-report")
    ]
    (treatment / "artifacts/stage-evidence.json").write_text(
        json.dumps({"events": incomplete_events}, indent=2) + "\n"
    )
    result = subprocess.run(
        [sys.executable, str(grader), str(treatment), "--trace", str(valid_trace), "--json"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    grade = json.loads(result.stdout)[0]
    assert grade["repository_grade"]["passed"] is True
    assert grade["trace_grade"]["passed"] is True
    assert grade["final_state_grade"]["passed"] is False
    assert "required_events_once" in grade["profile_grade"]["failure_codes"]


assert_required_stage_failure("target-native-candidate")
assert_required_stage_failure("ultra-post-review")
wrong_owner_events = [dict(event) for event in events]
wrong_owner_events[1]["owner"], wrong_owner_events[2]["owner"] = (
    wrong_owner_events[2]["owner"], wrong_owner_events[1]["owner"]
)
(treatment / "artifacts/stage-evidence.json").write_text(
    json.dumps({"events": wrong_owner_events}, indent=2) + "\n"
)
wrong_owner_result = subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(valid_trace), "--json"],
    capture_output=True, text=True,
)
assert wrong_owner_result.returncode != 0
assert "stage_owner" in json.loads(wrong_owner_result.stdout)[0]["profile_grade"]["failure_codes"]

duplicate_goal_events = [{**event, "goal": "same-goal"} for event in events]
(treatment / "artifacts/stage-evidence.json").write_text(
    json.dumps({"events": duplicate_goal_events}, indent=2) + "\n"
)
duplicate_goal_result = subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(valid_trace), "--json"],
    capture_output=True, text=True,
)
assert duplicate_goal_result.returncode != 0
assert "unique_evidence_goals" in json.loads(duplicate_goal_result.stdout)[0]["profile_grade"]["failure_codes"]

misordered_events = [events[1], events[0], *events[2:]]
(treatment / "artifacts/stage-evidence.json").write_text(
    json.dumps({"events": misordered_events}, indent=2) + "\n"
)
misordered_result = subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(valid_trace), "--json"],
    capture_output=True,
    text=True,
)
assert misordered_result.returncode != 0
misordered_grade = json.loads(misordered_result.stdout)[0]
assert misordered_grade["repository_grade"]["passed"] is True
assert misordered_grade["trace_grade"]["passed"] is True
assert misordered_grade["profile_grade"]["failure_codes"] == ["required_stage_order"]
(treatment / "artifacts/stage-evidence.json").write_text(
    json.dumps({"events": events}, indent=2) + "\n"
)

post_review_trace = treatment.parent / "post-review-trace.jsonl"
post_review_trace.write_text(valid_trace.read_text() + json.dumps({
    "type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "agent-review", "name": "Agent",
        "input": {
            "subagent_type": "general-purpose",
            "description": "independent post-artifact review",
            "prompt": (
                "Review and summarize the target-native exploration and candidate-discovery report; "
                "audit artifacts/architecture-report.md for ADR alignment and risk exclusions "
                "[eval-stage:ultra-post-review]"
            ),
        },
    }]},
}) + "\n" + json.dumps({
    "type": "user", "message": {"content": [{
        "type": "tool_result", "tool_use_id": "agent-review", "is_error": False,
    }]},
    "tool_use_result": {"state": "completed"},
}) + "\n")
post_review_result = subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(post_review_trace), "--json"],
    capture_output=True,
    text=True,
)
assert post_review_result.returncode == 0, (
    "a legal delegated post-review must not count as duplicate exploration: "
    + post_review_result.stdout + post_review_result.stderr
)

extra_trace = treatment.parent / "extra-trace.jsonl"
extra_trace.write_text(valid_trace.read_text() + json.dumps({
    "type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "agent-2", "name": "Agent",
        "input": {"subagent_type": "general-purpose", "description": "extra Ultra exploration", "prompt": "Explore [eval-stage:ultra-code-explore]"},
    }]},
}) + "\n" + json.dumps({
    "type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "agent-2", "is_error": False}]},
    "tool_use_result": {"state": "completed"},
}) + "\n")
extra_result = subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(extra_trace), "--json"],
    capture_output=True,
    text=True,
)
assert extra_result.returncode != 0, "trace grader must reject an extra Ultra exploration call"
extra_grade = json.loads(extra_result.stdout)[0]
assert set(extra_grade["trace_grade"]["failure_codes"]) == {
    "extra_exploration_call", "stage_trace_mismatch",
}

double_validation_trace = treatment.parent / "double-validation-trace.jsonl"
double_validation_trace.write_text(valid_trace.read_text() + json.dumps({
    "type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "bash-2", "name": "Bash",
        "input": {"command": "python3 scripts/check.py && echo OK"},
    }]},
}) + "\n" + json.dumps({
    "type": "user", "message": {"content": [{
        "type": "tool_result", "tool_use_id": "bash-2", "is_error": False,
    }]}, "tool_use_result": {"state": "completed"},
}) + "\n")
double_validation_result, double_validation_grade = grade_json(trace_path=double_validation_trace)
assert double_validation_result.returncode != 0
assert "validation_command_maximum" in double_validation_grade["trace_grade"]["failure_codes"]

newline_validation_trace = treatment.parent / "newline-validation-trace.jsonl"
newline_validation_trace.write_text(valid_trace.read_text() + json.dumps({
    "type": "assistant", "message": {"content": [{
        "type": "tool_use", "id": "bash-newline", "name": "Bash",
        "input": {"command": "python3 scripts/check.py\necho OK"},
    }]},
}) + "\n" + json.dumps({
    "type": "user", "message": {"content": [{
        "type": "tool_result", "tool_use_id": "bash-newline", "is_error": False,
    }]}, "tool_use_result": {"state": "completed"},
}) + "\n")
newline_result, newline_grade = grade_json(trace_path=newline_validation_trace)
assert newline_result.returncode != 0
assert "validation_command_maximum" in newline_grade["trace_grade"]["failure_codes"]

codex_trace = treatment.parent / "codex-collab-trace.jsonl"
codex_trace.write_text("\n".join(json.dumps(event) for event in (
    {"type": "thread.started", "thread_id": "fresh-primary"},
    {"type": "item.completed", "item": {
        "id": "collab-ok", "type": "collab_tool_call", "tool": "spawn_agent",
        "prompt": "Explore repository [eval-stage:target-native-explore]",
        "agents_states": {"agent-1": {"status": "completed"}}, "status": "completed",
    }},
    {"type": "item.completed", "item": {
        "id": "collab-child-failed", "type": "collab_tool_call", "tool": "spawn_agent",
        "prompt": "Explore repository [eval-stage:target-native-explore]",
        "agents_states": {"agent-2": {"status": "failed"}}, "status": "completed",
    }},
    {"type": "item.completed", "item": {
        "id": "collab-review", "type": "collab_tool_call", "tool": "spawn_agent",
        "prompt": "Review and summarize the target-native exploration report [eval-stage:ultra-post-review]",
        "agents_states": {"agent-3": {"status": "completed"}}, "status": "completed",
    }},
    {"type": "item.completed", "item": {
        "id": "command-ok", "type": "command_execution", "command": "python3 scripts/check.py",
        "exit_code": 0, "status": "completed",
    }},
)) + "\n")
completed = subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(codex_trace), "--json"],
    capture_output=True,
    text=True,
)
assert completed.returncode == 0, completed.stdout + completed.stderr
codex_grade = json.loads(completed.stdout)[0]
assert codex_grade["trace"]["agent_call_count"] == 2
assert codex_grade["trace"]["rejected_agent_call_count"] == 1
failed_call = next(call for call in codex_grade["trace"]["attempted_agent_calls"] if call["id"] == "collab-child-failed")
assert failed_call["runtime_status"] == "completed"
assert failed_call["agent_terminal_states"] == ["failed"]
assert codex_grade["trace"]["agent_calls"][0]["prompt"].endswith("[eval-stage:target-native-explore]")
review_call = next(call for call in codex_grade["trace"]["agent_calls"] if call["id"] == "collab-review")
assert review_call["role"] is None and review_call["stage_markers"] == ["[eval-stage:ultra-post-review]"]
assert codex_grade["trace"]["delegated_model_observation"] == "unknown/unavailable"
assert codex_grade["repository_grade"]["passed"] is True
assert codex_grade["profile_grade"]["passed"] is True

primary_unmarked_trace = treatment.parent / "primary-unmarked-trace.jsonl"
primary_unmarked_trace.write_text("\n".join(json.dumps(event) for event in (
    {"type": "thread.started", "thread_id": "primary-unmarked"},
    {"type": "item.completed", "item": {
        "id": "native", "type": "collab_tool_call", "tool": "spawn_agent",
        "prompt": "Explore repository [eval-stage:target-native-explore]",
        "agents_states": {"agent-1": {"status": "completed"}}, "status": "completed",
    }},
    {"type": "item.completed", "item": {
        "id": "unmarked-extra", "type": "collab_tool_call", "tool": "spawn_agent",
        "prompt": "Find another architecture and risk candidate",
        "agents_states": {"agent-2": {"status": "completed"}}, "status": "completed",
    }},
    {"type": "item.completed", "item": {
        "id": "command", "type": "command_execution", "command": "python3 scripts/check.py",
        "exit_code": 0, "status": "completed",
    }},
)) + "\n")
unmarked_result, unmarked_grade = grade_json(trace_path=primary_unmarked_trace)
assert unmarked_result.returncode != 0
assert "delegated_stage_marker_missing" in unmarked_grade["trace_grade"]["failure_codes"]

# The real canary failure shape is locked down: a semantic stage alias and a
# genuinely executed validation pass succeed, but an invalid tracker status does not.
tracker = treatment / ".scratch/eval/issues/01-order-routing.md"
tracker.write_text(tracker.read_text(encoding="utf-8").replace("Status: ready-for-agent", "Status: done"), encoding="utf-8")
tracker_failure = subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(valid_trace), "--json"],
    capture_output=True,
    text=True,
)
assert tracker_failure.returncode != 0
tracker_grade = json.loads(tracker_failure.stdout)[0]
assert set(tracker_grade["repository_grade"]["failure_codes"]) == {
    "tracker_status", "scenario_write_set",
}
assert tracker_grade["profile_grade"]["passed"] is True
tracker.write_text(tracker.read_text(encoding="utf-8").replace("Status: done", "Status: ready-for-agent"), encoding="utf-8")

artifact = ablation / "artifacts/architecture-report.md"
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text((treatment / "artifacts/architecture-report.md").read_text(), encoding="utf-8")
ablation_events = events + [{
    "name": "ultra-code-explore",
    "owner": "ultra",
    "goal": "second-candidate-discovery",
    "evidence": "completed Agent call agent-2",
}]
(ablation / "artifacts/stage-evidence.json").write_text(
    json.dumps({"events": ablation_events}, indent=2) + "\n"
)

# A ledger-only declaration cannot be attributed without a matching completed call.
ledger_only_result = subprocess.run(
    [sys.executable, str(grader), str(ablation), "--trace", str(valid_trace), "--json"],
    capture_output=True,
    text=True,
)
assert ledger_only_result.returncode != 0
ledger_mismatch_grade = json.loads(ledger_only_result.stdout)[0]
assert ledger_mismatch_grade["repository_grade"]["passed"] is True
assert ledger_mismatch_grade["trace_grade"]["failure_codes"] == ["stage_trace_mismatch"]

# With a second completed Explore in the raw trace, the same valid repository and
# truthful actual-stage ledger fail solely on the attributable ownership delta.
ablation_extra_result = subprocess.run(
    [sys.executable, str(grader), str(ablation), "--trace", str(extra_trace), "--json"],
    capture_output=True,
    text=True,
)
assert ablation_extra_result.returncode != 0
ablation_extra_grade = json.loads(ablation_extra_result.stdout)[0]
assert ablation_extra_grade["repository_grade"]["passed"] is True
assert ablation_extra_grade["repository_grade"]["failure_codes"] == []
assert ablation_extra_grade["final_state_grade"]["passed"] is True
assert ablation_extra_grade["profile_grade"]["failure_codes"] == ["extra_exploration_call"]
assert ablation_extra_grade["trace_grade"]["failure_codes"] == ["extra_exploration_call"]

runner_path = repo / "tests/evals/ultra-complementary-profiles/run-eval.py"
runner_spec = importlib.util.spec_from_file_location("complementary_runner", runner_path)
runner_module = importlib.util.module_from_spec(runner_spec)
assert runner_spec.loader is not None
runner_spec.loader.exec_module(runner_module)
clean_grade = {"repository_grade": {"passed": True}, "profile_grade": {"passed": True, "failure_codes": []}}
bad_tracker_grade = {
    "repository_grade": {"passed": False, "failure_codes": ["tracker_status"]},
    "profile_grade": {"passed": True, "failure_codes": []},
}
run_ok = {"result": {"run_exit_code": 0}, "grade": clean_grade}
attributable = runner_module.classify_canary(
    run_ok,
    {"result": {"run_exit_code": 0}, "grade": ablation_extra_grade},
    ["extra_exploration_call"],
    ["extra_exploration_call"],
)
assert attributable["matrix_gate_passed"] is True
ledger_mismatch = runner_module.classify_canary(
    run_ok,
    {"result": {"run_exit_code": 0}, "grade": ledger_mismatch_grade},
    ["extra_exploration_call"],
    ["extra_exploration_call"],
)
assert ledger_mismatch["conclusion"] == "ablation-non-attributable-profile-failure"
no_delta = runner_module.classify_canary(run_ok, run_ok, ["extra_exploration_call"], ["extra_exploration_call"])
assert no_delta["conclusion"] == "no-observed-attributable-difference"
assert no_delta["matrix_gate_passed"] is False
ledger_only_grade = {
    "repository_grade": {"passed": True},
    "profile_grade": {"passed": False, "failure_codes": ["forbidden_events_absent"]},
}
ledger_only = runner_module.classify_canary(
    run_ok,
    {"result": {"run_exit_code": 0}, "grade": ledger_only_grade},
    ["extra_exploration_call"],
    ["extra_exploration_call"],
)
assert ledger_only["conclusion"] == "ablation-non-attributable-profile-failure"
invalid = runner_module.classify_canary(
    run_ok,
    {"result": {"run_exit_code": 0}, "grade": bad_tracker_grade},
    ["extra_exploration_call"],
    ["extra_exploration_call"],
)
assert invalid["conclusion"] == "ablation-evidence-invalid"
PY

echo "ultra complementary profiles fixture passed"
