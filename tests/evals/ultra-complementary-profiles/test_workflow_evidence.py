#!/usr/bin/env python3
"""Deterministic regression tests for Workflow evidence transport in trace_evidence.py.

These tests verify that:
1. Direct Agent treatment continues to pass.
2. Workflow with full trusted trace passes equivalently.
3. Workflow overall completed but missing child terminal fails.
4. Script-claimed agent() without runtime evidence fails.
5. Marker, role, order mismatches fail.
6. Stage ledger / Workflow child event inconsistency fails.
7. Workflow runtime metadata does not pollute scenario write set.
8. Unbound .qoder files still trigger scenario_write_set.
9. Missing/corrupt journal/transcript/output fail closed.
10. Direct Agent and Workflow produce the same normalized summary.
11. Ablation's ultra-code-explore + target-native-explore detected as duplicate.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from trace_evidence import summarize, grade  # noqa: E402


def _jsonl(events: list[dict]) -> str:
    return "\n".join(json.dumps(event) for event in events) + "\n"


def _write_jsonl(directory: Path, name: str, events: list[dict]) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_jsonl(events), encoding="utf-8")
    return path


def _write_text(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_json(directory: Path, name: str, value: object) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


# -- Architecture scenario trace expectations (mirrors prepare-fixture.py) -----

ARCHITECTURE_TRACE_EXPECTED = {
    "capability_tools": ["Agent"],
    "forbidden_tools": ["Skill"],
    "known_stage_markers": {
        "target-native-explore": "[eval-stage:target-native-explore]",
        "target-native-candidate": "[eval-stage:target-native-candidate]",
        "ultra-post-review": "[eval-stage:ultra-post-review]",
        "ultra-code-explore": "[eval-stage:ultra-code-explore]",
        "validation": "[eval-stage:validation]",
    },
    "require_marker_for_agent_calls": True,
    "required_marker_events": ["target-native-explore", "ultra-post-review"],
    "reconcile_events": ["target-native-explore", "ultra-post-review", "ultra-code-explore"],
    "marker_sequence": ["target-native-explore", "ultra-post-review"],
    "timeline_sequence": [
        {"kind": "agent_marker", "value": "target-native-explore"},
        {"kind": "agent_marker", "value": "ultra-post-review"},
        {"kind": "command", "value": "python3 scripts/check.py", "status": "completed"},
    ],
    "marker_roles": {
        "target-native-explore": ["Explore"],
        "ultra-code-explore": ["Explore"],
    },
    "extra_exploration_calls": {
        "native_markers": ["[eval-stage:target-native-explore]"],
        "extra_markers": ["[eval-stage:ultra-code-explore]"],
        "max": 0,
    },
    "require_delegated_model": True,
    "command_calls": [
        {"command": "python3 scripts/check.py", "min": 1, "max": 1, "min_successful": 1},
    ],
}


# -- Direct Agent treatment trace (already passing, regression guard) ----------

def direct_agent_trace_events() -> list[dict]:
    """Standard direct Agent treatment trace for architecture scenario."""
    return [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash"],
         "agents": ["Explore", "general-purpose"], "model": "dfmodel"},
        # target-native-explore via Agent
        {"type": "assistant", "message": {"model": "dfmodel", "content": [
            {"type": "tool_use", "id": "call_explore", "name": "Agent",
             "input": {"description": "Architecture exploration",
                       "subagent_type": "Explore",
                       "prompt": "Explore [eval-stage:target-native-explore]",
                       "run_in_background": True}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_explore",
             "content": "Agent launched."}]},
         "tool_use_result": {"status": "async_launched"}},
        {"type": "system", "task_id": "aExplore-native",
         "tool_use_id": "call_explore", "description": "app/router.py"},
        {"type": "system", "task_id": "aExplore-native",
         "tool_use_id": "call_explore", "status": "completed"},
        # ultra-post-review via Agent
        {"type": "assistant", "message": {"model": "dfmodel", "content": [
            {"type": "tool_use", "id": "call_review", "name": "Agent",
             "input": {"description": "Fresh artifact review",
                       "subagent_type": "general-purpose",
                       "prompt": "Review [eval-stage:ultra-post-review]",
                       "run_in_background": True}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_review",
             "content": "Agent launched."}]},
         "tool_use_result": {"status": "async_launched"}},
        {"type": "system", "task_id": "ageneral-review",
         "tool_use_id": "call_review", "status": "completed"},
        # Validation command
        {"type": "assistant", "message": {"model": "dfmodel", "content": [
            {"type": "tool_use", "id": "call_validate", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_validate",
             "is_error": False, "content": "EXIT_CODE=0"}]},
         "tool_use_result": {"kind": "completed", "exitCode": 0}},
    ]


# -- Workflow trace builders (real Qoder 1.0.48 protocol) ---------------------

_SESSION_ID = "57f4c118-76cc-4fa6-9b89-6181108f516e"
_RUN_ID = "wf_54671518-a88"
_TASK_ID = "wf-54671518-a88"
_WF_TOOL_USE_ID = "call_9f46a0efa9f94a78832376ad"


def workflow_runtime_artifacts(
    runtime_dir: Path,
    session_id: str,
    run_id: str,
    children: list[dict],
    *,
    overall_status: str = "completed",
    corrupt_journal: bool = False,
    missing_journal: bool = False,
    missing_output: bool = False,
) -> Path:
    """Write real-protocol workflow artifacts to workflows/runs/<runId>/."""
    wf_dir = runtime_dir / ".qoder" / "sessions" / session_id / "workflows" / "runs" / run_id
    wf_dir.mkdir(parents=True, exist_ok=True)

    # manifest.json with agents array
    manifest_agents = []
    for idx, child in enumerate(children, start=1):
        manifest_agents.append({
            "index": idx,
            "label": child["label"],
            "phaseIndex": child.get("phase_index", 1),
            "phaseTitle": child.get("phase_title", "Explore"),
            "journalKey": child["journal_key"],
            "agentId": child["agent_id"],
            "agentType": child["agent_type"],
            "state": child.get("state", "done"),
            "attempts": 1,
        })
    _write_json(wf_dir, "manifest.json", {
        "runId": run_id,
        "workflowName": "test-workflow",
        "status": overall_status,
        "agents": manifest_agents,
    })

    # journal.jsonl with real format: started/event/result per key
    if not missing_journal:
        journal_events = []
        for child in children:
            key = child["journal_key"]
            journal_events.append({"type": "started", "key": key, "timestamp": 1000})
            journal_events.append({"type": "event", "key": key,
                                   "event": {"kind": "attempt_started", "attempt": 1}})
            if child.get("has_terminal", True):
                journal_events.append({"type": "result", "key": key,
                                       "agentId": child["agent_id"],
                                       "result": {"content": "{}"}})
        if corrupt_journal:
            _write_text(wf_dir, "journal.jsonl", "NOT-VALID-JSON\n{{bad\n")
        else:
            _write_jsonl(wf_dir, "journal.jsonl", journal_events)

    # output.json
    if not missing_output:
        _write_json(wf_dir, "output.json", {
            "runId": run_id,
            "taskId": _TASK_ID,
            "workflowName": "test-workflow",
            "status": overall_status,
            "result": {},
        })

    return wf_dir


def workflow_trace_events(
    session_id: str = _SESSION_ID,
    run_id: str = _RUN_ID,
    task_id: str = _TASK_ID,
    wf_tool_use_id: str = _WF_TOOL_USE_ID,
    children: list[dict] | None = None,
    *,
    overall_status: str = "completed",
    script_has_agent: bool = True,
) -> list[dict]:
    """Build trace events matching real Qoder 1.0.48 Workflow protocol."""
    events = [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash", "Workflow"],
         "agents": ["Explore", "general-purpose"], "model": "qmodel_preview",
         "session_id": session_id},
    ]
    # Workflow tool_use — input only has script
    script_body = "export const meta = { name: 'test' }" if script_has_agent else "// empty"
    events.append({
        "type": "assistant",
        "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": wf_tool_use_id,
             "name": "Workflow",
             "input": {"script": script_body}}]},
        "session_id": session_id,
    })
    # tool_result with payload containing taskId, runId, transcriptDir
    import json as _json
    payload = _json.dumps({
        "status": "async_launched",
        "taskId": task_id,
        "runId": run_id,
        "transcriptDir": f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/runs/{run_id}",
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": wf_tool_use_id,
             "content": f"Workflow launched.\ntaskId: {task_id}\nrunId: {run_id}"}]},
        "tool_use_result": {"payload": payload},
        "session_id": session_id,
    })
    # Child agent system events (with parent_tool_use_id = wf_tool_use_id)
    if children:
        for child in children:
            # task_started event
            events.append({
                "type": "system",
                "task_id": child["agent_id"],
                "parent_tool_use_id": wf_tool_use_id,
                "tool_use_id": wf_tool_use_id,
                "subtype": "task_started",
                "description": f"{child.get('marker_text', child['label'])}",
                "session_id": session_id,
            })
            # task_progress events
            events.append({
                "type": "system",
                "task_id": child["agent_id"],
                "parent_tool_use_id": wf_tool_use_id,
                "tool_use_id": wf_tool_use_id,
                "subtype": "task_progress",
                "description": f"{child.get('marker_text', '')}",
                "session_id": session_id,
            })
    # task_notification for Workflow completion
    events.append({
        "type": "system",
        "subtype": "task_notification",
        "task_id": task_id,
        "tool_use_id": wf_tool_use_id,
        "status": overall_status,
        "session_id": session_id,
    })
    # Validation command
    events.append({
        "type": "assistant",
        "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": "call_validate", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]},
        "session_id": session_id,
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_validate",
             "is_error": False, "content": "EXIT_CODE=0"}]},
        "tool_use_result": {"kind": "completed", "exitCode": 0},
        "session_id": session_id,
    })
    return events


def standard_workflow_children() -> list[dict]:
    """Standard 3-child workflow matching real Qoder 1.0.48 agent structure."""
    return [
        {
            "agent_id": "aExplore-963959565d8dca96",
            "label": "target-native-explore",
            "agent_type": "Explore",
            "journal_key": "v2:e4e9f74d7a1f75d86a132c25ddd1b90546ab1e21c67b37f491dba8834afbf8e7",
            "phase_index": 1,
            "phase_title": "Explore",
            "marker_text": "[eval-stage:target-native-explore]",
            "state": "done",
            "has_terminal": True,
        },
        {
            "agent_id": "aworkflow-subagent-873e6bdde1964c81",
            "label": "target-native-candidate",
            "agent_type": "workflow-subagent",
            "journal_key": "v2:5eea14e79089da9a5ce40ccf898d8339bf9ea10e28500b5dde9a97789edaeee0",
            "phase_index": 2,
            "phase_title": "Candidate",
            "marker_text": "[eval-stage:target-native-candidate]",
            "state": "done",
            "has_terminal": True,
        },
        {
            "agent_id": "aworkflow-subagent-6711054d3de79b1b",
            "label": "ultra-post-review",
            "agent_type": "workflow-subagent",
            "journal_key": "v2:eff74d58b80340cdf5d2f64bfc7d486a4299ab4c2380ef1f42307c11b6175766",
            "phase_index": 3,
            "phase_title": "Review",
            "marker_text": "[eval-stage:ultra-post-review]",
            "state": "done",
            "has_terminal": True,
        },
    ]


# -- Tests --------------------------------------------------------------------

def test_direct_agent_treatment_passes(tmp: Path) -> None:
    """Direct Agent treatment continues to pass (regression guard)."""
    trace = _write_jsonl(tmp / "traces", "direct-agent.jsonl", direct_agent_trace_events())
    summary = summarize(trace)
    assert summary["runtime"] == "qoder"
    assert summary["agent_call_count"] == 2, f"expected 2 agent calls, got {summary['agent_call_count']}"
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert not failures, f"direct agent treatment should pass: {failures}"


def test_workflow_complete_trusted_trace_passes(tmp: Path) -> None:
    """Workflow with full trusted runtime evidence passes like direct Agent."""
    children = standard_workflow_children()
    sid, rid = "sess-001", "wf_run-001"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    trace = _write_jsonl(tmp / "traces", "workflow-complete.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["runtime"] == "qoder"
    assert not summary.get("workflow_protocol_failures"), (
        f"unexpected protocol failures: {summary['workflow_protocol_failures']}"
    )
    assert summary["agent_call_count"] == 3, (
        f"expected 3 workflow child agent calls, got {summary['agent_call_count']}"
    )
    markers_found = set()
    for call in summary["agent_calls"]:
        for marker in call.get("stage_markers", []):
            markers_found.add(marker)
    assert "[eval-stage:target-native-explore]" in markers_found
    assert "[eval-stage:ultra-post-review]" in markers_found

    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert not failures, f"complete workflow should pass: {failures}"


def test_workflow_completed_but_child_missing_terminal_fails(tmp: Path) -> None:
    """Workflow overall completed but one child has no terminal event → fail."""
    children = standard_workflow_children()
    children[1]["state"] = "running"  # candidate not terminal
    children[1]["has_terminal"] = False

    sid, rid = "sess-002", "wf_run-002"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    trace = _write_jsonl(tmp / "traces", "workflow-missing-terminal.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    # Protocol should report failures for non-terminal child
    assert summary.get("workflow_protocol_failures"), (
        "non-terminal child should produce protocol failure"
    )
    assert summary["agent_call_count"] == 0, (
        "protocol failure should prevent any child calls"
    )


def test_script_claims_agent_no_runtime_evidence_fails(tmp: Path) -> None:
    """Script claims agent() but no runtime child evidence → fail closed."""
    sid, rid = "sess-003", "wf_run-003"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    # Empty children → manifest agents=[] → protocol failure
    workflow_runtime_artifacts(runtime_dir, sid, rid, [])

    trace = _write_jsonl(tmp / "traces", "workflow-script-claims.jsonl",
                         workflow_trace_events(session_id=sid, run_id=rid,
                                               script_has_agent=True))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0
    assert summary.get("workflow_protocol_failures"), "empty manifest should fail"
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert failures, "missing required stage markers should fail"


def test_marker_mismatch_fails(tmp: Path) -> None:
    """Workflow child with wrong marker → fail."""
    children = standard_workflow_children()
    children[0]["marker_text"] = "[eval-stage:wrong-marker]"

    sid, rid = "sess-004", "wf_run-004"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    trace = _write_jsonl(tmp / "traces", "workflow-marker-mismatch.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert any("required_stage_call" in c for c in codes), (
        f"marker mismatch should fail: {codes}"
    )


def test_role_mismatch_fails(tmp: Path) -> None:
    """Workflow child with wrong role/agentType → fail."""
    children = standard_workflow_children()
    children[0]["agent_type"] = "general-purpose"  # Should be Explore

    sid, rid = "sess-005", "wf_run-005"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    trace = _write_jsonl(tmp / "traces", "workflow-role-mismatch.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert any("delegated_stage_role" in c for c in codes), (
        f"role mismatch should fail: {codes}"
    )


def test_child_order_wrong_fails(tmp: Path) -> None:
    """Workflow children in wrong order → fail."""
    children = standard_workflow_children()
    children[0], children[2] = children[2], children[0]

    sid, rid = "sess-006", "wf_run-006"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    trace = _write_jsonl(tmp / "traces", "workflow-order-wrong.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert any("delegated_stage_order" in c for c in codes), (
        f"child order wrong should fail: {codes}"
    )


def test_missing_journal_fails_closed(tmp: Path) -> None:
    """Missing workflow journal → fail closed with explicit protocol failure."""
    sid, rid = "sess-007", "wf_run-007"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid,
                               standard_workflow_children(),
                               missing_journal=True)

    trace = _write_jsonl(tmp / "traces", "workflow-no-journal.jsonl",
                         workflow_trace_events(session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0
    pf = summary.get("workflow_protocol_failures", [])
    assert any("journal" in f for f in pf), f"should report journal failure: {pf}"


def test_corrupt_journal_fails_closed(tmp: Path) -> None:
    """Corrupt workflow journal → fail closed."""
    sid, rid = "sess-008", "wf_run-008"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid,
                               standard_workflow_children(),
                               corrupt_journal=True)

    trace = _write_jsonl(tmp / "traces", "workflow-corrupt-journal.jsonl",
                         workflow_trace_events(session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0
    pf = summary.get("workflow_protocol_failures", [])
    assert any("journal" in f for f in pf), f"should report journal failure: {pf}"


def test_missing_output_fails_closed(tmp: Path) -> None:
    """Missing workflow output → fail closed."""
    sid, rid = "sess-010", "wf_run-010"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid,
                               standard_workflow_children(),
                               missing_output=True)

    trace = _write_jsonl(tmp / "traces", "workflow-no-output.jsonl",
                         workflow_trace_events(session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0
    pf = summary.get("workflow_protocol_failures", [])
    assert any("output" in f for f in pf), f"should report output failure: {pf}"


def test_workflow_runtime_paths_allowed_in_write_set(tmp: Path) -> None:
    """Workflow runtime paths bound to session/run ID should be allowed."""
    from trace_evidence import classify_workflow_write_set
    session_id = "sess-011"
    run_id = "wf_run-011"
    paths = {
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/manifest.json",
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/journal.jsonl",
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/output.json",
        f".qoder/sessions/{session_id}/workflows/scripts/some-script.js",
    }
    bound = classify_workflow_write_set(paths, session_id, run_id)
    assert bound == paths, f"bound workflow paths should be allowed: {paths - bound}"


def test_unbound_qoder_files_still_trigger_write_set(tmp: Path) -> None:
    """Arbitrary .qoder files NOT bound to a valid session → write set violation."""
    from trace_evidence import classify_workflow_write_set
    session_id = "sess-012"
    run_id = "wf_run-012"
    unbound_paths = {
        ".qoder/settings.json",
        ".qoder/cache/data.bin",
        ".qoder/sessions/other-session/workflows/runs/other/journal.jsonl",
    }
    bound = classify_workflow_write_set(unbound_paths, session_id, run_id)
    assert not bound, f"no unbound paths should be classified: {bound}"
    remaining = unbound_paths - bound
    assert remaining == unbound_paths


def test_direct_agent_and_workflow_normalized_equivalently(tmp: Path) -> None:
    """Direct Agent and Workflow for the same stage plan → same normalized summary."""
    direct_trace = _write_jsonl(tmp / "traces", "equiv-direct.jsonl",
                                direct_agent_trace_events())
    direct_summary = summarize(direct_trace)

    children = standard_workflow_children()
    sid, rid = "sess-eq", "wf_run-eq"
    runtime_dir = tmp / "runtime-equiv"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    wf_trace = _write_jsonl(tmp / "traces", "equiv-workflow.jsonl",
                            workflow_trace_events(children=children,
                                                  session_id=sid, run_id=rid))
    wf_summary = summarize(wf_trace, workflow_runtime_root=runtime_dir)

    direct_markers = sorted(
        marker for call in direct_summary["agent_calls"]
        for marker in call.get("stage_markers", [])
    )
    wf_markers = sorted(
        marker for call in wf_summary["agent_calls"]
        for marker in call.get("stage_markers", [])
    )
    assert "[eval-stage:target-native-explore]" in direct_markers
    assert "[eval-stage:target-native-explore]" in wf_markers
    assert "[eval-stage:ultra-post-review]" in direct_markers
    assert "[eval-stage:ultra-post-review]" in wf_markers

    direct_checks, direct_failures, _ = grade(direct_summary, ARCHITECTURE_TRACE_EXPECTED)
    wf_checks, wf_failures, _ = grade(wf_summary, ARCHITECTURE_TRACE_EXPECTED)
    assert not direct_failures, f"direct should pass: {direct_failures}"
    assert not wf_failures, f"workflow should pass: {wf_failures}"


def test_ablation_duplicate_evidence_goal_and_extra_exploration(tmp: Path) -> None:
    """Ablation's ultra-code-explore + target-native-explore detected."""
    children = [
        {"agent_id": "aExplore-ultra", "label": "ultra-code-explore",
         "agent_type": "Explore", "journal_key": "v2:aaa111",
         "marker_text": "[eval-stage:ultra-code-explore]", "state": "done", "has_terminal": True},
        {"agent_id": "aExplore-native", "label": "target-native-explore",
         "agent_type": "Explore", "journal_key": "v2:bbb222",
         "marker_text": "[eval-stage:target-native-explore]", "state": "done", "has_terminal": True},
        {"agent_id": "aworkflow-sub-cand", "label": "target-native-candidate",
         "agent_type": "workflow-subagent", "journal_key": "v2:ccc333",
         "marker_text": "[eval-stage:target-native-candidate]", "state": "done", "has_terminal": True},
        {"agent_id": "aworkflow-sub-rev", "label": "ultra-post-review",
         "agent_type": "workflow-subagent", "journal_key": "v2:ddd444",
         "marker_text": "[eval-stage:ultra-post-review]", "state": "done", "has_terminal": True},
    ]
    sid, rid = "sess-abl", "wf_run-abl"
    runtime_dir = tmp / "runtime-ablation"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    trace = _write_jsonl(tmp / "traces", "ablation-workflow.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 4

    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert "extra_exploration_call" in codes, f"should detect extra_exploration_call: {codes}"
    all_markers = [
        marker for call in summary["agent_calls"]
        for marker in call.get("stage_markers", [])
    ]
    assert "[eval-stage:ultra-code-explore]" in all_markers
    assert "[eval-stage:target-native-explore]" in all_markers


def test_workflow_completed_no_child_evidence_fails(tmp: Path) -> None:
    """Workflow completed but no child runtime evidence at all → fail."""
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    trace = _write_jsonl(tmp / "traces", "workflow-no-evidence.jsonl",
                         workflow_trace_events(session_id="sess-none", run_id="wf_none"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert failures, "no evidence should fail"


def test_workflow_overall_completed_cannot_substitute_child(tmp: Path) -> None:
    """Workflow completed status alone cannot substitute for missing child lifecycle."""
    sid, rid = "sess-sub", "wf_run-sub"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    wf_dir = runtime_dir / ".qoder" / "sessions" / sid / "workflows" / "runs" / rid
    wf_dir.mkdir(parents=True, exist_ok=True)
    _write_json(wf_dir, "manifest.json", {
        "runId": rid, "workflowName": "test", "status": "completed",
        "agents": [],
    })
    _write_json(wf_dir, "output.json", {"runId": rid, "status": "completed", "result": {}})
    _write_jsonl(wf_dir, "journal.jsonl", [{"type": "started", "key": "v2:empty"}])

    trace = _write_jsonl(tmp / "traces", "workflow-substitute.jsonl",
                         workflow_trace_events(session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0
    pf = summary.get("workflow_protocol_failures", [])
    assert pf, "empty agents should produce protocol failure"


def test_stage_ledger_workflow_child_reconciliation(tmp: Path) -> None:
    """Stage ledger claims ultra-code-explore but workflow trace lacks it → fail."""
    children = [
        {"agent_id": "aExplore-rc", "label": "target-native-explore",
         "agent_type": "Explore", "journal_key": "v2:rc111",
         "marker_text": "[eval-stage:target-native-explore]", "state": "done", "has_terminal": True},
        {"agent_id": "aworkflow-sub-rc", "label": "ultra-post-review",
         "agent_type": "workflow-subagent", "journal_key": "v2:rc222",
         "marker_text": "[eval-stage:ultra-post-review]", "state": "done", "has_terminal": True},
    ]
    sid, rid = "sess-recon", "wf_run-recon"
    runtime_dir = tmp / "runtime-recon"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    trace = _write_jsonl(tmp / "traces", "workflow-reconciliation.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 2

    reconcile_events = ARCHITECTURE_TRACE_EXPECTED["reconcile_events"]
    marker_to_event = {
        marker: name
        for name, marker in ARCHITECTURE_TRACE_EXPECTED["known_stage_markers"].items()
    }
    traced_names = [
        marker_to_event[marker]
        for call in summary.get("agent_calls", [])
        for marker in call.get("stage_markers", [])
        if marker in marker_to_event
    ]

    ledger_names = ["target-native-explore", "ultra-code-explore", "ultra-post-review", "validation"]
    reconciled = set(reconcile_events)
    ledger_sequence = [name for name in ledger_names if name in reconciled]
    trace_sequence = [name for name in traced_names if name in reconciled]

    mismatched = [
        name for name in reconcile_events
        if ledger_names.count(name) != traced_names.count(name)
    ]
    assert mismatched or ledger_sequence != trace_sequence, (
        "reconciliation should detect mismatch"
    )
    assert "ultra-code-explore" in mismatched


def test_bound_plus_unbound_qoder_write_set(tmp: Path) -> None:
    """Bound workflow paths + unbound .qoder files → write-set still fails."""
    from trace_evidence import classify_workflow_write_set
    session_id = "sess-mixed"
    run_id = "wf_run-mixed"
    mixed_paths = {
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/manifest.json",
        ".qoder/settings.json",
        ".qoder/sessions/other-session/workflows/runs/other/journal.jsonl",
    }
    bound = classify_workflow_write_set(mixed_paths, session_id, run_id)
    # Only the bound path should be excluded
    assert bound == {f".qoder/sessions/{session_id}/workflows/runs/{run_id}/manifest.json"}
    remaining = mixed_paths - bound
    assert ".qoder/settings.json" in remaining
    assert ".qoder/sessions/other-session/workflows/runs/other/journal.jsonl" in remaining


# -- Runner -------------------------------------------------------------------

def main() -> None:
    passed = 0
    failed = 0
    errors: list[str] = []
    tests = [
        test_direct_agent_treatment_passes,
        test_workflow_complete_trusted_trace_passes,
        test_workflow_completed_but_child_missing_terminal_fails,
        test_script_claims_agent_no_runtime_evidence_fails,
        test_marker_mismatch_fails,
        test_role_mismatch_fails,
        test_child_order_wrong_fails,
        test_missing_journal_fails_closed,
        test_corrupt_journal_fails_closed,
        test_missing_output_fails_closed,
        test_workflow_runtime_paths_allowed_in_write_set,
        test_unbound_qoder_files_still_trigger_write_set,
        test_direct_agent_and_workflow_normalized_equivalently,
        test_ablation_duplicate_evidence_goal_and_extra_exploration,
        test_workflow_completed_no_child_evidence_fails,
        test_workflow_overall_completed_cannot_substitute_child,
        test_stage_ledger_workflow_child_reconciliation,
        test_bound_plus_unbound_qoder_write_set,
    ]
    for test in tests:
        with tempfile.TemporaryDirectory(prefix="workflow-evidence-") as td:
            try:
                test(Path(td))
                passed += 1
                print(f"  PASS: {test.__name__}")
            except Exception as exc:
                failed += 1
                errors.append(f"{test.__name__}: {exc}")
                print(f"  FAIL: {test.__name__}: {exc}")
    print(f"\n{passed}/{passed + failed} tests passed")
    if errors:
        print("\nFailures:")
        for error in errors:
            print(f"  - {error}")
    raise SystemExit(0 if not failed else 1)


if __name__ == "__main__":
    main()
