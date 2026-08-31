#!/usr/bin/env python3
"""Converge one Local Markdown Ticket outcome handoff."""

from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path
import local_ticket_frontier as frontier
import local_ticket_publication as publication

SCHEMA = "ultra-local-outcome-handoff/v1"
RECOVERY = {"blocked", "needs-info", "ready-for-human"}
TERMINAL = {"abandoned", "superseded"}


class HandoffError(RuntimeError):
    pass


class RetryableHandoff(HandoffError):
    pass


def git(cwd, *args):
    p = subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if p.returncode:
        raise HandoffError(p.stderr.strip() or "Git identity is unavailable")
    return p.stdout.strip()


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def result(status, key, receipt="", reason="", next_action=""):
    next_action = next_action or (
        "inspect the named conflict manually; do not retry unchanged"
        if status == "conflict"
        else "retry same key"
        if status == "retryable"
        else ""
    )
    data = {"schema": SCHEMA, "status": status, "handoff_key": key}
    data.update(
        {
            k: v
            for k, v in {
                "receipt": receipt,
                "reason": reason,
                "next_action": next_action,
            }.items()
            if v
        }
    )
    return data


def receipt_path(repo, ticket, key):
    name = hashlib.sha256(key.encode()).hexdigest() + ".md"
    return (
        ticket.path.parent.parent / "solve-records" / name
        if ticket.representation == "file-per-ticket"
        else repo / ".scratch/solve-records" / name
    )


def find_receipt(repo, key):
    name = hashlib.sha256(key.encode()).hexdigest() + ".md"
    found = sorted(
        p.resolve()
        for p in repo.glob(f".scratch/**/solve-records/{name}")
        if p.is_file()
    )
    if len(found) > 1:
        raise HandoffError("handoff key resolves to multiple canonical receipts")
    return found[0] if found else None


def scalar(text, field):
    values = re.findall(rf"(?m)^{re.escape(field)}:[ \t]*(\S(?:.*\S)?)[ \t]*$", text)
    if len(values) != 1:
        raise HandoffError(f"canonical receipt must define exactly one {field}")
    return values[0]


def list_field(text, field):
    m = re.search(rf"(?m)^{field}:\n((?:  - .+\n?)*)", text)
    if m is None:
        raise HandoffError(f"canonical receipt must define {field}")
    try:
        return [json.loads(line[4:]) for line in m.group(1).splitlines()]
    except json.JSONDecodeError as e:
        raise HandoffError(f"canonical receipt {field} is malformed") from e


def summary(text):
    values = re.findall(r"(?ms)^## Summary[ \t]*\n(.+?)(?=\n## |\Z)", text)
    if len(values) != 1 or not values[0].strip():
        raise HandoffError(
            "canonical receipt must define exactly one non-empty Summary"
        )
    return values[0].strip()


def render(binding, body):
    outcome, key = binding["outcome"], binding["handoff_key"]
    state = "open" if outcome == "candidate" or outcome in RECOVERY else "closed"
    lines = [
        "---",
        f"state: {state}",
        f"outcome: {outcome}",
        "tickets:",
        *[f"  - {x}" for x in binding["tickets"]],
        f"handoff_key: {json.dumps(key)}",
        f"binding_digest: {digest(binding)}",
    ]
    if outcome == "candidate":
        lines += [f"head: {binding['head']}", f"head_sha: {binding['head_sha']}"]
    elif outcome in RECOVERY:
        lines += [
            f"recovery_next_action: {json.dumps(binding['recovery_next_action'])}",
            "retained_resources:",
            *[f"  - {json.dumps(x)}" for x in binding["retained_resources"]],
        ]
    rid = hashlib.sha256(key.encode()).hexdigest()[:12]
    return "\n".join(
        lines
        + [
            "---",
            "",
            f"# Solve Record: {outcome.title()} {rid}",
            "",
            "## Summary",
            body,
            "",
        ]
    )


def backlink_count(text, backlink):
    return len(re.findall(rf"(?m)^- `{re.escape(backlink)}`[ \t]*$", text))


def add_backlink(text, backlink):
    count = backlink_count(text, backlink)
    if count > 1:
        raise HandoffError("Ticket contains duplicate receipt backlinks")
    return (
        text if count else text.rstrip() + f"\n\n## Solve Records\n\n- `{backlink}`\n"
    )


def candidate_identity(repo, ticket, allowed=frozenset(), require_clean=True):
    if not ticket.branch or not ticket.worktree:
        raise HandoffError(
            "outcome handoff requires an active Claim branch and worktree"
        )
    wt = Path(ticket.worktree).resolve()
    if not wt.is_dir():
        raise HandoffError("claimed worktree is unavailable")
    branch = git(wt, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch != ticket.branch:
        raise HandoffError("claimed branch does not match worktree HEAD")

    def common(cwd):
        p = Path(git(cwd, "rev-parse", "--git-common-dir"))
        return (cwd / p).resolve() if not p.is_absolute() else p.resolve()

    if common(repo) != common(wt):
        raise HandoffError("claimed worktree does not belong to the repository")
    dirty = set()
    for args in (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        dirty.update(filter(None, git(wt, *args).splitlines()))
    if require_clean and dirty - set(allowed):
        raise HandoffError(
            "candidate worktree contains unrecorded changes: "
            + ", ".join(sorted(dirty - set(allowed)))
        )
    return branch, git(wt, "rev-parse", "HEAD")


def resources(resources):
    canonical = sorted(resources)
    if len(canonical) != len(set(canonical)):
        raise HandoffError(
            "retained-resource declaration has ambiguous duplicate members"
        )
    return canonical


def verify_resources(repo, ticket, declared):
    parsed = {}
    for item in declared:
        parts = item.split(":", 2)
        if len(parts) != 3 or not all(parts):
            raise HandoffError(
                f"retained resource has stale or malformed identity: {item}"
            )
        owner, kind, value = parts
        if owner != "solve-owned":
            raise HandoffError(f"retained resource is not solve-owned: {item}")
        if kind not in {"branch", "worktree"}:
            raise HandoffError(f"retained resource type is unsupported: {item}")
        if kind in parsed:
            raise HandoffError(f"retained-resource ownership is ambiguous for {kind}")
        parsed[kind] = value
    if set(parsed) != {"branch", "worktree"}:
        raise HandoffError(
            "retained-resource declaration is partial; branch and worktree are both required"
        )
    if parsed["branch"] != ticket.branch:
        raise HandoffError("retained branch does not match the active Claim")
    if (
        not ticket.worktree
        or Path(parsed["worktree"]).resolve() != Path(ticket.worktree).resolve()
    ):
        raise HandoffError("retained worktree does not match the active Claim")
    candidate_identity(repo, ticket, require_clean=False)


def resumable_supported(text):
    m = re.search(r"(?mi)^Resumable Claims:[ \t]*(.+)$", text)
    return m is not None and m.group(1).strip().lower() in {"supported", "true", "yes"}


def handoff(repo, ticket_id, key, outcome, body, next_action, declared):
    if not key.strip():
        raise HandoffError("handoff key is required")
    if outcome not in {"candidate"} | RECOVERY | TERMINAL:
        raise HandoffError(f"unsupported outcome: {outcome}")
    if not body.strip():
        raise HandoffError("outcome Summary is required")
    with frontier.frontier_lock(repo):
        contract, contract_text = frontier.read_contract(repo)
        ticket = {
            a: t for t in frontier.load_tickets(repo, contract) for a in t.aliases
        }.get(ticket_id)
        if ticket is None:
            raise HandoffError(f"active Ticket is unavailable: {ticket_id}")
        declared, candidate = resources(declared), outcome == "candidate"
        if candidate and (next_action or declared):
            raise HandoffError("candidate handoff does not accept recovery inputs")
        if outcome in RECOVERY and not next_action.strip():
            raise HandoffError("recovery next action is required")
        if outcome in TERMINAL and (next_action or declared):
            raise HandoffError("terminal handoff does not accept recovery inputs")
        retain = not candidate and next_action == "resume"
        if retain:
            if outcome not in RECOVERY:
                raise HandoffError("terminal outcome cannot retain a resumable Claim")
            if not declared:
                raise HandoffError(
                    "resume requires a non-empty complete retained-resource declaration"
                )
            if not resumable_supported(contract_text):
                raise HandoffError("tracker does not support resumable Claims")
            verify_resources(repo, ticket, declared)
        elif declared:
            raise HandoffError("retained resources require resume intent")
        rel_ticket = ticket.path.relative_to(repo).as_posix()
        canonical, found = receipt_path(repo, ticket, key), find_receipt(repo, key)
        path = found or canonical
        rel_receipt = path.relative_to(repo).as_posix()
        if found is not None and found != canonical:
            return result(
                "conflict",
                key,
                rel_receipt,
                "handoff key is bound to different immutable facts",
                "use a new handoff key for changed immutable facts",
            )
        backlink = Path(os.path.relpath(path, ticket.path.parent)).as_posix()
        allowed = {rel_ticket, rel_receipt}
        binding = {
            "repo": str(repo),
            "handoff_key": key,
            "tickets": [rel_ticket],
            "outcome": outcome,
        }
        if candidate:
            head, sha = candidate_identity(
                repo, ticket, allowed if path.is_file() else set()
            )
            binding.update(head=head, head_sha=sha)
        elif outcome in RECOVERY:
            binding.update(
                recovery_next_action=next_action, retained_resources=declared
            )
        expected = render(binding, body.strip())
        if path.is_file():
            old = path.read_text()
            try:
                stored_key = json.loads(scalar(old, "handoff_key"))
            except json.JSONDecodeError as e:
                raise HandoffError("canonical receipt handoff key is malformed") from e
            if path != canonical or stored_key != key:
                return result(
                    "conflict",
                    key,
                    rel_receipt,
                    "handoff key is bound to different immutable facts",
                    "use a new handoff key for changed immutable facts",
                )
            tickets = [
                line[4:].strip()
                for line in re.search(r"(?m)^tickets:\n((?:  - .+\n?)+)", old)
                .group(1)
                .splitlines()
            ]
            stored = {
                "repo": str(repo),
                "handoff_key": stored_key,
                "tickets": tickets,
                "outcome": scalar(old, "outcome"),
            }
            if candidate:
                stored.update(
                    head=scalar(old, "head"), head_sha=scalar(old, "head_sha")
                )
            elif outcome in RECOVERY:
                stored.update(
                    recovery_next_action=json.loads(
                        scalar(old, "recovery_next_action")
                    ),
                    retained_resources=list_field(old, "retained_resources"),
                )
            if scalar(old, "binding_digest") != digest(stored):
                return result(
                    "conflict",
                    key,
                    rel_receipt,
                    "canonical receipt binding digest failed verification",
                    "inspect the canonical receipt manually; do not retry unchanged",
                )
            if stored != binding:
                return result(
                    "conflict",
                    key,
                    rel_receipt,
                    "handoff key is bound to different immutable facts",
                    "use a new handoff key for changed immutable facts",
                )
            expected = render(binding, summary(old))
            if old != expected:
                return result(
                    "conflict",
                    key,
                    rel_receipt,
                    "canonical receipt failed complete verification",
                    "inspect the canonical receipt manually; do not retry unchanged",
                )
        else:
            allowed_initial_states = {contract.ready_state}
            if outcome == "superseded":
                allowed_initial_states.update(contract.human_states)
            if (
                ticket.status not in allowed_initial_states
                or contract.claim_value not in ticket.flags
                or backlink_count(ticket.container_text, backlink)
            ):
                raise HandoffError(
                    "outcome handoff requires a valid active Ticket and Claim"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            publication.atomic_write(path, expected)
            if os.environ.get("ULTRA_HANDOFF_FAIL_AFTER_RECEIPT") == "1":
                raise RetryableHandoff(
                    "receipt installed; retry same key to converge tracker state"
                )
        status = (
            contract.completed_state
            if candidate
            else "needs-info"
            if outcome == "needs-info"
            else "ready-for-human"
            if outcome in {"blocked", "ready-for-human"}
            else ticket.status
            if outcome == "superseded"
            else contract.ready_state
        )
        claimed, links = (
            contract.claim_value in ticket.flags,
            backlink_count(ticket.container_text, backlink),
        )
        if ticket.status == status and claimed == retain and links == 1:
            transition = False
        elif (
            ticket.status
            in (
                {contract.ready_state}
                | (set(contract.human_states) if outcome == "superseded" else set())
            )
            and claimed
            and links == 0
        ):
            transition = True
        else:
            return result(
                "conflict",
                key,
                rel_receipt,
                "Ticket state, Claim, and backlink do not match an allowed handoff transition",
                "inspect Ticket state, Claim, and backlink manually; do not retry unchanged",
            )
        if transition:
            current = ticket.path.read_text()
            inner = current[ticket.inner_start : ticket.inner_end]
            inner = frontier.replace_or_insert_field(
                inner,
                contract.state_fields,
                ticket.state_field or contract.state_fields[0],
                status,
            )
            flags = ", ".join(
                ticket.flags
                if retain
                else [f for f in ticket.flags if f != contract.claim_value]
            )
            inner = frontier.replace_or_insert_field(
                inner, contract.claim_aliases, contract.claim_field, flags
            )
            updated = add_backlink(
                current[: ticket.inner_start] + inner + current[ticket.inner_end :],
                backlink,
            )
            try:
                if os.environ.get("ULTRA_HANDOFF_FAIL_BEFORE_TICKET_WRITE") == "1":
                    raise OSError("injected Ticket transition failure")
                publication.atomic_write(ticket.path, updated)
            except OSError as e:
                raise RetryableHandoff(
                    f"receipt installed but Ticket transition failed: {e}"
                ) from e
        final = {
            a: t for t in frontier.load_tickets(repo, contract) for a in t.aliases
        }.get(ticket_id)
        if (
            final is None
            or final.status != status
            or (contract.claim_value in final.flags) != retain
            or backlink_count(ticket.path.read_text(), backlink) != 1
            or path.read_text() != expected
        ):
            return result(
                "retryable", key, rel_receipt, "handoff postcondition is incomplete"
            )
        if candidate and candidate_identity(repo, final, allowed) != (
            binding["head"],
            binding["head_sha"],
        ):
            return result(
                "retryable",
                key,
                rel_receipt,
                "candidate identity postcondition is incomplete",
            )
        if retain:
            verify_resources(repo, final, declared)
        return result("success", key, rel_receipt)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("ticket-id", "handoff-key", "outcome", "summary"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--repo", default=".")
    p.add_argument("--recovery-next-action", default="")
    p.add_argument("--retained-resource", action="append", default=[])
    a = p.parse_args()
    try:
        payload = handoff(
            Path(a.repo).resolve(),
            a.ticket_id,
            a.handoff_key,
            a.outcome,
            a.summary,
            a.recovery_next_action,
            a.retained_resource,
        )
    except RetryableHandoff as e:
        payload = result("retryable", a.handoff_key, reason=str(e))
    except (HandoffError, frontier.FrontierError, OSError) as e:
        payload = result("conflict", a.handoff_key, reason=str(e))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
