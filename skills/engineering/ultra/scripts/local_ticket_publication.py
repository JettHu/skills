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


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


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


def one(metadata: dict[str, str | list[str]], *keys: str) -> str:
    values = [metadata.get(key) for key in keys if metadata.get(key) not in (None, "", [])]
    if len(values) > 1:
        raise AdapterError(f"conflicting Ticket metadata fields: {', '.join(keys)}")
    if not values:
        return ""
    value = values[0]
    if isinstance(value, list):
        raise AdapterError(f"Ticket metadata field {keys[0]} must be scalar")
    return str(value).strip()


def many(metadata: dict[str, str | list[str]], *keys: str) -> list[str]:
    value = next((metadata.get(key) for key in keys if metadata.get(key) not in (None, "", [])), [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item for item in re.split(r"[,\s]+", str(value).strip()) if item]


def replace_metadata_field(text: str, field: str, value: str) -> str:
    start, end, _kind = metadata_region(text)
    region = text[start:end]
    pattern = re.compile(rf"(?mi)^({re.escape(field)}[ \t]*:)[ \t]*.*$")
    matches = list(pattern.finditer(region))
    if len(matches) != 1:
        raise AdapterError(f"Ticket must define exactly one {field.title()} field")
    match = matches[0]
    updated = region[: match.start()] + match.group(1) + " " + value + region[match.end() :]
    return text[:start] + updated + text[end:]


def normalize_operational_fields(text: str) -> str:
    start, end, _kind = metadata_region(text)
    region = text[start:end]
    for field in (
        "status",
        "state",
        "flags",
        "labels",
        "solve_branch",
        "solve_worktree",
    ):
        pattern = re.compile(rf"(?mi)^({re.escape(field)}[ \t]*:)[ \t]*.*$")
        matches = list(pattern.finditer(region))
        if len(matches) > 1:
            raise AdapterError(f"Ticket defines {field} more than once")
        if matches:
            match = matches[0]
            region = region[: match.start()] + match.group(1) + f" <{field}>" + region[match.end() :]
    return text[:start] + region + text[end:]


def ticket_from_inner(path: Path, text: str, inner_start: int, inner_end: int, marker_id: str = "") -> Ticket | None:
    inner = text[inner_start:inner_end]
    metadata = parse_metadata(inner)
    ticket_id = one(metadata, "ticket_id", "id")
    run_id = one(metadata, "publication_run")
    status = one(metadata, "status", "state")
    state_field = "status" if "status" in metadata else "state" if "state" in metadata else ""
    flags_field = "flags" if "flags" in metadata else "labels" if "labels" in metadata else ""
    touched = any((ticket_id, run_id, status == "review-pending"))
    if not touched and not marker_id:
        return None
    if not ticket_id or not SAFE_ID.fullmatch(ticket_id):
        raise AdapterError(f"unsafe or missing Ticket ID in {path}")
    if marker_id and marker_id != ticket_id:
        raise AdapterError(f"section marker ID does not match Ticket ID in {path}")
    if not run_id or not SAFE_ID.fullmatch(run_id):
        raise AdapterError(f"unsafe or missing Publication Run for {ticket_id}")
    if status not in {
        "review-pending",
        "ready-for-agent",
        "completed",
        "ready-for-human",
        "needs-info",
    }:
        raise AdapterError(f"unsupported status for {ticket_id}: {status or '<missing>'}")
    source = one(metadata, "source_spec", "parent")
    if not source:
        raise AdapterError(f"missing Source Spec or Parent for {ticket_id}")
    return Ticket(
        ticket_id=ticket_id,
        run_id=run_id,
        status=status,
        source=source,
        blockers=many(metadata, "blocked_by", "blockers"),
        flags=many(metadata, "flags", "labels"),
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
    return LocalContract(representation, location_pattern, policy)


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


def load_file_per(location: Path) -> list[Ticket]:
    if not location.is_dir():
        raise AdapterError(f"file-per-ticket location is not a directory: {location}")
    tickets = []
    for path in sorted(location.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        ticket = ticket_from_inner(path, text, 0, len(text))
        if ticket:
            tickets.append(ticket)
    return tickets


def load_tickets_file(location: Path) -> list[Ticket]:
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
        ticket = ticket_from_inner(location, text, begin.end(), end.start(), begin.group(1))
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


def load_tickets_at(location: Path, representation: str) -> list[Ticket]:
    tickets = load_file_per(location) if representation == "file-per-ticket" else load_tickets_file(location)
    seen: dict[str, Path] = {}
    for ticket in tickets:
        if ticket.ticket_id in seen:
            raise AdapterError(f"duplicate Ticket ID: {ticket.ticket_id}")
        seen[ticket.ticket_id] = ticket.path
    return tickets


def load_tickets(repo: Path, representation: str, raw_location: str) -> tuple[Path, list[Ticket]]:
    location = safe_location(repo, raw_location)
    return location, load_tickets_at(location, representation)


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
        tickets = load_tickets_at(location, representation)
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
    repo: Path, representation: str, location: Path, run_id: str
) -> tuple[Path, list[Ticket], dict]:
    tickets = load_tickets_at(location, representation)
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
    location, _contract = validate_configured_surface(
        repo, representation, raw_location
    )
    return validate_against_journal_at(repo, representation, location, run_id)


def replace_status(ticket: Ticket, status: str) -> str:
    inner = replace_metadata_field(ticket.inner, ticket.state_field, status)
    return ticket.text[: ticket.inner_start] + inner + ticket.text[ticket.inner_end :]


def promote(repo: Path, representation: str, raw_location: str, run_id: str) -> dict:
    with stable_mutation_surface(
        repo, representation, raw_location
    ) as (location, _contract):
        path = journal_path(location, representation, run_id)
        location, tickets, data = validate_against_journal_at(
            repo, representation, location, run_id
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


def claimable_ids_at(
    repo: Path, representation: str, location: Path, run_id: str
) -> list[str]:
    _location, tickets, data = validate_against_journal_at(
        repo, representation, location, run_id
    )
    selected = run_tickets(tickets, run_id)
    post_publication_states = {
        "ready-for-agent",
        "completed",
        "ready-for-human",
        "needs-info",
    }
    if data.get("phase") != "promoted" or any(
        ticket.status not in post_publication_states for ticket in selected
    ):
        return []
    by_id = {ticket.ticket_id: ticket for ticket in tickets}
    result = []
    for ticket in selected:
        if ticket.status != "ready-for-agent":
            continue
        if "solve-in-progress" in ticket.flags:
            continue
        if all(by_id[blocker].status == "completed" for blocker in ticket.blockers):
            result.append(ticket.ticket_id)
    return sorted(result)


def claimable_ids(repo: Path, representation: str, raw_location: str, run_id: str) -> list[str]:
    location, _contract = validate_configured_surface(
        repo, representation, raw_location
    )
    return claimable_ids_at(repo, representation, location, run_id)


def claim(repo: Path, representation: str, raw_location: str, run_id: str, ticket_id: str) -> dict:
    if not ticket_id:
        raise AdapterError("claim requires --ticket-id")
    with stable_mutation_surface(
        repo, representation, raw_location
    ) as (location, _contract):
        location, tickets, _data = validate_against_journal_at(
            repo, representation, location, run_id
        )
        if ticket_id not in claimable_ids_at(
            repo, representation, location, run_id
        ):
            raise AdapterError(f"Ticket is not claimable: {ticket_id}")
        target = next(ticket for ticket in tickets if ticket.ticket_id == ticket_id)
        if not target.flags_field:
            raise AdapterError(
                f"Ticket has no configured Flags or Labels Claim field: {ticket_id}"
            )
        updated_flags = sorted(set(target.flags) | {"solve-in-progress"})
        replacement = replace_metadata_field(
            target.inner, target.flags_field, ", ".join(updated_flags)
        )
        if representation == "file-per-ticket":
            current = target.path.read_text(encoding="utf-8")
            if current != target.text:
                raise AdapterError("concurrent Ticket change detected before Claim")
            atomic_write(target.path, replacement)
        else:
            current = location.read_text(encoding="utf-8")
            if current != target.text:
                raise AdapterError("concurrent tickets-file change detected before Claim")
            updated = current[: target.inner_start] + replacement + current[target.inner_end :]
            atomic_write(location, updated)
        _location, refreshed, _journal = validate_against_journal_at(
            repo, representation, location, run_id
        )
        claimed = next(ticket for ticket in refreshed if ticket.ticket_id == ticket_id)
        if "solve-in-progress" not in claimed.flags:
            raise AdapterError("Claim post-write verification failed")
        return {"run_id": run_id, "ticket_id": ticket_id, "claimed": True}


def inspect(repo: Path, representation: str, raw_location: str, run_id: str) -> dict:
    location, _contract = validate_configured_surface(
        repo, representation, raw_location
    )
    tickets = load_tickets_at(location, representation)
    selected = run_tickets(tickets, run_id)
    path = journal_path(location, representation, run_id)
    data = read_journal(path) if path.exists() else None
    claimable = []
    if data:
        try:
            claimable = claimable_ids_at(repo, representation, location, run_id)
        except AdapterError:
            claimable = []
    return {
        "run_id": run_id,
        "phase": data.get("phase") if data else "unregistered",
        "members": sorted(ticket.ticket_id for ticket in selected),
        "statuses": {ticket.ticket_id: ticket.status for ticket in selected},
        "claimable": claimable,
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
    parser.add_argument("action", choices=("register", "inspect", "promote", "claim-check", "claim", "cleanup"))
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
        if args.action == "register":
            payload = register(repo, args.representation, args.location, args.run_id, args.allow_membership_change)
        elif args.action == "promote":
            payload = promote(repo, args.representation, args.location, args.run_id)
        elif args.action == "cleanup":
            payload = cleanup(repo, args.representation, args.location, args.run_id, args.explicit)
        elif args.action == "claim":
            payload = claim(
                repo,
                args.representation,
                args.location,
                args.run_id,
                args.ticket_id,
            )
        else:
            payload = inspect(repo, args.representation, args.location, args.run_id)
            if args.action == "claim-check":
                claimable = payload["claimable"]
                payload["ticket_id"] = args.ticket_id
                payload["allowed"] = args.ticket_id in claimable if args.ticket_id else bool(claimable)
                print(json.dumps(payload, indent=2, sort_keys=True))
                return 0 if payload["allowed"] else 3
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (AdapterError, OSError) as error:
        print(f"local-ticket-publication: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
