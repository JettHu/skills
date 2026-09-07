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
from datetime import datetime, timezone

import tracker_contract
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
    state_aliases: tuple[str, ...] = ()
    claim_aliases: tuple[str, ...] = ()
    branch_aliases: tuple[str, ...] = ()
    worktree_aliases: tuple[str, ...] = ()

    @property
    def inner(self) -> str:
        return self.text[self.inner_start : self.inner_end]

    @property
    def body_digest(self) -> str:
        normalized = normalize_operational_fields(
            self.inner,
            self.state_aliases,
            self.claim_aliases,
            self.branch_aliases,
            self.worktree_aliases,
        )
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
    blocker_heading: str
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
        if collecting:
            stripped = line.strip()
            if stripped.startswith("- "):
                value = stripped[2:].strip()
                if value and not re.fullmatch(r"none(?:\.|\s+[-—–].+)?", value, re.IGNORECASE):
                    quoted = re.findall(r"`([^`]+)`", value)
                    result.extend(item.strip() for item in (quoted or [value]) if item.strip())
    return result


def has_heading(text: str, heading: str) -> bool:
    target = heading.strip().lower()
    return any(
        match.group(2).strip().lower() == target
        for match in re.finditer(r"(?m)^(#+)\s+(.*)$", text)
    )


def replace_heading_blocker(text: str, heading: str, old: str, new: str) -> str:
    lines = text.splitlines(keepends=True)
    target = heading.strip().lower()
    collecting = False
    level = 0
    replaced = 0
    for index, line in enumerate(lines):
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
        if not collecting or not re.match(r"^\s*-\s+", line):
            continue
        prefix, value = re.match(r"^(\s*-\s+)(.*?)(\r?\n)?$", line).groups()
        newline = line[len(prefix) + len(value) :]
        quoted = value.startswith("`") and value.endswith("`")
        comparable = value[1:-1].strip() if quoted else value.strip()
        if comparable == old:
            lines[index] = prefix + (f"`{new}`" if quoted else new) + newline
            replaced += 1
            break
    if replaced != 1:
        raise AdapterError("blocker-target repair requires exactly one matching body blocker")
    return "".join(lines)


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


CANONICAL_SOLVE_RECORD_LINK = re.compile(
    r"^[ \t]*-[ \t]*`(?:\.\./)+solve-records/"
    r"[A-Za-z0-9][A-Za-z0-9._-]*\.md`[ \t]*(?:\r?\n|\Z)"
)
SOLVE_RECORD_HEADING = re.compile(r"^[ \t]*## Solve Records[ \t]*(?:\r?\n|\Z)")
ANY_H2_HEADING = re.compile(r"^[ \t]*## [^#].*(?:\r?\n|\Z)")


def remove_solve_record_backlinks(text: str) -> str:
    """Exclude only canonical path-only receipt backlinks from reviewed content."""
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    while index < len(lines):
        heading = SOLVE_RECORD_HEADING.fullmatch(lines[index])
        if not heading:
            output.append(lines[index])
            index += 1
            continue

        end = index + 1
        while end < len(lines) and not ANY_H2_HEADING.fullmatch(lines[end]):
            end += 1
        section = lines[index:end]
        retained = [line for line in section[1:] if not CANONICAL_SOLVE_RECORD_LINK.fullmatch(line)]
        if retained and any(line.strip() for line in retained):
            output.append(section[0])
            output.extend(retained)
        elif not any(line.strip() for line in retained):
            # An empty section containing only canonical lifecycle links is
            # mechanical, including the heading added by the writer.
            if output and not output[-1].strip():
                output.pop()
            pass
        else:
            output.extend(section)
        index = end
    return "".join(output)


def remove_legacy_solve_record_comments(text: str) -> str:
    """Exclude the historical path-only receipt comments from reviewed content."""
    prefix, separator, comments = text.rpartition("\n## Comments\n\n")
    if not separator:
        return text

    lines = [line for line in comments.rstrip("\n").splitlines() if line]
    if len(lines) < 2 or lines[0] not in {"### Solve Record", "### Solve Records"}:
        return text
    if not all(CANONICAL_SOLVE_RECORD_LINK.fullmatch(line + "\n") for line in lines[1:]):
        return text
    return prefix


def normalize_operational_fields(
    text: str,
    state_fields: tuple[str, ...],
    claim_fields: tuple[str, ...],
    branch_fields: tuple[str, ...],
    worktree_fields: tuple[str, ...],
) -> str:
    text = remove_legacy_solve_record_comments(remove_solve_record_backlinks(text))
    text = re.sub(
        r"(?m)^([ \t]*[-*+] [ \t]*\[)[ xX](\][ \t]+)",
        r"\1 \2",
        text,
    )
    start, end, kind = metadata_region(text)
    region = text[start:end]
    groups = (
        ({normalize_key(field) for field in state_fields}, "state", False),
        ({"completed"}, "completed", True),
        ({normalize_key(field) for field in claim_fields}, "claim", True),
        ({normalize_key(field) for field in branch_fields}, "branch", True),
        ({normalize_key(field) for field in worktree_fields}, "worktree", True),
    )
    pattern = re.compile(r"(?m)^([^\n:]+)([ \t]*:)[ \t]*.*(?:\n|\Z)")
    seen: set[str] = set()

    def replacement(match: re.Match[str]) -> str:
        key = normalize_key(match.group(1))
        for aliases, semantic, remove in groups:
            if key not in aliases:
                continue
            if semantic in seen:
                raise AdapterError(f"Ticket defines {semantic} more than once")
            seen.add(semantic)
            if remove:
                return ""
            newline = "\n" if match.group(0).endswith("\n") else ""
            return f"<{semantic}>:{newline}"
        return match.group(0)

    region = pattern.sub(replacement, region)
    if kind == "frontmatter":
        region = region.rstrip("\r\n")
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
        blockers=(
            heading_blockers(inner, contract.blocker_heading)
            if has_heading(inner, contract.blocker_heading)
            else many(metadata, *blocker_keys)
        ),
        flags=many(metadata, *claim_keys),
        state_field=state_field,
        flags_field=flags_field,
        state_aliases=contract.state_fields,
        claim_aliases=contract.claim_fields,
        branch_aliases=contract.branch_fields,
        worktree_aliases=contract.worktree_fields,
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
    try:
        documents = tracker_contract.read(repo)
    except tracker_contract.TrackerContractError as error:
        detail = str(error).replace("missing Tracker contract:", "missing Local tracker contract:", 1)
        raise AdapterError(detail) from error
    if documents.configured_adapter and documents.configured_adapter != "bundled-local-markdown-v1":
        raise AdapterError(
            f"unsupported configured Local Markdown adapter: {documents.configured_adapter}"
        )
    text = documents.capability_text
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
    try:
        blocker_heading = contract_value(text, "Blocker body heading")
    except AdapterError:
        # Older Local contracts had no body-heading declaration.
        blocker_heading = "Blocked by"
    return LocalContract(
        representation,
        location_pattern,
        policy,
        blocker_heading=blocker_heading,
        states=states,
        **fields,
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


def load_tickets_file_text(location: Path, text: str, contract: LocalContract) -> list[Ticket]:
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


def load_tickets_file(location: Path, contract: LocalContract) -> list[Ticket]:
    if not location.is_file():
        raise AdapterError(f"tickets-file does not exist: {location}")
    return load_tickets_file_text(location, location.read_text(encoding="utf-8"), contract)


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


def validate_blocker_targets(repo: Path, tickets: list[Ticket]) -> None:
    known = {ticket.ticket_id for ticket in tickets}
    known.update(ticket.path.relative_to(repo).as_posix() for ticket in tickets)
    for ticket in tickets:
        missing = sorted(set(ticket.blockers) - known)
        if missing:
            raise AdapterError(f"{ticket.ticket_id} has unresolved blocker IDs: {', '.join(missing)}")


def snapshot(selected: list[Ticket]) -> dict[str, str]:
    return {ticket.ticket_id: ticket.body_digest for ticket in selected}


def repair_audits(data: dict) -> list[dict]:
    audits = data.get("terminal_repairs", [])
    if not isinstance(audits, list) or any(not isinstance(item, dict) for item in audits):
        raise AdapterError("publication journal has malformed terminal repair audit history")
    return audits


def current_publication_snapshot(data: dict) -> dict[str, str]:
    """Project immutable registration digests through append-only terminal audits."""
    original = data.get("body_digests")
    if not isinstance(original, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in original.items()
    ):
        raise AdapterError("publication journal has malformed body_digests")
    current = dict(original)
    for audit in repair_audits(data):
        required = {"operation", "ticket_id", "old_digest", "new_digest", "reason", "timestamp"}
        if not required.issubset(audit) or audit.get("operation") != "terminal-repair":
            raise AdapterError("publication journal has malformed terminal repair audit entry")
        ticket_id = audit["ticket_id"]
        related = audit.get("related_digests", [])
        if not isinstance(related, list):
            raise AdapterError("publication journal has malformed related repair digests")
        for change in related:
            if not isinstance(change, dict) or set(change) != {"ticket_id", "old_digest", "new_digest"}:
                raise AdapterError("publication journal has malformed related repair digest")
            related_id = change["ticket_id"]
            if related_id not in current or current[related_id] != change["old_digest"]:
                raise AdapterError("publication journal has inconsistent related repair digest chain")
            current[related_id] = change["new_digest"]
        if ticket_id not in current or current[ticket_id] != audit["old_digest"]:
            raise AdapterError("publication journal has inconsistent terminal repair audit chain")
        new_ticket_id = audit.get("new_ticket_id", ticket_id)
        if new_ticket_id != ticket_id:
            if not isinstance(new_ticket_id, str) or new_ticket_id in current:
                raise AdapterError("publication journal has inconsistent repaired Ticket identity")
            del current[ticket_id]
        current[new_ticket_id] = audit["new_digest"]
    return current


def current_publication_members(data: dict) -> list[str]:
    members = data.get("members")
    if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
        raise AdapterError("publication journal has malformed members")
    current = list(members)
    for audit in repair_audits(data):
        old = audit["ticket_id"]
        new = audit.get("new_ticket_id", old)
        if new != old:
            if current.count(old) != 1 or new in current:
                raise AdapterError("publication journal has inconsistent repaired membership")
            current[current.index(old)] = new
    return sorted(current)


def register(repo: Path, representation: str, raw_location: str, run_id: str, allow_membership_change: bool) -> dict:
    with stable_mutation_surface(
        repo, representation, raw_location
    ) as (location, _contract):
        path = journal_path(location, representation, run_id)
        tickets = load_tickets_at(location, representation, _contract)
        selected = run_tickets(tickets, run_id)
        validate_blocker_targets(repo, tickets)
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
    validate_blocker_targets(repo, tickets)
    data = read_journal(journal_path(location, representation, run_id))
    if data.get("representation") != representation or data.get("location") != str(location.relative_to(repo)):
        raise AdapterError("publication journal does not match the configured adapter")
    if current_publication_members(data) != sorted(ticket.ticket_id for ticket in selected):
        raise AdapterError("publication membership drifted")
    if current_publication_snapshot(data) != snapshot(selected):
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


def replace_metadata_name(text: str, old: str, new: str) -> str:
    start, end, _kind = metadata_region(text)
    region = text[start:end]
    matches = list(re.finditer(r"(?m)^([^\n:]+)([ \t]*:)", region))
    selected = [match for match in matches if match.group(1).strip() == old]
    if len(selected) != 1:
        raise AdapterError(f"repair expected exactly one metadata field named {old}")
    match = selected[0]
    return text[:start] + region[:match.start(1)] + new + region[match.end(1):] + text[end:]


def typed_repair_text(ticket: Ticket, contract: LocalContract, repair_type: str, old: str, new: str) -> str:
    """Build one integrity-only edit; no arbitrary Ticket body is accepted."""
    inner = ticket.inner
    if repair_type == "ticket-identity":
        if ticket.ticket_id == new and SAFE_ID.fullmatch(old):
            return ticket.text
        if old != ticket.ticket_id or not SAFE_ID.fullmatch(new):
            raise AdapterError("ticket-identity repair requires the exact current ID and one safe new ID")
        field = metadata_spelling(inner, next(normalize_key(f) for f in contract.identity_fields if normalize_key(f) in parse_metadata(inner)))
        inner = replace_metadata_field(inner, field, new)
    elif repair_type == "blocker-target":
        if not SAFE_ID.fullmatch(old) or not SAFE_ID.fullmatch(new):
            raise AdapterError("blocker-target repair requires safe exact IDs")
        if ticket.blockers.count(old) == 0 and ticket.blockers.count(new) == 1:
            return ticket.text
        if ticket.blockers.count(old) != 1:
            raise AdapterError("blocker-target repair requires exactly one matching current blocker")
        if has_heading(inner, contract.blocker_heading):
            inner = replace_heading_blocker(inner, contract.blocker_heading, old, new)
        else:
            blockers = [new if item == old else item for item in ticket.blockers]
            metadata = parse_metadata(inner)
            key = next((normalize_key(f) for f in contract.blocker_fields if normalize_key(f) in metadata), "")
            if not key:
                raise AdapterError("blocker-target repair requires configured blocker metadata")
            inner = replace_metadata_field(inner, metadata_spelling(inner, key), ", ".join(blockers))
    elif repair_type == "publication-metadata":
        groups = (contract.identity_fields, contract.run_fields, contract.source_fields)
        group = next((items for items in groups if old in items and new in items), None)
        if group is None or normalize_key(old) == normalize_key(new):
            raise AdapterError("publication-metadata repair only renames one configured metadata alias")
        spellings = {line.split(":", 1)[0].strip() for line in inner[metadata_region(inner)[0]:metadata_region(inner)[1]].splitlines() if ":" in line}
        if old not in spellings and new in spellings:
            return ticket.text
        inner = replace_metadata_name(inner, old, new)
    elif repair_type == "digest-backlink-structure":
        if old or new:
            raise AdapterError("digest-backlink-structure repair does not accept replacement values")
        normalized = remove_legacy_solve_record_comments(inner)
        if normalized == inner:
            raise AdapterError("no legacy Solve Record backlink structure requires repair")
        legacy = inner[len(normalized):]
        links = re.findall(r"(?m)^-[ \t]*(`(?:\.\./)+solve-records/[A-Za-z0-9][A-Za-z0-9._-]*\.md`)[ \t]*$", legacy)
        inner = normalized.rstrip() + "\n\n## Solve Records\n\n" + "".join(f"- {link}\n" for link in links)
    else:
        raise AdapterError(f"unsupported terminal repair type: {repair_type}")
    text = ticket.text[:ticket.inner_start] + inner + ticket.text[ticket.inner_end:]
    if ticket.section_start or ticket.section_end:
        if repair_type == "ticket-identity":
            begin = BEGIN.search(text, ticket.section_start)
            if not begin or begin.group(1) != old:
                raise AdapterError("Ticket section identity changed concurrently")
            text = text[:begin.start(1)] + new + text[begin.end(1):]
    return text


def verify_solve_record_backlinks(repo: Path, ticket: Ticket) -> None:
    links = re.findall(r"(?m)^-[ \t]*`((?:\.\./)+solve-records/[A-Za-z0-9][A-Za-z0-9._-]*\.md)`[ \t]*$", ticket.inner)
    for raw in links:
        path = (ticket.path.parent / raw).resolve()
        try:
            path.relative_to(repo)
        except ValueError as error:
            raise AdapterError("Solve Record backlink escapes the repository") from error
        if not path.is_file():
            raise AdapterError(f"Solve Record backlink target is missing: {raw}")
        record = path.read_text(encoding="utf-8")
        record_ids = re.findall(r"(?m)^id:[ \t]*(\S+)[ \t]*$", record)
        outcomes = re.findall(r"(?m)^outcome:[ \t]*(\S+)[ \t]*$", record)
        if len(record_ids) != 1 or len(outcomes) != 1:
            raise AdapterError(f"Solve Record backlink target has malformed identity or outcome: {raw}")
        ticket_ref = str(ticket.path.relative_to(repo))
        issue_blocks = re.findall(r"(?ms)^issues:[ \t]*\n((?:[ \t]+-[^\n]*\n?)+)", record)
        linked = {
            line.split("-", 1)[1].strip().strip("'\"")
            for block in issue_blocks
            for line in block.splitlines()
            if line.strip().startswith("-")
        }
        if ticket_ref not in linked:
            raise AdapterError(f"Solve Record backlink does not point back to repaired Ticket: {raw}")


def terminal_repair(repo: Path, representation: str, raw_location: str, run_id: str,
                    ticket_id: str, expected_digest: str, repair_type: str,
                    old: str, new: str, reason: str) -> dict:
    if not ticket_id or not SAFE_ID.fullmatch(ticket_id):
        raise AdapterError("terminal repair requires one exact safe Ticket identity")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise AdapterError("terminal repair requires a lowercase SHA-256 expected digest")
    if not reason.strip():
        raise AdapterError("terminal repair requires a human reason")
    with stable_mutation_surface(repo, representation, raw_location) as (location, contract):
        path = journal_path(location, representation, run_id)
        data = read_journal(path)
        if data.get("phase") not in {"promoted", "completed"}:
            raise AdapterError("terminal repair requires a promoted or completed publication")
        tickets = load_tickets_at(location, representation, contract)
        selected = run_tickets(tickets, run_id)
        current = current_publication_snapshot(data)
        expected_members = current_publication_members(data)
        actual_members = sorted(item.ticket_id for item in selected)
        projected_identity_members = sorted(
            new if member == ticket_id else member for member in expected_members
        )
        partial_identity = (
            repair_type == "ticket-identity"
            and old == ticket_id
            and ticket_id in expected_members
            and actual_members == projected_identity_members
        )
        if actual_members != expected_members and not partial_identity:
            raise AdapterError("publication membership drifted")
        target = next((item for item in selected if item.ticket_id == ticket_id), None)
        if target is None and partial_identity:
            target = next((item for item in selected if item.ticket_id == new), None)
        if target is None and repair_type == "ticket-identity":
            audited = [
                item for item in repair_audits(data)
                if item.get("ticket_id") == ticket_id
                and item.get("old_digest") == expected_digest
                and item.get("new_ticket_id") == new
            ]
            if len(audited) == 1:
                target = next((item for item in selected if item.ticket_id == new), None)
        if target is None:
            raise AdapterError("terminal repair Ticket identity is ambiguous or absent")
        desired_text = typed_repair_text(target, contract, repair_type, old, new)
        # Parse the desired bytes independently without exposing a general editor.
        if representation == "file-per-ticket":
            desired = ticket_from_inner(target.path, desired_text, 0, len(desired_text), contract)
        else:
            desired_all = load_tickets_file_text(location, desired_text, contract)
            desired = next((item for item in desired_all if item.ticket_id in {ticket_id, new}), None)
        if desired is None:
            raise AdapterError("terminal repair did not produce one formal Ticket")
        desired_digest = desired.body_digest
        related_repairs: list[tuple[Ticket, Ticket, str]] = []
        if repair_type == "ticket-identity":
            selected_ids = {item.ticket_id for item in selected}
            external_references = sorted(
                item.ticket_id
                for item in tickets
                if item.ticket_id not in selected_ids and old in item.blockers
            )
            if external_references:
                raise AdapterError(
                    "terminal repair conflict: Ticket identity has references outside publication run: "
                    + ", ".join(external_references)
                )
            if representation == "tickets-file":
                combined = desired_text
                for original in selected:
                    if original is target:
                        continue
                    if old in original.blockers:
                        parsed = load_tickets_file_text(location, combined, contract)
                        dependent = next(item for item in parsed if item.ticket_id == original.ticket_id)
                        combined = typed_repair_text(dependent, contract, "blocker-target", old, new)
                        updated = next(
                            item for item in load_tickets_file_text(location, combined, contract)
                            if item.ticket_id == original.ticket_id
                        )
                        related_repairs.append((original, updated, combined))
                    elif new in original.blockers and original.body_digest != current.get(original.ticket_id):
                        prior_text = typed_repair_text(original, contract, "blocker-target", new, old)
                        prior = next(
                            item for item in load_tickets_file_text(location, prior_text, contract)
                            if item.ticket_id == original.ticket_id
                        )
                        if prior.body_digest != current.get(original.ticket_id):
                            raise AdapterError("terminal repair requires attention: dependent Ticket is inconsistent")
                        related_repairs.append((prior, original, combined))
                desired_text = combined
                desired = next(
                    item for item in load_tickets_file_text(location, desired_text, contract)
                    if item.ticket_id == new
                )
                desired_digest = desired.body_digest
            for item in selected:
                if representation == "tickets-file" or item is target:
                    continue
                if old in item.blockers:
                    before, updated_text = item, typed_repair_text(item, contract, "blocker-target", old, new)
                    updated = ticket_from_inner(item.path, updated_text, 0, len(updated_text), contract)
                elif new in item.blockers and item.body_digest != current.get(item.ticket_id):
                    prior_text = typed_repair_text(item, contract, "blocker-target", new, old)
                    before = ticket_from_inner(item.path, prior_text, 0, len(prior_text), contract)
                    updated, updated_text = item, item.text
                    if before is None or before.body_digest != current.get(item.ticket_id):
                        raise AdapterError("terminal repair requires attention: dependent Ticket is inconsistent")
                else:
                    continue
                if updated is None:
                    raise AdapterError("identity repair did not preserve a dependent Ticket")
                related_repairs.append((before, updated, updated_text))
        replacements = {before.ticket_id: after for before, after, _text in related_repairs}
        hypothetical = [desired if item is target else replacements.get(item.ticket_id, item) for item in tickets]
        if len({item.ticket_id for item in hypothetical}) != len(hypothetical):
            raise AdapterError("terminal repair would create duplicate Ticket identity")
        validate_blocker_targets(repo, hypothetical)
        verify_solve_record_backlinks(repo, desired)
        actual_snapshot = snapshot(selected)
        related_ids = {before.ticket_id for before, _after, _text in related_repairs}
        for member, digest in current.items():
            actual_key = new if partial_identity and member == ticket_id else member
            if actual_key != target.ticket_id and actual_key not in related_ids and actual_snapshot.get(actual_key) != digest:
                raise AdapterError("terminal repair requires attention: another run member is inconsistent")
        matching = [a for a in repair_audits(data) if a.get("ticket_id") == ticket_id and a.get("old_digest") == expected_digest and a.get("new_digest") == desired_digest]
        if target.body_digest == desired_digest and len(matching) == 1:
            _location, refreshed, _final = validate_against_journal_at(repo, representation, location, run_id, contract)
            repaired = next((item for item in refreshed if item.ticket_id == desired.ticket_id), None)
            if repaired is None:
                raise AdapterError("terminal repair retry postcondition verification failed")
            verify_solve_record_backlinks(repo, repaired)
            return {"status": "success", "ticket_id": desired.ticket_id, "old_digest": expected_digest, "new_digest": desired_digest, "repaired": True, "retry": True}
        partial_ticket_write = target.body_digest == desired_digest and not matching
        if current.get(ticket_id) != expected_digest or (target.body_digest != expected_digest and not partial_ticket_write):
            raise AdapterError("terminal repair conflict: unexpected current digest")
        if matching:
            raise AdapterError("terminal repair requires attention: audit exists before Ticket update")
        for before, _after, _updated_text in related_repairs:
            if before.body_digest != current.get(before.ticket_id):
                raise AdapterError("terminal repair requires attention: dependent Ticket is inconsistent")
        fail_after = os.environ.get("ULTRA_TERMINAL_REPAIR_FAIL_AFTER", "")
        ticket_writes = 0

        def interrupt_after_ticket_write() -> None:
            nonlocal ticket_writes
            ticket_writes += 1
            expected = 1 if fail_after == "ticket" else (
                int(fail_after.split(":", 1)[1])
                if fail_after.startswith("ticket:") and fail_after.split(":", 1)[1].isdigit()
                else 0
            )
            if expected and ticket_writes >= expected:
                raise AdapterError("injected terminal repair interruption after Ticket write")

        if not partial_ticket_write:
            if representation == "file-per-ticket":
                atomic_write(target.path, desired_text)
            else:
                atomic_write(location, desired_text)
            interrupt_after_ticket_write()
        related_digest_audit = []
        for before, after, updated_text in related_repairs:
            if before.body_digest == after.body_digest:
                continue
            if representation == "file-per-ticket":
                current_member = next(
                    item for item in selected if item.ticket_id == after.ticket_id
                )
                if current_member.body_digest != after.body_digest:
                    atomic_write(before.path, updated_text)
                    interrupt_after_ticket_write()
            related_digest_audit.append({
                "ticket_id": before.ticket_id,
                "old_digest": before.body_digest,
                "new_digest": after.body_digest,
            })
        audit = {"operation": "terminal-repair", "ticket_id": ticket_id, "old_digest": expected_digest,
                 "new_digest": desired_digest, "reason": reason.strip(),
                 "timestamp": datetime.now(timezone.utc).isoformat()}
        if desired.ticket_id != ticket_id:
            audit["new_ticket_id"] = desired.ticket_id
        if related_digest_audit:
            audit["related_digests"] = related_digest_audit
        data.setdefault("terminal_repairs", []).append(audit)
        write_journal(path, data)
        if os.environ.get("ULTRA_TERMINAL_REPAIR_FAIL_AFTER") == "journal":
            raise AdapterError("injected terminal repair interruption after journal write")
        _location, refreshed, final = validate_against_journal_at(repo, representation, location, run_id, contract)
        repaired = next((item for item in refreshed if item.ticket_id == desired.ticket_id), None)
        if repaired is None or repaired.blockers != desired.blockers or repaired.body_digest != desired_digest:
            raise AdapterError("terminal repair postcondition verification failed")
        verify_solve_record_backlinks(repo, repaired)
        return {"status": "success", "ticket_id": repaired.ticket_id, "old_digest": expected_digest,
                "new_digest": desired_digest, "repaired": True, "retry": False}


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
                if hashlib.sha256(
                    normalize_operational_fields(
                        current,
                        ticket.state_aliases,
                        ticket.claim_aliases,
                        ticket.branch_aliases,
                        ticket.worktree_aliases,
                    ).encode()
                ).hexdigest() != ticket.body_digest:
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
    data = None
    if path.exists():
        _location, tickets, data = validate_against_journal_at(
            repo, representation, location, run_id, contract
        )
        selected = run_tickets(tickets, run_id)
    return {
        "run_id": run_id,
        "phase": data.get("phase") if data else "unregistered",
        "members": sorted(ticket.ticket_id for ticket in selected),
        "statuses": {ticket.ticket_id: ticket.status for ticket in selected},
        "body_digests": snapshot(selected),
        "original_body_digests": data.get("body_digests", {}) if data else {},
        "terminal_repairs": repair_audits(data) if data else [],
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
    parser.add_argument("--expected-digest")
    parser.add_argument("--repair-type", choices=("ticket-identity", "blocker-target", "publication-metadata", "digest-backlink-structure"))
    parser.add_argument("--old-value", default="")
    parser.add_argument("--new-value", default="")
    parser.add_argument("--reason")
    parser.add_argument("--allow-membership-change", action="store_true")
    parser.add_argument("--explicit", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    try:
        if args.action not in {"register", "inspect", "promote", "cleanup", "terminal-repair"}:
            raise AdapterError(f"unsupported operation: {args.action}")
        if args.action == "register":
            payload = register(repo, args.representation, args.location, args.run_id, args.allow_membership_change)
        elif args.action == "promote":
            payload = promote(repo, args.representation, args.location, args.run_id)
        elif args.action == "cleanup":
            payload = cleanup(repo, args.representation, args.location, args.run_id, args.explicit)
        elif args.action == "terminal-repair":
            payload = terminal_repair(
                repo, args.representation, args.location, args.run_id,
                args.ticket_id or "", args.expected_digest or "", args.repair_type or "",
                args.old_value, args.new_value, args.reason or "",
            )
        else:
            payload = inspect(repo, args.representation, args.location, args.run_id)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    except (AdapterError, OSError) as error:
        print(f"local-ticket-publication: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
