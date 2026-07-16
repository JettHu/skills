#!/usr/bin/env python3
"""Extract runtime capability and real delegation evidence from JSONL traces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


AGENT_NAMES = {"Agent", "spawn_agent", "collaboration.spawn_agent", "mcp__collaboration__spawn_agent"}
SUCCESSFUL_AGENT_STATES = {"completed"}


def json_lines(path: Path) -> list[dict[str, Any]]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
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

    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            runtime = "qoder"
            root_model = event.get("model")
            tools = [str(value) for value in event.get("tools", [])]
            agents = [str(value) for value in event.get("agents", [])]
        elif event.get("type") == "collab_tool_call" or str(event.get("type", "")).startswith(("thread.", "turn.", "item.")):
            runtime = "primary"

        for use in qoder_tool_uses(event):
            if use.get("name") not in AGENT_NAMES:
                continue
            input_value = use.get("input") if isinstance(use.get("input"), dict) else {}
            calls.append(
                {
                    "id": use.get("id"),
                    "role": input_value.get("subagent_type") or input_value.get("agent_type") or input_value.get("task_name"),
                    "description": input_value.get("description") or input_value.get("task_name"),
                    "prompt": input_value.get("prompt") or input_value.get("message"),
                    "status": "requested",
                    "agents_states": {},
                    "delegated_models": [],
                }
            )
        use = codex_tool_use(event)
        if use:
            input_value = use["input"]
            calls.append(
                {
                    "id": use.get("id"),
                    "role": input_value.get("subagent_type") or input_value.get("agent_type") or input_value.get("task_name") or ("Explore" if "explore" in str(use.get("prompt", "")).casefold() else None),
                    "description": use.get("prompt") or input_value.get("description") or input_value.get("message") or input_value.get("task_name"),
                    "prompt": use.get("prompt"),
                    "status": use.get("status"),
                    "runtime_status": use.get("runtime_status"),
                    "agents_states": use.get("agents_states"),
                    "agent_terminal_states": use.get("agent_terminal_states"),
                    "delegated_models": [],
                }
            )

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
                if tool_use_id not in by_id:
                    continue
                tool_result = event.get("tool_use_result")
                state = tool_result.get("state") if isinstance(tool_result, dict) else None
                if item.get("is_error") is True or state in {"failed", "error", "cancelled"}:
                    by_id[tool_use_id]["status"] = "failed"
                elif state == "completed" or item.get("is_error") is False:
                    by_id[tool_use_id]["status"] = "completed"

    successful_calls = [call for call in calls if call.get("status") == "completed"]
    if runtime == "primary" and calls:
        tools = sorted(set(tools) | {"spawn_agent", "Agent"})
        agents = sorted(set(agents) | {str(call["role"]) for call in successful_calls if call.get("role")})
        if any("explore" in f"{call.get('role', '')} {call.get('description', '')} {call.get('prompt', '')}".casefold() for call in successful_calls):
            agents = sorted(set(agents) | {"Explore"})
    return {
        "runtime": runtime,
        "root_model": root_model,
        "capabilities": {"tools": tools, "agents": agents},
        "agent_calls": successful_calls,
        "agent_call_count": len(successful_calls),
        "attempted_agent_calls": calls,
        "rejected_agent_call_count": len(calls) - len(successful_calls),
        "delegated_models": sorted(
            {model for call in successful_calls for model in call.get("delegated_models", [])}
        ),
        "delegated_model_observation": "unknown/unavailable" if runtime == "primary" else "observed-in-trace",
    }


def grade(summary: dict[str, Any], expected: dict[str, Any]) -> tuple[list[str], list[str]]:
    checks: list[str] = []
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        (checks if condition else failures).append(message)

    capabilities = summary["capabilities"]
    for tool in expected.get("capability_tools", []):
        check(tool in capabilities["tools"], f"runtime exposes delegation tool: {tool}")
    for agent in expected.get("capability_agents", []):
        check(agent in capabilities["agents"], f"runtime exposes delegation role: {agent}")
    calls = summary["agent_calls"]
    for requirement in expected.get("agent_calls", []):
        role = requirement.get("role", "").casefold()
        marker = requirement.get("marker", "")
        matching = [
            call for call in calls
            if (not role or role in f"{call.get('role', '')} {call.get('description', '')} {call.get('prompt', '')}".casefold())
            and (not marker or marker in f"{call.get('description', '')} {call.get('prompt', '')}")
        ]
        minimum = requirement.get("min", 0)
        maximum = requirement.get("max")
        label = requirement.get("marker") or requirement.get("role") or "Agent"
        check(len(matching) >= minimum, f"real {label} delegation count is at least {minimum}")
        if maximum is not None:
            check(len(matching) <= maximum, f"real {label} delegation count is at most {maximum}")
    maximum_total = expected.get("max_total_agent_calls")
    if maximum_total is not None:
        check(len(calls) <= maximum_total, f"no extra Ultra exploration beyond {maximum_total} Agent call(s)")
    if expected.get("require_delegated_model") and summary["runtime"] == "qoder":
        check(bool(summary["delegated_models"]), "delegated model is observed in the runtime trace")
    return checks, failures
