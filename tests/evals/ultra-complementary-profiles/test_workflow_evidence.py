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


# -- Workflow trace builders ---------------------------------------------------

def workflow_runtime_artifacts(
    runtime_dir: Path,
    session_id: str,
    workflow_id: str,
    children: list[dict],
    *,
    overall_status: str = "completed",
    corrupt_journal: bool = False,
    missing_journal: bool = False,
    missing_transcript: bool = False,
    missing_output: bool = False,
) -> Path:
    """Write workflow runtime artifacts and return the workflow directory."""
    wf_dir = runtime_dir / ".qoder" / "sessions" / session_id / "workflows" / workflow_id
    wf_dir.mkdir(parents=True, exist_ok=True)

    # Manifest
    _write_json(wf_dir, "manifest.json", {
        "workflow_id": workflow_id,
        "session_id": session_id,
        "task_id": "wf-task-001",
        "run_id": "wf-run-001",
        "stages": [
            {"name": child["name"], "agent_type": child["role"]}
            for child in children
        ],
    })

    # Journal (runtime-owned lifecycle events)
    if not missing_journal:
        journal_events = []
        for child in children:
            journal_events.append({
                "event": "agent_started",
                "agent_id": child["agent_id"],
                "agent_type": child["role"],
                "task_id": child.get("task_id", f"task-{child['agent_id']}"),
                "prompt": child["prompt"],
                "stage_markers": child.get("stage_markers", []),
                "trace_index": child.get("started_index", 0),
            })
            if child.get("has_terminal", True):
                journal_events.append({
                    "event": "agent_completed" if child.get("terminal_status", "completed") == "completed" else "agent_failed",
                    "agent_id": child["agent_id"],
                    "delegated_models": child.get("delegated_models", ["delegate-model"]),
                    "trace_index": child.get("completed_index", 1),
                })
        if corrupt_journal:
            _write_text(wf_dir, "journal.jsonl", "NOT-VALID-JSON\n{{bad\n")
        else:
            _write_jsonl(wf_dir, "journal.jsonl", journal_events)

    # Transcript
    if not missing_transcript:
        _write_jsonl(wf_dir, "transcript.jsonl", [
            {"event": "workflow_started", "workflow_id": workflow_id},
            *[
                {"event": "agent_event", "agent_id": child["agent_id"],
                 "stage_markers": child.get("stage_markers", [])}
                for child in children
            ],
            {"event": "workflow_completed", "status": overall_status},
        ])

    # Output
    if not missing_output:
        _write_json(wf_dir, "output.json", {
            "status": overall_status,
            "children": [
                {"agent_id": child["agent_id"], "status": child.get("terminal_status", "completed")}
                for child in children if child.get("has_terminal", True)
            ],
        })

    return wf_dir


def workflow_trace_events(
    session_id: str = "sess-001",
    workflow_id: str = "wf-001",
    children: list[dict] | None = None,
    *,
    overall_status: str = "completed",
    script_has_agent: bool = True,
) -> list[dict]:
    """Build a Qoder Workflow trace (top-level events only)."""
    events = [
        {"type": "system", "subtype": "init", "tools": ["Agent", "Bash", "Workflow"],
         "agents": ["Explore", "general-purpose"], "model": "dfmodel"},
    ]
    # Workflow tool-use request
    script_body = ""
    if script_has_agent:
        script_body = "agent('explore'); agent('candidate'); agent('review');"
    else:
        script_body = "// no agent calls"
    events.append({
        "type": "assistant",
        "message": {"model": "dfmodel", "content": [
            {"type": "tool_use", "id": f"call_wf_{workflow_id}",
             "name": "Workflow",
             "input": {
                 "description": "Architecture workflow",
                 "script": script_body,
                 "session_id": session_id,
                 "workflow_id": workflow_id,
                 "run_id": "wf-run-001",
                 "task_id": "wf-task-001",
             }}]}
    })
    # Workflow launched
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"call_wf_{workflow_id}",
             "content": "Workflow launched."}]},
        "tool_use_result": {"status": "async_launched"},
    })
    # Workflow system events
    events.append({
        "type": "system",
        "task_id": "wf-task-001",
        "tool_use_id": f"call_wf_{workflow_id}",
        "session_id": session_id,
        "workflow_id": workflow_id,
        "description": "workflow execution",
    })
    events.append({
        "type": "system",
        "task_id": "wf-task-001",
        "tool_use_id": f"call_wf_{workflow_id}",
        "status": overall_status,
        "session_id": session_id,
        "workflow_id": workflow_id,
    })
    # Validation command
    events.append({
        "type": "assistant",
        "message": {"model": "dfmodel", "content": [
            {"type": "tool_use", "id": "call_validate", "name": "Bash",
             "input": {"command": "python3 scripts/check.py",
                       "dir_path": "/tmp/fixture"}}]}
    })
    events.append({
        "type": "user",
        "message": {"content": [
            {"type": "tool_result", "tool_use_id": "call_validate",
             "is_error": False, "content": "EXIT_CODE=0"}]},
        "tool_use_result": {"kind": "completed", "exitCode": 0},
    })
    return events


def standard_workflow_children() -> list[dict]:
    """Standard 3-child workflow: explore, candidate, post-review."""
    return [
        {
            "agent_id": "agent-explore-001",
            "name": "target-native-explore",
            "role": "Explore",
            "prompt": "Explore [eval-stage:target-native-explore]",
            "stage_markers": ["[eval-stage:target-native-explore]"],
            "task_id": "task-explore-001",
            "delegated_models": ["delegate-model"],
            "started_index": 3,
            "completed_index": 4,
            "has_terminal": True,
            "terminal_status": "completed",
        },
        {
            "agent_id": "agent-candidate-001",
            "name": "target-native-candidate",
            "role": "general-purpose",
            "prompt": "Produce candidate [eval-stage:target-native-candidate]",
            "stage_markers": ["[eval-stage:target-native-candidate]"],
            "task_id": "task-candidate-001",
            "delegated_models": ["delegate-model"],
            "started_index": 5,
            "completed_index": 6,
            "has_terminal": True,
            "terminal_status": "completed",
        },
        {
            "agent_id": "agent-review-001",
            "name": "ultra-post-review",
            "role": "general-purpose",
            "prompt": "Review [eval-stage:ultra-post-review]",
            "stage_markers": ["[eval-stage:ultra-post-review]"],
            "task_id": "task-review-001",
            "delegated_models": ["delegate-model"],
            "started_index": 7,
            "completed_index": 8,
            "has_terminal": True,
            "terminal_status": "completed",
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
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-001", "wf-001", children)

    trace = _write_jsonl(tmp / "traces", "workflow-complete.jsonl",
                         workflow_trace_events(children=children))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["runtime"] == "qoder"
    assert summary["agent_call_count"] == 3, (
        f"expected 3 workflow child agent calls, got {summary['agent_call_count']}"
    )
    # Verify markers and roles from runtime evidence
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
    children[1]["has_terminal"] = False  # candidate has no terminal event

    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-002", "wf-002", children,
                               overall_status="completed")

    trace = _write_jsonl(tmp / "traces", "workflow-missing-terminal.jsonl",
                         workflow_trace_events(children=children,
                                               workflow_id="wf-002",
                                               session_id="sess-002"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    # Should have only 2 completed calls (explore + review), not 3
    completed_markers = [
        marker
        for call in summary["agent_calls"]
        for marker in call.get("stage_markers", [])
    ]
    assert "[eval-stage:target-native-candidate]" not in completed_markers, (
        "child without terminal should not appear as completed"
    )
    # The grader should still require all markers; missing candidate may not
    # itself be a required marker, but the overall trace should be incomplete.
    # At minimum, agent_call_count should reflect only truly completed children
    assert summary["agent_call_count"] <= 2


def test_script_claims_agent_no_runtime_evidence_fails(tmp: Path) -> None:
    """Script claims agent() but no runtime child evidence → fail closed."""
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    # Write empty journal - no child events
    workflow_runtime_artifacts(runtime_dir, "sess-003", "wf-003", [])

    trace = _write_jsonl(tmp / "traces", "workflow-script-claims.jsonl",
                         workflow_trace_events(workflow_id="wf-003",
                                               session_id="sess-003",
                                               script_has_agent=True))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0, (
        "script-claimed agents without runtime evidence should not count"
    )
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert failures, "missing required stage markers should fail"


def test_marker_mismatch_fails(tmp: Path) -> None:
    """Workflow child with wrong marker → fail."""
    children = standard_workflow_children()
    children[0]["stage_markers"] = ["[eval-stage:wrong-marker]"]

    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-004", "wf-004", children)

    trace = _write_jsonl(tmp / "traces", "workflow-marker-mismatch.jsonl",
                         workflow_trace_events(children=children,
                                               workflow_id="wf-004",
                                               session_id="sess-004"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert any("delegated_stage_marker_missing" in c or "required_stage_call" in c
               for c in codes), f"marker mismatch should fail: {codes}"


def test_role_mismatch_fails(tmp: Path) -> None:
    """Workflow child with wrong role/agentType → fail."""
    children = standard_workflow_children()
    children[0]["role"] = "general-purpose"  # Should be Explore

    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-005", "wf-005", children)

    trace = _write_jsonl(tmp / "traces", "workflow-role-mismatch.jsonl",
                         workflow_trace_events(children=children,
                                               workflow_id="wf-005",
                                               session_id="sess-005"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert any("delegated_stage_role" in c for c in codes), (
        f"role mismatch should fail: {codes}"
    )


def test_child_order_wrong_fails(tmp: Path) -> None:
    """Workflow children in wrong order → fail."""
    children = standard_workflow_children()
    # Swap explore and review order
    children[0], children[2] = children[2], children[0]

    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-006", "wf-006", children)

    trace = _write_jsonl(tmp / "traces", "workflow-order-wrong.jsonl",
                         workflow_trace_events(children=children,
                                               workflow_id="wf-006",
                                               session_id="sess-006"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert any("delegated_stage_order" in c for c in codes), (
        f"child order wrong should fail: {codes}"
    )


def test_missing_journal_fails_closed(tmp: Path) -> None:
    """Missing workflow journal → fail closed, not pass."""
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-007", "wf-007",
                               standard_workflow_children(),
                               missing_journal=True)

    trace = _write_jsonl(tmp / "traces", "workflow-no-journal.jsonl",
                         workflow_trace_events(workflow_id="wf-007",
                                               session_id="sess-007"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0, (
        "missing journal should produce zero agent calls"
    )
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert failures, "missing journal should fail"


def test_corrupt_journal_fails_closed(tmp: Path) -> None:
    """Corrupt workflow journal → fail closed."""
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-008", "wf-008",
                               standard_workflow_children(),
                               corrupt_journal=True)

    trace = _write_jsonl(tmp / "traces", "workflow-corrupt-journal.jsonl",
                         workflow_trace_events(workflow_id="wf-008",
                                               session_id="sess-008"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0, (
        "corrupt journal should produce zero agent calls"
    )
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert failures, "corrupt journal should fail"


def test_missing_transcript_fails_closed(tmp: Path) -> None:
    """Missing workflow transcript → fail closed."""
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-009", "wf-009",
                               standard_workflow_children(),
                               missing_transcript=True)

    trace = _write_jsonl(tmp / "traces", "workflow-no-transcript.jsonl",
                         workflow_trace_events(workflow_id="wf-009",
                                               session_id="sess-009"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0, (
        "missing transcript should produce zero agent calls"
    )


def test_missing_output_fails_closed(tmp: Path) -> None:
    """Missing workflow output → fail closed."""
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-010", "wf-010",
                               standard_workflow_children(),
                               missing_output=True)

    trace = _write_jsonl(tmp / "traces", "workflow-no-output.jsonl",
                         workflow_trace_events(workflow_id="wf-010",
                                               session_id="sess-010"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0, (
        "missing output should produce zero agent calls"
    )


def test_workflow_runtime_paths_allowed_in_write_set(tmp: Path) -> None:
    """Workflow runtime paths bound to session/run ID should be allowed."""
    from trace_evidence import classify_workflow_write_set
    session_id = "sess-011"
    workflow_id = "wf-011"
    paths = {
        f".qoder/sessions/{session_id}/workflows/{workflow_id}/manifest.json",
        f".qoder/sessions/{session_id}/workflows/{workflow_id}/journal.jsonl",
        f".qoder/sessions/{session_id}/workflows/{workflow_id}/transcript.jsonl",
        f".qoder/sessions/{session_id}/workflows/{workflow_id}/output.json",
    }
    bound = classify_workflow_write_set(paths, session_id, workflow_id)
    assert bound == paths, f"bound workflow paths should be allowed: {paths - bound}"


def test_unbound_qoder_files_still_trigger_write_set(tmp: Path) -> None:
    """Arbitrary .qoder files NOT bound to a valid session → write set violation."""
    from trace_evidence import classify_workflow_write_set
    session_id = "sess-012"
    workflow_id = "wf-012"
    unbound_paths = {
        ".qoder/settings.json",
        ".qoder/cache/data.bin",
        ".qoder/sessions/other-session/workflows/other-wf/journal.jsonl",
    }
    bound = classify_workflow_write_set(unbound_paths, session_id, workflow_id)
    assert not bound, f"no unbound paths should be classified: {bound}"
    # The remaining paths should all be violations
    remaining = unbound_paths - bound
    assert remaining == unbound_paths


def test_direct_agent_and_workflow_normalized_equivalently(tmp: Path) -> None:
    """Direct Agent and Workflow for the same stage plan → same normalized summary."""
    # Direct Agent
    direct_trace = _write_jsonl(tmp / "traces", "equiv-direct.jsonl",
                                direct_agent_trace_events())
    direct_summary = summarize(direct_trace)

    # Workflow with equivalent stages
    children = standard_workflow_children()
    runtime_dir = tmp / "runtime-equiv"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-eq", "wf-eq", children)

    wf_trace = _write_jsonl(tmp / "traces", "equiv-workflow.jsonl",
                            workflow_trace_events(children=children,
                                                  session_id="sess-eq",
                                                  workflow_id="wf-eq"))
    wf_summary = summarize(wf_trace, workflow_runtime_root=runtime_dir)

    # Both should produce the same set of stage markers
    direct_markers = sorted(
        marker
        for call in direct_summary["agent_calls"]
        for marker in call.get("stage_markers", [])
    )
    wf_markers = sorted(
        marker
        for call in wf_summary["agent_calls"]
        for marker in call.get("stage_markers", [])
    )
    # Workflow has 3 children (explore, candidate, review), direct has 2 (explore, review)
    # But the required markers should overlap
    assert "[eval-stage:target-native-explore]" in direct_markers
    assert "[eval-stage:target-native-explore]" in wf_markers
    assert "[eval-stage:ultra-post-review]" in direct_markers
    assert "[eval-stage:ultra-post-review]" in wf_markers

    # Grade both with the same expectations
    direct_checks, direct_failures, direct_codes = grade(direct_summary, ARCHITECTURE_TRACE_EXPECTED)
    wf_checks, wf_failures, wf_codes = grade(wf_summary, ARCHITECTURE_TRACE_EXPECTED)
    assert not direct_failures, f"direct should pass: {direct_failures}"
    assert not wf_failures, f"workflow should pass: {wf_failures}"


def test_ablation_duplicate_evidence_goal_and_extra_exploration(tmp: Path) -> None:
    """Ablation's ultra-code-explore + target-native-explore detected."""
    children = [
        {
            "agent_id": "agent-ultra-explore",
            "name": "ultra-code-explore",
            "role": "Explore",
            "prompt": "Explore [eval-stage:ultra-code-explore]",
            "stage_markers": ["[eval-stage:ultra-code-explore]"],
            "task_id": "task-ultra-explore",
            "delegated_models": ["delegate-model"],
            "started_index": 3,
            "completed_index": 4,
            "has_terminal": True,
        },
        {
            "agent_id": "agent-native-explore",
            "name": "target-native-explore",
            "role": "Explore",
            "prompt": "Explore [eval-stage:target-native-explore]",
            "stage_markers": ["[eval-stage:target-native-explore]"],
            "task_id": "task-native-explore",
            "delegated_models": ["delegate-model"],
            "started_index": 5,
            "completed_index": 6,
            "has_terminal": True,
        },
        {
            "agent_id": "agent-candidate",
            "name": "target-native-candidate",
            "role": "general-purpose",
            "prompt": "Candidate [eval-stage:target-native-candidate]",
            "stage_markers": ["[eval-stage:target-native-candidate]"],
            "task_id": "task-candidate",
            "delegated_models": ["delegate-model"],
            "started_index": 7,
            "completed_index": 8,
            "has_terminal": True,
        },
        {
            "agent_id": "agent-review",
            "name": "ultra-post-review",
            "role": "general-purpose",
            "prompt": "Review [eval-stage:ultra-post-review]",
            "stage_markers": ["[eval-stage:ultra-post-review]"],
            "task_id": "task-review",
            "delegated_models": ["delegate-model"],
            "started_index": 9,
            "completed_index": 10,
            "has_terminal": True,
        },
    ]
    runtime_dir = tmp / "runtime-ablation"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-abl", "wf-abl", children)

    trace = _write_jsonl(tmp / "traces", "ablation-workflow.jsonl",
                         workflow_trace_events(children=children,
                                               session_id="sess-abl",
                                               workflow_id="wf-abl"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 4

    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert "extra_exploration_call" in codes, (
        f"ablation should detect extra_exploration_call: {codes}"
    )
    # The duplicate_evidence_goal is detected at the grade-run.py level through
    # stage-evidence.json reconciliation, not trace_evidence.py directly.
    # But the trace should at least show both exploration markers present.
    all_markers = [
        marker
        for call in summary["agent_calls"]
        for marker in call.get("stage_markers", [])
    ]
    assert "[eval-stage:ultra-code-explore]" in all_markers
    assert "[eval-stage:target-native-explore]" in all_markers


def test_workflow_completed_no_child_evidence_fails(tmp: Path) -> None:
    """Workflow completed but no child runtime evidence at all → fail."""
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    # No runtime artifacts at all for this workflow
    trace = _write_jsonl(tmp / "traces", "workflow-no-evidence.jsonl",
                         workflow_trace_events(workflow_id="wf-none",
                                               session_id="sess-none"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0, (
        "workflow with no runtime evidence should have zero agent calls"
    )
    checks, failures, codes = grade(summary, ARCHITECTURE_TRACE_EXPECTED)
    assert failures, "no evidence should fail"


def test_workflow_overall_completed_cannot_substitute_child(tmp: Path) -> None:
    """Workflow completed status alone cannot substitute for missing child lifecycle."""
    runtime_dir = tmp / "runtime"
    runtime_dir.mkdir()
    # Write only manifest and output (no journal/transcript)
    wf_dir = runtime_dir / ".qoder" / "sessions" / "sess-sub" / "workflows" / "wf-sub"
    wf_dir.mkdir(parents=True, exist_ok=True)
    _write_json(wf_dir, "manifest.json", {
        "workflow_id": "wf-sub", "session_id": "sess-sub",
        "task_id": "wf-task-sub", "run_id": "wf-run-sub",
        "stages": [],
    })
    _write_json(wf_dir, "output.json", {"status": "completed", "children": []})

    trace = _write_jsonl(tmp / "traces", "workflow-substitute.jsonl",
                         workflow_trace_events(workflow_id="wf-sub",
                                               session_id="sess-sub"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 0, (
        "workflow completed without child evidence should not produce agent calls"
    )


def test_stage_ledger_workflow_child_reconciliation(tmp: Path) -> None:
    """Stage ledger claims ultra-code-explore but workflow trace lacks it → fail.

    The architecture scenario reconcile_events include ultra-code-explore.
    If the stage ledger records it but the workflow trace doesn't produce a
    matching agent call, the reconciliation should detect stage_trace_mismatch.

    This test simulates what grade-run.py does: comparing ledger event names
    against traced agent markers for the reconcile_events subset.
    """
    # Workflow with only explore + review (no ultra-code-explore)
    children = [
        {
            "agent_id": "agent-explore-rc",
            "name": "target-native-explore",
            "role": "Explore",
            "prompt": "Explore [eval-stage:target-native-explore]",
            "stage_markers": ["[eval-stage:target-native-explore]"],
            "task_id": "task-explore-rc",
            "delegated_models": ["delegate-model"],
            "started_index": 3,
            "completed_index": 4,
            "has_terminal": True,
        },
        {
            "agent_id": "agent-review-rc",
            "name": "ultra-post-review",
            "role": "general-purpose",
            "prompt": "Review [eval-stage:ultra-post-review]",
            "stage_markers": ["[eval-stage:ultra-post-review]"],
            "task_id": "task-review-rc",
            "delegated_models": ["delegate-model"],
            "started_index": 5,
            "completed_index": 6,
            "has_terminal": True,
        },
    ]
    runtime_dir = tmp / "runtime-recon"
    runtime_dir.mkdir()
    workflow_runtime_artifacts(runtime_dir, "sess-recon", "wf-recon", children)

    trace = _write_jsonl(tmp / "traces", "workflow-reconciliation.jsonl",
                         workflow_trace_events(children=children,
                                               session_id="sess-recon",
                                               workflow_id="wf-recon"))
    summary = summarize(trace, workflow_runtime_root=runtime_dir)
    assert summary["agent_call_count"] == 2

    # Simulate the grade-run.py reconciliation logic
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

    # Simulate a stage ledger that claims ultra-code-explore occurred
    ledger_names = ["target-native-explore", "ultra-code-explore", "ultra-post-review", "validation"]
    reconciled = set(reconcile_events)
    ledger_sequence = [name for name in ledger_names if name in reconciled]
    trace_sequence = [name for name in traced_names if name in reconciled]

    # The ledger claims ultra-code-explore but the trace doesn't have it
    mismatched = [
        name for name in reconcile_events
        if ledger_names.count(name) != traced_names.count(name)
    ]
    assert mismatched or ledger_sequence != trace_sequence, (
        "reconciliation should detect mismatch: ledger has ultra-code-explore, trace does not"
    )
    assert "ultra-code-explore" in mismatched, (
        f"ultra-code-explore should be the mismatched event: {mismatched}"
    )


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
        test_missing_transcript_fails_closed,
        test_missing_output_fails_closed,
        test_workflow_runtime_paths_allowed_in_write_set,
        test_unbound_qoder_files_still_trigger_write_set,
        test_direct_agent_and_workflow_normalized_equivalently,
        test_ablation_duplicate_evidence_goal_and_extra_exploration,
        test_workflow_completed_no_child_evidence_fails,
        test_workflow_overall_completed_cannot_substitute_child,
        test_stage_ledger_workflow_child_reconciliation,
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
