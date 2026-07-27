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


def json_lines(path: Path) -> list[dict[str, Any]]:
    events = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return events
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


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


def _build_workflow_child_calls_real(
    session_id: str,
    run_id: str,
    task_id: str,
    manifest: dict[str, Any],
    journal_events: list[dict[str, Any]],
    main_trace_events: list[dict[str, Any]],
    wf_tool_use_id: str,
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

    # 2. Build journal result index by key
    journal_results: dict[str, dict[str, Any]] = {}
    for evt in journal_events:
        if evt.get("type") == "result" and isinstance(evt.get("key"), str):
            journal_results[evt["key"]] = evt

    # 3. Index main trace system events by parent_tool_use_id (child activity)
    trace_children: dict[str, list[dict[str, Any]]] = {}
    for evt in main_trace_events:
        if evt.get("type") != "system":
            continue
        parent = evt.get("parent_tool_use_id") or evt.get("tool_use_id")
        if parent == wf_tool_use_id or str(parent) == str(wf_tool_use_id):
            child_task = evt.get("task_id", "")
            if isinstance(child_task, str) and child_task:
                trace_children.setdefault(child_task, []).append(evt)

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

        # 6. Cross-validate: main trace must have child activity for this agentId
        child_events = trace_children.get(agent_id, [])
        if not child_events:
            failures.append(f"workflow_agent_{label}_trace_children_missing")
            continue

        # 7. Determine terminal status from manifest state
        if state == "done":
            terminal_status = "completed"
        elif state in ("failed", "error", "cancelled", "timeout"):
            terminal_status = "failed"
        else:
            failures.append(f"workflow_agent_{label}_non_terminal_state")
            continue

        # 8. Extract stage markers from main trace child event descriptions
        stage_markers: list[str] = []
        for ce in child_events:
            desc = str(ce.get("description", ""))
            found = re.findall(r"\[[a-z0-9-]+:[a-z0-9-]+\]", desc, flags=re.IGNORECASE)
            for m in found:
                if m not in stage_markers:
                    stage_markers.append(m)

        # 9. Determine trace indices from main trace events
        started_index = None
        completed_index = None
        for ce in child_events:
            subtype = ce.get("subtype", "")
            if subtype == "task_started" and started_index is None:
                started_index = ce.get("_trace_index")
            if subtype in ("task_completed", "task_progress"):
                completed_index = ce.get("_trace_index")

        # 10. Extract delegated model from child events
        delegated_models: list[str] = []
        for ce in child_events:
            msg = ce.get("message")
            if isinstance(msg, dict):
                model = msg.get("model")
                if isinstance(model, str) and model and model not in delegated_models:
                    delegated_models.append(model)

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
) -> set[str]:
    """Return the subset of paths that are bound Workflow runtime artifacts.

    Only paths matching .qoder/sessions/<session>/workflows/ (the entire
    session's workflow directory tree) are considered legitimate runtime paths.
    All other .qoder/** paths remain unauthorized for the scenario write set.
    """
    prefix = f".qoder/sessions/{session_id}/workflows/"
    return {path for path in paths if path.startswith(prefix)}


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
    events = json_lines(path)
    runtime = "unknown"
    root_model = None
    tools: list[str] = []
    agents: list[str] = []
    calls: list[dict[str, Any]] = []
    command_calls: list[dict[str, Any]] = []
    tools_used: list[str] = []
    workflow_sessions: dict[str, dict[str, Any]] = {}

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
            workflow_sessions[tool_use_id] = {
                "tool_use_id": tool_use_id,
                "session_id": "",
                "run_id": "",
                "task_id": "",
                "status": "requested",
                "trace_index": event_index,
                "protocol_failures": [],
            }

    # Second pass: resolve Workflow IDs from tool_result and system events.
    # Also tag system events with _trace_index for child activity tracking.
    for event_index, event in enumerate(events):
        event["_trace_index"] = event_index
        if event.get("type") == "system":
            session_id = event.get("session_id")
            if isinstance(session_id, str) and session_id:
                for wf in workflow_sessions.values():
                    if not wf["session_id"]:
                        wf["session_id"] = session_id
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
        # System task_notification events for Workflow completion
        if event.get("type") == "system" and event.get("subtype") == "task_notification":
            task_id = str(event.get("task_id", ""))
            for wf in workflow_sessions.values():
                if wf["task_id"] == task_id:
                    wf_status = str(event.get("status") or "").casefold()
                    if wf_status:
                        wf["status"] = wf_status
                        wf["trace_index"] = event_index

    # Resolve Workflow runtime artifacts and build child agent calls.
    # Fail closed with EXPLICIT protocol failures — no silent continue.
    # A detected Workflow invocation that cannot produce valid child evidence
    # generates failures that cannot be masked by direct Agent calls.
    workflow_protocol_failures: list[str] = []
    if workflow_runtime_root is not None and workflow_sessions:
        for wf in workflow_sessions.values():
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

            child_calls, child_failures = _build_workflow_child_calls_real(
                session_id,
                run_id,
                wf.get("task_id", ""),
                manifest,
                journal_events,
                events,
                wf.get("tool_use_id", ""),
            )
            if child_failures:
                workflow_protocol_failures.extend(child_failures)
                # Do NOT add partial calls — protocol is compromised
                continue

            calls.extend(child_calls)


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
        check(
            not roles or all(role in {str(value).casefold() for value in allowed_roles} for role in roles),
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
        delegated_execution_observed = bool(summary["delegated_models"]) or any(
            call.get("background_task_id") for call in calls
        )
        check(
            delegated_execution_observed,
            "delegated Agent completion is observed in the runtime trace",
            "delegated_model_observed",
        )
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
