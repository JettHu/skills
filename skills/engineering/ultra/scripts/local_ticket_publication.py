#!/usr/bin/env python3
"""Fail-closed Local Markdown Ticket review-publication adapter."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from local_ticket_surface import (
    REPRESENTATIONS,
    SurfacePatternError,
    configured_location_regex as compile_location_regex,
)


SCHEMA = "ultra-local-ticket-publication/v1"
CONTRACT = Path("docs/agents/ultra-tracker.md")
CANCELLATION_POLICIES = {
    "retain-until-explicit-cleanup",
    "delete-on-cancel",
}
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
BEGIN = re.compile(
    r"(?m)^<!-- ultra-ticket:begin id=([A-Za-z0-9][A-Za-z0-9._-]*) -->[ \t]*\n"
)
END = re.compile(r"(?m)^<!-- ultra-ticket:end -->[ \t]*(?:\n|\Z)")


class AdapterError(RuntimeError):
    """The configured representation cannot be mutated safely."""


@dataclass
class Ticket:
    ticket_id: str
    run_id: str
    status: str
    source: str
    blockers: list[str]
    flags: list[str]
    state_field: str
    flags_field: str
    path: Path
    text: str
    inner_start: int = 0
    inner_end: int = 0
    section_start: int = 0
    section_end: int = 0

    @property
    def inner(self) -> str:
        return self.text[self.inner_start : self.inner_end]

    @property
    def body_digest(self) -> str:
        normalized = normalize_operational_fields(self.inner)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LocalContract:
    representation: str
    location_pattern: str
    cancellation_policy: str
    identity_fields: tuple[str, ...]
    run_fields: tuple[str, ...]
    source_fields: tuple[str, ...]
    state_fields: tuple[str, ...]
    blocker_fields: tuple[str, ...]
    claim_fields: tuple[str, ...]
    branch_fields: tuple[str, ...]
    worktree_fields: tuple[str, ...]
    states: dict[str, str]


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


RESERVED_FIELD_ALIASES = {
    normalize_key(field)
    for field in (
        "Ticket ID", "ID", "Publication Run", "Publication Run ID",
        "Source Spec", "Parent", "Status", "State", "Ticket Status",
        "Blocked By", "Blocker", "Blockers", "Flags", "Labels",
        "Solve Branch", "Branch", "Solve Worktree", "Worktree",
    )
}


def csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def state_registry(value: str) -> dict[str, str]:
    """Parse an explicit canonical-state registry with separator/case variants."""
    result: dict[str, str] = {}
    for canonical in csv(value):
        key = normalize_key(canonical)
        if not key or key in result:
            raise AdapterError("State values must be unique and non-empty")
        result[key] = canonical
    return result


def parse_scalar(value: str) -> str | list[str]:
    value = value.strip().strip("'\"")
    if value.startswith("[") and value.endswith("]"):
        return [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
    return value


def metadata_region(text: str) -> tuple[int, int, str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end < 0:
            raise AdapterError("unclosed Ticket frontmatter")
        return 4, end, "frontmatter"
    start = 0
    while start < len(text) and text[start] == "\n":
        start += 1
    cursor = start
    saw_field = False
    for line in text[start:].splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            break
        saw_field = True
        cursor += len(line)
    if not saw_field:
        raise AdapterError("Ticket has no structured metadata header")
    return start, cursor, "header"


def parse_metadata(text: str) -> dict[str, str | list[str]]:
    start, end, _kind = metadata_region(text)
    metadata: dict[str, str | list[str]] = {}
    for line in text[start:end].splitlines():
        if not line.strip() or line.lstrip().startswith("-") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized = normalize_key(key)
        if normalized in metadata:
            raise AdapterError(f"Ticket metadata defines {key.strip()} more than once")
        metadata[normalized] = parse_scalar(value)
    return metadata


def metadata_spelling(text: str, normalized: str) -> str:
    start, end, _kind = metadata_region(text)
    for line in text[start:end].splitlines():
        if not line.strip() or line.lstrip().startswith("-") or ":" not in line:
            continue
        key, _value = line.split(":", 1)
        if normalize_key(key) == normalized:
            return key.strip()
    return ""


def one(metadata: dict[str, str | list[str]], *keys: str) -> str:
    values = [(key, metadata[key]) for key in keys if key in metadata]
    if len(values) > 1:
        raise AdapterError(f"conflicting Ticket metadata fields: {', '.join(keys)}")
    if not values:
        return ""
    _key, value = values[0]
    if isinstance(value, list):
        raise AdapterError(f"Ticket metadata field {keys[0]} must be scalar")
    return str(value).strip()


def many(metadata: dict[str, str | list[str]], *keys: str) -> list[str]:
    values = [(key, metadata[key]) for key in keys if key in metadata]
    if len(values) > 1:
        raise AdapterError(f"conflicting Ticket metadata fields: {', '.join(keys)}")
    value = values[0][1] if values else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item for item in re.split(r"[,\s]+", str(value).strip()) if item]


def replace_metadata_field(text: str, field: str, value: str) -> str:
    start, end, _kind = metadata_region(text)
    region = text[start:end]
    pattern = re.compile(r"(?m)^([^\n:]+)([ \t]*:)[ \t]*.*$")
    matches = [
        match
        for match in pattern.finditer(region)
        if normalize_key(match.group(1)) == normalize_key(field)
    ]
    if len(matches) != 1:
        raise AdapterError(f"Ticket must define exactly one {field.title()} field")
    match = matches[0]
    updated = (
        region[: match.start()]
        + match.group(1)
        + match.group(2)
        + " "
        + value
        + region[match.end() :]
    )
    return text[:start] + updated + text[end:]


def normalize_operational_fields(text: str) -> str:
    start, end, _kind = metadata_region(text)
    region = text[start:end]
    fields = {
        "status": (r"status", False),
        "state": (r"state", False),
        "flags": (r"flags", False),
        "labels": (r"labels", False),
        "solve_branch": (r"(?:solve[ _-]+branch|branch)", True),
        "solve_worktree": (r"(?:solve[ _-]+worktree|worktree)", True),
    }
    for field, (spelling, remove) in fields.items():
        pattern = re.compile(
            rf"(?mi)^({spelling}[ \t]*:)[ \t]*.*(?:\n|\Z)" if remove
            else rf"(?mi)^({spelling}[ \t]*:)[ \t]*.*$"
        )
        matches = list(pattern.finditer(region))
        if len(matches) > 1:
            raise AdapterError(f"Ticket defines {field} more than once")
        if matches:
            match = matches[0]
            replacement = "" if remove else match.group(1) + f" <{field}>"
            region = region[: match.start()] + replacement + region[match.end() :]
    return text[:start] + region + text[end:]


def ticket_from_inner(
    path: Path,
    text: str,
    inner_start: int,
    inner_end: int,
    contract: LocalContract,
    marker_id: str = "",
) -> Ticket | None:
    inner = text[inner_start:inner_end]
    metadata = parse_metadata(inner)
    identity_keys = tuple(normalize_key(field) for field in contract.identity_fields)
    run_keys = tuple(normalize_key(field) for field in contract.run_fields)
    state_keys = tuple(normalize_key(field) for field in contract.state_fields)
    source_keys = tuple(normalize_key(field) for field in contract.source_fields)
    blocker_keys = tuple(normalize_key(field) for field in contract.blocker_fields)
    claim_keys = tuple(normalize_key(field) for field in contract.claim_fields)
    branch_keys = tuple(normalize_key(field) for field in contract.branch_fields)
    worktree_keys = tuple(normalize_key(field) for field in contract.worktree_fields)
    configured_keys = {
        *identity_keys, *run_keys, *state_keys, *source_keys, *blocker_keys,
        *claim_keys,
        *branch_keys, *worktree_keys,
    }
    undeclared = sorted((metadata.keys() & RESERVED_FIELD_ALIASES) - configured_keys)
    if undeclared:
        raise AdapterError(
            "Ticket metadata uses undeclared field aliases: " + ", ".join(undeclared)
        )
    ticket_id = one(metadata, *identity_keys)
    run_id = one(metadata, *run_keys)
    raw_status = one(metadata, *state_keys)
    status = contract.states.get(normalize_key(raw_status), "")
    state_key = next((key for key in state_keys if key in metadata), "")
    flags_key = next((key for key in claim_keys if key in metadata), "")
    state_field = metadata_spelling(inner, state_key) if state_key else ""
    flags_field = metadata_spelling(inner, flags_key) if flags_key else ""
    touched = any((ticket_id, run_id, status == "review-pending"))
    if not touched and not marker_id:
        return None
    if not ticket_id or not SAFE_ID.fullmatch(ticket_id):
        raise AdapterError(f"unsafe or missing Ticket ID in {path}")
    if marker_id and marker_id != ticket_id:
        raise AdapterError(f"section marker ID does not match Ticket ID in {path}")
    if not run_id or not SAFE_ID.fullmatch(run_id):
        raise AdapterError(f"unsafe or missing Publication Run for {ticket_id}")
    if not status:
        raise AdapterError(f"unsupported status for {ticket_id}: {raw_status or '<missing>'}")
    source = one(metadata, *source_keys)
    if not source:
        raise AdapterError(f"missing Source Spec or Parent for {ticket_id}")
    one(metadata, *branch_keys)
    one(metadata, *worktree_keys)
    return Ticket(
        ticket_id=ticket_id,
        run_id=run_id,
        status=status,
        source=source,
        blockers=many(metadata, *blocker_keys),
        flags=many(metadata, *claim_keys),
        state_field=state_field,
        flags_field=flags_field,
        path=path,
        text=text,
        inner_start=inner_start,
        inner_end=inner_end,
    )


def safe_location(repo: Path, raw: str) -> Path:
    location = (repo / raw).resolve()
    try:
        location.relative_to(repo)
    except ValueError as error:
        raise AdapterError("configured Ticket location escapes the repository") from error
    return location


def contract_value(text: str, field: str) -> str:
    matches = re.findall(
        rf"(?m)^{re.escape(field)}:[ \t]*(\S(?:.*\S)?)[ \t]*$", text
    )
    if len(matches) != 1:
        raise AdapterError(f"Local tracker contract must define exactly one {field}")
    return matches[0]


def configured_local_contract(repo: Path) -> LocalContract:
    path = repo / CONTRACT
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise AdapterError(f"missing Local tracker contract: {path}") from error
    strategy = contract_value(text, "Publication strategy")
    if strategy != "local-review-pending":
        raise AdapterError(
            "Local tracker contract must select local-review-pending exactly once"
        )
    representation = contract_value(text, "Local Ticket representation")
    if representation not in REPRESENTATIONS:
        raise AdapterError(
            f"unsupported Local Ticket representation: {representation}"
        )
    location_pattern = contract_value(text, "Local Ticket path")
    policy = contract_value(text, "Cancellation policy")
    if policy not in CANCELLATION_POLICIES:
        raise AdapterError(f"unsupported cancellation policy: {policy}")
    fields = {
        "identity_fields": csv(contract_value(text, "Ticket ID field aliases")),
        "run_fields": csv(contract_value(text, "Publication Run field aliases")),
        "source_fields": csv(contract_value(text, "Source field aliases")),
        "state_fields": csv(contract_value(text, "Ticket state fields")),
        "blocker_fields": csv(contract_value(text, "Blocker metadata fields")),
        "claim_fields": csv(contract_value(text, "Claim field aliases")),
        "branch_fields": csv(contract_value(text, "Solve branch field aliases")),
        "worktree_fields": csv(contract_value(text, "Solve worktree field aliases")),
    }
    if not all(fields.values()):
        raise AdapterError("Local tracker contract contains an empty field alias list")
    normalized = [normalize_key(alias) for aliases in fields.values() for alias in aliases]
    if len(normalized) != len(set(normalized)):
        raise AdapterError("Local tracker contract has ambiguous field aliases")
    states = state_registry(contract_value(text, "Ticket state values"))
    required_states = {
        "review-pending",
        contract_value(text, "Ready state"),
        contract_value(text, "Completed state"),
        *csv(contract_value(text, "Human-blocked states")),
    }
    if not all(normalize_key(state) in states for state in required_states):
        raise AdapterError("Local tracker contract state registry is incomplete")
    return LocalContract(
        representation, location_pattern, policy, states=states, **fields
    )


def configured_location_regex(contract: LocalContract) -> re.Pattern[str]:
    try:
        return compile_location_regex(
            contract.representation, contract.location_pattern
        )
    except SurfacePatternError as error:
        raise AdapterError(str(error)) from error


def validate_configured_surface(
    repo: Path, representation: str, raw_location: str
) -> tuple[Path, LocalContract]:
    contract = configured_local_contract(repo)
    if representation != contract.representation:
        raise AdapterError(
            "configured Local Ticket representation does not match the requested adapter"
        )
    location = safe_location(repo, raw_location)
    relative = location.relative_to(repo).as_posix()
    if not configured_location_regex(contract).fullmatch(relative):
        raise AdapterError(
            f"configured Local Ticket path does not authorize requested surface: {relative}"
        )
    return location, contract


def load_file_per(location: Path, contract: LocalContract) -> list[Ticket]:
    if not location.is_dir():
        raise AdapterError(f"file-per-ticket location is not a directory: {location}")
    tickets = []
    for path in sorted(location.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        ticket = ticket_from_inner(path, text, 0, len(text), contract)
        if ticket:
            tickets.append(ticket)
    return tickets


def load_tickets_file(location: Path, contract: LocalContract) -> list[Ticket]:
    if not location.is_file():
        raise AdapterError(f"tickets-file does not exist: {location}")
    text = location.read_text(encoding="utf-8")
    tickets: list[Ticket] = []
    cursor = 0
    while True:
        begin = BEGIN.search(text, cursor)
        end_before_begin = END.search(text, cursor)
        if end_before_begin and (not begin or end_before_begin.start() < begin.start()):
            raise AdapterError("tickets-file has an unmatched end marker")
        if not begin:
            break
        end = END.search(text, begin.end())
        nested = BEGIN.search(text, begin.end())
        if not end or (nested and nested.start() < end.start()):
            raise AdapterError("tickets-file has an ambiguous or nested Ticket section")
        ticket = ticket_from_inner(
            location, text, begin.end(), end.start(), contract, begin.group(1)
        )
        if ticket is None:
            raise AdapterError("tickets-file marker encloses no formal Ticket")
        ticket.section_start = begin.start()
        ticket.section_end = end.end()
        tickets.append(ticket)
        cursor = end.end()
    if END.search(text, cursor):
        raise AdapterError("tickets-file has an unmatched end marker")
    outside_parts = []
    cursor = 0
    for ticket in tickets:
        outside_parts.append(text[cursor : ticket.section_start])
        cursor = ticket.section_end
    outside_parts.append(text[cursor:])
    outside = "".join(outside_parts)
    if re.search(
        r"(?mi)^(?:#{1,6}\s+Ticket\b|(?:Status|State|Ticket ID|Publication Run)[ \t]*:)",
        outside,
    ):
        raise AdapterError("tickets-file contains formal Ticket content outside safe section markers")
    return tickets


def load_tickets_at(
    location: Path, representation: str, contract: LocalContract
) -> list[Ticket]:
    tickets = (
        load_file_per(location, contract)
        if representation == "file-per-ticket"
        else load_tickets_file(location, contract)
    )
    seen: dict[str, Path] = {}
    for ticket in tickets:
        if ticket.ticket_id in seen:
            raise AdapterError(f"duplicate Ticket ID: {ticket.ticket_id}")
        seen[ticket.ticket_id] = ticket.path
    return tickets


def load_tickets(repo: Path, representation: str, raw_location: str) -> tuple[Path, list[Ticket]]:
    location, contract = validate_configured_surface(repo, representation, raw_location)
    return location, load_tickets_at(location, representation, contract)


def journal_dir(location: Path, representation: str) -> Path:
    base = location if representation == "file-per-ticket" else location.parent
    return base / ".ultra-publications"


def journal_path(location: Path, representation: str, run_id: str) -> Path:
    if not SAFE_ID.fullmatch(run_id):
        raise AdapterError("unsafe publication-run identity")
    return journal_dir(location, representation) / f"{run_id}.json"


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_journal(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"missing or invalid publication journal: {path}") from error
    if data.get("schema") != SCHEMA:
        raise AdapterError("unsupported publication journal schema")
    return data


def write_journal(path: Path, data: dict) -> None:
    atomic_write(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


@contextmanager
def mutation_lock(location: Path, representation: str):
    lock = journal_dir(location, representation) / ".adapter.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def stable_mutation_surface(
    repo: Path, representation: str, raw_location: str, attempts: int = 3
):
    """Lock only a surface that resolves identically before and after locking."""
    for _attempt in range(attempts):
        expected, _contract = validate_configured_surface(
            repo, representation, raw_location
        )
        with mutation_lock(expected, representation):
            confirmed, contract = validate_configured_surface(
                repo, representation, raw_location
            )
            if confirmed != expected:
                continue
            yield confirmed, contract
            return
    raise AdapterError(
        "configured Ticket surface changed while acquiring its mutation lock"
    )


def run_tickets(tickets: list[Ticket], run_id: str) -> list[Ticket]:
    selected = [ticket for ticket in tickets if ticket.run_id == run_id]
    if not selected:
        raise AdapterError(f"publication run has no formal Tickets: {run_id}")
    return selected


def validate_blocker_targets(tickets: list[Ticket]) -> None:
    known = {ticket.ticket_id for ticket in tickets}
    for ticket in tickets:
        missing = sorted(set(ticket.blockers) - known)
        if missing:
            raise AdapterError(f"{ticket.ticket_id} has unresolved blocker IDs: {', '.join(missing)}")


def snapshot(selected: list[Ticket]) -> dict[str, str]:
    return {ticket.ticket_id: ticket.body_digest for ticket in selected}


def register(repo: Path, representation: str, raw_location: str, run_id: str, allow_membership_change: bool) -> dict:
    with stable_mutation_surface(
        repo, representation, raw_location
    ) as (location, _contract):
        path = journal_path(location, representation, run_id)
        tickets = load_tickets_at(location, representation, _contract)
        selected = run_tickets(tickets, run_id)
        validate_blocker_targets(tickets)
        if any(ticket.status != "review-pending" for ticket in selected):
            raise AdapterError("registration requires every run member to be review-pending")
        old = read_journal(path) if path.exists() else None
        members = sorted(ticket.ticket_id for ticket in selected)
        if old and old.get("phase") in {"promoting", "promoted"}:
            raise AdapterError("cannot re-register a promoting or promoted run")
        if old and sorted(old.get("members", [])) != members and not allow_membership_change:
            raise AdapterError("publication membership changed without explicit review-fix authorization")
        data = {
            "schema": SCHEMA,
            "run_id": run_id,
            "representation": representation,
            "location": str(location.relative_to(repo)),
            "members": members,
            "body_digests": snapshot(selected),
            "phase": "review-pending",
        }
        write_journal(path, data)
    return data


def validate_against_journal_at(
    repo: Path,
    representation: str,
    location: Path,
    run_id: str,
    contract: LocalContract | None = None,
) -> tuple[Path, list[Ticket], dict]:
    contract = contract or configured_local_contract(repo)
    tickets = load_tickets_at(location, representation, contract)
    selected = run_tickets(tickets, run_id)
    validate_blocker_targets(tickets)
    data = read_journal(journal_path(location, representation, run_id))
    if data.get("representation") != representation or data.get("location") != str(location.relative_to(repo)):
        raise AdapterError("publication journal does not match the configured adapter")
    if sorted(data.get("members", [])) != sorted(ticket.ticket_id for ticket in selected):
        raise AdapterError("publication membership drifted")
    if data.get("body_digests") != snapshot(selected):
        raise AdapterError("Ticket content changed after review registration")
    return location, tickets, data


def validate_against_journal(repo: Path, representation: str, raw_location: str, run_id: str) -> tuple[Path, list[Ticket], dict]:
    location, contract = validate_configured_surface(
        repo, representation, raw_location
    )
    return validate_against_journal_at(
        repo, representation, location, run_id, contract
    )


def replace_status(ticket: Ticket, status: str) -> str:
    inner = replace_metadata_field(ticket.inner, ticket.state_field, status)
    return ticket.text[: ticket.inner_start] + inner + ticket.text[ticket.inner_end :]


def promote(repo: Path, representation: str, raw_location: str, run_id: str) -> dict:
    with stable_mutation_surface(
        repo, representation, raw_location
    ) as (location, contract):
        path = journal_path(location, representation, run_id)
        location, tickets, data = validate_against_journal_at(
            repo, representation, location, run_id, contract
        )
        if data.get("phase") == "promoted":
            if all(ticket.status == "ready-for-agent" for ticket in run_tickets(tickets, run_id)):
                return data
            raise AdapterError("promoted journal has non-ready members")
        if data.get("phase") not in {"review-pending", "promoting"}:
            raise AdapterError(f"unsupported publication phase: {data.get('phase')}")
        selected = run_tickets(tickets, run_id)
        if any(ticket.status not in {"review-pending", "ready-for-agent"} for ticket in selected):
            raise AdapterError("promotion found an unsupported member state")
        data["phase"] = "promoting"
        write_journal(path, data)

        fail_after = int(os.environ.get("ULTRA_PUBLICATION_FAIL_AFTER", "0") or 0)
        changed = 0
        if representation == "file-per-ticket":
            for ticket in selected:
                if ticket.status == "ready-for-agent":
                    continue
                current = ticket.path.read_text(encoding="utf-8")
                if hashlib.sha256(normalize_operational_fields(current).encode()).hexdigest() != ticket.body_digest:
                    raise AdapterError(f"concurrent Ticket change detected: {ticket.ticket_id}")
                atomic_write(
                    ticket.path,
                    replace_metadata_field(
                        current, ticket.state_field, "ready-for-agent"
                    ),
                )
                changed += 1
                if fail_after and changed >= fail_after:
                    raise AdapterError("injected mid-promotion interruption")
        else:
            current = location.read_text(encoding="utf-8")
            if current != selected[0].text:
                raise AdapterError("concurrent tickets-file change detected")
            updated = current
            for ticket in sorted(selected, key=lambda item: item.inner_start, reverse=True):
                if ticket.status == "review-pending":
                    inner = replace_metadata_field(
                        ticket.inner, ticket.state_field, "ready-for-agent"
                    )
                    updated = updated[: ticket.inner_start] + inner + updated[ticket.inner_end :]
            atomic_write(location, updated)

        _location, refreshed, final = validate_against_journal_at(
            repo, representation, location, run_id
        )
        if any(ticket.status != "ready-for-agent" for ticket in run_tickets(refreshed, run_id)):
            raise AdapterError("complete-set post-promotion verification failed")
        final["phase"] = "promoted"
        write_journal(path, final)
        return final


def inspect(repo: Path, representation: str, raw_location: str, run_id: str) -> dict:
    location, contract = validate_configured_surface(
        repo, representation, raw_location
    )
    tickets = load_tickets_at(location, representation, contract)
    selected = run_tickets(tickets, run_id)
    path = journal_path(location, representation, run_id)
    data = read_journal(path) if path.exists() else None
    return {
        "run_id": run_id,
        "phase": data.get("phase") if data else "unregistered",
        "members": sorted(ticket.ticket_id for ticket in selected),
        "statuses": {ticket.ticket_id: ticket.status for ticket in selected},
    }


def cleanup(repo: Path, representation: str, raw_location: str, run_id: str, explicit: bool) -> dict:
    with stable_mutation_surface(
        repo, representation, raw_location
    ) as (location, contract):
        path = journal_path(location, representation, run_id)
        if (
            not explicit
            and contract.cancellation_policy == "retain-until-explicit-cleanup"
        ):
            raise AdapterError("cancellation retains review-pending artifacts; cleanup requires --explicit")
        location, tickets, data = validate_against_journal_at(
            repo, representation, location, run_id
        )
        phase = data.get("phase")
        if phase != "review-pending":
            raise AdapterError(
                f"cleanup requires journal phase review-pending, found {phase or '<missing>'}"
            )
        selected = run_tickets(tickets, run_id)
        if any(ticket.status != "review-pending" for ticket in selected):
            raise AdapterError(
                "cleanup requires every run member to be review-pending"
            )
        if representation == "file-per-ticket":
            for ticket in selected:
                if ticket.path.read_text(encoding="utf-8") != ticket.text:
                    raise AdapterError(
                        f"concurrent Ticket change detected before cleanup: {ticket.ticket_id}"
                    )
            for ticket in selected:
                ticket.path.unlink()
        else:
            text = location.read_text(encoding="utf-8")
            if text != selected[0].text:
                raise AdapterError("concurrent tickets-file change detected before cleanup")
            for ticket in sorted(selected, key=lambda item: item.section_start, reverse=True):
                text = text[: ticket.section_start] + text[ticket.section_end :]
            atomic_write(location, text)
        path.unlink()
    return {"run_id": run_id, "cleaned": sorted(ticket.ticket_id for ticket in selected)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--representation", required=True, choices=("file-per-ticket", "tickets-file"))
    parser.add_argument("--location", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--ticket-id")
    parser.add_argument("--allow-membership-change", action="store_true")
    parser.add_argument("--explicit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    try:
        if args.action not in {"register", "inspect", "promote", "cleanup"}:
            raise AdapterError(f"unsupported operation: {args.action}")
        if args.action == "register":
            payload = register(repo, args.representation, args.location, args.run_id, args.allow_membership_change)
        elif args.action == "promote":
            payload = promote(repo, args.representation, args.location, args.run_id)
        elif args.action == "cleanup":
            payload = cleanup(repo, args.representation, args.location, args.run_id, args.explicit)
        else:
            payload = inspect(repo, args.representation, args.location, args.run_id)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (AdapterError, OSError) as error:
        print(f"local-ticket-publication: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
