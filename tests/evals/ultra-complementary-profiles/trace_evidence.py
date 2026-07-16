#!/usr/bin/env python3
"""Extract runtime capability and real delegation evidence from JSONL traces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


AGENT_NAMES = {"Agent", "spawn_agent", "collaboration.spawn_agent", "mcp__collaboration__spawn_agent"}


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


def codex_tool_use(event: dict[str, Any]) -> Optional[dict[str, Any]]:
    item = event.get("item")
    if not isinstance(item, dict):
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
    return {
        "id": item.get("id") or item.get("call_id"),
        "name": name,
        "input": arguments if isinstance(arguments, dict) else {},
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
        elif str(event.get("type", "")).startswith(("thread.", "turn.", "item.")):
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
                    "delegated_models": [],
                }
            )
        use = codex_tool_use(event)
        if use:
            input_value = use["input"]
            calls.append(
                {
                    "id": use.get("id"),
                    "role": input_value.get("subagent_type") or input_value.get("agent_type") or input_value.get("task_name"),
                    "description": input_value.get("description") or input_value.get("message") or input_value.get("task_name"),
                    "delegated_models": [],
                }
            )

    unique_calls = []
    seen_ids = set()
    for call in calls:
        call_id = call.get("id")
        if call_id and call_id in seen_ids:
            continue
        unique_calls.append(call)
        if call_id:
            seen_ids.add(call_id)
    calls = unique_calls
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

    if runtime == "primary" and calls:
        tools = sorted(set(tools) | {"spawn_agent", "Agent"})
        agents = sorted(set(agents) | {str(call["role"]) for call in calls if call.get("role")})
        if any("explore" in f"{call.get('role', '')} {call.get('description', '')}".casefold() for call in calls):
            agents = sorted(set(agents) | {"Explore"})
    return {
        "runtime": runtime,
        "root_model": root_model,
        "capabilities": {"tools": tools, "agents": agents},
        "agent_calls": calls,
        "agent_call_count": len(calls),
        "delegated_models": sorted(
            {model for call in calls for model in call.get("delegated_models", [])}
        ),
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
        role = requirement["role"].casefold()
        matching = [
            call for call in calls
            if role in f"{call.get('role', '')} {call.get('description', '')}".casefold()
        ]
        minimum = requirement.get("min", 0)
        maximum = requirement.get("max")
        check(len(matching) >= minimum, f"real {requirement['role']} delegation count is at least {minimum}")
        if maximum is not None:
            check(len(matching) <= maximum, f"real {requirement['role']} delegation count is at most {maximum}")
    maximum_total = expected.get("max_total_agent_calls")
    if maximum_total is not None:
        check(len(calls) <= maximum_total, f"no extra Ultra exploration beyond {maximum_total} Agent call(s)")
    if expected.get("require_delegated_model") and summary["runtime"] == "qoder":
        check(bool(summary["delegated_models"]), "delegated model is observed in the runtime trace")
    return checks, failures
