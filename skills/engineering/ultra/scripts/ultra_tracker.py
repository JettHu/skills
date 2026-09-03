#!/usr/bin/env python3
"""Thin bundled facade for Ultra Ticket, publication, and Solve Record helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


SCHEMA = "ultra-tracker/v1"
CONTRACT = Path("docs/agents/ultra-tracker.md")
SUCCESS = 0
REFUSED = 3
INVALID = 4
UNAVAILABLE = 5
RETRYABLE = 6


class FacadeError(RuntimeError):
    """A facade input or configured route is unavailable or invalid."""


class FacadeArgumentError(FacadeError):
    """The facade command shape is invalid before delegation begins."""


class FacadeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise FacadeArgumentError(message)


def envelope(operation: str, *, data: Any = None, error: dict[str, str] | None = None) -> None:
    result: dict[str, Any] = {"schema": SCHEMA, "operation": operation, "ok": error is None}
    if error is None:
        result["data"] = data
    else:
        result["error"] = error
    print(json.dumps(result, indent=2, sort_keys=True))


def handoff_envelope(operation: str, payload: Any) -> int:
    """Project a handoff result onto the facade's success and exit contract."""
    if not isinstance(payload, dict) or payload.get("status") not in {
        "success",
        "retryable",
        "conflict",
        "unavailable",
    }:
        error(
            operation,
            "invalid-delegated-result",
            "handoff helper returned an invalid status",
        )
        return INVALID
    status = payload["status"]
    if status == "success":
        envelope(operation, data=payload)
        return SUCCESS
    result = {
        "schema": SCHEMA,
        "operation": operation,
        "ok": False,
        "data": payload,
        "error": {
            "code": f"handoff-{status}",
            "detail": payload.get("reason") or f"handoff returned {status}",
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return {
        "retryable": RETRYABLE,
        "conflict": REFUSED,
        "unavailable": UNAVAILABLE,
    }[status]


def error(operation: str, code: str, detail: str) -> None:
    envelope(operation, error={"code": code, "detail": detail})


def exactly_one_contract_value(text: str, field: str) -> str:
    values = re.findall(rf"(?m)^{re.escape(field)}:[ \t]*(\S(?:.*\S)?)[ \t]*$", text)
    if len(values) != 1:
        raise FacadeError(f"Tracker contract must define exactly one {field}")
    return values[0]


def publication_config(repo: Path) -> tuple[str, str]:
    """Read the configured publication coordinates without interpreting Ticket state."""
    path = repo / CONTRACT
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FacadeError(f"missing Tracker contract: {path}") from exc
    if exactly_one_contract_value(text, "Publication strategy") != "local-review-pending":
        raise FacadeError("configured publication strategy is not supported by bundled Local Markdown helper")
    representation = exactly_one_contract_value(text, "Local Ticket representation")
    location = exactly_one_contract_value(text, "Local Ticket path")
    if representation not in {"file-per-ticket", "tickets-file"}:
        raise FacadeError(f"unsupported configured Local Ticket representation: {representation}")
    return representation, location


def helper_path(name: str) -> Path:
    ultra = Path(__file__).resolve().parent
    if name == "publication":
        return ultra / "local_ticket_publication.py"
    if name == "ticket":
        return ultra / "local_ticket_frontier.py"
    if name == "handoff":
        return ultra / "local_outcome_handoff.py"
    if name == "solve-record":
        return ultra.parent.parent / "solve-records" / "scripts" / "solve-records.py"
    raise AssertionError(f"unknown helper: {name}")


def refusal(detail: str) -> bool:
    normalized = detail.lower()
    return any(
        marker in normalized
        for marker in (
            "not claimable",
            "stale dependency state",
            "claim-conflict",
            "requires --explicit",
            "cleanup requires",
            "terminal repair conflict",
            "merge gate",
            "not eligible",
        )
    )


def payload_refusal(helper: str, payload: Any) -> bool:
    if helper != "solve-record" or not isinstance(payload, dict):
        return False
    if payload.get("eligible") is False:
        return True
    return payload.get("status") in {"blocked", "needs_landing_construction", "not_applicable"}


def delegate(operation: str, helper: str, args: list[str]) -> int:
    path = helper_path(helper)
    if not path.is_file():
        error(operation, "helper-unavailable", f"bundled delegated helper is unavailable: {path}")
        return UNAVAILABLE
    result = subprocess.run(
        [sys.executable, str(path), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip() or f"delegated helper exited {result.returncode}"
        if refusal(detail):
            error(operation, "not-allowed", detail)
            return REFUSED
        error(operation, "invalid-input-or-state", detail)
        return INVALID
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        error(operation, "invalid-delegated-result", "delegated helper did not emit a JSON result")
        return INVALID
    if payload_refusal(helper, payload):
        detail = json.dumps(payload.get("reasons") or payload.get("reason") or payload, sort_keys=True)
        error(operation, "not-allowed", detail)
        return REFUSED
    if helper == "handoff":
        return handoff_envelope(operation, payload)
    envelope(operation, data=payload)
    return SUCCESS


def parse_args() -> argparse.Namespace:
    parser = FacadeArgumentParser(
        description="Bundled Ultra Tracker facade for Ticket publication, Claim, Attempt, and Solve Record helpers."
    )
    groups = parser.add_subparsers(
        dest="group", required=True, title="command groups", parser_class=FacadeArgumentParser
    )

    publication = groups.add_parser("publication", help="Local Markdown Ticket publication lifecycle")
    publication_actions = publication.add_subparsers(
        dest="action", required=True, title="publication operations", parser_class=FacadeArgumentParser
    )
    for action in ("register", "inspect", "promote", "cleanup", "terminal-repair"):
        child = publication_actions.add_parser(action, help=f"delegate Ticket publication {action}")
        child.add_argument("--repo", default=".", help="repository containing the configured Tracker contract")
        child.add_argument("--run-id", required=True, help="publication run identity")
        child.add_argument(
            "--location",
            help="concrete configured Ticket surface when the contract path contains <feature>",
        )
        if action == "register":
            child.add_argument("--allow-membership-change", action="store_true")
        if action == "cleanup":
            child.add_argument("--explicit", action="store_true")
        if action == "terminal-repair":
            child.add_argument("--ticket-id", required=True, help="exact current Ticket identity")
            child.add_argument("--expected-digest", required=True, help="current Ticket SHA-256 digest")
            child.add_argument("--repair-type", required=True, choices=("ticket-identity", "blocker-target", "publication-metadata", "digest-backlink-structure"))
            child.add_argument("--old-value", default="", help="typed current value; unused for backlink structure")
            child.add_argument("--new-value", default="", help="typed repaired value; unused for backlink structure")
            child.add_argument("--reason", required=True, help="human authorization reason")

    ticket = groups.add_parser("ticket", help="Ticket frontier discovery and conflict-detecting Claim")
    ticket_actions = ticket.add_subparsers(
        dest="action", required=True, title="Ticket operations", parser_class=FacadeArgumentParser
    )
    frontier = ticket_actions.add_parser("frontier", help="discover claimable Tickets")
    frontier.add_argument("--repo", default=".")
    frontier.add_argument("--ticket-id", action="append", default=[], help="exact Ticket identity; repeatable")
    claim = ticket_actions.add_parser("claim", help="atomically Claim one Ticket from a frontier snapshot")
    claim.add_argument("--repo", default=".")
    claim.add_argument("--ticket-id", required=True, help="exact Ticket identity")
    claim.add_argument("--expected-snapshot", required=True, help="frontier snapshot returned by discovery")
    claim.add_argument("--branch", required=True, help="configured Ticket coordination branch assignment")
    claim.add_argument("--worktree", required=True, help="configured Ticket coordination worktree assignment")
    handoff = ticket_actions.add_parser(
        "handoff",
        help="canonical writer for one compact candidate or recovery outcome handoff",
        description=(
            "Atomically converge one compact canonical receipt, Ticket backlink/state, "
            "Claim disposition, retained-resource ownership, and optional successor relation. "
            "Create the opaque handoff key before any side effect; retry a retryable result "
            "with the same key and identical immutable inputs. Only success returns ok=true "
            "and exits 0; retryable (6), conflict (3), and unavailable (5) retain their "
            "structured result with ok=false."
        ),
    )
    handoff.add_argument("--repo", default=".")
    handoff.add_argument(
        "--ticket-id",
        action="append",
        required=True,
        help="exact active Ticket identity; repeatable",
    )
    handoff.add_argument("--handoff-key", required=True, help="mandatory caller-generated durable opaque retry key")
    handoff.add_argument("--outcome", required=True, help="semantic candidate, recovery, or terminal outcome")
    handoff.add_argument("--summary", required=True, help="concise outcome Summary")
    handoff.add_argument("--recovery-next-action", help="recovery intent; use resume only when retaining ownership")
    handoff.add_argument("--retained-resource", action="append", default=[], help="complete retained resource declaration")
    handoff.add_argument("--supersedes", help="canonical open recovery predecessor; success preserves its outcome and records the successor relation")

    records = groups.add_parser("solve-record", help="read-only Attempt and Solve Record inspection and gates")
    record_actions = records.add_subparsers(
        dest="action", required=True, title="Solve Record operations", parser_class=FacadeArgumentParser
    )
    for action in ("dashboard", "list", "select", "merge-gate", "landing-plan", "cleanup-plan"):
        child = record_actions.add_parser(action, help=f"delegate Solve Record {action}")
        child.add_argument("--repo", default=".")
        if action == "select":
            child.add_argument("--query", required=True)
        if action in {"merge-gate", "landing-plan", "cleanup-plan"}:
            child.add_argument("--record", required=True)
        if action == "landing-plan":
            child.add_argument("--landing-sha")
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        operation = f"{args.group}.{args.action}"
        repo = Path(args.repo).resolve()
        if args.group == "publication":
            representation, configured_location = publication_config(repo)
            if "<feature>" in configured_location and not args.location:
                raise FacadeError(
                    "publication requires --location for the contract's concrete <feature> Ticket surface"
                )
            location = args.location or configured_location
            delegated = [args.action, "--repo", str(repo), "--representation", representation, "--location", location, "--run-id", args.run_id]
            if getattr(args, "allow_membership_change", False):
                delegated.append("--allow-membership-change")
            if getattr(args, "explicit", False):
                delegated.append("--explicit")
            if args.action == "terminal-repair":
                delegated.extend([
                    "--ticket-id", args.ticket_id,
                    "--expected-digest", args.expected_digest,
                    "--repair-type", args.repair_type,
                    "--old-value", args.old_value,
                    "--new-value", args.new_value,
                    "--reason", args.reason,
                ])
            return delegate(operation, "publication", delegated)
        if args.group == "ticket":
            if args.action == "handoff":
                delegated = [
                    "--repo", str(repo), "--handoff-key", args.handoff_key,
                    "--outcome", args.outcome,
                    "--summary", args.summary,
                ]
                for ticket_id in args.ticket_id:
                    delegated.extend(["--ticket-id", ticket_id])
                if args.recovery_next_action is not None:
                    delegated.extend(["--recovery-next-action", args.recovery_next_action])
                for resource in args.retained_resource:
                    delegated.extend(["--retained-resource", resource])
                if args.supersedes is not None:
                    delegated.extend(["--supersedes", args.supersedes])
                return delegate(operation, "handoff", delegated)
            delegated = [args.action, "--repo", str(repo)]
            if args.action == "frontier":
                for ticket_id in args.ticket_id:
                    delegated.extend(["--ticket-id", ticket_id])
            else:
                delegated.extend(["--ticket-id", args.ticket_id, "--expected-snapshot", args.expected_snapshot, "--branch", args.branch, "--worktree", args.worktree])
            return delegate(operation, "ticket", delegated)
        delegated = [args.action, "--repo", str(repo), "--json"]
        if args.action == "select":
            delegated.extend(["--query", args.query])
        if args.action in {"merge-gate", "landing-plan", "cleanup-plan"}:
            delegated.extend(["--record", args.record])
        if args.action == "landing-plan" and args.landing_sha:
            delegated.extend(["--landing-sha", args.landing_sha])
        return delegate(operation, "solve-record", delegated)
    except FacadeError as exc:
        operation = locals().get("operation", "parse")
        error(operation, "invalid-input-or-state", str(exc))
        return INVALID


if __name__ == "__main__":
    raise SystemExit(main())
