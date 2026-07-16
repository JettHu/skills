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
assert prepare_source.count("[target-native:architecture-candidate-discovery]") == 1
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

python3 - "$TMP/fake-qoder" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text("#!/usr/bin/env python3\nimport sys\nraise SystemExit(9)\n", encoding="utf-8")
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
    expected = json.loads((fixture / "EVAL_EXPECTATIONS.json").read_text(encoding="utf-8"))
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
    assert "[target-native:" not in prompt
    assert " -> " not in prompt
    if expected["scenario"] == "architecture-native-ownership":
        assert expected_vocabulary == {
            "target-native-explore", "target-native-candidate", "target-native-report",
            "ultra-code-explore", "ultra-post-review", "validation",
        }
        assert "`ultra-research`" not in prompt
        assert "`target-feedback-loop-red`" not in prompt
        assert "`ultra-complete-set-review`" not in prompt
    assert subprocess.run(
        [sys.executable, str(grader), str(fixture)], capture_output=True
    ).returncode != 0, f"untouched fixture unexpectedly passed: {fixture}"
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
assert "[target-native:architecture-candidate-discovery]" not in prompt
assert "target-native-explore` -> `target-native-candidate" not in prompt
assert "required stages exactly once" not in prompt
assert "Record these required stages" not in prompt
assert "Extra stages are allowed only" not in prompt
assert "do not repeat a required goal" not in prompt
target_contract = (treatment / "TARGET_SKILL.md").read_text(encoding="utf-8")
assert target_contract == (ablation / "TARGET_SKILL.md").read_text(encoding="utf-8")
assert "[target-native:architecture-candidate-discovery]" in target_contract
assert "the target skill, not its caller, supplies this marker" in target_contract
assert subprocess.run([sys.executable, str(grader), str(treatment)], capture_output=True).returncode != 0

artifact = treatment / "artifacts/architecture-report.md"
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text("Order Router route_order ADR-0001\n", encoding="utf-8")
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
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "agent-1", "name": "Agent", "input": {"subagent_type": "Explore", "description": "target-native explore", "prompt": "Explore repository [target-native:architecture-candidate-discovery]"}}]}},
    {"type": "assistant", "parent_tool_use_id": "agent-1", "message": {"model": "delegated-model", "content": []}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "agent-1", "is_error": False}]}, "tool_use_result": {"state": "completed"}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "bash-1", "name": "Bash", "input": {"command": "python3 scripts/check.py"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "bash-1", "is_error": False}]}, "tool_use_result": {"stdout": "", "stderr": "", "interrupted": False}},
)) + "\n")
assert subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(valid_trace)],
    capture_output=True,
).returncode == 0

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
                "audit artifacts/architecture-report.md for ADR alignment and risk exclusions"
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
        "input": {"subagent_type": "Explore", "description": "extra Ultra exploration", "prompt": "Explore without target marker"},
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
assert extra_grade["trace_grade"]["failure_codes"] == ["extra_exploration_call"]

codex_trace = treatment.parent / "codex-collab-trace.jsonl"
codex_trace.write_text("\n".join(json.dumps(event) for event in (
    {"type": "thread.started", "thread_id": "fresh-primary"},
    {"type": "item.completed", "item": {
        "id": "collab-ok", "type": "collab_tool_call", "tool": "spawn_agent",
        "prompt": "Explore repository [target-native:architecture-candidate-discovery]",
        "agents_states": {"agent-1": {"status": "completed"}}, "status": "completed",
    }},
    {"type": "item.completed", "item": {
        "id": "collab-child-failed", "type": "collab_tool_call", "tool": "spawn_agent",
        "prompt": "Explore repository [target-native:architecture-candidate-discovery]",
        "agents_states": {"agent-2": {"status": "failed"}}, "status": "completed",
    }},
    {"type": "item.completed", "item": {
        "id": "collab-review", "type": "collab_tool_call", "tool": "spawn_agent",
        "prompt": "Review and summarize the target-native exploration and candidate-discovery report",
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
assert codex_grade["trace"]["agent_calls"][0]["prompt"].endswith("[target-native:architecture-candidate-discovery]")
review_call = next(call for call in codex_grade["trace"]["agent_calls"] if call["id"] == "collab-review")
assert review_call["role"] is None and review_call["stage_markers"] == []
assert codex_grade["trace"]["delegated_model_observation"] == "unknown/unavailable"
assert codex_grade["repository_grade"]["passed"] is True
assert codex_grade["profile_grade"]["passed"] is True

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
assert tracker_grade["repository_grade"]["failure_codes"] == ["tracker_status"]
assert tracker_grade["profile_grade"]["passed"] is True
tracker.write_text(tracker.read_text(encoding="utf-8").replace("Status: done", "Status: ready-for-agent"), encoding="utf-8")

artifact = ablation / "artifacts/architecture-report.md"
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text("Order Router route_order ADR-0001\n", encoding="utf-8")
ablation_events = events + [{
    "name": "ultra-code-explore",
    "owner": "ultra",
    "goal": "second-candidate-discovery",
    "evidence": "completed Agent call agent-2",
}]
(ablation / "artifacts/stage-evidence.json").write_text(
    json.dumps({"events": ablation_events}, indent=2) + "\n"
)

# A ledger-only declaration is descriptive evidence, not proof of an attributable
# duplicate. With one real Explore call the ablation remains profile-correct.
ledger_only_result = subprocess.run(
    [sys.executable, str(grader), str(ablation), "--trace", str(valid_trace), "--json"],
    capture_output=True,
    text=True,
)
assert ledger_only_result.returncode == 0, ledger_only_result.stdout + ledger_only_result.stderr

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
