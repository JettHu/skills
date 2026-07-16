#!/usr/bin/env python3
"""Extract runtime capability and real delegation evidence from JSONL traces."""

from __future__ import annotations

import json
from pathlib import Path
import re
import shlex
from typing import Any, Optional


AGENT_NAMES = {"Agent", "spawn_agent", "collaboration.spawn_agent", "mcp__collaboration__spawn_agent"}
COMMAND_NAMES = {"Bash", "exec_command", "functions.exec_command"}
SUCCESSFUL_AGENT_STATES = {"completed"}


def stage_markers(*values: object) -> list[str]:
    text = " ".join(str(value or "") for value in values)
    return list(dict.fromkeys(
        re.findall(r"\[[a-z0-9-]+:[a-z0-9-]+\]", text, flags=re.IGNORECASE)
    ))


def command_segments(command: object) -> list[str]:
    if not isinstance(command, str):
        return []
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


def summarize(path: Path) -> dict[str, Any]:
    events = json_lines(path)
    runtime = "unknown"
    root_model = None
    tools: list[str] = []
    agents: list[str] = []
    calls: list[dict[str, Any]] = []
    command_calls: list[dict[str, Any]] = []
    tools_used: list[str] = []

    for event in events:
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
                        "status": "requested",
                    }
                )
            if use.get("name") not in AGENT_NAMES:
                continue
            input_value = use.get("input") if isinstance(use.get("input"), dict) else {}
            agent_role = input_value.get("subagent_type") or input_value.get("agent_type")
            task_name = input_value.get("task_name")
            description = input_value.get("description") or task_name
            prompt = input_value.get("prompt") or input_value.get("message")
            calls.append(
                {
                    "id": use.get("id"),
                    "role": agent_role or task_name,
                    "role_source": "agent_type" if agent_role else ("task_name" if task_name else None),
                    "description": description,
                    "prompt": prompt,
                    "stage_markers": stage_markers(description, prompt),
                    "status": "requested",
                    "agents_states": {},
                    "delegated_models": [],
                }
            )
        use = codex_tool_use(event)
        if use:
            tools_used.append(str(use.get("name") or "spawn_agent"))
            input_value = use["input"]
            agent_role = input_value.get("subagent_type") or input_value.get("agent_type")
            task_name = input_value.get("task_name")
            prompt = use.get("prompt")
            description = prompt or input_value.get("description") or input_value.get("message") or task_name
            calls.append(
                {
                    "id": use.get("id"),
                    "role": agent_role or task_name,
                    "role_source": "agent_type" if agent_role else ("task_name" if task_name else None),
                    "description": description,
                    "prompt": prompt,
                    "stage_markers": stage_markers(description, prompt),
                    "status": use.get("status"),
                    "runtime_status": use.get("runtime_status"),
                    "agents_states": use.get("agents_states"),
                    "agent_terminal_states": use.get("agent_terminal_states"),
                    "delegated_models": [],
                }
            )
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "command_execution":
            exit_code = item.get("exit_code")
            runtime_status = str(item.get("status") or "unknown").casefold()
            command_calls.append(
                {
                    "id": item.get("id"),
                    "command": item.get("command") or item.get("cmd"),
                    "status": "completed" if runtime_status == "completed" and exit_code in (None, 0) else "failed",
                    "exit_code": exit_code,
                }
            )
            tools_used.append("command_execution")

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
    for event in events:
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

        message_content = message.get("content") if isinstance(message, dict) else None
        if isinstance(message_content, list):
            for item in message_content:
                if not isinstance(item, dict) or item.get("type") != "tool_result":
                    continue
                tool_use_id = item.get("tool_use_id")
                tool_result = event.get("tool_use_result")
                state = tool_result.get("state") if isinstance(tool_result, dict) else None
                if tool_use_id in by_id:
                    if item.get("is_error") is True or state in {"failed", "error", "cancelled"}:
                        by_id[tool_use_id]["status"] = "failed"
                    elif state == "completed" or item.get("is_error") is False:
                        by_id[tool_use_id]["status"] = "completed"
                if tool_use_id in commands_by_id:
                    result = tool_result if isinstance(tool_result, dict) else {}
                    failed = (
                        item.get("is_error") is True
                        or state in {"failed", "error", "cancelled"}
                        or result.get("interrupted") is True
                        or result.get("exit_code") not in (None, 0)
                    )
                    commands_by_id[tool_use_id]["status"] = "failed" if failed else "completed"
                    if "exit_code" in result:
                        commands_by_id[tool_use_id]["exit_code"] = result["exit_code"]

    successful_calls = [call for call in calls if call.get("status") == "completed"]
    if runtime == "primary" and calls:
        tools = sorted(set(tools) | {"spawn_agent", "Agent"})
        agents = sorted(set(agents) | {str(call["role"]) for call in successful_calls if call.get("role")})
    for call in command_calls:
        call["segments"] = command_segments(call.get("command"))
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
        "delegated_models": sorted(
            {model for call in successful_calls for model in call.get("delegated_models", [])}
        ),
        "delegated_model_observation": "unknown/unavailable" if runtime == "primary" else "observed-in-trace",
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
        check(bool(summary["delegated_models"]), "delegated model is observed in the runtime trace", "delegated_model_observed")
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
