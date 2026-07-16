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
spec = importlib.util.spec_from_file_location("complementary_prepare", prepare_path)
prepare = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prepare)
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
  --output "$TMP" --run-id fixture --scenario architecture-native-ownership \
  --treatment-ref working-tree --ablation-ref HEAD >/dev/null

python3 - "$REPO_ROOT" "$TMP" <<'PY'
import json
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
assert subprocess.run([sys.executable, str(grader), str(treatment)], capture_output=True).returncode != 0

artifact = treatment / "artifacts/architecture-report.md"
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text("Order Router route_order ADR-0001\nvalidation: python3 scripts/check.py\n")
events = [
    {"name": "target-native-explore", "owner": "target", "goal": "discover-candidates", "evidence": "app/router.py"},
    {"name": "target-native-candidate", "owner": "target", "goal": "produce-report", "evidence": "artifacts/architecture-report.md"},
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
)) + "\n")
assert subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(valid_trace)],
    capture_output=True,
).returncode == 0

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
assert subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(extra_trace)],
    capture_output=True,
).returncode != 0, "trace grader must reject an extra Ultra exploration call"

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
)) + "\n")
completed = subprocess.run(
    [sys.executable, str(grader), str(treatment), "--trace", str(codex_trace), "--json"],
    capture_output=True,
    text=True,
)
assert completed.returncode == 0, completed.stdout + completed.stderr
codex_grade = json.loads(completed.stdout)[0]
assert codex_grade["trace"]["agent_call_count"] == 1
assert codex_grade["trace"]["rejected_agent_call_count"] == 1
assert codex_grade["trace"]["attempted_agent_calls"][1]["runtime_status"] == "completed"
assert codex_grade["trace"]["attempted_agent_calls"][1]["agent_terminal_states"] == ["failed"]
assert codex_grade["trace"]["agent_calls"][0]["prompt"].endswith("[target-native:architecture-candidate-discovery]")
assert codex_grade["trace"]["delegated_model_observation"] == "unknown/unavailable"

artifact = ablation / "artifacts/architecture-report.md"
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text("Order Router route_order ADR-0001\nvalidation: python3 scripts/check.py\n")
events.insert(0, {"name": "ultra-code-explore", "owner": "ultra", "goal": "duplicate-discovery", "evidence": "app/router.py"})
(ablation / "artifacts/stage-evidence.json").write_text(json.dumps({"events": events}, indent=2) + "\n")
assert subprocess.run(
    [sys.executable, str(grader), str(ablation), "--trace", str(valid_trace)],
    capture_output=True,
).returncode != 0
PY

echo "ultra complementary profiles fixture passed"
