#!/usr/bin/env python3
"""Converge one Local Markdown Ticket candidate handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import local_ticket_frontier as frontier
import local_ticket_publication as publication


SCHEMA = "ultra-local-outcome-handoff/v1"


class HandoffError(RuntimeError):
    """The requested handoff conflicts with canonical tracker state."""


class RetryableHandoff(HandoffError):
    """A canonical receipt exists but mechanical convergence is incomplete."""


def git(worktree: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise HandoffError(result.stderr.strip() or "candidate Git identity is unavailable")
    return result.stdout.strip()


def binding_digest(binding: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def receipt_path(repo: Path, ticket: frontier.Ticket, key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()
    if ticket.representation == "file-per-ticket":
        return ticket.path.parent.parent / "solve-records" / f"{digest}.md"
    return repo / ".scratch/solve-records" / f"{digest}.md"


def existing_receipt(repo: Path, key: str) -> Path | None:
    name = hashlib.sha256(key.encode()).hexdigest() + ".md"
    matches = sorted(path.resolve() for path in repo.glob(f".scratch/**/solve-records/{name}") if path.is_file())
    if len(matches) > 1:
        raise HandoffError("handoff key resolves to multiple canonical receipts")
    return matches[0] if matches else None


def quoted(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_receipt(
    relative_ticket: str,
    key: str,
    binding: str,
    head: str,
    head_sha: str,
    summary: str,
) -> str:
    record_id = hashlib.sha256(key.encode()).hexdigest()
    return f"""---
state: open
outcome: candidate
tickets:
  - {relative_ticket}
handoff_key: {quoted(key)}
binding_digest: {binding}
head: {head}
head_sha: {head_sha}
---

# Solve Record: Candidate {record_id[:12]}

## Summary
{summary}
"""


def receipt_scalar(text: str, field: str) -> str:
    matches = re.findall(rf"(?m)^{re.escape(field)}:[ \t]*(\S(?:.*\S)?)[ \t]*$", text)
    if len(matches) != 1:
        raise HandoffError(f"canonical receipt must define exactly one {field}")
    return matches[0]


def receipt_summary(text: str) -> str:
    matches = re.findall(r"(?ms)^## Summary[ \t]*\n(.+?)(?=\n## |\Z)", text)
    if len(matches) != 1 or not matches[0].strip():
        raise HandoffError("canonical receipt must define exactly one non-empty Summary")
    return matches[0].strip()


def receipt_tickets(text: str) -> list[str]:
    match = re.search(r"(?m)^tickets:[ \t]*\n((?:  - .+\n?)+)", text)
    if match is None:
        raise HandoffError("canonical receipt must define Ticket membership")
    return [line[4:].strip() for line in match.group(1).splitlines()]


def remove_claim(flags: list[str], claim: str) -> str:
    return ", ".join(item for item in flags if item != claim)


def add_backlink(text: str, relative_receipt: str) -> str:
    marker = f"- `{relative_receipt}`"
    count = backlink_count(text, relative_receipt)
    if count:
        if count != 1:
            raise HandoffError("Ticket contains duplicate receipt backlinks")
        return text
    return text.rstrip() + f"\n\n## Solve Records\n\n{marker}\n"


def backlink_count(text: str, relative_receipt: str) -> int:
    return len(re.findall(rf"(?m)^- `{re.escape(relative_receipt)}`[ \t]*$", text))


def dirty_paths(worktree: Path) -> set[str]:
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(line for line in git(worktree, *args).splitlines() if line)
    return paths


def current_candidate(
    repo: Path,
    ticket: frontier.Ticket,
    *,
    allowed_dirty: set[str] | None = None,
) -> tuple[str, str]:
    if not ticket.branch or not ticket.worktree:
        raise HandoffError("candidate handoff requires an active Claim branch and worktree")
    worktree = Path(ticket.worktree).resolve()
    if not worktree.is_dir():
        raise HandoffError("claimed worktree is unavailable")
    actual_head = git(worktree, "symbolic-ref", "--quiet", "--short", "HEAD")
    if actual_head != ticket.branch:
        raise HandoffError("claimed branch does not match worktree HEAD")
    repo_common = Path(git(repo, "rev-parse", "--git-common-dir"))
    worktree_common = Path(git(worktree, "rev-parse", "--git-common-dir"))
    repo_common = (repo / repo_common).resolve() if not repo_common.is_absolute() else repo_common.resolve()
    worktree_common = (worktree / worktree_common).resolve() if not worktree_common.is_absolute() else worktree_common.resolve()
    if repo_common != worktree_common:
        raise HandoffError("claimed worktree does not belong to the repository")
    unexpected_dirty = dirty_paths(worktree) - (allowed_dirty or set())
    if unexpected_dirty:
        raise HandoffError(
            "candidate worktree contains unrecorded changes: "
            + ", ".join(sorted(unexpected_dirty))
        )
    return actual_head, git(worktree, "rev-parse", "HEAD")


def result(status: str, key: str, receipt: str = "", reason: str = "", next_action: str = "") -> dict:
    if not next_action and status == "conflict":
        next_action = "inspect the named conflict manually; do not retry unchanged"
    elif not next_action and status == "retryable":
        next_action = "retry same key"
    payload = {"schema": SCHEMA, "status": status, "handoff_key": key}
    if receipt:
        payload["receipt"] = receipt
    if reason:
        payload["reason"] = reason
    if next_action:
        payload["next_action"] = next_action
    return payload


def handoff(repo: Path, ticket_id: str, key: str, outcome: str, summary: str) -> dict:
    if not key.strip():
        raise HandoffError("handoff key is required")
    if outcome != "candidate":
        raise HandoffError("this operation accepts only candidate outcome")
    if not summary.strip():
        raise HandoffError("candidate Summary is required")

    with frontier.frontier_lock(repo):
        contract, _contract_text = frontier.read_contract(repo)
        tickets = frontier.load_tickets(repo, contract)
        aliases = {alias: item for item in tickets for alias in item.aliases}
        ticket = aliases.get(ticket_id)
        if ticket is None:
            raise HandoffError(f"active Ticket is unavailable: {ticket_id}")
        relative_ticket = ticket.path.relative_to(repo).as_posix()
        canonical_path = receipt_path(repo, ticket, key)
        found_path = existing_receipt(repo, key)
        path = found_path or canonical_path
        relative_receipt = path.relative_to(repo).as_posix()
        backlink = Path(os.path.relpath(path, ticket.path.parent)).as_posix()

        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if existing:
            stored_head = receipt_scalar(existing, "head")
            stored_head_sha = receipt_scalar(existing, "head_sha")
            stored_outcome = receipt_scalar(existing, "outcome")
            stored_tickets = receipt_tickets(existing)
            stored_binding = receipt_scalar(existing, "binding_digest")
            stored_key_value = receipt_scalar(existing, "handoff_key")
            try:
                stored_key = json.loads(stored_key_value)
            except json.JSONDecodeError as error:
                raise HandoffError("canonical receipt handoff key is malformed") from error
            if path != canonical_path:
                return result(
                    "conflict",
                    key,
                    relative_receipt,
                    "handoff key is bound to different immutable facts",
                    "use a new handoff key for changed immutable facts",
                )
            if stored_key != key:
                return result(
                    "conflict",
                    key,
                    relative_receipt,
                    "canonical receipt handoff key failed verification",
                    "inspect the canonical receipt manually; do not retry unchanged",
                )
            stored_facts = {
                "repo": str(repo), "handoff_key": stored_key, "tickets": stored_tickets,
                "outcome": stored_outcome, "head": stored_head, "head_sha": stored_head_sha,
            }
            if stored_binding != binding_digest(stored_facts):
                return result(
                    "conflict",
                    key,
                    relative_receipt,
                    "canonical receipt binding digest failed verification",
                    "inspect the canonical receipt manually; do not retry unchanged",
                )
            allowed_dirty = {relative_ticket, relative_receipt}
            head, head_sha = current_candidate(repo, ticket, allowed_dirty=allowed_dirty)
            binding = {
                "repo": str(repo), "handoff_key": key, "tickets": [relative_ticket],
                "outcome": outcome, "head": head, "head_sha": head_sha,
            }
            if stored_binding != binding_digest(binding):
                return result(
                    "conflict",
                    key,
                    relative_receipt,
                    "handoff key is bound to different immutable facts",
                    "use a new handoff key for changed immutable facts",
                )
            expected_receipt = render_receipt(
                relative_ticket,
                key,
                stored_binding,
                head,
                head_sha,
                receipt_summary(existing),
            )
            if existing != expected_receipt:
                return result(
                    "conflict",
                    key,
                    relative_receipt,
                    "canonical receipt failed complete verification",
                    "inspect the canonical receipt manually; do not retry unchanged",
                )
        else:
            if (
                ticket.status != contract.ready_state
                or contract.claim_value not in ticket.flags
                or backlink_count(ticket.container_text, backlink) != 0
            ):
                raise HandoffError("candidate handoff requires a valid active Ticket and Claim")
            head, head_sha = current_candidate(repo, ticket)
            binding = {
                "repo": str(repo), "handoff_key": key, "tickets": [relative_ticket],
                "outcome": outcome, "head": head, "head_sha": head_sha,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            expected_receipt = render_receipt(
                relative_ticket, key, binding_digest(binding), head, head_sha, summary.strip()
            )
            publication.atomic_write(path, expected_receipt)
            if os.environ.get("ULTRA_HANDOFF_FAIL_AFTER_RECEIPT") == "1":
                raise RetryableHandoff("receipt installed; retry same key to converge tracker state")

        current_backlinks = backlink_count(ticket.container_text, backlink)
        claimed = contract.claim_value in ticket.flags
        if (
            ticket.status == contract.completed_state
            and not claimed
            and current_backlinks == 1
        ):
            transition_needed = False
        elif (
            ticket.status == contract.ready_state
            and claimed
            and current_backlinks == 0
        ):
            transition_needed = True
        else:
            return result(
                "conflict",
                key,
                relative_receipt,
                "Ticket state, Claim, and backlink do not match an allowed handoff transition",
                "inspect Ticket state, Claim, and backlink manually; do not retry unchanged",
            )

        if transition_needed:
            current = ticket.path.read_text(encoding="utf-8")
            inner = current[ticket.inner_start:ticket.inner_end]
            inner = frontier.replace_or_insert_field(
                inner, contract.state_fields, ticket.state_field or contract.state_fields[0], contract.completed_state
            )
            inner = frontier.replace_or_insert_field(
                inner, contract.claim_aliases, contract.claim_field, remove_claim(ticket.flags, contract.claim_value)
            )
            updated = current[:ticket.inner_start] + inner + current[ticket.inner_end:]
            updated = add_backlink(updated, backlink)
            try:
                if os.environ.get("ULTRA_HANDOFF_FAIL_BEFORE_TICKET_WRITE") == "1":
                    raise OSError("injected Ticket transition failure")
                publication.atomic_write(ticket.path, updated)
            except OSError as error:
                raise RetryableHandoff(
                    f"receipt installed but Ticket transition failed: {error}"
                ) from error

        refreshed = frontier.load_tickets(repo, contract)
        refreshed_aliases = {alias: item for item in refreshed for alias in item.aliases}
        final_ticket = refreshed_aliases.get(ticket_id)
        final_text = ticket.path.read_text(encoding="utf-8")
        final_head = ("", "")
        if final_ticket is not None:
            final_head = current_candidate(
                repo,
                final_ticket,
                allowed_dirty={relative_ticket, relative_receipt},
            )
        if (
            final_ticket is None
            or final_ticket.status != contract.completed_state
            or contract.claim_value in final_ticket.flags
            or backlink_count(final_text, backlink) != 1
            or not path.is_file()
            or path.read_text(encoding="utf-8") != expected_receipt
            or final_head != (head, head_sha)
        ):
            return result("retryable", key, relative_receipt, "handoff postcondition is incomplete", "retry same key")
        return result("success", key, relative_receipt)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--ticket-id", required=True)
    parser.add_argument("--handoff-key", required=True)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--summary", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    key = args.handoff_key
    try:
        payload = handoff(Path(args.repo).resolve(), args.ticket_id, key, args.outcome, args.summary)
    except RetryableHandoff as error:
        payload = result("retryable", key, reason=str(error), next_action="retry same key")
    except (HandoffError, frontier.FrontierError, OSError) as error:
        payload = result("conflict", key, reason=str(error))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
