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

def _read_json_file(path: Path) -> Optional[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _workflow_journal_events(journal_path: Path) -> Optional[list[dict[str, Any]]]:
    """Parse a runtime-owned workflow journal; return None on any error."""
    events = json_lines(journal_path)
    if not events:
        return None
    return events


def _workflow_transcript_events(transcript_path: Path) -> Optional[list[dict[str, Any]]]:
    """Parse a runtime-owned workflow transcript; return None on any error."""
    events = json_lines(transcript_path)
    if not events:
        return None
    return events


def _build_workflow_child_calls(
    workflow_id: str,
    session_id: str,
    run_id: str,
    task_id: str,
    journal_events: list[dict[str, Any]],
    transcript_events: list[dict[str, Any]],
    output: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build normalized agent call records from runtime-owned workflow evidence.

    Each child agent() invocation in the journal produces an independent lifecycle
    record.  Markers, role, task identity, terminal status, and order come
    exclusively from the journal and transcript -- never from the model-written
    workflow script or stage ledger.

    Workflow overall completed alone cannot substitute for a missing child
    terminal event.  A child without a terminal event is not counted as completed.
    """
    # Index journal events by agent_id
    children: dict[str, dict[str, Any]] = {}
    for event in journal_events:
        agent_id = event.get("agent_id")
        if not agent_id or not isinstance(agent_id, str):
            continue
        event_type = event.get("event")
        if event_type == "agent_started":
            children[agent_id] = {
                "agent_id": agent_id,
                "agent_type": event.get("agent_type"),
                "task_id": event.get("task_id"),
                "prompt": event.get("prompt"),
                "stage_markers": event.get("stage_markers", []),
                "started_trace_index": event.get("trace_index"),
                "terminal_status": None,
                "delegated_models": [],
                "completed_trace_index": None,
            }
        elif event_type in {"agent_completed", "agent_failed"} and agent_id in children:
            children[agent_id]["terminal_status"] = (
                "completed" if event_type == "agent_completed" else "failed"
            )
            children[agent_id]["delegated_models"] = event.get("delegated_models", [])
            children[agent_id]["completed_trace_index"] = event.get("trace_index")

    # Verify transcript corroborates the journal (fail closed if inconsistent)
    transcript_agent_ids = set()
    for event in transcript_events:
        agent_id = event.get("agent_id")
        if isinstance(agent_id, str):
            transcript_agent_ids.add(agent_id)

    # Build normalized call records only for children with both journal and
    # transcript evidence AND a terminal event.
    calls: list[dict[str, Any]] = []
    for agent_id, child in children.items():
        # Must appear in transcript
        if agent_id not in transcript_agent_ids:
            continue
        # Must have a terminal event (workflow overall completed is not enough)
        terminal_status = child.get("terminal_status")
        if terminal_status not in {"completed", "failed"}:
            continue

        agent_role = child.get("agent_type")
        prompt = child.get("prompt", "")
        description = prompt
        stage_markers = [
            m for m in child.get("stage_markers", []) if isinstance(m, str)
        ]

        calls.append({
            "id": agent_id,
            "role": agent_role,
            "role_source": "workflow_journal_agent_type",
            "task_name": child.get("task_id"),
            "description": description,
            "prompt": prompt,
            "stage_markers": stage_markers,
            "status": terminal_status,
            "trace_index": child.get("completed_trace_index"),
            "requested_trace_index": child.get("started_trace_index"),
            "runtime_status": terminal_status,
            "agents_states": {},
            "agent_terminal_states": [terminal_status],
            "background_task_id": task_id,
            "delegated_models": child.get("delegated_models", []),
            "workflow_id": workflow_id,
            "workflow_session_id": session_id,
            "workflow_run_id": run_id,
        })
    return calls


def classify_workflow_write_set(
    paths: set[str],
    session_id: str,
    workflow_id: str,
) -> set[str]:
    """Return the subset of paths that are bound Workflow runtime artifacts.

    Only paths matching the exact session_id/workflow_id pattern are considered
    legitimate Workflow runtime paths.  All other .qoder/** paths remain
    unauthorized for the scenario write set.
    """
    prefix = f".qoder/sessions/{session_id}/workflows/{workflow_id}/"
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

        # -- Workflow tool-use detection --
        # Detect Workflow tool-use in both Qoder (message.content) and
        # Codex (item) traces, then resolve runtime artifacts.
        for use in qoder_tool_uses(event):
            if use.get("name") not in WORKFLOW_NAMES:
                continue
            wf_input = use.get("input") if isinstance(use.get("input"), dict) else {}
            wf_session_id = wf_input.get("session_id", "")
            wf_workflow_id = wf_input.get("workflow_id", "")
            wf_run_id = wf_input.get("run_id", "")
            wf_task_id = wf_input.get("task_id", "")
            tools_used.append("Workflow")
            workflow_sessions[str(use.get("id", ""))] = {
                "tool_use_id": use.get("id"),
                "session_id": wf_session_id,
                "workflow_id": wf_workflow_id,
                "run_id": wf_run_id,
                "task_id": wf_task_id,
                "status": "requested",
                "trace_index": event_index,
            }
        # Codex-style Workflow detection
        codex_wf = None
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "collab_tool_call":
            name = item.get("name") or item.get("tool") or item.get("tool_name")
            if str(name) in WORKFLOW_NAMES:
                codex_wf = item
        if codex_wf is not None:
            wf_input = codex_wf.get("arguments") or codex_wf.get("input") or {}
            if isinstance(wf_input, str):
                try:
                    wf_input = json.loads(wf_input)
                except json.JSONDecodeError:
                    wf_input = {}
            wf_session_id = wf_input.get("session_id", "") if isinstance(wf_input, dict) else ""
            wf_workflow_id = wf_input.get("workflow_id", "") if isinstance(wf_input, dict) else ""
            wf_run_id = wf_input.get("run_id", "") if isinstance(wf_input, dict) else ""
            wf_task_id = wf_input.get("task_id", "") if isinstance(wf_input, dict) else ""
            tools_used.append("Workflow")
            wf_call_id = str(codex_wf.get("id") or codex_wf.get("call_id") or "")
            workflow_sessions[wf_call_id] = {
                "tool_use_id": wf_call_id,
                "session_id": wf_session_id,
                "workflow_id": wf_workflow_id,
                "run_id": wf_run_id,
                "task_id": wf_task_id,
                "status": str(codex_wf.get("status") or "requested").casefold(),
                "trace_index": event_index,
            }

    # Resolve Workflow system events (started/completed)
    for event_index, event in enumerate(events):
        if event.get("type") != "system":
            continue
        tool_use_id = str(event.get("tool_use_id") or "")
        if tool_use_id not in workflow_sessions:
            continue
        wf = workflow_sessions[tool_use_id]
        wf_status = str(event.get("status") or "").casefold()
        if wf_status:
            wf["status"] = wf_status
            wf["trace_index"] = event_index
        if event.get("session_id"):
            wf["session_id"] = event["session_id"]
        if event.get("workflow_id"):
            wf["workflow_id"] = event["workflow_id"]

    # Resolve Workflow runtime artifacts and build child agent calls.
    # Fail closed: journal, transcript, and output must all be present and
    # parseable.  Workflow overall completed cannot substitute for missing
    # child lifecycle.  Model-written scripts are not authoritative.
    if workflow_runtime_root is not None:
        for wf in workflow_sessions.values():
            wf_dir = (
                workflow_runtime_root
                / ".qoder" / "sessions" / wf["session_id"]
                / "workflows" / wf["workflow_id"]
            )
            journal_path = wf_dir / "journal.jsonl"
            transcript_path = wf_dir / "transcript.jsonl"
            output_path = wf_dir / "output.json"
            manifest_path = wf_dir / "manifest.json"

            journal_events = _workflow_journal_events(journal_path)
            transcript_events = _workflow_transcript_events(transcript_path)
            output = _read_json_file(output_path)
            manifest = _read_json_file(manifest_path)

            # All four artifacts must be present and parseable
            if journal_events is None or transcript_events is None or output is None or manifest is None:
                continue

            # Use the Workflow's initial request trace index as the base
            # for child trace indices (not the completed event), so child
            # calls appear before subsequent main-trace events like
            # validation commands in the timeline ordering.
            wf_base_index = min(
                wf.get("trace_index", 0),
                next(
                    (idx for idx, ev in enumerate(events)
                     if any(
                         isinstance(c, dict) and c.get("type") == "tool_use"
                         and c.get("id") == wf.get("tool_use_id")
                         for c in (
                             (ev.get("message", {}).get("content", [])
                              if isinstance(ev.get("message"), dict) else [])
                         )
                     )),
                    wf.get("trace_index", 0),
                ),
            )
            child_calls = _build_workflow_child_calls(
                wf["workflow_id"],
                wf["session_id"],
                wf["run_id"],
                wf["task_id"],
                journal_events,
                transcript_events,
                output,
            )
            # Offset child trace indices relative to the Workflow's position
            # in the main trace.  Each completed child gets a slightly
            # increasing offset so their relative order is preserved.
            for offset, call in enumerate(child_calls, start=1):
                call["trace_index"] = wf_base_index + offset
                if call.get("requested_trace_index") is not None:
                    call["requested_trace_index"] = wf_base_index + offset - 1
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
    }


def grade(summary: dict[str, Any], expected: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    checks: list[str] = []
    failures: list[str] = []
    failure_codes: list[str] = []

    def check(condition: bool, message: str, code: str) -> None:
        (checks if condition else failures).append(message)
        if not condition:
            failure_codes.append(code)

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
