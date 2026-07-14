#!/usr/bin/env python3
"""Deterministic remote Ticket publication state machine.

This is a provider-neutral fixture adapter for the GitHub and GitLab
publication contracts.  Its JSON remote store deliberately models only the
operations the contract must make durable: provisional creation, in-place
updates, relationship wiring, exact rereads, promotion, supersession, and
resume.  A real Agent still uses the configured provider-native API/CLI; this
tool makes those invariants reproducible without credentials or a network.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA = "ultra-remote-ticket-publication/v1"
READY = "ready-for-agent"


class PublicationError(RuntimeError):
    pass


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise PublicationError(f"missing required file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PublicationError(f"invalid JSON: {path}") from error


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def marker(run_id: str) -> str:
    return f"<!-- ultra-publication-set:{run_id} -->"


def rendered_body(ticket: dict[str, Any], run_id: str) -> str:
    body = str(ticket.get("body", "")).rstrip()
    return f"{body}\n\n{marker(run_id)}\n" if body else f"{marker(run_id)}\n"


def fallback_body(ticket: dict[str, Any], run_id: str) -> str:
    lines = [f"{kind}: {key}" for kind, keys in desired_edges(ticket).items() for key in keys]
    relationships = "\n".join(lines)
    return rendered_body(ticket, run_id).rstrip() + f"\n\n<!-- ultra-relationships:begin -->\n{relationships}\n<!-- ultra-relationships:end -->\n"


def expected_remote_body(remote: dict[str, Any], ticket: dict[str, Any], run_id: str) -> str:
    return fallback_body(ticket, run_id) if remote.get("relationship_mode") == "textual-fallback" else rendered_body(ticket, run_id)


def reviewed_remote_body(remote: dict[str, Any], run_id: str) -> str:
    """Extract the reviewer-owned body while retaining only adapter-owned markers."""
    body = str(remote.get("body", ""))
    run_marker = marker(run_id)
    if body.count(run_marker) != 1:
        raise PublicationError("provisional remote Ticket has an unsafe publication marker")
    reviewed, suffix = body.split(run_marker, 1)
    suffix = suffix.strip()
    if suffix:
        relationship_start = "<!-- ultra-relationships:begin -->"
        relationship_end = "<!-- ultra-relationships:end -->"
        if not (suffix.startswith(relationship_start) and suffix.endswith(relationship_end)):
            raise PublicationError("provisional remote Ticket changed adapter-owned marker content")
    return reviewed.rstrip()


def adopt_provisional_review(existing: dict[str, Any], desired: dict[str, Any], run_id: str, provisional_marker: str) -> None:
    """Use an exact provisional remote artifact as the review/fix source of truth."""
    if existing.get("ready") or provisional_marker not in existing.get("labels", []):
        raise PublicationError(f"provisional state is unsafe for {desired['key']}")
    title = existing.get("title")
    if not isinstance(title, str) or not title:
        raise PublicationError(f"provisional remote Ticket has an unsafe title for {desired['key']}")
    desired["title"] = title
    desired["body"] = reviewed_remote_body(existing, run_id)
    existing["reviewed_title"] = desired["title"]
    existing["reviewed_body"] = desired["body"]


def canonical_published_ticket(remote: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    """Recover accepted reviewer body fixes when checking a later completed run."""
    title = remote.get("reviewed_title")
    body = remote.get("reviewed_body")
    if not isinstance(title, str) or not title or not isinstance(body, str):
        return desired
    canonical = dict(desired)
    canonical["title"] = title
    canonical["body"] = body
    return canonical


def validate_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    tickets = spec.get("tickets")
    if not isinstance(tickets, list) or not tickets:
        raise PublicationError("spec must contain a non-empty tickets list")
    keys: set[str] = set()
    for ticket in tickets:
        if not isinstance(ticket, dict):
            raise PublicationError("each Ticket spec must be an object")
        key = ticket.get("key")
        title = ticket.get("title")
        if not isinstance(key, str) or not key or not isinstance(title, str) or not title:
            raise PublicationError("each Ticket needs non-empty key and title")
        if key in keys:
            raise PublicationError(f"duplicate Ticket key: {key}")
        keys.add(key)
        for edge_key in ([ticket["parent"]] if ticket.get("parent") else []) + ticket.get("blocks", []):
            if edge_key not in keys and edge_key not in {item.get("key") for item in tickets}:
                raise PublicationError(f"Ticket {key} references missing Ticket {edge_key}")
    return tickets


def state_ticket(state: dict[str, Any], run_id: str, key: str) -> dict[str, Any] | None:
    for ticket in state["tickets"]:
        if ticket.get("publication_run") == run_id and ticket.get("key") == key:
            return ticket
    return None


def ensure_state(path: Path, provider: str) -> dict[str, Any]:
    state = read_json(path, {"schema": SCHEMA, "provider": provider, "next_id": 1, "tickets": []})
    if state.get("schema") != SCHEMA or state.get("provider") != provider:
        raise PublicationError("remote state provider or schema does not match invocation")
    if not isinstance(state.get("next_id"), int) or not isinstance(state.get("tickets"), list):
        raise PublicationError("remote state has an unsafe shape")
    return state


def stage_root(root: Path, run_id: str) -> Path:
    if not run_id or "/" in run_id or ".." in run_id:
        raise PublicationError("unsafe publication-run identity")
    return root / run_id


def write_staging(root: Path, run_id: str, provider: str, tickets: list[dict[str, Any]]) -> Path:
    directory = stage_root(root, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    draft = directory / "tickets.md"
    if not draft.exists():
        draft.write_text(
            "# Staged Tickets\n\n"
            "Edit the exact JSON between the markers during review; it is the "
            "durable source that will be published.\n\n"
            "<!-- ultra-staging:begin -->\n"
            + json.dumps({"tickets": tickets}, indent=2, sort_keys=True)
            + "\n<!-- ultra-staging:end -->\n",
            encoding="utf-8",
        )
    manifest_path = directory / "manifest.json"
    manifest = read_json(manifest_path, None) if manifest_path.exists() else {
        "schema": SCHEMA,
        "provider": provider,
        "strategy": "local-staging",
        "run_id": run_id,
        "phase": "review-pending",
        "tickets": {},
        "remaining_recovery_work": ["fresh-context review", "remote publication", "promotion"],
    }
    if manifest.get("schema") != SCHEMA or manifest.get("provider") != provider or manifest.get("run_id") != run_id:
        raise PublicationError("staging manifest identity does not match invocation")
    desired_keys = {ticket["key"] for ticket in tickets}
    for key in set(manifest["tickets"]) - desired_keys:
        manifest["tickets"][key]["superseded"] = True
    for ticket in tickets:
        entry = manifest["tickets"].setdefault(ticket["key"], {})
        entry.setdefault("title", ticket["title"])
        entry.setdefault("body_digest", digest(rendered_body(ticket, run_id)))
    write_json(manifest_path, manifest)
    return manifest_path


def read_staged_tickets(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    start = "<!-- ultra-staging:begin -->"
    end = "<!-- ultra-staging:end -->"
    before, marker_start, rest = text.partition(start)
    del before
    payload, marker_end, after = rest.partition(end)
    del after
    if not marker_start or not marker_end:
        raise PublicationError("staged Ticket draft lacks exact durable JSON markers")
    try:
        return validate_spec(json.loads(payload))
    except json.JSONDecodeError as error:
        raise PublicationError("staged Ticket draft has invalid JSON") from error


def refresh_staging_manifest(path: Path, tickets: list[dict[str, Any]], run_id: str) -> None:
    manifest = read_json(path)
    desired_keys = {ticket["key"] for ticket in tickets}
    for key, entry in manifest["tickets"].items():
        if key not in desired_keys:
            entry["superseded"] = True
    for ticket in tickets:
        entry = manifest["tickets"].setdefault(ticket["key"], {})
        entry.update({"title": ticket["title"], "body_digest": digest(rendered_body(ticket, run_id))})
        entry.pop("superseded", None)
    write_json(path, manifest)


def desired_edges(ticket: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {"blocks": list(ticket.get("blocks", []))}
    if ticket.get("parent"):
        result["parent"] = [ticket["parent"]]
    return result


def sync(
    state_path: Path,
    provider: str,
    strategy: str,
    run_id: str,
    tickets: list[dict[str, Any]],
    provisional_marker: str,
    native_relationships: bool,
    reviewed: bool,
    supersede: bool,
    fail_at: str | None,
    staging_manifest: Path | None,
) -> dict[str, Any]:
    state = ensure_state(state_path, provider)
    manifest = read_json(staging_manifest) if staging_manifest else None
    desired_keys = {ticket["key"] for ticket in tickets}
    current_keys = {
        ticket["key"]
        for ticket in state["tickets"]
        if ticket.get("publication_run") == run_id and not ticket.get("superseded")
    }
    if current_keys and current_keys != desired_keys and not supersede:
        raise PublicationError("publication membership changed without explicit supersession")
    if manifest and manifest.get("phase") == "promoted":
        for desired in tickets:
            remote = state_ticket(state, run_id, desired["key"])
            if (
                remote is None
                or not remote.get("ready")
                or READY not in remote.get("labels", [])
                or provisional_marker in remote.get("labels", [])
                or marker(run_id) not in remote.get("body", "")
                or remote.get("relationships") != desired_edges(desired)
                or remote.get("body") != expected_remote_body(remote, desired, run_id)
            ):
                raise PublicationError(f"promoted remote Ticket drifted for {desired['key']}")
        directory = staging_manifest.parent
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()
        return {"phase": "promoted", "resumed": True, "ids": {key: value["remote_id"] for key, value in manifest["tickets"].items() if "remote_id" in value}, "claimable": sorted(desired_keys)}
    if manifest and manifest.get("phase") == "promoting":
        ids = {key: value["remote_id"] for key, value in manifest["tickets"].items() if "remote_id" in value}
        if set(ids) != desired_keys:
            raise PublicationError("promoting manifest membership does not match the reviewed set")
        for desired in tickets:
            remote = state_ticket(state, run_id, desired["key"])
            if (
                remote is None
                or not remote.get("ready")
                or READY not in remote.get("labels", [])
                or provisional_marker in remote.get("labels", [])
                or marker(run_id) not in remote.get("body", "")
                or remote.get("relationships") != desired_edges(desired)
                or remote.get("body") != expected_remote_body(remote, desired, run_id)
            ):
                raise PublicationError(f"ready-state verification failed while resuming {desired['key']}")
        manifest["phase"] = "promoted"
        manifest["remaining_recovery_work"] = []
        write_json(staging_manifest, manifest)
        directory = staging_manifest.parent
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()
        return {"phase": "promoted", "resumed": True, "ids": ids, "claimable": sorted(ids)}

    existing_members = [state_ticket(state, run_id, ticket["key"]) for ticket in tickets]
    if all(existing_members) and all(member.get("ready") for member in existing_members):
        for desired, remote in zip(tickets, existing_members):
            assert remote is not None
            canonical = canonical_published_ticket(remote, desired)
            if (
                marker(run_id) not in remote["body"]
                or remote.get("relationships") != desired_edges(canonical)
                or READY not in remote.get("labels", [])
                or provisional_marker in remote.get("labels", [])
                or remote.get("body") != expected_remote_body(remote, canonical, run_id)
            ):
                raise PublicationError(f"ready remote Ticket drifted for {desired['key']}")
        return {
            "phase": "promoted",
            "resumed": True,
            "ids": {ticket["key"]: remote["id"] for ticket, remote in zip(tickets, existing_members)},
            "claimable": sorted(ticket["key"] for ticket in tickets),
        }

    ids: dict[str, int] = {}
    for desired in tickets:
        existing = state_ticket(state, run_id, desired["key"])
        if existing is None:
            existing = {
                "id": state["next_id"], "key": desired["key"], "publication_run": run_id,
                "title": desired["title"], "body": rendered_body(desired, run_id),
                "labels": [provisional_marker], "relationships": {}, "ready": False,
            }
            state["next_id"] += 1
            state["tickets"].append(existing)
        else:
            if existing.get("ready"):
                if existing.get("title") != desired["title"] or existing.get("body") != expected_remote_body(existing, desired, run_id):
                    raise PublicationError(f"concurrent remote body change for {desired['key']}")
            else:
                adopt_provisional_review(existing, desired, run_id, provisional_marker)
            existing.setdefault("labels", [])
            existing.setdefault("relationships", {})
            if not existing.get("ready") and provisional_marker not in existing["labels"]:
                existing["labels"].append(provisional_marker)
        ids[desired["key"]] = existing["id"]
        if manifest is not None:
            manifest["tickets"][desired["key"]]["remote_id"] = existing["id"]
            manifest["tickets"][desired["key"]]["created"] = True
            write_json(staging_manifest, manifest)
        write_json(state_path, state)
    if manifest is not None:
        manifest["phase"] = "created"
        manifest["remaining_recovery_work"] = ["relationship wiring", "verification", "promotion"]
        write_json(staging_manifest, manifest)
    if fail_at == "create":
        raise PublicationError("injected failure after durable create")

    if supersede:
        for existing in state["tickets"]:
            if existing.get("publication_run") == run_id and existing.get("key") not in desired_keys:
                existing["superseded"] = True
                existing["ready"] = False
                if provisional_marker in existing.get("labels", []):
                    existing["labels"].remove(provisional_marker)
                if READY in existing.get("labels", []):
                    existing["labels"].remove(READY)
                if "superseded" not in existing["labels"]:
                    existing["labels"].append("superseded")

    for desired in tickets:
        remote = state_ticket(state, run_id, desired["key"])
        assert remote is not None
        remote["relationships"] = desired_edges(desired)
        remote["relationship_mode"] = "native" if native_relationships else "textual-fallback"
        if not native_relationships:
            remote["body"] = fallback_body(desired, run_id)
    write_json(state_path, state)
    if manifest is not None:
        manifest["phase"] = "wired"
        for key in ids:
            manifest["tickets"][key]["relationships_wired"] = True
        manifest["remaining_recovery_work"] = ["verification", "promotion"]
        write_json(staging_manifest, manifest)
    if fail_at == "wire":
        raise PublicationError("injected failure after durable relationship wiring")

    for desired in tickets:
        remote = state_ticket(state, run_id, desired["key"])
        if remote is None or marker(run_id) not in remote["body"] or remote["relationships"] != desired_edges(desired):
            raise PublicationError(f"remote verification failed for {desired['key']}")
        if remote.get("ready") or provisional_marker not in remote.get("labels", []):
            raise PublicationError(f"provisional state is unsafe for {desired['key']}")
    if manifest is not None:
        manifest["phase"] = "verified"
        for key in ids:
            manifest["tickets"][key]["verified"] = True
        manifest["remaining_recovery_work"] = ["promotion"]
        write_json(staging_manifest, manifest)
    if fail_at == "verify":
        raise PublicationError("injected failure after durable verification")
    if not reviewed:
        return {"phase": "review-pending", "ids": ids, "claimable": []}

    for desired in tickets:
        remote = state_ticket(state, run_id, desired["key"])
        assert remote is not None
        if provisional_marker not in remote["labels"]:
            raise PublicationError(f"cannot promote {desired['key']} without configured provisional marker")
        remote["labels"].remove(provisional_marker)
        if READY not in remote["labels"]:
            remote["labels"].append(READY)
        remote["ready"] = True
    write_json(state_path, state)
    if manifest is not None:
        manifest["phase"] = "promoting"
        write_json(staging_manifest, manifest)
    if fail_at == "promote":
        raise PublicationError("injected failure after remote promotion before complete-set verification")

    for desired in tickets:
        remote = state_ticket(state, run_id, desired["key"])
        if remote is None or not remote.get("ready") or READY not in remote.get("labels", []):
            raise PublicationError(f"ready-state verification failed for {desired['key']}")
    if manifest is not None:
        manifest["phase"] = "promoted"
        manifest["remaining_recovery_work"] = []
        write_json(staging_manifest, manifest)
        directory = staging_manifest.parent
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()
    return {"phase": "promoted", "ids": ids, "claimable": sorted(ids)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("publish", nargs="?", default="publish")
    parser.add_argument("--provider", choices=("github", "gitlab"), required=True)
    parser.add_argument("--strategy", choices=("remote-review-pending", "local-staging"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--remote-state", type=Path, required=True)
    parser.add_argument("--provisional-marker", default="review-pending")
    parser.add_argument("--native-relationships", action="store_true")
    parser.add_argument("--reviewed", action="store_true")
    parser.add_argument("--supersede", action="store_true")
    parser.add_argument("--staging-root", type=Path)
    parser.add_argument("--fail-at", choices=("create", "wire", "verify", "promote"))
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        tickets = validate_spec(read_json(args.spec))
        staging_manifest = None
        if args.strategy == "local-staging":
            if args.staging_root is None:
                raise PublicationError("local-staging requires --staging-root")
            staging_manifest = write_staging(args.staging_root, args.run_id, args.provider, tickets)
            if not args.reviewed:
                print(json.dumps({"phase": "review-pending", "claimable": []}, sort_keys=True))
                return 0
            tickets = read_staged_tickets(staging_manifest.parent / "tickets.md")
            refresh_staging_manifest(staging_manifest, tickets, args.run_id)
        result = sync(
            args.remote_state, args.provider, args.strategy, args.run_id, tickets,
            args.provisional_marker, args.native_relationships, args.reviewed,
            args.supersede, args.fail_at, staging_manifest,
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (PublicationError, OSError) as error:
        print(f"remote-ticket-publication: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
