#!/usr/bin/env python3
"""Extract runtime capability and real delegation evidence from JSONL traces.

Supports two delegation surfaces:
- Direct Agent calls (Agent/spawn_agent tool-use events in the trace).
- Qoder Workflow calls: a Workflow tool-use in the trace whose runtime-owned
  artifacts (journal, transcript, output, manifest) provide authoritative child
  agent lifecycle evidence.

Workflow is a capability-equivalent delegation surface.  The evaluator uses the
same normalized stage model for both surfaces and never trusts model-written
workflow scripts, stage ledgers, or prose as authoritative evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
from typing import Any, Optional


AGENT_NAMES = {"Agent", "spawn_agent", "collaboration.spawn_agent", "mcp__collaboration__spawn_agent"}
COMMAND_NAMES = {"Bash", "exec_command", "functions.exec_command"}
WORKFLOW_NAMES = {"Workflow", "workflow", "qoder_workflow"}
SUCCESSFUL_AGENT_STATES = {"completed"}


def stage_markers(*values: object) -> list[str]:
    text = " ".join(str(value or "") for value in values)
    return list(dict.fromkeys(
        re.findall(r"\[[a-z0-9-]+:[a-z0-9-]+\]", text, flags=re.IGNORECASE)
    ))


def command_segments(command: object) -> list[str]:
    if not isinstance(command, str):
        return []
    command = re.sub(r"(?<!\S)\d*[<>]&(?:\d+|-)(?=\s|[;&|]|$)", "", command)
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|(){}\n")
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return []
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token and set(token) <= {";", "&", "|", "(", ")", "{", "}", "\n"}:
            if segments[-1]:
                segments.append([])
        else:
            segments[-1].append(token)
    return [shlex.join(segment) for segment in segments if segment]


def normalize_command_path(command: str, cwd: object) -> str:
    if not isinstance(cwd, str) or not cwd:
        return command
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command
    normalized = []
    for token in tokens:
        path = Path(token)
        if path.is_absolute():
            try:
                token = str(path.relative_to(Path(cwd)))
            except ValueError:
                pass
        normalized.append(token)
    return shlex.join(normalized)


def observable_commands(command: object, cwd: object = None, depth: int = 0) -> list[str]:
    """Expose commands executed through common cooperative shell wrappers."""
    if not isinstance(command, str) or depth > 4:
        return []
    observed: list[str] = []
    substitutions = re.findall(r"\$\(([^()]*)\)", command)
    for nested in substitutions:
        observed.extend(observable_commands(nested, cwd, depth + 1))
    for segment in command_segments(command):
        observed.append(segment)
        normalized = normalize_command_path(segment, cwd)
        if normalized != segment:
            observed.append(normalized)
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        if not tokens:
            continue
        shell = Path(tokens[0]).name
        if shell not in {"sh", "bash", "zsh"}:
            continue
        command_index = next(
            (index + 1 for index, token in enumerate(tokens[:-1]) if token in {"-c", "-lc"}),
            None,
        )
        if command_index is not None:
            observed.extend(observable_commands(tokens[command_index], cwd, depth + 1))
    return list(dict.fromkeys(observed))


def json_lines(path: Path) -> tuple[list[dict[str, Any]], bool]:
    events = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return events, False
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return [], False
        if not isinstance(value, dict):
            return [], False
        events.append(value)
    return events, bool(events)


# -- Workflow runtime artifact parsing ----------------------------------------
# Aligned with real Qoder 1.0.48 Workflow protocol:
# - Workflow tool_use input: { script: "..." }
# - tool_result payload: { taskId, runId, transcriptDir, scriptPath }
# - Runtime dir: .qoder/sessions/<session>/workflows/runs/<runId>/
# - Artifacts: manifest.json, journal.jsonl, output.json (no transcript.jsonl)
# - manifest.json agents[]: { index, label, agentId, agentType, state, journalKey }
# - journal.jsonl: { type: "started"|"event"|"result", key, agentId?, ... }
# - Main trace system events: parent_tool_use_id = Workflow tool call ID

_OPAQUE_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def _safe_opaque_id(value: object) -> Optional[str]:
    """Validate an opaque identifier: non-empty, safe charset, no path traversal."""
    if not isinstance(value, str) or not value:
        return None
    if not _OPAQUE_ID_RE.match(value):
        return None
    if ".." in value or "/" in value or "\\" in value:
        return None
    return value


def _canonical_declared_path(value: object) -> Optional[str]:
    """Accept only normalized absolute POSIX paths from runtime declarations."""
    if not isinstance(value, str) or not value.startswith("/"):
        return None
    path = Path(value)
    if ".." in path.parts or "." in path.parts or str(path) != value:
        return None
    return value


def _read_json_file_strict(path: Path) -> Optional[dict[str, Any]]:
    """Read a JSON file; return None only on OS/encoding errors, not on malformed JSON."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None  # caller must treat this as protocol failure
    return value if isinstance(value, dict) else None


def _read_jsonl_strict(path: Path) -> Optional[list[dict[str, Any]]]:
    """Read a JSONL file strictly: every non-blank line must parse as a JSON object."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            return None  # any bad line = protocol failure
        if not isinstance(value, dict):
            return None
        events.append(value)
    return events if events else None


def _resolve_workflow_dir(
    runtime_root: Path,
    session_id: str,
    run_id: str,
) -> Optional[Path]:
    """Resolve the Workflow runtime directory and verify it stays within root."""
    if runtime_root.is_symlink():
        return None
    wf_dir = runtime_root / ".qoder" / "sessions" / session_id / "workflows" / "runs" / run_id
    try:
        resolved = wf_dir.resolve()
        root_resolved = runtime_root.resolve()
    except (OSError, ValueError):
        return None
    # Verify the resolved path is within the runtime root
    try:
        resolved.relative_to(root_resolved)
    except ValueError:
        return None
    # Reject symlink components in the path chain
    check = runtime_root
    for part in [".qoder", "sessions", session_id, "workflows", "runs", run_id]:
        check = check / part
        if check.is_symlink():
            return None
    return wf_dir if wf_dir.is_dir() else None


def _workflow_child_transcript(
    runtime_root: Path,
    session_id: str,
    agent_id: str,
    declared_path: object = None,
) -> Optional[list[dict[str, Any]]]:
    """Resolve exactly one strict, non-symlinked child transcript snapshot."""
    if runtime_root.is_symlink():
        return None
    expected_name = f"agent-{agent_id}.jsonl"
    expected_suffix = f"/{session_id}/subagents/{expected_name}"
    if declared_path is not None:
        declared = _canonical_declared_path(declared_path)
        if declared is None or not declared.endswith(expected_suffix):
            return None
    candidates = list(
        (runtime_root / "config-projects").glob(
            f"*/{session_id}/subagents/{expected_name}"
        )
    )
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    try:
        relative = candidate.relative_to(runtime_root)
    except ValueError:
        return None
    current = runtime_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return None
    return _read_jsonl_strict(candidate)


def _build_workflow_child_calls_real(
    session_id: str,
    run_id: str,
    task_id: str,
    manifest: dict[str, Any],
    journal_events: list[dict[str, Any]],
    main_trace_events: list[dict[str, Any]],
    wf_tool_use_id: str,
    workflow_runtime_root: Path,
    workflow_result_index: Optional[int] = None,
    workflow_notification_index: Optional[int] = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Build normalized agent call records from real Qoder 1.0.48 Workflow evidence.

    Returns (calls, protocol_failures).  If protocol_failures is non-empty,
    the calls list must be discarded — the Workflow evidence is unreliable.
    """
    failures: list[str] = []

    # 1. Extract agents from manifest (authoritative lifecycle)
    manifest_agents = manifest.get("agents")
    if not isinstance(manifest_agents, list) or not manifest_agents:
        failures.append("workflow_manifest_agents_missing")
        return [], failures

    # Manifest child identity must be one-to-one across every binding field.
    identity_fields = ("index", "label", "agentId", "journalKey")
    for field in identity_fields:
        values = [
            agent.get(field) if isinstance(agent, dict) else None
            for agent in manifest_agents
        ]
        if any(value is None or value == "" for value in values):
            failures.append(f"workflow_manifest_{field}_missing")
        elif len({str(value) for value in values}) != len(values):
            failures.append(f"workflow_manifest_{field}_duplicate")
    indices = [
        agent.get("index") if isinstance(agent, dict) else None
        for agent in manifest_agents
    ]
    if indices != list(range(1, len(manifest_agents) + 1)):
        failures.append("workflow_manifest_index_sequence_invalid")
    if failures:
        return [], failures

    # 2. Build strict journal lifecycle indices.  Every manifest journalKey
    # must have exactly one started followed by exactly one result.
    journal_started: dict[str, int] = {}
    journal_results: dict[str, dict[str, Any]] = {}
    journal_result_indices: dict[str, int] = {}
    manifest_journal_keys = {
        str(agent["journalKey"]) for agent in manifest_agents if isinstance(agent, dict)
    }
    for event_index, evt in enumerate(journal_events):
        event_type = evt.get("type")
        key = evt.get("key")
        if event_type not in {"started", "event", "result"}:
            failures.append("workflow_journal_event_type_unknown")
            continue
        if not isinstance(key, str) or not key:
            failures.append("workflow_journal_key_missing")
            continue
        if key not in manifest_journal_keys:
            failures.append("workflow_journal_key_unbound")
            continue
        if event_type == "started":
            if key in journal_started:
                failures.append("workflow_journal_duplicate_started_key")
                continue
            journal_started[key] = event_index
        elif event_type == "event":
            nested = evt.get("event")
            if (
                not isinstance(nested, dict)
                or nested.get("kind") not in {"attempt_started"}
            ):
                failures.append("workflow_journal_event_kind_unknown")
        elif event_type == "result":
            key = evt["key"]
            if key in journal_results:
                failures.append("workflow_journal_duplicate_result_key")
                continue
            journal_results[key] = evt
            journal_result_indices[key] = event_index
    for key in manifest_journal_keys:
        if key not in journal_started:
            failures.append("workflow_journal_started_missing")
        if key not in journal_results:
            failures.append("workflow_journal_result_missing")
        if (
            key in journal_started
            and key in journal_result_indices
            and journal_started[key] >= journal_result_indices[key]
        ):
            failures.append("workflow_journal_started_after_result")
    manifest_journal_order = [
        str(agent["agentId"])
        for agent in sorted(manifest_agents, key=lambda item: item["index"])
    ]
    journal_agent_order = [
        str(next(
            agent["agentId"] for agent in manifest_agents
            if agent["journalKey"] == key
        ))
        for key, _ in sorted(journal_started.items(), key=lambda item: item[1])
    ]
    if journal_agent_order != manifest_journal_order:
        failures.append("workflow_manifest_index_journal_order_mismatch")
    if failures:
        return [], failures

    # 3. Index main trace events by parent_tool_use_id (child activity).
    # Include ALL event types (not just system) so delegated model evidence
    # from assistant messages can be captured.
    trace_children: dict[str, list[dict[str, Any]]] = {}
    for evt in main_trace_events:
        if evt.get("subtype") == "task_notification":
            continue
        parent = evt.get("parent_tool_use_id")
        if parent == wf_tool_use_id or str(parent) == str(wf_tool_use_id):
            child_task = evt.get("task_id", "")
            if isinstance(child_task, str) and child_task:
                trace_children.setdefault(child_task, []).append(evt)

    # Root-trace child lifecycle is still on the same global trace as the
    # Workflow transport.  A child event outside the tool_result →
    # task_notification interval cannot be attributed to this invocation.
    if workflow_result_index is not None and workflow_notification_index is not None:
        if workflow_result_index >= workflow_notification_index:
            failures.append("workflow_global_interval_invalid")
            return [], failures
        for child_events in trace_children.values():
            for event in child_events:
                event_index = event.get("_trace_index")
                if not isinstance(event_index, int):
                    failures.append("workflow_trace_child_global_index_missing")
                elif not workflow_result_index < event_index < workflow_notification_index:
                    failures.append("workflow_trace_child_outside_interval")
        if failures:
            return [], failures

    manifest_start_order = [
        str(agent["agentId"])
        for agent in sorted(manifest_agents, key=lambda item: item["index"])
    ]
    observed_starts = sorted(
        (
            int(event["_trace_index"]),
            agent_id,
        )
        for agent_id, child_events in trace_children.items()
        for event in child_events
        if event.get("subtype") == "task_started"
        and isinstance(event.get("_trace_index"), int)
    )
    observed_start_ids = [agent_id for _, agent_id in observed_starts]
    unknown_start_ids = set(observed_start_ids) - set(manifest_start_order)
    if unknown_start_ids:
        failures.append("workflow_trace_child_unbound")
        return [], failures
    if len(observed_start_ids) == len(manifest_start_order):
        if observed_start_ids != manifest_start_order:
            failures.append("workflow_manifest_index_start_order_mismatch")
            return [], failures
    elif observed_start_ids:
        positions = [manifest_start_order.index(agent_id) for agent_id in observed_start_ids]
        if positions != sorted(positions):
            failures.append("workflow_manifest_index_start_order_mismatch")
            return [], failures

    # 4. Build calls from manifest agents, cross-validated against journal + trace
    calls: list[dict[str, Any]] = []
    for idx, agent in enumerate(manifest_agents):
        if not isinstance(agent, dict):
            failures.append(f"workflow_manifest_agent_{idx}_malformed")
            continue

        label = agent.get("label")
        agent_id = agent.get("agentId")
        agent_type = agent.get("agentType")
        state = agent.get("state")
        journal_key = agent.get("journalKey")
        agent_index = agent.get("index")

        # All binding fields must be present and valid
        if not isinstance(label, str) or not label:
            failures.append(f"workflow_agent_{idx}_label_missing")
            continue
        if not isinstance(agent_id, str) or not agent_id:
            failures.append(f"workflow_agent_{idx}_agentId_missing")
            continue
        if not isinstance(agent_type, str) or not agent_type:
            failures.append(f"workflow_agent_{idx}_agentType_missing")
            continue
        if not isinstance(state, str) or not state:
            failures.append(f"workflow_agent_{idx}_state_missing")
            continue
        if not isinstance(journal_key, str) or not journal_key:
            failures.append(f"workflow_agent_{idx}_journalKey_missing")
            continue

        # 5. Cross-validate: journal must have a result for this key
        journal_result = journal_results.get(journal_key)
        if journal_result is None:
            failures.append(f"workflow_agent_{label}_journal_result_missing")
            continue
        # Verify journal agentId matches manifest
        journal_agent_id = journal_result.get("agentId")
        if journal_agent_id != agent_id:
            failures.append(f"workflow_agent_{label}_journal_agentId_mismatch")
            continue
        journal_result_value = journal_result.get("result")
        if not isinstance(journal_result_value, dict):
            failures.append(f"workflow_agent_{label}_journal_result_malformed")
            continue
        result_state = str(journal_result_value.get("state") or "").casefold()
        result_agent_type = journal_result_value.get("agentType")
        raw_result = journal_result_value.get("rawResult")
        raw_state = str(raw_result.get("state") or "").casefold() if isinstance(raw_result, dict) else ""
        if result_state not in {"done", "completed"}:
            failures.append(f"workflow_agent_{label}_journal_result_{result_state or 'state_missing'}")
            continue
        if result_agent_type != agent_type:
            failures.append(f"workflow_agent_{label}_journal_agentType_mismatch")
            continue
        if not isinstance(raw_result, dict):
            failures.append(f"workflow_agent_{label}_journal_raw_result_missing")
            continue
        if (
            raw_result.get("agentId") != agent_id
            or raw_result.get("agentType") != agent_type
            or raw_state not in {"done", "completed"}
        ):
            failures.append(f"workflow_agent_{label}_journal_raw_result_identity_mismatch")
            continue
        manifest_transcript_path = agent.get("transcriptPath")
        journal_transcript_path = (
            journal_result_value.get("transcriptPath")
        )
        raw_transcript_path = raw_result.get("transcriptPath")
        transcript_suffix = (
            f"/{session_id}/subagents/agent-{agent_id}.jsonl"
        )
        if (
            not isinstance(manifest_transcript_path, str)
            or not manifest_transcript_path.endswith(transcript_suffix)
            or journal_transcript_path != manifest_transcript_path
            or raw_transcript_path != manifest_transcript_path
        ):
            failures.append(f"workflow_agent_{label}_transcript_identity_mismatch")
            continue

        # 6. Cross-validate: main trace must have child activity for this agentId.
        # Each child event must belong to the same session/workflow.
        child_events = trace_children.get(agent_id, [])
        child_transcript = _workflow_child_transcript(
            workflow_runtime_root, session_id, agent_id, manifest_transcript_path,
        )
        conflicting_root_terminal = next(
            (
                event.get("subtype")
                for event in child_events
                if event.get("subtype") in {
                    "task_failed", "task_cancelled", "task_timeout",
                    "task_error", "task_unknown",
                }
            ),
            None,
        )
        if conflicting_root_terminal:
            failures.append(
                f"workflow_agent_{label}_conflicting_terminal_"
                f"{conflicting_root_terminal}"
            )
            continue
        use_snapshot_transcript = not (
            sum(event.get("subtype") == "task_started" for event in child_events) == 1
            and sum(event.get("subtype") == "task_completed" for event in child_events) == 1
        )
        if use_snapshot_transcript:
            if child_transcript is None:
                failures.append(f"workflow_agent_{label}_trace_children_missing")
                continue
            child_events = child_transcript
        # Verify every child event belongs to this Workflow's session.
        # Missing session_id on a child event is also a protocol failure —
        # every event must be traceable to its owning Workflow.
        for ce in child_events:
            ce_session = ce.get("session_id")
            if not isinstance(ce_session, str) or not ce_session:
                failures.append(f"workflow_agent_{label}_missing_session")
                break
            if ce_session != session_id:
                failures.append(f"workflow_agent_{label}_cross_session_event")
                break
            if use_snapshot_transcript and (
                ce.get("agent_id") != agent_id
                or ce.get("agent_type") != agent_type
                or ce.get("task_id") != agent_id
                or ce.get("parent_tool_use_id") != wf_tool_use_id
                or ce.get("tool_use_id") != wf_tool_use_id
            ):
                failures.append(f"workflow_agent_{label}_transcript_identity_mismatch")
                break
        else:
            pass  # no session issue found
        if failures and (failures[-1].endswith("_cross_session_event") or failures[-1].endswith("_missing_session")):
            continue

        # 7. Determine terminal status from manifest state.
        # Only "done" is a successful terminal state.
        # All other states (failed, error, cancelled, timeout, unknown) must
        # produce explicit protocol failures — no child call is created.
        if state == "done":
            terminal_status = "completed"
        elif state in ("failed", "error", "cancelled", "timeout"):
            failures.append(f"workflow_agent_{label}_{state}_state")
            continue
        else:
            failures.append(f"workflow_agent_{label}_non_terminal_state")
            continue

        # 8. Extract stage markers from main trace child event descriptions
        stage_markers: list[str] = []
        for ce in child_events:
            message = ce.get("message")
            content = message.get("content") if isinstance(message, dict) else ""
            if isinstance(content, list):
                content = " ".join(
                    str(item.get("text", ""))
                    for item in content if isinstance(item, dict)
                )
            evidence_text = f"{ce.get('description', '')}\n{content}"
            found = re.findall(
                r"\[[a-z0-9-]+:[a-z0-9-]+\]",
                evidence_text,
                flags=re.IGNORECASE,
            )
            for m in found:
                if m not in stage_markers:
                    stage_markers.append(m)
        expected_marker = f"[eval-stage:{label}]".casefold()
        if expected_marker not in {marker.casefold() for marker in stage_markers}:
            failures.append(f"workflow_agent_{label}_stage_marker_mismatch")
            continue

        # 9. Bind unique started and terminal runtime events.
        # Reject duplicate or conflicting lifecycle: exactly one task_started
        # and exactly one task_completed are required.
        # task_progress is NOT a terminal event.
        # Any co-existing failed, cancelled, timeout, or unknown lifecycle
        # events (task_failed, task_cancelled, etc.) are also rejected.
        started_count = 0
        completed_count = 0
        started_index = None
        completed_index = None
        for ce in child_events:
            subtype = ce.get("subtype", "")
            if subtype == "task_started":
                started_count += 1
                if started_index is None:
                    started_index = ce.get("_trace_index")
            if subtype == "task_completed":
                completed_count += 1
                if completed_index is None:
                    completed_index = ce.get("_trace_index")
            # Reject conflicting terminal subtypes
            if subtype in ("task_failed", "task_cancelled", "task_timeout",
                           "task_error", "task_unknown"):
                failures.append(
                    f"workflow_agent_{label}_conflicting_terminal_{subtype}"
                )
                break
        if failures:
            continue
        if started_count != 1:
            failures.append(f"workflow_agent_{label}_started_event_count_{started_count}")
            continue
        if completed_count != 1:
            failures.append(f"workflow_agent_{label}_completed_event_count_{completed_count}")
            continue
        if use_snapshot_transcript:
            if workflow_result_index is None or workflow_notification_index is None:
                failures.append(f"workflow_agent_{label}_global_timeline_missing")
                continue
            if workflow_result_index >= workflow_notification_index:
                failures.append(f"workflow_agent_{label}_workflow_interval_invalid")
                continue
            child_position = manifest_start_order.index(str(agent_id))
            child_count = len(manifest_start_order)
            interval = workflow_notification_index - workflow_result_index
            started_index = workflow_result_index + interval * (child_position + 0.25) / (child_count + 1)
            completed_index = workflow_result_index + interval * (child_position + 0.75) / (child_count + 1)
        if started_index is None or completed_index is None:
            failures.append(f"workflow_agent_{label}_missing_lifecycle_index")
            continue
        # started MUST precede terminal in the trace
        if started_index >= completed_index:
            failures.append(f"workflow_agent_{label}_started_after_terminal")
            continue

        # 10. Extract delegated model from child events.
        # Every child agent MUST have at least one real model event —
        # an empty delegated_models list means the child produced no
        # verifiable model evidence and the protocol is compromised.
        delegated_models: list[str] = []
        for ce in child_events:
            msg = ce.get("message")
            if isinstance(msg, dict):
                model = msg.get("model")
                if isinstance(model, str) and model and model not in delegated_models:
                    delegated_models.append(model)
        if not delegated_models:
            failures.append(f"workflow_agent_{label}_no_delegated_model")
            continue

        calls.append({
            "id": agent_id,
            "role": agent_type,
            "role_source": "workflow_manifest_agentType",
            "task_name": label,
            "description": label,
            "prompt": label,
            "stage_markers": stage_markers,
            "status": terminal_status,
            "trace_index": completed_index,
            "requested_trace_index": started_index,
            "runtime_status": terminal_status,
            "agents_states": {},
            "agent_terminal_states": [terminal_status],
            "background_task_id": task_id,
            "delegated_models": delegated_models,
            "workflow_run_id": run_id,
            "workflow_session_id": session_id,
            "manifest_index": agent_index,
            "manifest_label": label,
            "journal_key": journal_key,
        })

    return calls, failures


def classify_workflow_write_set(
    paths: set[str],
    session_id: str,
    run_id: str,
    declared_script_path: object = None,
) -> set[str]:
    """Return the subset of paths that are bound Workflow runtime artifacts.

    Only the exact bound run directory and, when fully cross-bound by the
    Workflow transport/artifacts, the exact declared script are legitimate.
    Sibling runs, scripts, metadata, and other non-run paths remain visible.
    """
    prefix = f".qoder/sessions/{session_id}/workflows/runs/{run_id}/"
    bound = {path for path in paths if path.startswith(prefix)}
    declared = _canonical_declared_path(declared_script_path)
    script_prefix = f"/.qoder/sessions/{session_id}/workflows/scripts/"
    marker = declared.find(script_prefix) if declared else -1
    if marker >= 0 and declared.endswith(".js"):
        relative = declared[marker + 1:]
        if relative in paths:
            bound.add(relative)
    return bound


def qoder_tool_uses(event: dict[str, Any]) -> list[dict[str, Any]]:
    message = event.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict) and item.get("type") == "tool_use"]


def agent_terminal_states(agents_states: dict[str, Any]) -> list[str]:
    states = []
    for value in agents_states.values():
        if isinstance(value, dict):
            state = value.get("status") or value.get("state")
        else:
            state = value
        states.append(str(state or "unknown").casefold())
    return states


def explicit_agent_role(input_value: dict[str, Any]) -> tuple[object, Optional[str]]:
    if input_value.get("subagent_type"):
        return input_value["subagent_type"], "subagent_type"
    if input_value.get("agent_type"):
        return input_value["agent_type"], "agent_type"
    return None, None


def codex_tool_use(event: dict[str, Any]) -> Optional[dict[str, Any]]:
    item = event.get("item")
    if not isinstance(item, dict) and event.get("type") == "collab_tool_call":
        item = event
    if not isinstance(item, dict):
        return None
    if item.get("type") != "collab_tool_call":
        return None
    name = item.get("name") or item.get("tool") or item.get("tool_name")
    if name not in AGENT_NAMES and not str(name).endswith("spawn_agent"):
        return None
    arguments = item.get("arguments") or item.get("input") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {"raw": arguments}
    agents_states = item.get("agents_states") if isinstance(item.get("agents_states"), dict) else {}
    outer_status = str(item.get("status") or event.get("status") or "unknown").casefold()
    child_states = agent_terminal_states(agents_states)
    effective_status = (
        "completed"
        if outer_status == "completed"
        and bool(child_states)
        and all(state in SUCCESSFUL_AGENT_STATES for state in child_states)
        else "failed"
    )
    return {
        "id": item.get("id") or item.get("call_id"),
        "name": name,
        "input": arguments if isinstance(arguments, dict) else {},
        "prompt": item.get("prompt") or arguments.get("prompt") or arguments.get("message"),
        "status": effective_status,
        "runtime_status": outer_status,
        "agents_states": agents_states,
        "agent_terminal_states": child_states,
    }


def grade_primary_collaboration_canary(path: Path, marker: str) -> dict[str, Any]:
    """Strictly grade one Primary spawn lifecycle without trusting payload prose."""
    protocol_errors: list[str] = []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        lines = []
        protocol_errors.append("primary_trace_protocol_unrecognized")
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            protocol_errors.append("primary_trace_protocol_unrecognized")
            continue
        if not isinstance(value, dict):
            protocol_errors.append("primary_trace_protocol_unrecognized")
            continue
        events.append(value)

    calls: dict[str, dict[str, Any]] = {}
    anonymous_calls: list[dict[str, Any]] = []
    for event_index, event in enumerate(events):
        item = event.get("item")
        if not isinstance(item, dict) and event.get("type") == "collab_tool_call":
            item = event
        if not isinstance(item, dict) or item.get("type") != "collab_tool_call":
            continue
        name = str(item.get("name") or item.get("tool") or item.get("tool_name") or "")
        if name not in AGENT_NAMES and not name.endswith((".spawn_agent", "__spawn_agent")):
            continue
        call_id = item.get("id") or item.get("call_id")
        call = (
            calls.setdefault(str(call_id), {"started_events": 0, "terminal_events": []})
            if call_id
            else {"started_events": 0, "terminal_events": []}
        )
        if not call_id:
            anonymous_calls.append(call)
        for key in ("prompt", "arguments", "input"):
            value = item.get(key)
            if value not in (None, "", {}, []):
                call[key] = value
        event_type = str(event.get("type") or "")
        if event_type == "item.started":
            call["started_events"] += 1
        if event_type in {"item.completed", "item.failed", "item.cancelled"}:
            call["terminal_events"].append(
                {
                    "event_type": event_type,
                    "status": str(item.get("status") or "unknown").casefold(),
                    "agents_states": item.get("agents_states"),
                    "receiver_thread_ids": item.get("receiver_thread_ids"),
                    "trace_index": event_index,
                }
            )

    all_calls = list(calls.values()) + anonymous_calls
    marker_calls = []
    for call in all_calls:
        arguments = call.get("arguments") or call.get("input") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                protocol_errors.append("primary_trace_protocol_unrecognized")
                arguments = {}
        prompt = call.get("prompt")
        if not prompt and isinstance(arguments, dict):
            prompt = arguments.get("prompt") or arguments.get("message")
        if marker in str(prompt or ""):
            marker_calls.append(call)

    selected = all_calls[0] if len(all_calls) == 1 else {}
    started_events = selected.get("started_events", 0)
    terminal_events = selected.get("terminal_events", [])
    terminal = terminal_events[0] if len(terminal_events) == 1 else {}
    states = terminal.get("agents_states") if isinstance(terminal.get("agents_states"), dict) else {}
    receiver_ids = terminal.get("receiver_thread_ids")
    identities = {str(value) for value in states if str(value)}
    if isinstance(receiver_ids, list):
        identities.update(str(value) for value in receiver_ids if str(value))
    child_states = agent_terminal_states(states)
    outer_status = str(terminal.get("status") or "unknown").casefold()
    terminal_event_type = str(terminal.get("event_type") or "")

    failure_codes = list(dict.fromkeys(protocol_errors))
    if len(all_calls) == 1 and started_events != 1:
        failure_codes.append("primary_trace_protocol_unrecognized")
    if len(all_calls) != 1:
        failure_codes.append("primary_spawn_count_invalid")
    if len(marker_calls) != 1 or len(all_calls) != 1:
        failure_codes.append("primary_spawn_marker_invalid")
    if (
        len(terminal_events) != 1
        or terminal_event_type != "item.completed"
        or outer_status != "completed"
    ):
        failure_codes.append("primary_outer_collaboration_incomplete")
    if len(identities) != 1:
        failure_codes.append("primary_child_identity_invalid")
    if len(states) != 1 or child_states != ["completed"]:
        failure_codes.append("primary_child_terminal_state_invalid")
    return {
        "passed": not failure_codes,
        "failure_codes": list(dict.fromkeys(failure_codes)),
        "spawn_count": len(all_calls),
        "marked_spawn_count": len(marker_calls),
        "outer_status": outer_status,
        "outer_terminal_event": terminal_event_type or None,
        "child_identities": sorted(identities),
        "child_terminal_states": child_states,
    }


def summarize(path: Path, workflow_runtime_root: Optional[Path] = None) -> dict[str, Any]:
    events, trace_valid = json_lines(path)
    runtime = "unknown"
    root_model = None
    tools: list[str] = []
    agents: list[str] = []
    calls: list[dict[str, Any]] = []
    command_calls: list[dict[str, Any]] = []
    tools_used: list[str] = []
    workflow_sessions: dict[str, dict[str, Any]] = {}
    trace_protocol_failures: list[str] = (
        [] if trace_valid else ["main_trace_malformed_jsonl"]
    )

    for event_index, event in enumerate(events):
        if event.get("type") == "system" and event.get("subtype") == "init":
            runtime = "qoder"
            root_model = event.get("model")
            tools = [str(value) for value in event.get("tools", [])]
            agents = [str(value) for value in event.get("agents", [])]
        elif event.get("type") == "collab_tool_call" or str(event.get("type", "")).startswith(("thread.", "turn.", "item.")):
            runtime = "primary"

        for use in qoder_tool_uses(event):
            tools_used.append(str(use.get("name") or ""))
            if use.get("name") in COMMAND_NAMES:
                input_value = use.get("input") if isinstance(use.get("input"), dict) else {}
                command_calls.append(
                    {
                        "id": use.get("id"),
                        "command": input_value.get("command") or input_value.get("cmd"),
                        "cwd": input_value.get("dir_path") or input_value.get("workdir"),
                        "status": "requested",
                        "trace_index": None,
                        "requested_trace_index": event_index,
                    }
                )
            if use.get("name") not in AGENT_NAMES:
                continue
            input_value = use.get("input") if isinstance(use.get("input"), dict) else {}
            agent_role, role_source = explicit_agent_role(input_value)
            task_name = input_value.get("task_name")
            description = input_value.get("description") or task_name
            prompt = input_value.get("prompt") or input_value.get("message")
            calls.append(
                {
                    "id": use.get("id"),
                    "role": agent_role,
                    "role_source": role_source,
                    "task_name": task_name,
                    "description": description,
                    "prompt": prompt,
                    "stage_markers": stage_markers(description, prompt),
                    "status": "requested",
                    "trace_index": None,
                    "requested_trace_index": event_index,
                    "agents_states": {},
                    "background_task_id": None,
                    "delegated_models": [],
                }
            )
        use = codex_tool_use(event)
        if use:
            tools_used.append(str(use.get("name") or "spawn_agent"))
            input_value = use["input"]
            agent_role, role_source = explicit_agent_role(input_value)
            task_name = input_value.get("task_name")
            prompt = use.get("prompt")
            description = prompt or input_value.get("description") or input_value.get("message") or task_name
            calls.append(
                {
                    "id": use.get("id"),
                    "role": agent_role,
                    "role_source": role_source,
                    "task_name": task_name,
                    "description": description,
                    "prompt": prompt,
                    "stage_markers": stage_markers(description, prompt),
                    "status": use.get("status"),
                    "trace_index": event_index,
                    "runtime_status": use.get("runtime_status"),
                    "agents_states": use.get("agents_states"),
                    "agent_terminal_states": use.get("agent_terminal_states"),
                    "background_task_id": None,
                    "delegated_models": [],
                }
            )
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            exit_code = item.get("exit_code")
            runtime_status = str(item.get("status") or "unknown").casefold()
            if runtime_status == "completed":
                effective_status = "completed" if exit_code in (None, 0) else "failed"
            elif runtime_status in {"failed", "error", "cancelled"}:
                effective_status = "failed"
            else:
                effective_status = "requested"
            command_calls.append(
                {
                    "id": item.get("id"),
                    "command": item.get("command") or item.get("cmd"),
                    "status": effective_status,
                    "exit_code": exit_code,
                    "trace_index": event_index,
                }
            )
            tools_used.append("command_execution")

        # -- Workflow tool-use detection (real Qoder 1.0.48 protocol) --
        # Workflow tool_use input only has { script: "..." }.
        # IDs (taskId, runId) come from the tool_result payload, not input.
        for use in qoder_tool_uses(event):
            if use.get("name") not in WORKFLOW_NAMES:
                continue
            tools_used.append("Workflow")
            tool_use_id = str(use.get("id", ""))
            if not tool_use_id:
                trace_protocol_failures.append("workflow_tool_use_id_missing")
                continue
            if tool_use_id in workflow_sessions:
                prior_session = workflow_sessions[tool_use_id].get("session_id")
                event_session = event.get("session_id")
                code = (
                    "workflow_tool_use_id_cross_session"
                    if prior_session and event_session != prior_session
                    else "workflow_tool_use_id_duplicate"
                )
                trace_protocol_failures.append(code)
                continue
            workflow_sessions[tool_use_id] = {
                "tool_use_id": tool_use_id,
                "session_id": (
                    event.get("session_id")
                    if isinstance(event.get("session_id"), str)
                    else ""
                ),
                "run_id": "",
                "task_id": "",
                "transcript_dir": "",
                "script_path": "",
                "notification_output_file": "",
                "status": "requested",
                "trace_index": event_index,
                "tool_result_trace_index": None,
                "notification_trace_index": None,
                "evidence_valid": False,
                "protocol_failures": [],
                "tool_result_count": 0,
                "notification_count": 0,
            }

    # Second pass: resolve Workflow IDs from tool_result and system events.
    # Also tag system events with _trace_index for child activity tracking.
    # Each Workflow binds its own session_id from its tool_use event, not from
    # the first global system init event.  Child events must also verify session.
    # Build a mapping of tool_use_id → session_id from tool_use events first.
    for event_index, event in enumerate(events):
        event["_trace_index"] = event_index
        for use in qoder_tool_uses(event):
            if use.get("name") in WORKFLOW_NAMES:
                tuid = str(use.get("id", ""))
                if tuid in workflow_sessions and not workflow_sessions[tuid]["session_id"]:
                    evt_session = event.get("session_id")
                    if isinstance(evt_session, str) and evt_session:
                        workflow_sessions[tuid]["session_id"] = evt_session
    for event_index, event in enumerate(events):
        # Parse Workflow tool_result for IDs (real protocol)
        message = event.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict) or item.get("type") != "tool_result":
                        continue
                    tuid = str(item.get("tool_use_id", ""))
                    if tuid not in workflow_sessions:
                        continue
                    wf = workflow_sessions[tuid]
                    wf["tool_result_count"] += 1
                    wf["tool_result_trace_index"] = event_index
                    if wf["tool_result_count"] > 1:
                        wf["protocol_failures"].append(
                            f"workflow_tool_result_count_{wf['tool_result_count']}"
                        )
                    # Verify tool_result belongs to same session as the workflow
                    result_session = event.get("session_id")
                    wf_session = wf.get("session_id")
                    if not isinstance(result_session, str) or not result_session:
                        wf["protocol_failures"].append(
                            "workflow_tool_result_session_missing"
                        )
                    elif result_session != wf_session:
                        wf["protocol_failures"].append(
                            "workflow_tool_result_cross_session"
                        )
                    # Parse payload from tool_use_result or content text
                    payload = None
                    tur = event.get("tool_use_result")
                    if isinstance(tur, dict):
                        raw_payload = tur.get("payload")
                        if isinstance(raw_payload, str):
                            try:
                                payload = json.loads(raw_payload)
                            except json.JSONDecodeError:
                                pass
                    if payload is None:
                        # Try content text for embedded IDs
                        text_content = item.get("content", "")
                        if isinstance(text_content, str):
                            task_match = re.search(r"taskId:\s*(\S+)", text_content)
                            run_match = re.search(r"runId:\s*(\S+)", text_content)
                            if task_match:
                                wf["task_id"] = task_match.group(1)
                            if run_match:
                                wf["run_id"] = run_match.group(1)
                    else:
                        wf["task_id"] = str(payload.get("taskId", ""))
                        wf["run_id"] = str(payload.get("runId", ""))
                        wf["transcript_dir"] = str(payload.get("transcriptDir", ""))
                        wf["script_path"] = str(payload.get("scriptPath", ""))
        # System task_notification events for Workflow completion.
        # Verify session consistency: the notification must belong to the
        # same session as the Workflow it reports on.
        if event.get("type") == "system" and event.get("subtype") == "task_notification":
            task_id = str(event.get("task_id", ""))
            notification_tool_id = str(event.get("tool_use_id", ""))
            notif_session = event.get("session_id")
            for wf in workflow_sessions.values():
                task_matches = bool(task_id) and wf["task_id"] == task_id
                tool_matches = (
                    bool(notification_tool_id)
                    and wf["tool_use_id"] == notification_tool_id
                )
                if not (task_matches or tool_matches):
                    continue
                wf["notification_count"] += 1
                if wf["notification_count"] > 1:
                    wf["protocol_failures"].append(
                        f"workflow_notification_count_{wf['notification_count']}"
                    )
                if not task_matches or not tool_matches:
                    wf["protocol_failures"].append(
                        "workflow_notification_identity_mismatch"
                    )
                wf_session = wf.get("session_id")
                if not isinstance(notif_session, str) or not notif_session:
                    wf["protocol_failures"].append(
                        "workflow_notification_session_missing"
                    )
                elif notif_session != wf_session:
                    wf["protocol_failures"].append(
                        "workflow_notification_cross_session"
                    )
                wf_status = str(event.get("status") or "").casefold()
                wf["notification_output_file"] = str(event.get("output_file", ""))
                if wf_status:
                    wf["status"] = wf_status
                    wf["trace_index"] = event_index
                    wf["notification_trace_index"] = event_index

    # Resolve Workflow runtime artifacts and build child agent calls.
    # Fail closed with EXPLICIT protocol failures — no silent continue.
    # A detected Workflow invocation that cannot produce valid child evidence
    # generates failures that cannot be masked by direct Agent calls.
    workflow_protocol_failures: list[str] = list(trace_protocol_failures)
    # Flush per-workflow protocol failures (from tool_result/notification checks)
    for wf in workflow_sessions.values():
        if wf.get("tool_result_count") != 1:
            wf["protocol_failures"].append(
                f"workflow_tool_result_count_{wf.get('tool_result_count', 0)}"
            )
        if wf.get("notification_count") != 1:
            wf["protocol_failures"].append(
                f"workflow_notification_count_{wf.get('notification_count', 0)}"
            )
        workflow_protocol_failures.extend(wf.get("protocol_failures", []))
    if workflow_sessions:
        if workflow_runtime_root is None:
            workflow_protocol_failures.append("workflow_runtime_root_unavailable")
        else:
            for wf in workflow_sessions.values():
                # Invocation-level identity/lifecycle failures invalidate every
                # child attributed to this Workflow.  Runtime artifacts cannot
                # repair an ambiguous or unbound transport event.
                if wf.get("protocol_failures"):
                    continue
                session_id = _safe_opaque_id(wf.get("session_id"))
                run_id = _safe_opaque_id(wf.get("run_id"))
                if not session_id or not run_id:
                    workflow_protocol_failures.append("workflow_id_unresolvable")
                    continue

                wf_dir = _resolve_workflow_dir(workflow_runtime_root, session_id, run_id)
                if wf_dir is None:
                    workflow_protocol_failures.append("workflow_runtime_dir_unresolvable")
                    continue

                manifest = _read_json_file_strict(wf_dir / "manifest.json")
                journal_events = _read_jsonl_strict(wf_dir / "journal.jsonl")
                output = _read_json_file_strict(wf_dir / "output.json")

                if any(
                    (wf_dir / name).is_symlink()
                    for name in ("manifest.json", "journal.jsonl", "output.json")
                ):
                    workflow_protocol_failures.append("workflow_artifact_symlink")
                    continue

                # All three artifacts must be present and strictly parseable.
                # Missing or corrupt = explicit protocol failure, not silent skip.
                if manifest is None:
                    workflow_protocol_failures.append("workflow_manifest_missing_or_corrupt")
                    continue
                if journal_events is None:
                    workflow_protocol_failures.append("workflow_journal_missing_or_corrupt")
                    continue
                if output is None:
                    workflow_protocol_failures.append("workflow_output_missing_or_corrupt")
                    continue

                # Cross-validate manifest runId against trace-derived run_id
                manifest_run_id = manifest.get("runId")
                if manifest_run_id != run_id:
                    workflow_protocol_failures.append("workflow_manifest_runId_mismatch")
                    continue

                # Cross-validate output identity and terminal status.
                # output.json MUST have matching runId, taskId, and a
                # successful terminal status.  Any mismatch or non-completed
                # status is an explicit protocol failure.
                output_run_id = output.get("runId")
                output_task_id = output.get("taskId")
                output_status = str(output.get("status", "")).casefold()
                if output_run_id != run_id:
                    workflow_protocol_failures.append("workflow_output_runId_mismatch")
                    continue
                wf_task_id = wf.get("task_id", "")
                # output taskId MUST be present — missing identity is a protocol failure
                if not isinstance(output_task_id, str) or not output_task_id:
                    workflow_protocol_failures.append("workflow_output_taskId_missing")
                    continue
                if output_task_id != wf_task_id:
                    workflow_protocol_failures.append("workflow_output_taskId_mismatch")
                    continue
                if output_status not in ("completed", "done"):
                    workflow_protocol_failures.append(f"workflow_output_status_{output_status}")
                    continue

                manifest_status = str(manifest.get("status", "")).casefold()
                if manifest_status not in {"completed", "done"}:
                    workflow_protocol_failures.append(
                        f"workflow_manifest_status_{manifest_status or 'missing'}"
                    )
                    continue
                if manifest_status != output_status:
                    workflow_protocol_failures.append("workflow_manifest_output_status_mismatch")
                    continue

                transcript_dir = _canonical_declared_path(wf.get("transcript_dir"))
                script_path = _canonical_declared_path(wf.get("script_path"))
                output_file = _canonical_declared_path(
                    wf.get("notification_output_file")
                )
                run_suffix = (
                    f"/.qoder/sessions/{session_id}/workflows/runs/{run_id}"
                )
                script_prefix = (
                    f"/.qoder/sessions/{session_id}/workflows/scripts/"
                )
                if transcript_dir is None or not transcript_dir.endswith(run_suffix):
                    workflow_protocol_failures.append("workflow_transcriptDir_mismatch")
                    continue
                if (
                    script_path is None
                    or script_prefix not in script_path
                    or not script_path.endswith(".js")
                    or Path(script_path).name in {"", ".", ".."}
                ):
                    workflow_protocol_failures.append("workflow_scriptPath_mismatch")
                    continue
                expected_output_file = f"{transcript_dir}/output.json"
                if output_file != expected_output_file:
                    workflow_protocol_failures.append("workflow_notification_output_file_mismatch")
                    continue
                if manifest.get("scriptPath") != script_path:
                    workflow_protocol_failures.append("workflow_manifest_scriptPath_mismatch")
                    continue
                if manifest.get("outputPath") != expected_output_file:
                    workflow_protocol_failures.append("workflow_manifest_outputPath_mismatch")
                    continue
                if output.get("scriptPath") != script_path:
                    workflow_protocol_failures.append("workflow_output_scriptPath_mismatch")
                    continue
                if output.get("transcriptDir") != transcript_dir:
                    workflow_protocol_failures.append("workflow_output_transcriptDir_mismatch")
                    continue

                # Workflow notification must confirm successful terminal status.
                # A task_notification with failed/cancelled/timeout status means
                # the Workflow itself did not complete successfully, regardless
                # of individual child states in the manifest.
                wf_notification_status = str(wf.get("status", "")).casefold()
                if wf_notification_status != "completed":
                    workflow_protocol_failures.append(f"workflow_notification_status_{wf_notification_status}")
                    continue
                if wf_notification_status != output_status or wf_notification_status != manifest_status:
                    workflow_protocol_failures.append("workflow_manifest_output_notification_status_mismatch")
                    continue

                child_calls, child_failures = _build_workflow_child_calls_real(
                    session_id,
                    run_id,
                    wf.get("task_id", ""),
                    manifest,
                    journal_events,
                    events,
                    wf.get("tool_use_id", ""),
                    workflow_runtime_root,
                    wf.get("tool_result_trace_index"),
                    wf.get("notification_trace_index"),
                )
                if child_failures:
                    workflow_protocol_failures.extend(child_failures)
                    # Do NOT add partial calls — protocol is compromised
                    continue

                calls.extend(child_calls)
                wf["evidence_valid"] = True


    if not trace_valid or trace_protocol_failures:
        calls = []

    unique_by_id: dict[str, dict[str, Any]] = {}
    unique_without_id = []
    for call in calls:
        call_id = call.get("id")
        if call_id:
            prior = unique_by_id.get(call_id)
            if prior is None or call.get("status") in {"completed", "failed", "error", "cancelled"}:
                unique_by_id[call_id] = call
        else:
            unique_without_id.append(call)
    calls = list(unique_by_id.values()) + unique_without_id
    calls.sort(key=lambda call: (
        call.get("trace_index") is None,
        call.get("trace_index") if call.get("trace_index") is not None else 0,
    ))
    by_id = {call["id"]: call for call in calls if call.get("id")}
    commands_by_id = {call["id"]: call for call in command_calls if call.get("id")}
    for event_index, event in enumerate(events):
        parent = event.get("parent_tool_use_id")
        message = event.get("message")
        model = message.get("model") if isinstance(message, dict) else None
        if parent in by_id and model and model not in by_id[parent]["delegated_models"]:
            by_id[parent]["delegated_models"].append(model)
        item = event.get("item")
        if isinstance(item, dict):
            call_id = item.get("parent_call_id") or item.get("call_id")
            delegated_model = item.get("model")
            if call_id in by_id and delegated_model and delegated_model not in by_id[call_id]["delegated_models"]:
                by_id[call_id]["delegated_models"].append(delegated_model)

        if event.get("type") == "system":
            tool_use_id = event.get("tool_use_id")
            task_id = event.get("task_id")
            if tool_use_id in by_id and task_id:
                by_id[tool_use_id]["background_task_id"] = task_id
                task_status = str(event.get("status") or "").casefold()
                if task_status == "completed":
                    by_id[tool_use_id]["status"] = "completed"
                    by_id[tool_use_id]["trace_index"] = event_index
                elif task_status in {"failed", "error", "cancelled", "stopped"}:
                    by_id[tool_use_id]["status"] = "failed"
                    by_id[tool_use_id]["trace_index"] = event_index

        message_content = message.get("content") if isinstance(message, dict) else None
        if isinstance(message_content, list):
            for item in message_content:
                if not isinstance(item, dict) or item.get("type") != "tool_result":
                    continue
                tool_use_id = item.get("tool_use_id")
                tool_result = event.get("tool_use_result")
                if isinstance(tool_result, dict):
                    state = (
                        tool_result.get("state")
                        or tool_result.get("status")
                        or tool_result.get("kind")
                    )
                else:
                    state = None
                if tool_use_id in by_id:
                    if item.get("is_error") is True or state in {"failed", "error", "cancelled"}:
                        by_id[tool_use_id]["status"] = "failed"
                        by_id[tool_use_id]["trace_index"] = event_index
                    elif state == "completed" or item.get("is_error") is False:
                        by_id[tool_use_id]["status"] = "completed"
                        by_id[tool_use_id]["trace_index"] = event_index
                if tool_use_id in commands_by_id:
                    result = tool_result if isinstance(tool_result, dict) else {}
                    exit_code = result.get("exit_code", result.get("exitCode"))
                    failed = (
                        item.get("is_error") is True
                        or state in {"failed", "error", "cancelled"}
                        or result.get("interrupted") is True
                        or exit_code not in (None, 0)
                    )
                    commands_by_id[tool_use_id]["status"] = "failed" if failed else "completed"
                    commands_by_id[tool_use_id]["trace_index"] = event_index
                    if exit_code is not None:
                        commands_by_id[tool_use_id]["exit_code"] = exit_code

    terminal_command_states = {"completed", "failed"}
    unique_commands_by_id: dict[str, dict[str, Any]] = {}
    unique_commands_without_id = []
    for call in command_calls:
        call_id = call.get("id")
        if not call_id:
            unique_commands_without_id.append(call)
            continue
        prior = unique_commands_by_id.get(call_id)
        if prior is None or call.get("status") in terminal_command_states:
            unique_commands_by_id[call_id] = call
    command_calls = list(unique_commands_by_id.values()) + unique_commands_without_id

    successful_calls = [call for call in calls if call.get("status") == "completed"]
    if runtime == "primary" and calls:
        tools = sorted(set(tools) | {"spawn_agent", "Agent"})
        agents = sorted(set(agents) | {str(call["role"]) for call in successful_calls if call.get("role")})
    # Workflow child calls also populate agents from runtime evidence
    if workflow_sessions and calls:
        agents = sorted(set(agents) | {str(call["role"]) for call in successful_calls if call.get("role")})
        tools = sorted(set(tools) | {"Agent"})
    for call in command_calls:
        call["segments"] = observable_commands(call.get("command"), call.get("cwd"))
    delegated_models = sorted(
        {model for call in successful_calls for model in call.get("delegated_models", [])}
    )
    background_completion_observed = any(
        call.get("background_task_id") for call in successful_calls
    )
    return {
        "runtime": runtime,
        "root_model": root_model,
        "capabilities": {"tools": tools, "agents": agents},
        "agent_calls": successful_calls,
        "agent_call_count": len(successful_calls),
        "attempted_agent_calls": calls,
        "rejected_agent_call_count": len(calls) - len(successful_calls),
        "command_calls": command_calls,
        "tools_used": sorted(set(tools_used)),
        "delegated_models": delegated_models,
        "delegated_model_observation": (
            "unknown/unavailable"
            if runtime == "primary"
            else "observed-in-trace"
            if delegated_models
            else "runtime-task-completion-observed-model-unavailable"
            if background_completion_observed
            else "unknown/unavailable"
        ),
        "workflow_sessions": list(workflow_sessions.values()),
        "workflow_protocol_failures": workflow_protocol_failures,
    }


def grade(summary: dict[str, Any], expected: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    checks: list[str] = []
    failures: list[str] = []
    failure_codes: list[str] = []

    def check(condition: bool, message: str, code: str) -> None:
        (checks if condition else failures).append(message)
        if not condition:
            failure_codes.append(code)

    # Workflow protocol failures are explicit and cannot be masked by direct Agent calls
    wf_protocol_failures = summary.get("workflow_protocol_failures", [])
    if wf_protocol_failures:
        for pf in wf_protocol_failures:
            failures.append(f"workflow protocol failure: {pf}")
            failure_codes.append("workflow_protocol_failure")

    capabilities = summary["capabilities"]
    for tool in expected.get("capability_tools", []):
        check(tool in capabilities["tools"], f"runtime exposes delegation tool: {tool}", "delegation_tool_available")
    for agent in expected.get("capability_agents", []):
        check(agent in capabilities["agents"], f"runtime exposes delegation role: {agent}", "delegation_role_available")
    tools_used = {tool.casefold() for tool in summary.get("tools_used", [])}
    for tool in expected.get("forbidden_tools", []):
        check(
            tool.casefold() not in tools_used,
            f"runtime does not invoke global tool: {tool}",
            "forbidden_runtime_tool",
        )
    calls = summary["agent_calls"]
    known_markers = expected.get("known_stage_markers", {})
    known_marker_values = set(known_markers.values())
    if expected.get("require_marker_for_agent_calls"):
        marker_shape_ok = all(
            len([marker for marker in call.get("stage_markers", []) if marker in known_marker_values]) == 1
            and len(call.get("stage_markers", [])) == 1
            for call in calls
        )
        check(marker_shape_ok, "every completed Agent call has exactly one known stage marker", "delegated_stage_marker_missing")
    for event_name in expected.get("required_marker_events", []):
        marker = known_markers.get(event_name)
        matching = [call for call in calls if marker in call.get("stage_markers", [])]
        check(len(matching) == 1, f"completed delegation is observed for stage: {event_name}", "required_stage_call")
    for event_name, allowed_roles in expected.get("marker_roles", {}).items():
        marker = known_markers.get(event_name)
        matching = [call for call in calls if marker in call.get("stage_markers", [])]
        roles = [str(call["role"]).casefold() for call in matching if call.get("role")]
        # Every required-marker call MUST have an explicit role.
        # A missing role (empty list) is NOT equivalent to "any role allowed" —
        # it means the agent identity is unverifiable.
        if matching and not roles:
            check(
                False,
                f"delegated runtime role is missing for stage: {event_name}",
                "delegated_stage_role",
            )
            continue
        check(
            all(role in {str(value).casefold() for value in allowed_roles} for role in roles),
            f"delegated runtime role matches stage intent: {event_name}",
            "delegated_stage_role",
        )
    marker_sequence = expected.get("marker_sequence", [])
    if marker_sequence:
        observed_markers = [
            name
            for call in calls
            for name, marker in known_markers.items()
            if marker in call.get("stage_markers", [])
        ]
        cursor = 0
        ordered = True
        for wanted in marker_sequence:
            try:
                cursor = observed_markers.index(wanted, cursor) + 1
            except ValueError:
                ordered = False
                break
        check(ordered, "required completed delegation stages occur in runtime order", "delegated_stage_order")
    timeline_sequence = expected.get("timeline_sequence", [])
    if timeline_sequence:
        marker_names = {marker: name for name, marker in known_markers.items()}
        observed_timeline = []
        for call in calls:
            for marker in call.get("stage_markers", []):
                if marker in marker_names:
                    observed_timeline.append({
                        "trace_index": call.get("trace_index"),
                        "kind": "agent_marker",
                        "value": marker_names[marker],
                    })
        for call in summary.get("command_calls", []):
            for segment in call.get("segments", []):
                observed_timeline.append({
                    "trace_index": call.get("trace_index"),
                    "kind": "command",
                    "value": segment,
                    "status": call.get("status"),
                })
        observed_timeline.sort(key=lambda item: (
            item["trace_index"] is None,
            item["trace_index"] if item["trace_index"] is not None else 0,
        ))
        cursor = 0
        ordered = True
        for wanted in timeline_sequence:
            try:
                cursor = next(
                    index + 1
                    for index in range(cursor, len(observed_timeline))
                    if all(observed_timeline[index].get(key) == value for key, value in wanted.items())
                )
            except StopIteration:
                ordered = False
                break
        check(
            ordered,
            "required Agent and command events occur in unified runtime order",
            "trace_event_order",
        )
    maximum_total = expected.get("max_total_agent_calls")
    if maximum_total is not None:
        check(len(calls) <= maximum_total, f"no extra Ultra exploration beyond {maximum_total} Agent call(s)", "agent_calls_max_total")
    extra_exploration = expected.get("extra_exploration_calls")
    if extra_exploration:
        extra_markers = set(extra_exploration.get("extra_markers", []))
        extra_count = sum(
            1 for call in calls if set(call.get("stage_markers", [])) & extra_markers
        )
        maximum = extra_exploration.get("max")
        if maximum is not None:
            check(
                extra_count <= maximum,
                f"completed extra exploration call count is at most {maximum}",
                "extra_exploration_call",
            )
    if expected.get("require_delegated_model") and summary["runtime"] == "qoder":
        # Per-child model proof: every completed child that participates in
        # required markers, order, or extra-exploration must have its own
        # real model evidence.  One child's model event cannot vouch for
        # another child.  background_task_id is never a substitute.
        known_marker_values = set(expected.get("known_stage_markers", {}).values())
        for call in calls:
            markers = set(call.get("stage_markers", []))
            if markers & known_marker_values:
                if not call.get("delegated_models"):
                    failures.append(
                        f"child {call.get('task_name') or call.get('id')} "
                        "participates in stage markers but has no delegated model evidence"
                    )
                    failure_codes.append("delegated_model_observed")
                    break
        else:
            # All marker-participating children have model proof
            checks.append("every marker-participating child has delegated model evidence")
    for requirement in expected.get("command_calls", []):
        command = requirement["command"]
        matching = [
            call for call in summary.get("command_calls", [])
            for segment in call.get("segments", [])
            if segment == command
        ]
        successful = [call for call in matching if call.get("status") == "completed"]
        minimum = requirement.get("min", 0)
        maximum = requirement.get("max")
        minimum_successful = requirement.get("min_successful")
        if minimum_successful is None:
            check(len(successful) >= minimum, f"successful `{command}` execution count is at least {minimum}", "validation_command_minimum")
        else:
            check(len(matching) >= minimum, f"`{command}` execution count is at least {minimum}", "validation_command_minimum")
            check(
                len(successful) >= minimum_successful,
                f"successful `{command}` execution count is at least {minimum_successful}",
                "validation_command_success",
            )
        if maximum is not None:
            check(len(matching) <= maximum, f"`{command}` execution count is at most {maximum}", "validation_command_maximum")
    sequence = expected.get("command_sequence", [])
    if sequence:
        observed = [
            {"command": segment, "status": call.get("status")}
            for call in summary.get("command_calls", [])
            for segment in call.get("segments", [])
        ]
        cursor = 0
        ordered = True
        for wanted in sequence:
            try:
                cursor = next(
                    index + 1 for index in range(cursor, len(observed))
                    if observed[index] == wanted
                )
            except StopIteration:
                ordered = False
                break
        check(ordered, "required command outcomes occur in order", "command_sequence")
    return checks, failures, failure_codes
