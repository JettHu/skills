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
import importlib.util
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
        # Real child model evidence (parent_tool_use_id matches tool_use_id)
        {"type": "assistant", "parent_tool_use_id": "call_explore",
         "message": {"model": "dfmodel-child", "content": []}},
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
        # Real child model evidence
        {"type": "assistant", "parent_tool_use_id": "call_review",
         "message": {"model": "dfmodel-child2", "content": []}},
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
    task_id: str = _TASK_ID,
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
            "transcriptPath": (
                f"/tmp/config/projects/fixture-project/{session_id}/subagents/"
                f"agent-{child['agent_id']}.jsonl"
            ),
        })
    _write_json(wf_dir, "manifest.json", {
        "runId": run_id,
        "workflowName": "test-workflow",
        "status": overall_status,
        "scriptPath": (
            f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/"
            f"scripts/test-workflow-{run_id}.js"
        ),
        "outputPath": (
            f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/"
            f"runs/{run_id}/output.json"
        ),
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
                                       "result": {
                                           "content": "{}",
                                           "transcriptPath": (
                                               f"/tmp/config/projects/fixture-project/"
                                               f"{session_id}/subagents/"
                                               f"agent-{child['agent_id']}.jsonl"
                                           ),
                                       }})
        if corrupt_journal:
            _write_text(wf_dir, "journal.jsonl", "NOT-VALID-JSON\n{{bad\n")
        else:
            _write_jsonl(wf_dir, "journal.jsonl", journal_events)

    # output.json
    if not missing_output:
        _write_json(wf_dir, "output.json", {
            "runId": run_id,
            "taskId": task_id,
            "workflowName": "test-workflow",
            "status": overall_status,
            "transcriptDir": (
                f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/runs/{run_id}"
            ),
            "scriptPath": (
                f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/"
                f"scripts/test-workflow-{run_id}.js"
            ),
            "result": {},
        })

    transcript_root = (
        runtime_dir / "config-projects" / "fixture-project" / session_id / "subagents"
    )
    transcript_root.mkdir(parents=True, exist_ok=True)
    for child in children:
        transcript_path = transcript_root / f"agent-{child['agent_id']}.jsonl"
        _write_jsonl(transcript_path.parent, transcript_path.name, [
            {
                "type": "user",
                "message": {"content": child.get("marker_text", child["label"])},
                "session_id": session_id,
            },
            {
                "type": "assistant",
                "message": {
                    "model": f"child-model-{child['agent_id'][:8]}",
                    "content": [],
                },
                "session_id": session_id,
            },
        ])

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
        "scriptPath": (
            f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/"
            f"scripts/test-workflow-{run_id}.js"
        ),
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
            # task_completed event (with delegated model evidence)
            events.append({
                "type": "assistant",
                "parent_tool_use_id": wf_tool_use_id,
                "task_id": child["agent_id"],
                "message": {"model": f"child-model-{child['agent_id'][:8]}", "content": []},
                "session_id": session_id,
            })
            events.append({
                "type": "system",
                "task_id": child["agent_id"],
                "parent_tool_use_id": wf_tool_use_id,
                "tool_use_id": wf_tool_use_id,
                "subtype": "task_completed",
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
        "output_file": (
            f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/"
            f"runs/{run_id}/output.json"
        ),
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
    """Workflow runtime paths under runs/<runId>/ should be allowed."""
    from trace_evidence import classify_workflow_write_set
    session_id = "sess-011"
    run_id = "wf_run-011"
    paths = {
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/manifest.json",
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/journal.jsonl",
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/output.json",
    }
    bound = classify_workflow_write_set(paths, session_id, run_id)
    assert bound == paths, f"bound run paths should be allowed: {paths - bound}"


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
    # Only the bound path should be excluded (must match run_id)
    assert bound == {f".qoder/sessions/{session_id}/workflows/runs/{run_id}/manifest.json"}
    remaining = mixed_paths - bound
    assert ".qoder/settings.json" in remaining
    assert ".qoder/sessions/other-session/workflows/runs/other/journal.jsonl" in remaining


# -- NEW red-first regression tests for Ticket 20 Workflow evidence gaps ------

def test_workflow_trace_no_runtime_root_fails(tmp: Path) -> None:
    """Workflow invocation detected but no --workflow-runtime-root → fail closed.

    When a trace contains Workflow tool_use events but the grader is not
    provided --workflow-runtime-root, the Workflow protocol failures MUST
    be explicit and cannot be silently skipped.
    """
    children = standard_workflow_children()
    sid, rid = "sess-nort", "wf_run-nort"
    # Do NOT create runtime artifacts directory
    trace = _write_jsonl(tmp / "traces", "workflow-no-runtime-root.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    # summarize WITHOUT workflow_runtime_root
    summary = summarize(trace)
    assert summary.get("workflow_sessions"), "should detect Workflow sessions"
    pf = summary.get("workflow_protocol_failures", [])
    assert pf, (
        f"Workflow trace without runtime root MUST produce protocol failures, "
        f"got: {pf}"
    )
    # The failures must prevent any agent calls from being created
    assert summary["agent_call_count"] == 0, (
        "no agent calls should be produced when Workflow evidence is missing"
    )


def test_workflow_failures_not_masked_by_direct_agent(tmp: Path) -> None:
    """Workflow protocol failures are NOT masked by direct Agent evidence.

    Even if the same trace has direct Agent calls that satisfy all stage
    markers, Workflow protocol failures (missing runtime evidence) must
    still cause an explicit grade failure.
    """
    sid, rid = "sess-masked", "wf_run-masked"
    # Build a trace that has BOTH Workflow AND direct Agent calls
    events = [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash", "Workflow"],
         "agents": ["Explore", "general-purpose"], "model": "qmodel_preview",
         "session_id": sid},
        # Direct Agent call (target-native-explore) — this would normally pass
        {"type": "assistant", "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": "call_direct_explore", "name": "Agent",
             "input": {"description": "Direct explore",
                       "subagent_type": "Explore",
                       "prompt": "Explore [eval-stage:target-native-explore]",
                       "run_in_background": True}}]},
         "session_id": sid},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_direct_explore",
             "content": "Agent launched."}]},
         "tool_use_result": {"status": "async_launched"},
         "session_id": sid},
        {"type": "system", "task_id": "aDirectExplore",
         "tool_use_id": "call_direct_explore",
         "description": "[eval-stage:target-native-explore] app/router.py",
         "session_id": sid},
        {"type": "system", "task_id": "aDirectExplore",
         "tool_use_id": "call_direct_explore", "status": "completed",
         "session_id": sid},
        # Direct Agent call (ultra-post-review) — this would normally pass
        {"type": "assistant", "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": "call_direct_review", "name": "Agent",
             "input": {"description": "Direct review",
                       "subagent_type": "general-purpose",
                       "prompt": "Review [eval-stage:ultra-post-review]",
                       "run_in_background": True}}]},
         "session_id": sid},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_direct_review",
             "content": "Agent launched."}]},
         "tool_use_result": {"status": "async_launched"},
         "session_id": sid},
        {"type": "system", "task_id": "aDirectReview",
         "tool_use_id": "call_direct_review", "status": "completed",
         "session_id": sid},
    ]
    # Add Workflow invocation (tool_use + tool_result) AFTER direct Agent calls
    import json as _json
    wf_tool_use_id = "call_masked_wf"
    task_id = "wf-masked-task"
    events.append({
        "type": "assistant",
        "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": wf_tool_use_id,
             "name": "Workflow",
             "input": {"script": "export const meta = { name: 'masked' }"}}]},
        "session_id": sid,
    })
    payload = _json.dumps({
        "status": "async_launched",
        "taskId": task_id,
        "runId": rid,
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": wf_tool_use_id,
             "content": f"Workflow launched.\ntaskId: {task_id}\nrunId: {rid}"}]},
        "tool_use_result": {"payload": payload},
        "session_id": sid,
    })
    events.append({
        "type": "system", "subtype": "task_notification",
        "task_id": task_id, "tool_use_id": wf_tool_use_id,
        "status": "completed", "session_id": sid,
    })
    # Validation command
    events.append({
        "type": "assistant",
        "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": "call_validate_masked", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]},
        "session_id": sid,
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_validate_masked",
             "is_error": False, "content": "EXIT_CODE=0"}]},
        "tool_use_result": {"kind": "completed", "exitCode": 0},
        "session_id": sid,
    })

    trace = _write_jsonl(tmp / "traces", "workflow-masked.jsonl", events)
    # NO --workflow-runtime-root!
    summary = summarize(trace)
    # Direct Agent calls should exist
    assert summary["agent_call_count"] >= 2, (
        f"direct agent calls should be detected; got {summary['agent_call_count']}"
    )
    # But Workflow protocol failures MUST exist
    pf = summary.get("workflow_protocol_failures", [])
    assert pf, (
        "Workflow protocol failures MUST NOT be masked by direct Agent calls"
    )
    # Grade must fail because of workflow_protocol_failures
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert "workflow_protocol_failure" in codes, (
        f"grade must report workflow_protocol_failure even with direct Agent passing; "
        f"got codes: {codes}"
    )


def test_workflow_task_progress_not_terminal(tmp: Path) -> None:
    """task_progress subtype must not be treated as terminal lifecycle.

    Only task_completed constitutes a terminal event.  A child with only
    task_progress (no task_completed) must produce a protocol failure.
    """
    children = standard_workflow_children()
    # Remove the child that has both started + progress → only progress remains for it
    sid, rid = "sess-prog", "wf_run-prog"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    # Build trace where all children have task_started but only task_progress, no task_completed
    events = [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash", "Workflow"],
         "agents": ["Explore", "general-purpose"], "model": "qmodel_preview",
         "session_id": sid},
        {"type": "assistant",
         "message": {"model": "qmodel_preview", "content": [
             {"type": "tool_use", "id": "call_prog_wf",
              "name": "Workflow",
              "input": {"script": "export const meta = { name: 'prog' }"}}]},
         "session_id": sid},
    ]
    import json as _json
    payload = _json.dumps({
        "status": "async_launched", "taskId": "wf-prog-task", "runId": rid,
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_prog_wf",
             "content": f"Workflow launched.\ntaskId: wf-prog-task\nrunId: {rid}"}]},
        "tool_use_result": {"payload": payload},
        "session_id": sid,
    })
    # Children: only task_started and task_progress, NO task_completed
    for child in children:
        events.append({
            "type": "system", "task_id": child["agent_id"],
            "parent_tool_use_id": "call_prog_wf",
            "tool_use_id": "call_prog_wf",
            "subtype": "task_started",
            "description": child.get("marker_text", child["label"]),
            "session_id": sid,
        })
        events.append({
            "type": "system", "task_id": child["agent_id"],
            "parent_tool_use_id": "call_prog_wf",
            "tool_use_id": "call_prog_wf",
            "subtype": "task_progress",
            "description": child.get("marker_text", ""),
            "session_id": sid,
        })
    # Workflow completed notification
    events.append({
        "type": "system", "subtype": "task_notification",
        "task_id": "wf-prog-task", "tool_use_id": "call_prog_wf",
        "status": "completed", "session_id": sid,
    })
    # Validation
    events.append({
        "type": "assistant",
        "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": "call_val_prog", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]},
        "session_id": sid,
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_val_prog",
             "is_error": False, "content": "EXIT_CODE=0"}]},
        "tool_use_result": {"kind": "completed", "exitCode": 0},
        "session_id": sid,
    })

    trace = _write_jsonl(tmp / "traces", "workflow-progress-only.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    # task_progress must not count as terminal — child should fail
    pf = summary.get("workflow_protocol_failures", [])
    assert pf, (
        f"task_progress-only children must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0, (
        "no calls should be produced when children lack task_completed"
    )


def test_workflow_child_started_after_terminal_fails(tmp: Path) -> None:
    """Child with started_index after terminal_index → protocol failure.

    The started event MUST occur before the terminal event in the trace.
    Reversed order indicates corrupted or tampered evidence.
    """
    children = standard_workflow_children()
    sid, rid = "sess-rev", "wf_run-rev"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children)

    # Build trace where task_completed appears BEFORE task_started for children
    events = [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash", "Workflow"],
         "agents": ["Explore", "general-purpose"], "model": "qmodel_preview",
         "session_id": sid},
        {"type": "assistant",
         "message": {"model": "qmodel_preview", "content": [
             {"type": "tool_use", "id": "call_rev_wf",
              "name": "Workflow",
              "input": {"script": "export const meta = { name: 'rev' }"}}]},
         "session_id": sid},
    ]
    import json as _json
    payload = _json.dumps({
        "status": "async_launched", "taskId": "wf-rev-task", "runId": rid,
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_rev_wf",
             "content": f"Workflow launched.\ntaskId: wf-rev-task\nrunId: {rid}"}]},
        "tool_use_result": {"payload": payload},
        "session_id": sid,
    })
    # Deliberately emit task_completed BEFORE task_started (reversed)
    for child in children:
        events.append({
            "type": "system", "task_id": child["agent_id"],
            "parent_tool_use_id": "call_rev_wf",
            "tool_use_id": "call_rev_wf",
            "subtype": "task_completed",
            "description": child.get("marker_text", child["label"]),
            "session_id": sid,
        })
        events.append({
            "type": "system", "task_id": child["agent_id"],
            "parent_tool_use_id": "call_rev_wf",
            "tool_use_id": "call_rev_wf",
            "subtype": "task_started",
            "description": child.get("marker_text", child["label"]),
            "session_id": sid,
        })
    events.append({
        "type": "system", "subtype": "task_notification",
        "task_id": "wf-rev-task", "tool_use_id": "call_rev_wf",
        "status": "completed", "session_id": sid,
    })
    events.append({
        "type": "assistant",
        "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": "call_val_rev", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]},
        "session_id": sid,
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_val_rev",
             "is_error": False, "content": "EXIT_CODE=0"}]},
        "tool_use_result": {"kind": "completed", "exitCode": 0},
        "session_id": sid,
    })

    trace = _write_jsonl(tmp / "traces", "workflow-reversed.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert pf, (
        f"reversed started/terminal must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_workflow_child_failed_state_fails(tmp: Path) -> None:
    """Child with state 'failed' in manifest → protocol failure."""
    children = standard_workflow_children()
    children[0]["state"] = "failed"  # Failed child

    sid, rid = "sess-fl", "wf_run-fl"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children,
                               overall_status="failed")

    trace = _write_jsonl(tmp / "traces", "workflow-failed-child.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid,
                                               overall_status="failed"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert pf, (
        f"failed child state must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_workflow_child_cancelled_state_fails(tmp: Path) -> None:
    """Child with state 'cancelled' in manifest → protocol failure."""
    children = standard_workflow_children()
    children[1]["state"] = "cancelled"

    sid, rid = "sess-cx", "wf_run-cx"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children,
                               overall_status="cancelled")

    trace = _write_jsonl(tmp / "traces", "workflow-cancelled-child.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid,
                                               overall_status="cancelled"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert pf, (
        f"cancelled child state must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_background_task_id_not_model_proof(tmp: Path) -> None:
    """background_task_id alone must not satisfy require_delegated_model.

    Real delegated model evidence (delegated_models populated from child
    events' message.model) is required.  A background_task_id without
    delegated_models must fail require_delegated_model.
    """
    children = standard_workflow_children()
    sid, rid = "sess-bgt", "wf_run-bgt"
    task_id = "wf-bgt-task"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, sid, rid, children, task_id=task_id)

    # Build trace where children have system events but NO model in message
    # (background_task_id gets set but delegated_models stays empty)
    events = [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash", "Workflow"],
         "agents": ["Explore", "general-purpose"], "model": "qmodel_preview",
         "session_id": sid},
        {"type": "assistant",
         "message": {"model": "qmodel_preview", "content": [
             {"type": "tool_use", "id": "call_bgt_wf",
              "name": "Workflow",
              "input": {"script": "export const meta = { name: 'bgt' }"}}]},
         "session_id": sid},
    ]
    import json as _json
    payload = _json.dumps({
        "status": "async_launched", "taskId": task_id, "runId": rid,
        "transcriptDir": f"/tmp/workspace/.qoder/sessions/{sid}/workflows/runs/{rid}",
        "scriptPath": (
            f"/tmp/workspace/.qoder/sessions/{sid}/workflows/scripts/"
            f"test-workflow-{rid}.js"
        ),
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_bgt_wf",
             "content": f"Workflow launched.\ntaskId: {task_id}\nrunId: {rid}"}]},
        "tool_use_result": {"payload": payload},
        "session_id": sid,
    })
    # Child system events WITHOUT model in message
    for child in children:
        events.append({
            "type": "system", "task_id": child["agent_id"],
            "parent_tool_use_id": "call_bgt_wf",
            "tool_use_id": "call_bgt_wf",
            "subtype": "task_started",
            "description": child.get("marker_text", child["label"]),
            "session_id": sid,
        })
        events.append({
            "type": "system", "task_id": child["agent_id"],
            "parent_tool_use_id": "call_bgt_wf",
            "tool_use_id": "call_bgt_wf",
            "subtype": "task_completed",
            "description": child.get("marker_text", child["label"]),
            "session_id": sid,
            # NOTE: no "message" key with model info
        })
    events.append({
        "type": "system", "subtype": "task_notification",
        "task_id": task_id, "tool_use_id": "call_bgt_wf",
        "status": "completed",
        "output_file": (
            f"/tmp/workspace/.qoder/sessions/{sid}/workflows/runs/{rid}/output.json"
        ),
        "session_id": sid,
    })
    events.append({
        "type": "assistant",
        "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": "call_val_bgt", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]},
        "session_id": sid,
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_val_bgt",
             "is_error": False, "content": "EXIT_CODE=0"}]},
        "tool_use_result": {"kind": "completed", "exitCode": 0},
        "session_id": sid,
    })

    trace = _write_jsonl(tmp / "traces", "workflow-bgtask.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    # background_task_id may be set, but delegated_models must be empty
    assert not summary.get("delegated_models"), (
        "delegated_models must be empty when child events lack model info"
    )
    # Children without model evidence fail at protocol level (no_delegated_model)
    assert summary["agent_call_count"] == 0, (
        "no agent calls should be produced without delegated model evidence"
    )
    pf = summary.get("workflow_protocol_failures", [])
    assert any("no_delegated_model" in f for f in pf), (
        f"must report no_delegated_model; got: {pf}"
    )


def test_sibling_run_still_triggers_write_set(tmp: Path) -> None:
    """Sibling run paths in same session → write-set violations.

    Only the exact run_id-bound paths are excluded.  Sibling runs within
    the same session must still trigger scenario_write_set.
    """
    from trace_evidence import classify_workflow_write_set
    session_id = "sess-sib"
    bound_run_id = "wf_run-bound"
    sibling_run_id = "wf_run-sibling"
    paths = {
        f".qoder/sessions/{session_id}/workflows/runs/{bound_run_id}/manifest.json",
        f".qoder/sessions/{session_id}/workflows/runs/{bound_run_id}/journal.jsonl",
        f".qoder/sessions/{session_id}/workflows/runs/{sibling_run_id}/manifest.json",
        f".qoder/sessions/{session_id}/workflows/scripts/shared.js",
    }
    bound = classify_workflow_write_set(paths, session_id, bound_run_id)
    # Only bound run paths excluded
    expected_bound = {
        f".qoder/sessions/{session_id}/workflows/runs/{bound_run_id}/manifest.json",
        f".qoder/sessions/{session_id}/workflows/runs/{bound_run_id}/journal.jsonl",
    }
    assert bound == expected_bound, (
        f"only bound run paths should be excluded; got bound={bound}, "
        f"expected={expected_bound}"
    )
    remaining = paths - bound
    assert f".qoder/sessions/{session_id}/workflows/runs/{sibling_run_id}/manifest.json" in remaining, (
        "sibling run paths must remain as violations"
    )
    assert f".qoder/sessions/{session_id}/workflows/scripts/shared.js" in remaining, (
        "scripts and non-run paths must remain as violations"
    )


def test_run_id_must_match_write_set_exclusion(tmp: Path) -> None:
    """Only paths matching the exact session+run_id are excluded.

    run_id must participate in the path matching; paths without matching
    run_id must not be excluded even if they share the session prefix.
    """
    from trace_evidence import classify_workflow_write_set
    session_id = "sess-exact"
    run_id = "wf_run-exact"
    paths = {
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/manifest.json",
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/journal.jsonl",
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/output.json",
        # Metadata at workflows level, not within runs/<runId>/
        f".qoder/sessions/{session_id}/workflows/metadata.json",
        # Sibling run
        f".qoder/sessions/{session_id}/workflows/runs/wf_other/script.js",
    }
    bound = classify_workflow_write_set(paths, session_id, run_id)
    expected_bound = {
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/manifest.json",
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/journal.jsonl",
        f".qoder/sessions/{session_id}/workflows/runs/{run_id}/output.json",
    }
    assert bound == expected_bound, (
        f"only paths under runs/{run_id}/ should be excluded; got bound={bound}"
    )
    remaining = paths - bound
    assert f".qoder/sessions/{session_id}/workflows/metadata.json" in remaining, (
        "non-run metadata must not be excluded"
    )
    assert f".qoder/sessions/{session_id}/workflows/runs/wf_other/script.js" in remaining, (
        "sibling run must not be excluded"
    )


# -- Fixture builder: shared Workflow test harness ---------------------------

class WorkflowFixture:
    """Reusable builder for Workflow trace + runtime artifacts.

    Each negative test creates a fixture, mutates one aspect, and verifies
    the expected protocol failure.  This eliminates the duplicated event
    construction that previously existed in every negative test.
    """

    def __init__(self, tmp: Path, suffix: str = ""):
        self.suffix = suffix or f"-{id(self):x}"[:8]
        self.session_id = f"sess{self.suffix}"
        self.run_id = f"wf_run{self.suffix}"
        self.task_id = f"wf-task{self.suffix}"
        self.wf_tool_use_id = f"call_wf{self.suffix}"
        self.children = standard_workflow_children()
        self.tmp = tmp

    def build_artifacts(self, **overrides) -> Path:
        """Build runtime artifacts, forwarding kwargs to workflow_runtime_artifacts."""
        runtime_dir = self.tmp / "runtime"
        runtime_dir.mkdir(exist_ok=True)
        kwargs = {
            "task_id": self.task_id,
            **overrides,
        }
        workflow_runtime_artifacts(
            runtime_dir, self.session_id, self.run_id,
            self.children, **kwargs,
        )
        return runtime_dir

    def build_events(self, **overrides) -> list[dict]:
        """Build trace events.  overrides can set overall_status, children, etc."""
        children = overrides.pop("children", self.children)
        overall_status = overrides.pop("overall_status", "completed")
        session_id = overrides.pop("session_id", self.session_id)
        run_id = overrides.pop("run_id", self.run_id)
        task_id = overrides.pop("task_id", self.task_id)
        wf_tool_use_id = overrides.pop("wf_tool_use_id", self.wf_tool_use_id)
        include_children = overrides.pop("include_children", True)
        include_notification = overrides.pop("include_notification", True)
        child_event_session = overrides.pop("child_event_session", session_id)
        notification_status = overrides.pop("notification_status", overall_status)
        include_model_events = overrides.pop("include_model_events", True)

        events = [
            {"type": "system", "subtype": "init",
             "tools": ["Agent", "Bash", "Workflow"],
             "agents": ["Explore", "general-purpose"], "model": "qmodel_preview",
             "session_id": session_id},
            {"type": "assistant",
             "message": {"model": "qmodel_preview", "content": [
                 {"type": "tool_use", "id": wf_tool_use_id,
                  "name": "Workflow",
                  "input": {"script": "export const meta = { name: 'test' }"}}]},
             "session_id": session_id},
        ]
        import json as _json
        payload = _json.dumps({
            "status": "async_launched",
            "taskId": task_id,
            "runId": run_id,
            "transcriptDir": (
                f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/runs/{run_id}"
            ),
            "scriptPath": (
                f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/"
                f"scripts/test-workflow-{run_id}.js"
            ),
        })
        events.append({
            "type": "user",
            "message": {"content": [
                {"type": "tool_result", "tool_use_id": wf_tool_use_id,
                 "content": f"Workflow launched.\ntaskId: {task_id}\nrunId: {run_id}"}]},
            "tool_use_result": {"payload": payload},
            "session_id": session_id,
        })
        # Child events
        if include_children and children:
            for child in children:
                events.append({
                    "type": "system",
                    "task_id": child["agent_id"],
                    "parent_tool_use_id": wf_tool_use_id,
                    "tool_use_id": wf_tool_use_id,
                    "subtype": "task_started",
                    "description": child.get("marker_text", child["label"]),
                    "session_id": child_event_session,
                })
                if include_model_events:
                    events.append({
                        "type": "assistant",
                        "parent_tool_use_id": wf_tool_use_id,
                        "task_id": child["agent_id"],
                        "message": {"model": f"child-model-{child['agent_id'][:8]}",
                                    "content": []},
                        "session_id": child_event_session,
                    })
                events.append({
                    "type": "system",
                    "task_id": child["agent_id"],
                    "parent_tool_use_id": wf_tool_use_id,
                    "tool_use_id": wf_tool_use_id,
                    "subtype": "task_completed",
                    "description": child.get("marker_text", ""),
                    "session_id": child_event_session,
                })
        if include_notification:
            events.append({
                "type": "system", "subtype": "task_notification",
                "task_id": task_id, "tool_use_id": wf_tool_use_id,
                "status": notification_status,
                "output_file": (
                    f"/tmp/workspace/.qoder/sessions/{session_id}/workflows/"
                    f"runs/{run_id}/output.json"
                ),
                "session_id": session_id,
            })
        # Validation command
        events.append({
            "type": "assistant",
            "message": {"model": "qmodel_preview", "content": [
                {"type": "tool_use", "id": f"call_val{self.suffix}", "name": "Bash",
                 "input": {"command": "python3 scripts/check.py",
                           "dir_path": "/tmp/fixture"}}]},
            "session_id": session_id,
        })
        events.append({
            "type": "user",
            "message": {"content": [
                {"type": "tool_result", "tool_use_id": f"call_val{self.suffix}",
                 "is_error": False, "content": "EXIT_CODE=0"}]},
            "tool_use_result": {"kind": "completed", "exitCode": 0},
            "session_id": session_id,
        })
        return events

    def summarize(self) -> dict:
        runtime_dir = self.build_artifacts()
        events = self.build_events()
        trace = _write_jsonl(self.tmp / "traces", f"fixture{self.suffix}.jsonl", events)
        return summarize(trace, workflow_runtime_root=runtime_dir)

    def summarize_events(self, events: list[dict], runtime_dir: Path | None = None) -> dict:
        """Grade one focused trace mutation through the public summarize seam."""
        runtime_dir = runtime_dir or self.build_artifacts()
        trace = _write_jsonl(
            self.tmp / "traces", f"fixture{self.suffix}-mutated.jsonl", events,
        )
        return summarize(trace, workflow_runtime_root=runtime_dir)

    def artifact_dir(self, runtime_dir: Path) -> Path:
        return (
            runtime_dir / ".qoder" / "sessions" / self.session_id
            / "workflows" / "runs" / self.run_id
        )


# -- New [P0] red-first tests: output gating, cross-session, per-child model ---

def test_workflow_output_failed_status_fails(tmp: Path) -> None:
    """output.json status is 'failed' → protocol failure even if children look OK."""
    fx = WorkflowFixture(tmp, "-outfail")
    runtime_dir = fx.build_artifacts(overall_status="failed")
    events = fx.build_events()
    trace = _write_jsonl(tmp / "traces", "output-failed.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert any("output_status" in f for f in pf), (
        f"output failed status must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_workflow_output_task_id_mismatch_fails(tmp: Path) -> None:
    """output.json taskId doesn't match trace taskId → protocol failure."""
    fx = WorkflowFixture(tmp, "-taskmis")
    runtime_dir = fx.build_artifacts(task_id="wrong-task-id")
    events = fx.build_events()
    trace = _write_jsonl(tmp / "traces", "output-task-mismatch.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert any("taskId" in f for f in pf), (
        f"output taskId mismatch must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_workflow_cross_session_child_event_fails(tmp: Path) -> None:
    """Child event from a different session → protocol failure."""
    fx = WorkflowFixture(tmp, "-xsess")
    runtime_dir = fx.build_artifacts()
    # Build events where child events have a different session_id
    events = fx.build_events(
        child_event_session="other-session-id",
    )
    trace = _write_jsonl(tmp / "traces", "cross-session.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert any("cross_session" in f for f in pf), (
        f"cross-session child event must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_workflow_notification_failed_fails(tmp: Path) -> None:
    """Workflow task_notification status is 'failed' → protocol failure."""
    fx = WorkflowFixture(tmp, "-notfail")
    runtime_dir = fx.build_artifacts()
    events = fx.build_events(notification_status="failed")
    trace = _write_jsonl(tmp / "traces", "notification-failed.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert any("notification_status" in f for f in pf), (
        f"failed notification status must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_model_less_explore_cannot_trigger_extra_exploration(tmp: Path) -> None:
    """Model-less Explore child cannot satisfy extra_exploration_call gate.

    A child with an extra-exploration marker but no delegated model evidence
    must not count toward extra-exploration detection.  Model-less children
    in marker positions must fail require_delegated_model.
    """
    # Create children where ultra-code-explore has NO model evidence
    children = [
        {"agent_id": "aExplore-ultra", "label": "ultra-code-explore",
         "agent_type": "Explore", "journal_key": "v2:aaa111",
         "marker_text": "[eval-stage:ultra-code-explore]",
         "state": "done", "has_terminal": True},
        {"agent_id": "aExplore-native", "label": "target-native-explore",
         "agent_type": "Explore", "journal_key": "v2:bbb222",
         "marker_text": "[eval-stage:target-native-explore]",
         "state": "done", "has_terminal": True},
        {"agent_id": "aworkflow-sub-rev", "label": "ultra-post-review",
         "agent_type": "workflow-subagent", "journal_key": "v2:ddd444",
         "marker_text": "[eval-stage:ultra-post-review]",
         "state": "done", "has_terminal": True},
    ]
    fx = WorkflowFixture(tmp, "-nomodel")
    fx.children = children
    runtime_dir = fx.build_artifacts()
    events = fx.build_events(include_model_events=False)
    trace = _write_jsonl(tmp / "traces", "model-less-explore.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    # All children should fail because no delegated_models
    assert summary["agent_call_count"] == 0, (
        f"model-less children should all fail; got {summary['agent_call_count']}"
    )
    # delegated_model must not be satisfied by empty delegated_models
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert "delegated_model_observed" in codes or any(
        "workflow_protocol" in c for c in codes
    ), f"model-less children must fail; got: {codes}"


def test_workflow_child_missing_session_fails(tmp: Path) -> None:
    """Child events without session_id → protocol failure.

    Every child event must be traceable to its owning Workflow session.
    Missing session_id means the event cannot be bound to any workflow.
    """
    fx = WorkflowFixture(tmp, "-noss")
    runtime_dir = fx.build_artifacts()
    # Build events where child events have NO session_id
    events = fx.build_events(child_event_session=None)
    trace = _write_jsonl(tmp / "traces", "missing-session.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert any("missing_session" in f for f in pf), (
        f"missing session_id must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_workflow_duplicate_journal_key_fails(tmp: Path) -> None:
    """Journal with duplicate result keys → protocol failure.

    Each journal result must have a unique key.  Duplicate keys indicate
    tampered or corrupted journal data.
    """
    sid, rid = "sess-dup", "wf_run-dup"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    wf_dir = runtime_dir / ".qoder" / "sessions" / sid / "workflows" / "runs" / rid
    wf_dir.mkdir(parents=True)
    children = standard_workflow_children()
    # Build manifest normally
    manifest_agents = []
    for idx, child in enumerate(children, start=1):
        manifest_agents.append({
            "index": idx, "label": child["label"],
            "phaseIndex": child.get("phase_index", 1),
            "phaseTitle": child.get("phase_title", "Explore"),
            "journalKey": child["journal_key"],
            "agentId": child["agent_id"],
            "agentType": child["agent_type"],
            "state": child.get("state", "done"),
            "attempts": 1,
        })
    _write_json(wf_dir, "manifest.json", {
        "runId": rid, "workflowName": "test", "status": "completed",
        "scriptPath": (
            f"/tmp/workspace/.qoder/sessions/{sid}/workflows/scripts/"
            f"test-workflow-{rid}.js"
        ),
        "outputPath": (
            f"/tmp/workspace/.qoder/sessions/{sid}/workflows/runs/{rid}/output.json"
        ),
        "agents": manifest_agents,
    })
    # Build journal with DUPLICATE result key
    journal_events = []
    for child in children:
        key = child["journal_key"]
        journal_events.append({"type": "started", "key": key, "timestamp": 1000})
        journal_events.append({"type": "result", "key": key,
                               "agentId": child["agent_id"],
                               "result": {"content": "{}"}})
    # Add duplicate result for the first key
    dup_key = children[0]["journal_key"]
    journal_events.append({"type": "result", "key": dup_key,
                           "agentId": children[0]["agent_id"],
                           "result": {"content": "duplicate"}})
    _write_jsonl(wf_dir, "journal.jsonl", journal_events)
    _write_json(wf_dir, "output.json", {
        "runId": rid, "taskId": _TASK_ID,
        "workflowName": "test", "status": "completed",
        "transcriptDir": (
            f"/tmp/workspace/.qoder/sessions/{sid}/workflows/runs/{rid}"
        ),
        "scriptPath": (
            f"/tmp/workspace/.qoder/sessions/{sid}/workflows/scripts/"
            f"test-workflow-{rid}.js"
        ),
        "result": {},
    })

    trace = _write_jsonl(tmp / "traces", "dup-journal.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert any("duplicate_result_key" in f for f in pf), (
        f"duplicate journal key must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_workflow_conflicting_terminal_event_fails(tmp: Path) -> None:
    """Child with task_failed event alongside task_completed → protocol failure.

    Any co-existing failed/cancelled/timeout/unknown lifecycle event
    alongside success events must be rejected — the evidence is conflicting.
    """
    children = standard_workflow_children()
    sid, rid = "sess-cfl", "wf_run-cfl"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    task_id = "wf-cfl-task"
    workflow_runtime_artifacts(runtime_dir, sid, rid, children, task_id=task_id)

    # Build trace with task_failed alongside task_completed for first child
    wf_tool_use_id = "call_cfl_wf"
    events = [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash", "Workflow"],
         "agents": ["Explore", "general-purpose"], "model": "qmodel_preview",
         "session_id": sid},
        {"type": "assistant",
         "message": {"model": "qmodel_preview", "content": [
             {"type": "tool_use", "id": wf_tool_use_id, "name": "Workflow",
              "input": {"script": "export const meta = {}"}}]},
         "session_id": sid},
    ]
    import json as _json
    payload = _json.dumps({
        "status": "async_launched", "taskId": task_id, "runId": rid,
        "transcriptDir": f"/tmp/workspace/.qoder/sessions/{sid}/workflows/runs/{rid}",
        "scriptPath": (
            f"/tmp/workspace/.qoder/sessions/{sid}/workflows/scripts/"
            f"test-workflow-{rid}.js"
        ),
    })
    events.append({
        "type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": wf_tool_use_id,
             "content": f"Workflow launched.\ntaskId: {task_id}\nrunId: {rid}"}]},
        "tool_use_result": {"payload": payload}, "session_id": sid,
    })
    for child in children:
        events.append({
            "type": "system", "task_id": child["agent_id"],
            "parent_tool_use_id": wf_tool_use_id,
            "tool_use_id": wf_tool_use_id,
            "subtype": "task_started",
            "description": child.get("marker_text", child["label"]),
            "session_id": sid,
        })
        events.append({
            "type": "assistant", "parent_tool_use_id": wf_tool_use_id,
            "task_id": child["agent_id"],
            "message": {"model": f"cm-{child['agent_id'][:8]}", "content": []},
            "session_id": sid,
        })
        # First child gets task_failed BEFORE task_completed
        if child == children[0]:
            events.append({
                "type": "system", "task_id": child["agent_id"],
                "parent_tool_use_id": wf_tool_use_id,
                "tool_use_id": wf_tool_use_id,
                "subtype": "task_failed",
                "description": "failed", "session_id": sid,
            })
        events.append({
            "type": "system", "task_id": child["agent_id"],
            "parent_tool_use_id": wf_tool_use_id,
            "tool_use_id": wf_tool_use_id,
            "subtype": "task_completed",
            "description": child.get("marker_text", ""),
            "session_id": sid,
        })
    events.append({
        "type": "system", "subtype": "task_notification",
        "task_id": task_id, "tool_use_id": wf_tool_use_id,
        "status": "completed",
        "output_file": (
            f"/tmp/workspace/.qoder/sessions/{sid}/workflows/runs/{rid}/output.json"
        ),
        "session_id": sid,
    })
    events.append({
        "type": "assistant",
        "message": {"model": "qmodel_preview", "content": [
            {"type": "tool_use", "id": "call_val_cfl", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]},
        "session_id": sid,
    })
    events.append({
        "type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_val_cfl",
             "is_error": False, "content": "EXIT_CODE=0"}]},
        "tool_use_result": {"kind": "completed", "exitCode": 0},
        "session_id": sid,
    })

    trace = _write_jsonl(tmp / "traces", "conflicting-term.jsonl", events)
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert any("conflicting_terminal" in f for f in pf), (
        f"conflicting terminal event must produce protocol failure; got: {pf}"
    )


def test_direct_agent_missing_role_fails(tmp: Path) -> None:
    """Direct Agent call without subagent_type/agent_type → role failure.

    A required marker's Agent call must have an explicit role.  Missing role
    means the agent identity is unverifiable — not equivalent to any role.
    """
    trace = _write_jsonl(tmp / "traces", "no-role.jsonl", [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash"],
         "agents": ["Explore", "general-purpose"], "model": "dfmodel"},
        # Agent call WITHOUT subagent_type
        {"type": "assistant", "message": {"model": "dfmodel", "content": [
            {"type": "tool_use", "id": "call_norole", "name": "Agent",
             "input": {"description": "Explore", "prompt": "Explore [eval-stage:target-native-explore]",
                       "run_in_background": True}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_norole",
             "content": "Agent launched."}]},
         "tool_use_result": {"status": "async_launched"}},
        {"type": "system", "task_id": "aNoRole",
         "tool_use_id": "call_norole", "description": "explore"},
        {"type": "assistant", "parent_tool_use_id": "call_norole",
         "message": {"model": "child-model", "content": []}},
        {"type": "system", "task_id": "aNoRole",
         "tool_use_id": "call_norole", "status": "completed"},
        # Agent call with role
        {"type": "assistant", "message": {"model": "dfmodel", "content": [
            {"type": "tool_use", "id": "call_review", "name": "Agent",
             "input": {"subagent_type": "general-purpose",
                       "description": "Review",
                       "prompt": "Review [eval-stage:ultra-post-review]",
                       "run_in_background": True}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_review",
             "content": "Agent launched."}]},
         "tool_use_result": {"status": "async_launched"}},
        {"type": "assistant", "parent_tool_use_id": "call_review",
         "message": {"model": "child-model2", "content": []}},
        {"type": "system", "task_id": "aReview",
         "tool_use_id": "call_review", "status": "completed"},
        {"type": "assistant", "message": {"model": "dfmodel", "content": [
            {"type": "tool_use", "id": "call_val", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_val",
             "is_error": False, "content": "EXIT_CODE=0"}]},
         "tool_use_result": {"kind": "completed", "exitCode": 0}},
    ])
    summary = summarize(trace)
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert "delegated_stage_role" in codes, (
        f"direct Agent without role must fail delegated_stage_role; got: {codes}"
    )


def test_workflow_output_missing_task_id_fails(tmp: Path) -> None:
    """output.json without taskId → protocol failure.

    output taskId is mandatory identity evidence.  Missing taskId means
    the output cannot be bound to the trace-derived workflow task.
    """
    sid, rid = "sess-otm", "wf_run-otm"
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    wf_dir = runtime_dir / ".qoder" / "sessions" / sid / "workflows" / "runs" / rid
    wf_dir.mkdir(parents=True)
    children = standard_workflow_children()
    manifest_agents = []
    for idx, child in enumerate(children, start=1):
        manifest_agents.append({
            "index": idx, "label": child["label"],
            "phaseIndex": child.get("phase_index", 1),
            "phaseTitle": child.get("phase_title", "Explore"),
            "journalKey": child["journal_key"],
            "agentId": child["agent_id"],
            "agentType": child["agent_type"],
            "state": child.get("state", "done"),
            "attempts": 1,
        })
    _write_json(wf_dir, "manifest.json", {
        "runId": rid, "workflowName": "test", "status": "completed",
        "agents": manifest_agents,
    })
    journal_events = []
    for child in children:
        key = child["journal_key"]
        journal_events.append({"type": "started", "key": key})
        journal_events.append({"type": "result", "key": key,
                               "agentId": child["agent_id"],
                               "result": {"content": "{}"}})
    _write_jsonl(wf_dir, "journal.jsonl", journal_events)
    # output.json WITHOUT taskId
    _write_json(wf_dir, "output.json", {
        "runId": rid, "workflowName": "test", "status": "completed", "result": {},
    })

    trace = _write_jsonl(tmp / "traces", "no-taskid.jsonl",
                         workflow_trace_events(children=children,
                                               session_id=sid, run_id=rid))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    pf = summary.get("workflow_protocol_failures", [])
    assert any("taskId_missing" in f for f in pf), (
        f"missing output taskId must produce protocol failure; got: {pf}"
    )
    assert summary["agent_call_count"] == 0


def test_workflow_tool_result_missing_session_fails(tmp: Path) -> None:
    """Workflow tool_result without session identity must fail closed."""
    fx = WorkflowFixture(tmp, "-result-no-session")
    runtime_dir = fx.build_artifacts()
    events = fx.build_events()
    result_event = next(
        event for event in events
        if any(
            item.get("type") == "tool_result"
            and item.get("tool_use_id") == fx.wf_tool_use_id
            for item in event.get("message", {}).get("content", [])
            if isinstance(item, dict)
        )
    )
    result_event.pop("session_id")
    summary = fx.summarize_events(events, runtime_dir)
    assert "workflow_tool_result_session_missing" in summary["workflow_protocol_failures"]
    assert summary["agent_call_count"] == 0


def test_workflow_notification_binding_is_unique_and_complete(tmp: Path) -> None:
    """Missing/wrong/duplicate Workflow notifications must fail closed."""
    mutations = {
        "missing-session": lambda event: event.pop("session_id"),
        "wrong-tool": lambda event: event.__setitem__("tool_use_id", "other-workflow"),
    }
    for suffix, mutate in mutations.items():
        fx = WorkflowFixture(tmp / suffix, f"-notif-{suffix}")
        fx.tmp.mkdir()
        runtime_dir = fx.build_artifacts()
        events = fx.build_events()
        notification = next(
            event for event in events if event.get("subtype") == "task_notification"
        )
        mutate(notification)
        summary = fx.summarize_events(events, runtime_dir)
        assert summary["workflow_protocol_failures"], suffix
        assert summary["agent_call_count"] == 0

    fx = WorkflowFixture(tmp / "duplicate", "-notif-duplicate")
    fx.tmp.mkdir()
    runtime_dir = fx.build_artifacts()
    events = fx.build_events()
    notification = next(
        event for event in events if event.get("subtype") == "task_notification"
    )
    events.insert(events.index(notification) + 1, dict(notification))
    summary = fx.summarize_events(events, runtime_dir)
    assert "workflow_notification_count_2" in summary["workflow_protocol_failures"]
    assert summary["agent_call_count"] == 0


def test_workflow_duplicate_tool_result_fails(tmp: Path) -> None:
    """A Workflow invocation has exactly one identity-bearing tool_result."""
    fx = WorkflowFixture(tmp, "-duplicate-result")
    runtime_dir = fx.build_artifacts()
    events = fx.build_events()
    result_event = next(
        event for event in events
        if any(
            item.get("type") == "tool_result"
            and item.get("tool_use_id") == fx.wf_tool_use_id
            for item in event.get("message", {}).get("content", [])
            if isinstance(item, dict)
        )
    )
    events.insert(events.index(result_event) + 1, dict(result_event))
    summary = fx.summarize_events(events, runtime_dir)
    assert "workflow_tool_result_count_2" in summary["workflow_protocol_failures"]
    assert summary["agent_call_count"] == 0


def test_workflow_journal_requires_unique_ordered_started_and_result(tmp: Path) -> None:
    """Every manifest journalKey has one started before one result."""
    mutations = {
        "missing-started": lambda rows, key: rows.__setitem__(
            slice(None), [row for row in rows if not (
                row.get("type") == "started" and row.get("key") == key
            )],
        ),
        "duplicate-started": lambda rows, key: rows.insert(
            1, {"type": "started", "key": key, "timestamp": 1001},
        ),
        "result-before-started": lambda rows, key: rows.sort(
            key=lambda row: (
                0 if row.get("type") == "result" and row.get("key") == key
                else 1 if row.get("type") == "started" and row.get("key") == key
                else 2
            ),
        ),
    }
    for suffix, mutate in mutations.items():
        case_root = tmp / suffix
        case_root.mkdir()
        fx = WorkflowFixture(case_root, f"-journal-{suffix}")
        runtime_dir = fx.build_artifacts()
        journal_path = fx.artifact_dir(runtime_dir) / "journal.jsonl"
        rows = [
            json.loads(line)
            for line in journal_path.read_text(encoding="utf-8").splitlines()
        ]
        mutate(rows, fx.children[0]["journal_key"])
        _write_jsonl(journal_path.parent, journal_path.name, rows)
        summary = fx.summarize_events(fx.build_events(), runtime_dir)
        assert summary["workflow_protocol_failures"], suffix
        assert summary["agent_call_count"] == 0


def test_workflow_manifest_child_identity_fields_are_unique(tmp: Path) -> None:
    """agentId/index/label/journalKey each identify exactly one child."""
    for field in ("agentId", "index", "label", "journalKey"):
        case_root = tmp / field
        case_root.mkdir()
        fx = WorkflowFixture(case_root, f"-identity-{field}")
        runtime_dir = fx.build_artifacts()
        manifest_path = fx.artifact_dir(runtime_dir) / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["agents"][1][field] = manifest["agents"][0][field]
        _write_json(manifest_path.parent, manifest_path.name, manifest)
        summary = fx.summarize_events(fx.build_events(), runtime_dir)
        assert summary["workflow_protocol_failures"], field
        assert summary["agent_call_count"] == 0


def test_main_trace_corrupt_jsonl_fails_closed(tmp: Path) -> None:
    """One malformed main-trace line invalidates the complete invocation."""
    fx = WorkflowFixture(tmp, "-corrupt-main-trace")
    runtime_dir = fx.build_artifacts()
    trace = _write_jsonl(tmp / "traces", "corrupt-main.jsonl", fx.build_events())
    lines = trace.read_text(encoding="utf-8").splitlines()
    trace.write_text("\n".join([lines[0], "NOT-JSON", *lines[1:]]) + "\n",
                     encoding="utf-8")
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert "main_trace_malformed_jsonl" in summary["workflow_protocol_failures"]
    assert summary["agent_call_count"] == 0


def test_workflow_invocation_id_must_be_nonempty_and_unique(tmp: Path) -> None:
    """Empty, duplicate, and cross-session Workflow IDs are ambiguous."""
    for suffix, replacement_id, replacement_session in (
        ("empty", "", None),
        ("duplicate", None, None),
        ("cross-session", None, "other-session"),
    ):
        case = tmp / suffix
        case.mkdir()
        fx = WorkflowFixture(case, f"-invocation-{suffix}")
        runtime_dir = fx.build_artifacts()
        events = fx.build_events()
        invocation = next(
            event for event in events
            if any(item.get("name") == "Workflow"
                   for item in event.get("message", {}).get("content", [])
                   if isinstance(item, dict))
        )
        duplicate = json.loads(json.dumps(invocation))
        if replacement_id is not None:
            duplicate["message"]["content"][0]["id"] = replacement_id
        if replacement_session is not None:
            duplicate["session_id"] = replacement_session
        events.insert(events.index(invocation) + 1, duplicate)
        summary = fx.summarize_events(events, runtime_dir)
        assert summary["workflow_protocol_failures"], suffix
        assert summary["agent_call_count"] == 0, suffix


def test_workflow_artifact_symlink_fails_closed(tmp: Path) -> None:
    """Concrete manifest/journal/output symlinks stay outside the trust boundary."""
    for artifact in ("manifest.json", "journal.jsonl", "output.json"):
        case = tmp / artifact.replace(".", "-")
        case.mkdir()
        fx = WorkflowFixture(case, f"-symlink-{artifact.split('.')[0]}")
        runtime_dir = fx.build_artifacts()
        path = fx.artifact_dir(runtime_dir) / artifact
        target = case / f"outside-{artifact}"
        path.rename(target)
        path.symlink_to(target)
        summary = fx.summarize_events(fx.build_events(), runtime_dir)
        assert "workflow_artifact_symlink" in summary["workflow_protocol_failures"], artifact
        assert summary["agent_call_count"] == 0, artifact


def test_workflow_manifest_label_and_journal_kind_are_bound(tmp: Path) -> None:
    """Labels bind evaluator markers; journal nested event kinds are closed."""
    for suffix, mutate in (
        ("label", lambda manifest, rows: manifest["agents"][0].__setitem__(
            "label", "invented-stage"
        )),
        ("kind", lambda manifest, rows: rows[1]["event"].__setitem__(
            "kind", "unknown_future_kind"
        )),
    ):
        case = tmp / suffix
        case.mkdir()
        fx = WorkflowFixture(case, f"-binding-{suffix}")
        runtime_dir = fx.build_artifacts()
        artifact_dir = fx.artifact_dir(runtime_dir)
        manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in
                (artifact_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
        mutate(manifest, rows)
        _write_json(artifact_dir, "manifest.json", manifest)
        _write_jsonl(artifact_dir, "journal.jsonl", rows)
        summary = fx.summarize_events(fx.build_events(), runtime_dir)
        assert summary["workflow_protocol_failures"], suffix
        assert summary["agent_call_count"] == 0, suffix


def test_workflow_calls_follow_runtime_start_order(tmp: Path) -> None:
    """Normalized Workflow calls follow runtime starts, never manifest order."""
    fx = WorkflowFixture(tmp, "-runtime-order")
    runtime_dir = fx.build_artifacts()
    events = fx.build_events()
    child_events = events[3:12]
    events[3:12] = child_events[3:6] + child_events[0:3] + child_events[6:9]
    summary = fx.summarize_events(events, runtime_dir)
    assert summary["workflow_protocol_failures"]
    assert summary["agent_call_count"] == 0


def test_workflow_transport_paths_must_cross_bind(tmp: Path) -> None:
    """Transport, manifest, notification, and output paths are one identity."""
    for suffix, mutate in (
        ("transcript", lambda payload, notification, manifest, output:
         payload.__setitem__("transcriptDir", "/tmp/other/run")),
        ("script", lambda payload, notification, manifest, output:
         manifest.__setitem__("scriptPath", "/tmp/other/script.js")),
        ("output", lambda payload, notification, manifest, output:
         notification.__setitem__("output_file", "/tmp/other/output.json")),
    ):
        case = tmp / suffix
        case.mkdir()
        fx = WorkflowFixture(case, f"-path-{suffix}")
        runtime_dir = fx.build_artifacts()
        events = fx.build_events()
        result_event = next(event for event in events if event.get("tool_use_result"))
        payload = json.loads(result_event["tool_use_result"]["payload"])
        notification = next(event for event in events
                            if event.get("subtype") == "task_notification")
        artifact_dir = fx.artifact_dir(runtime_dir)
        manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
        output = json.loads((artifact_dir / "output.json").read_text(encoding="utf-8"))
        mutate(payload, notification, manifest, output)
        result_event["tool_use_result"]["payload"] = json.dumps(payload)
        _write_json(artifact_dir, "manifest.json", manifest)
        _write_json(artifact_dir, "output.json", output)
        summary = fx.summarize_events(events, runtime_dir)
        assert summary["workflow_protocol_failures"], suffix
        assert summary["agent_call_count"] == 0, suffix


def test_real_protocol_uses_journal_lifecycle_and_child_transcripts(tmp: Path) -> None:
    """Qoder 1.0.48 need not repeat every child lifecycle in the root trace."""
    fx = WorkflowFixture(tmp, "-real-child-transcripts")
    runtime_dir = fx.build_artifacts()
    events = fx.build_events(include_children=False)
    summary = fx.summarize_events(events, runtime_dir)
    assert summary["workflow_protocol_failures"] == []
    assert summary["agent_call_count"] == 3
    assert [call["task_name"] for call in summary["agent_calls"]] == [
        child["label"] for child in fx.children
    ]
    assert all(call["delegated_models"] for call in summary["agent_calls"])


def test_snapshot_preserves_symlink_and_scrubs_qoder_from_scored_repo(tmp: Path) -> None:
    """Snapshot exposes symlink tampering and removes all Qoder write-set noise."""
    spec = importlib.util.spec_from_file_location("run_eval_fixture", HERE / "run-eval.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    runtime_repo = tmp / "repo"
    run_dir = runtime_repo / ".qoder/sessions/sess/workflows/runs/run"
    run_dir.mkdir(parents=True)
    outside = tmp / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    (run_dir / "manifest.json").symlink_to(outside)
    script = runtime_repo / ".qoder/sessions/sess/workflows/scripts/generated.js"
    script.parent.mkdir(parents=True)
    script.write_text("// runtime\n", encoding="utf-8")
    evidence_root = tmp / "runtime-evidence"
    assert module.snapshot_qoder_repo_evidence(runtime_repo, evidence_root)
    assert (
        evidence_root / ".qoder/sessions/sess/workflows/runs/run/manifest.json"
    ).is_symlink()
    assert not (runtime_repo / ".qoder").exists()


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
        # Red-first: Workflow evidence fail-open
        test_workflow_trace_no_runtime_root_fails,
        test_workflow_failures_not_masked_by_direct_agent,
        # Red-first: child lifecycle, model, ordering
        test_workflow_task_progress_not_terminal,
        test_workflow_child_started_after_terminal_fails,
        test_workflow_child_failed_state_fails,
        test_workflow_child_cancelled_state_fails,
        test_background_task_id_not_model_proof,
        # Red-first: .qoder write-set
        test_sibling_run_still_triggers_write_set,
        test_run_id_must_match_write_set_exclusion,
        # Red-first: output gating, cross-session, per-child model
        test_workflow_output_failed_status_fails,
        test_workflow_output_task_id_mismatch_fails,
        test_workflow_cross_session_child_event_fails,
        test_workflow_notification_failed_fails,
        test_model_less_explore_cannot_trigger_extra_exploration,
        # Red-first: missing session, dup journal, conflicting terminal, missing role
        test_workflow_child_missing_session_fails,
        test_workflow_duplicate_journal_key_fails,
        test_workflow_conflicting_terminal_event_fails,
        test_direct_agent_missing_role_fails,
        test_workflow_output_missing_task_id_fails,
        # Red-first: transport and child identity must be one-to-one
        test_workflow_tool_result_missing_session_fails,
        test_workflow_notification_binding_is_unique_and_complete,
        test_workflow_duplicate_tool_result_fails,
        test_workflow_journal_requires_unique_ordered_started_and_result,
        test_workflow_manifest_child_identity_fields_are_unique,
        test_main_trace_corrupt_jsonl_fails_closed,
        test_workflow_invocation_id_must_be_nonempty_and_unique,
        test_workflow_artifact_symlink_fails_closed,
        test_workflow_manifest_label_and_journal_kind_are_bound,
        test_workflow_calls_follow_runtime_start_order,
        test_workflow_transport_paths_must_cross_bind,
        test_real_protocol_uses_journal_lifecycle_and_child_transcripts,
        test_snapshot_preserves_symlink_and_scrubs_qoder_from_scored_repo,
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
