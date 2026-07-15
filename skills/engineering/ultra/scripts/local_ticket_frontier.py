#!/usr/bin/env python3
"""Discover and Claim the configured Local Markdown Ticket frontier safely."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

import local_ticket_publication as publication
from local_ticket_surface import (
    SurfacePatternError,
    configured_location_regex,
)


CONTRACT = Path("docs/agents/ultra-tracker.md")
BEGIN = re.compile(
    r"(?m)^<!-- ultra-ticket:begin id=([A-Za-z0-9][A-Za-z0-9._-]*) -->[ \t]*\n"
)
END = re.compile(r"(?m)^<!-- ultra-ticket:end -->[ \t]*(?:\n|\Z)")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


class FrontierError(RuntimeError):
    """The configured frontier cannot be read or mutated safely."""


@dataclass(frozen=True)
class FrontierContract:
    representation: str
    location_pattern: str
    state_fields: tuple[str, ...]
    ready_state: str
    completed_state: str
    human_states: tuple[str, ...]
    blocker_fields: tuple[str, ...]
    blocker_heading: str
    claim_field: str
    claim_aliases: tuple[str, ...]
    claim_value: str
    branch_field: str
    branch_aliases: tuple[str, ...]
    worktree_field: str
    worktree_aliases: tuple[str, ...]
    identity_fields: tuple[str, ...]
    run_fields: tuple[str, ...]
    source_fields: tuple[str, ...]
    states: dict[str, str]


@dataclass
class Ticket:
    identity: str
    aliases: set[str]
    status: str
    flags: list[str]
    blockers: list[str]
    publication_run: str
    path: Path
    container_text: str
    inner_start: int
    inner_end: int
    state_field: str
    flags_field: str
    branch_field: str
    worktree_field: str
    branch: str
    worktree: str
    representation: str
    publication_ready: bool = True
    publication_reason: str = ""

    @property
    def inner(self) -> str:
        return self.container_text[self.inner_start : self.inner_end]


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def state_registry(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for canonical in csv(value):
        key = normalize_key(canonical)
        if not key or key in result:
            raise FrontierError("Ticket state values must be unique and non-empty")
        result[key] = canonical
    return result


def contract_value(text: str, field: str) -> str:
    matches = re.findall(
        rf"(?m)^{re.escape(field)}:[ \t]*(\S(?:.*\S)?)[ \t]*$", text
    )
    if len(matches) != 1:
        raise FrontierError(f"Local tracker contract must define exactly one {field}")
    return matches[0]


def read_contract(repo: Path) -> tuple[FrontierContract, str]:
    path = repo / CONTRACT
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise FrontierError(f"missing Local tracker contract: {path}") from error
    if contract_value(text, "Frontier adapter") != "bundled-local-markdown-v1":
        raise FrontierError("unsupported Local frontier adapter")
    representation = contract_value(text, "Local Ticket representation")
    location = contract_value(text, "Local Ticket path")
    try:
        configured_location_regex(representation, location)
    except SurfacePatternError as error:
        raise FrontierError(str(error)) from error
    contract = FrontierContract(
        representation=representation,
        location_pattern=location,
        state_fields=csv(contract_value(text, "Ticket state fields")),
        ready_state=contract_value(text, "Ready state"),
        completed_state=contract_value(text, "Completed state"),
        human_states=csv(contract_value(text, "Human-blocked states")),
        blocker_fields=csv(contract_value(text, "Blocker metadata fields")),
        blocker_heading=contract_value(text, "Blocker body heading"),
        claim_field=contract_value(text, "Claim field"),
        claim_aliases=csv(contract_value(text, "Claim field aliases")),
        claim_value=contract_value(text, "Claim value"),
        branch_field=contract_value(text, "Solve branch field"),
        branch_aliases=csv(contract_value(text, "Solve branch field aliases")),
        worktree_field=contract_value(text, "Solve worktree field"),
        worktree_aliases=csv(contract_value(text, "Solve worktree field aliases")),
        identity_fields=csv(contract_value(text, "Ticket ID field aliases")),
        run_fields=csv(contract_value(text, "Publication Run field aliases")),
        source_fields=csv(contract_value(text, "Source field aliases")),
        states=state_registry(contract_value(text, "Ticket state values")),
    )
    if not all(
        (
            contract.state_fields,
            contract.blocker_fields,
            contract.claim_aliases,
            contract.branch_aliases,
            contract.worktree_aliases,
            contract.identity_fields,
            contract.run_fields,
            contract.source_fields,
        )
    ):
        raise FrontierError("Local frontier contract contains an empty field list")
    configured_aliases = [
        normalize_key(alias)
        for aliases in (
            contract.state_fields,
            contract.blocker_fields,
            contract.claim_aliases,
            contract.branch_aliases,
            contract.worktree_aliases,
            contract.identity_fields,
            contract.run_fields,
            contract.source_fields,
        )
        for alias in aliases
    ]
    if len(configured_aliases) != len(set(configured_aliases)):
        raise FrontierError("Local frontier contract has ambiguous field aliases")
    required_states = {
        "review-pending", contract.ready_state, contract.completed_state,
        *contract.human_states,
    }
    if not all(normalize_key(state) in contract.states for state in required_states):
        raise FrontierError("Local frontier contract state registry is incomplete")
    return contract, text


def metadata_region(text: str) -> tuple[int, int]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end < 0:
            raise FrontierError("unclosed Ticket frontmatter")
        return 4, end
    start = 0
    while start < len(text) and text[start] == "\n":
        start += 1
    cursor = start
    saw_field = False
    for line in text[start:].splitlines(keepends=True):
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            break
        saw_field = True
        cursor += len(line)
    if not saw_field:
        raise FrontierError("Ticket has no structured metadata header")
    return start, cursor


def parse_scalar(value: str) -> str | list[str]:
    value = value.strip().strip("'\"")
    if value.startswith("[") and value.endswith("]"):
        return [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
    return value


def parse_metadata(text: str) -> tuple[dict[str, str | list[str]], dict[str, str]]:
    start, end = metadata_region(text)
    values: dict[str, str | list[str]] = {}
    spellings: dict[str, str] = {}
    for line in text[start:end].splitlines():
        if not line.strip() or line.lstrip().startswith("-") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = normalize_key(key)
        if normalized in values:
            raise FrontierError(f"Ticket metadata defines {key.strip()} more than once")
        values[normalized] = parse_scalar(value)
        spellings[normalized] = key.strip()
    return values, spellings


def one(values: dict[str, str | list[str]], fields: tuple[str, ...]) -> tuple[str, str]:
    found = []
    for field in fields:
        normalized = normalize_key(field)
        if normalized in values:
            value = values[normalized]
            if isinstance(value, list):
                raise FrontierError(f"Ticket metadata field {field} must be scalar")
            found.append((field, str(value).strip()))
    if len(found) > 1:
        raise FrontierError(f"conflicting Ticket metadata fields: {', '.join(field for field, _ in found)}")
    return found[0] if found else ("", "")


def many(values: dict[str, str | list[str]], fields: tuple[str, ...]) -> tuple[str, list[str]]:
    found = []
    for field in fields:
        normalized = normalize_key(field)
        if normalized in values:
            found.append((field, values[normalized]))
    if len(found) > 1:
        raise FrontierError(f"conflicting Ticket metadata fields: {', '.join(field for field, _ in found)}")
    if not found:
        return "", []
    field, value = found[0]
    if isinstance(value, list):
        return field, [str(item).strip() for item in value if str(item).strip()]
    return field, [item for item in re.split(r"[,\s]+", str(value).strip()) if item]


def heading_blockers(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    target = heading.strip().lower()
    collecting = False
    level = 0
    result: list[str] = []
    for line in lines:
        match = re.match(r"^(#+)\s+(.*)$", line)
        if match:
            current_level = len(match.group(1))
            title = match.group(2).strip().lower()
            if collecting and current_level <= level:
                break
            if not collecting and title == target:
                collecting = True
                level = current_level
                continue
        if not collecting:
            continue
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        quoted = re.findall(r"`([^`]+)`", value)
        result.extend(item.strip() for item in quoted if item.strip())
        if not quoted and value:
            result.append(value)
    return result


def parse_ticket(
    repo: Path,
    path: Path,
    container: str,
    inner_start: int,
    inner_end: int,
    contract: FrontierContract,
    marker_id: str = "",
) -> Ticket:
    inner = container[inner_start:inner_end]
    values, spellings = parse_metadata(inner)
    configured = {
        normalize_key(alias)
        for aliases in (
            contract.state_fields,
            contract.blocker_fields,
            contract.claim_aliases,
            contract.branch_aliases,
            contract.worktree_aliases,
            contract.identity_fields,
            contract.run_fields,
            contract.source_fields,
        )
        for alias in aliases
    }
    undeclared = sorted((values.keys() & publication.RESERVED_FIELD_ALIASES) - configured)
    if undeclared:
        raise FrontierError(
            "Ticket metadata uses undeclared field aliases: " + ", ".join(undeclared)
        )
    state_field, raw_status = one(values, contract.state_fields)
    if not state_field or not raw_status:
        raise FrontierError(f"Ticket has no configured state field: {path.relative_to(repo)}")
    status = contract.states.get(normalize_key(raw_status), "")
    if not status:
        raise FrontierError(f"Ticket has unknown configured state: {raw_status}")
    flags_field, flags = many(values, contract.claim_aliases)
    blocker_field, blockers = many(values, contract.blocker_fields)
    del blocker_field
    blockers.extend(heading_blockers(inner, contract.blocker_heading))
    blockers = list(dict.fromkeys(blockers))
    identity_field, ticket_id = one(values, contract.identity_fields)
    del identity_field
    relative = path.relative_to(repo).as_posix()
    identity = marker_id or ticket_id or relative
    if (marker_id or ticket_id) and not SAFE_ID.fullmatch(identity):
        raise FrontierError(f"unsafe Ticket identity: {identity}")
    if marker_id and ticket_id and marker_id != ticket_id:
        raise FrontierError(f"section marker ID does not match Ticket ID in {relative}")
    publication_field, publication_run = one(values, contract.run_fields)
    del publication_field
    source_field, _source = one(values, contract.source_fields)
    del source_field, _source
    branch_field, branch = one(values, contract.branch_aliases)
    worktree_field, worktree = one(values, contract.worktree_aliases)
    aliases = {identity}
    if contract.representation == "file-per-ticket":
        aliases.add(relative)
    if ticket_id:
        aliases.add(ticket_id)
    return Ticket(
        identity=identity,
        aliases=aliases,
        status=status,
        flags=flags,
        blockers=blockers,
        publication_run=publication_run,
        path=path,
        container_text=container,
        inner_start=inner_start,
        inner_end=inner_end,
        state_field=spellings.get(normalize_key(state_field), state_field),
        flags_field=spellings.get(normalize_key(flags_field), flags_field),
        branch_field=spellings.get(normalize_key(branch_field), branch_field),
        worktree_field=spellings.get(normalize_key(worktree_field), worktree_field),
        branch=branch,
        worktree=worktree,
        representation=contract.representation,
    )


def configured_paths(repo: Path, contract: FrontierContract) -> list[Path]:
    pattern = re.sub(r"<[^>]+>", "*", contract.location_pattern)
    pattern_path = Path(pattern)
    if pattern_path.is_absolute() or ".." in pattern_path.parts:
        raise FrontierError("configured Local Ticket path escapes the repository")
    matcher = configured_location_regex(contract.representation, contract.location_pattern)
    return sorted(
        path.resolve()
        for path in repo.glob(pattern)
        if path.is_file()
        and matcher.fullmatch(
            (
                path.parent.relative_to(repo).as_posix()
                if contract.representation == "file-per-ticket"
                else path.relative_to(repo).as_posix()
            )
        )
    )


def load_tickets(repo: Path, contract: FrontierContract) -> list[Ticket]:
    tickets: list[Ticket] = []
    for path in configured_paths(repo, contract):
        text = path.read_text(encoding="utf-8")
        if contract.representation == "file-per-ticket":
            tickets.append(parse_ticket(repo, path, text, 0, len(text), contract))
            continue
        cursor = 0
        found = False
        while True:
            begin = BEGIN.search(text, cursor)
            stray_end = END.search(text, cursor)
            if stray_end and (not begin or stray_end.start() < begin.start()):
                raise FrontierError(f"tickets-file has an unmatched end marker: {path.relative_to(repo)}")
            if not begin:
                break
            end = END.search(text, begin.end())
            nested = BEGIN.search(text, begin.end())
            if not end or (nested and nested.start() < end.start()):
                raise FrontierError(f"tickets-file has an ambiguous Ticket section: {path.relative_to(repo)}")
            tickets.append(
                parse_ticket(
                    repo,
                    path,
                    text,
                    begin.end(),
                    end.start(),
                    contract,
                    begin.group(1),
                )
            )
            found = True
            cursor = end.end()
        if END.search(text, cursor):
            raise FrontierError(f"tickets-file has an unmatched end marker: {path.relative_to(repo)}")
        if not found:
            raise FrontierError(f"configured tickets-file has no safe Ticket sections: {path.relative_to(repo)}")
        outside = []
        cursor = 0
        for ticket in [item for item in tickets if item.path == path]:
            marker = BEGIN.search(text, cursor)
            if marker is None:
                raise FrontierError(f"tickets-file section index drifted: {path.relative_to(repo)}")
            outside.append(text[cursor : marker.start()])
            end = END.search(text, marker.end())
            if end is None:
                raise FrontierError(f"tickets-file section index drifted: {path.relative_to(repo)}")
            cursor = end.end()
        outside.append(text[cursor:])
        if re.search(
            r"(?mi)^(?:#{1,6}\s+Ticket\b|(?:Status|State|Ticket ID|Publication Run)[ \t]*:)",
            "".join(outside),
        ):
            raise FrontierError(f"tickets-file contains formal Ticket content outside safe section markers: {path.relative_to(repo)}")
    if not tickets:
        raise FrontierError("configured Local Ticket surface contains no Tickets")
    aliases: dict[str, str] = {}
    identities: set[str] = set()
    for ticket in tickets:
        if ticket.identity in identities:
            raise FrontierError(f"duplicate Ticket identity: {ticket.identity}")
        identities.add(ticket.identity)
        for alias in ticket.aliases:
            if alias in aliases and aliases[alias] != ticket.identity:
                raise FrontierError(f"ambiguous Ticket identity: {alias}")
            aliases[alias] = ticket.identity
    return tickets


def apply_publication_gates(repo: Path, tickets: list[Ticket], contract: FrontierContract) -> None:
    groups: dict[tuple[str, str], list[Ticket]] = {}
    for ticket in tickets:
        if not ticket.publication_run:
            continue
        raw_location = (
            ticket.path.relative_to(repo).as_posix()
            if contract.representation == "tickets-file"
            else ticket.path.parent.relative_to(repo).as_posix()
        )
        groups.setdefault((raw_location, ticket.publication_run), []).append(ticket)
    for (raw_location, run_id), members in groups.items():
        try:
            _location, published, journal = publication.validate_against_journal(
                repo, contract.representation, raw_location, run_id
            )
            selected = publication.run_tickets(published, run_id)
            ready = journal.get("phase") == "promoted" and all(
                item.status
                in {
                    contract.ready_state,
                    contract.completed_state,
                    *contract.human_states,
                }
                for item in selected
            )
            reason = "" if ready else "publication-not-promoted"
        except (publication.AdapterError, OSError) as error:
            ready = False
            reason = f"publication-invalid:{error}"
        for ticket in members:
            ticket.publication_ready = ready
            ticket.publication_reason = reason


def resolve_graph(tickets: list[Ticket]) -> tuple[dict[str, Ticket], dict[str, list[str]], dict[str, list[str]]]:
    by_id = {ticket.identity: ticket for ticket in tickets}
    aliases = {alias: ticket.identity for ticket in tickets for alias in ticket.aliases}
    edges: dict[str, list[str]] = {}
    missing: dict[str, list[str]] = {}
    for ticket in tickets:
        resolved = []
        for blocker in ticket.blockers:
            identity = aliases.get(blocker)
            if identity is None:
                missing.setdefault(ticket.identity, []).append(blocker)
            else:
                resolved.append(identity)
        edges[ticket.identity] = list(dict.fromkeys(resolved))
    return by_id, edges, missing


def cycle_nodes(edges: dict[str, list[str]]) -> set[str]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    low: dict[str, int] = {}
    cyclic: set[str] = set()

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in edges[node]:
            if target not in indexes:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indexes[target])
        if low[node] != indexes[node]:
            return
        component = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            component.append(member)
            if member == node:
                break
        if len(component) > 1 or node in edges[node]:
            cyclic.update(component)

    for node in edges:
        if node not in indexes:
            visit(node)
    return cyclic


def graph_snapshot(contract_text: str, tickets: list[Ticket]) -> str:
    payload = {
        "contract": hashlib.sha256(contract_text.encode()).hexdigest(),
        "tickets": [
            {
                "id": ticket.identity,
                "path": ticket.path.as_posix(),
                "text": hashlib.sha256(ticket.container_text.encode()).hexdigest(),
                "publication_ready": ticket.publication_ready,
                "publication_reason": ticket.publication_reason,
            }
            for ticket in sorted(tickets, key=lambda item: item.identity)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def frontier(repo: Path, selected: list[str]) -> tuple[dict, dict[str, Ticket], FrontierContract, str]:
    contract, contract_text = read_contract(repo)
    tickets = load_tickets(repo, contract)
    apply_publication_gates(repo, tickets, contract)
    by_id, edges, missing = resolve_graph(tickets)
    aliases = {alias: ticket.identity for ticket in tickets for alias in ticket.aliases}
    cyclic = cycle_nodes(edges)
    requested = []
    absent = []
    if selected:
        for raw in selected:
            identity = aliases.get(raw)
            if identity is None:
                absent.append(raw)
            elif identity not in requested:
                requested.append(identity)
    else:
        requested = sorted(by_id)
    reasons: dict[str, list[str]] = {}
    claimable = []
    for identity in requested:
        ticket = by_id[identity]
        item_reasons = []
        if ticket.status == "review-pending":
            item_reasons.append("provisional-state:review-pending")
        elif ticket.status in contract.human_states:
            item_reasons.append(f"human-blocked-state:{ticket.status}")
        elif ticket.status != contract.ready_state:
            item_reasons.append(f"wrong-state:{ticket.status}")
        if not ticket.publication_ready:
            item_reasons.append(ticket.publication_reason)
        if contract.claim_value in ticket.flags:
            item_reasons.append("claim-conflict")
        for blocker in missing.get(identity, []):
            item_reasons.append(f"missing-blocker-target:{blocker}")
        if identity in cyclic:
            item_reasons.append("dependency-cycle")
        for blocker_id in edges[identity]:
            blocker = by_id[blocker_id]
            if blocker.status != contract.completed_state:
                item_reasons.append(f"blocked-by:{blocker_id}:{blocker.status}")
        if item_reasons:
            reasons[identity] = sorted(dict.fromkeys(item_reasons))
        else:
            claimable.append(identity)
    for identity in absent:
        reasons[identity] = ["missing-ticket"]
    payload = {
        "schema": "ultra-local-ticket-frontier/v1",
        "safe_for_batch": True,
        "snapshot": graph_snapshot(contract_text, tickets),
        "selected": selected or "all-configured-tickets",
        "claimable": sorted(claimable),
        "non_frontier": dict(sorted(reasons.items())),
    }
    return payload, by_id, contract, contract_text


def replace_or_insert_field(
    text: str,
    aliases: tuple[str, ...],
    canonical: str,
    value: str,
) -> str:
    start, end = metadata_region(text)
    region = text[start:end]
    allowed = {normalize_key(alias) for alias in aliases}
    pattern = re.compile(r"(?m)^([^\n:]+)([ \t]*:)[ \t]*.*$")
    matches = [
        match for match in pattern.finditer(region)
        if normalize_key(match.group(1)) in allowed
    ]
    if len(matches) > 1:
        raise FrontierError(f"Ticket defines conflicting {canonical} fields")
    if matches:
        match = matches[0]
        updated = (
            region[: match.start()]
            + match.group(1)
            + match.group(2)
            + f" {value}"
            + region[match.end() :]
        )
    else:
        separator = "" if region.endswith("\n") or not region else "\n"
        updated = f"{region}{separator}{canonical}: {value}\n"
    return text[:start] + updated + text[end:]


def git_lock_path(repo: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-path", "ultra-frontier.lock"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise FrontierError(result.stderr.strip() or "cannot resolve Git lock path")
    path = Path(result.stdout.strip())
    return path if path.is_absolute() else (repo / path).resolve()


@contextmanager
def frontier_lock(repo: Path):
    path = git_lock_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def claim(
    repo: Path,
    ticket_id: str,
    expected_snapshot: str,
    branch: str,
    worktree: str,
) -> dict:
    if not all((ticket_id, expected_snapshot, branch, worktree)):
        raise FrontierError("Claim requires Ticket ID, expected snapshot, branch, and worktree")
    with frontier_lock(repo):
        state, by_id, contract, _contract_text = frontier(repo, [ticket_id])
        if state["snapshot"] != expected_snapshot:
            raise FrontierError("stale dependency state: frontier snapshot changed before Claim")
        resolved = state["claimable"][0] if len(state["claimable"]) == 1 else ""
        if not resolved:
            reasons = sorted(
                reason
                for values in state["non_frontier"].values()
                for reason in values
            ) or ["not-claimable"]
            raise FrontierError(f"Ticket is not claimable: {ticket_id} ({', '.join(reasons)})")
        target = by_id[resolved]
        inner = target.inner
        flags = sorted(set(target.flags) | {contract.claim_value})
        inner = replace_or_insert_field(
            inner,
            contract.claim_aliases,
            contract.claim_field,
            ", ".join(flags),
        )
        inner = replace_or_insert_field(
            inner,
            contract.branch_aliases,
            contract.branch_field,
            branch,
        )
        inner = replace_or_insert_field(
            inner,
            contract.worktree_aliases,
            contract.worktree_field,
            worktree,
        )
        current = target.path.read_text(encoding="utf-8")
        if current != target.container_text:
            raise FrontierError("concurrent Ticket change detected before Claim")
        updated = current[: target.inner_start] + inner + current[target.inner_end :]
        publication.atomic_write(target.path, updated)
        refreshed, refreshed_by_id, _contract, _text = frontier(repo, [resolved])
        claimed = refreshed_by_id[resolved]
        if (
            contract.claim_value not in claimed.flags
            or claimed.branch != branch
            or claimed.worktree != worktree
            or (claimed.publication_run and not claimed.publication_ready)
        ):
            raise FrontierError("Claim post-write verification failed")
        return {
            "schema": "ultra-local-ticket-frontier/v1",
            "ticket_id": resolved,
            "claimed": True,
            "previous_snapshot": expected_snapshot,
            "snapshot": refreshed["snapshot"],
            "branch": branch,
            "worktree": worktree,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("frontier", "claim"))
    parser.add_argument("--repo", default=".")
    parser.add_argument("--ticket-id", action="append", default=[])
    parser.add_argument("--expected-snapshot")
    parser.add_argument("--branch")
    parser.add_argument("--worktree")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    try:
        if args.action == "frontier":
            payload, _tickets, _contract, _text = frontier(repo, args.ticket_id)
        else:
            if len(args.ticket_id) != 1:
                raise FrontierError("Claim requires exactly one --ticket-id")
            payload = claim(
                repo,
                args.ticket_id[0],
                args.expected_snapshot or "",
                args.branch or "",
                args.worktree or "",
            )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (FrontierError, OSError, publication.AdapterError) as error:
        print(f"local-ticket-frontier: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
