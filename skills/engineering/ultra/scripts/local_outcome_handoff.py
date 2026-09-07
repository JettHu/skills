#!/usr/bin/env python3
"""Converge one Local Markdown Ticket outcome handoff."""

from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, subprocess
from datetime import datetime, timezone
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


class UnavailableHandoff(HandoffError):
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


def receipt_path(repo, tickets, key):
    name = hashlib.sha256(key.encode()).hexdigest() + ".md"
    roots = {ticket.path.parent.parent for ticket in tickets}
    if (
        all(ticket.representation == "file-per-ticket" for ticket in tickets)
        and len(roots) == 1
    ):
        return roots.pop() / "solve-records" / name
    return repo / ".scratch/solve-records" / name


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


def ticket_membership(text):
    match = re.search(r"(?m)^tickets:\n((?:  - .+\n?)+)", text)
    if match is None:
        raise HandoffError("canonical receipt must define tickets")
    return [line[4:].strip() for line in match.group(1).splitlines()]


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
    if binding.get("supersedes"):
        lines.append(f"supersedes: {json.dumps(binding['supersedes'])}")
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


def replace_scalar(text, field, value):
    updated, count = re.subn(
        rf"(?m)^{re.escape(field)}:[ \t]*.*$", f"{field}: {value}", text
    )
    if count != 1:
        raise HandoffError(f"canonical receipt must define exactly one {field}")
    return updated


def replace_frontmatter_scalar(text, field, value):
    end = text.find("\n---", 4)
    if not text.startswith("---\n") or end == -1:
        raise HandoffError("canonical receipt frontmatter is malformed")
    frontmatter = text[:end]
    updated, count = re.subn(
        rf"(?m)^{re.escape(field)}:[ \t]*.*$", f"{field}: {value}", frontmatter
    )
    if count != 1:
        raise HandoffError(f"canonical receipt must define exactly one {field}")
    return updated + text[end:]


def remove_section(text, name):
    pattern = rf"(?ms)\n## {re.escape(name)}[ \t]*\n.*?(?=\n## |\Z)"
    return re.sub(pattern, "", text, count=1).rstrip() + "\n"


def invalidate_legacy_gate_evidence(text, observed):
    text = replace_frontmatter_scalar(text, "head_sha", observed)
    text = re.sub(
        r"(?m)^(Head SHA:[ \t]*`?)[^`\n]+(`?[ \t]*)$",
        rf"\g<1>{observed}\g<2>",
        text,
    )
    for name in ("Verification", "Checks", "Review", "Merge"):
        text = remove_section(text, name)
    return text


def relation_value(text, field):
    try:
        return json.loads(scalar(text, field))
    except json.JSONDecodeError as e:
        raise HandoffError(f"canonical receipt {field} is malformed") from e


def predecessor_binding(repo, path):
    try:
        text = path.read_text()
        key = relation_value(text, "handoff_key")
        outcome = scalar(text, "outcome")
        tickets = ticket_membership(text)
        binding = {
            "repo": str(repo),
            "handoff_key": key,
            "tickets": tickets,
            "outcome": outcome,
            "recovery_next_action": relation_value(text, "recovery_next_action"),
            "retained_resources": list_field(text, "retained_resources"),
        }
        if outcome not in RECOVERY:
            raise HandoffError("predecessor is not a recovery receipt")
        if scalar(text, "binding_digest") != digest(binding):
            raise HandoffError("predecessor binding digest failed verification")
        if find_receipt(repo, key) != path:
            raise HandoffError("predecessor is not the canonical receipt for its handoff key")
        summary(text)
        return text, binding
    except AttributeError as e:
        raise HandoffError("predecessor receipt is malformed") from e


def close_predecessor(text, successor):
    updated = replace_scalar(text, "state", "closed")
    frontmatter_end = updated.find("\n---", 4)
    if frontmatter_end == -1:
        raise HandoffError("predecessor receipt is malformed")
    relation = (
        f"\nsuperseded_by: {json.dumps(successor)}"
        f"\nclosed_at: {json.dumps(datetime.now(timezone.utc).isoformat())}"
    )
    return updated[:frontmatter_end] + relation + updated[frontmatter_end:]


def backlink_count(text, backlink):
    return len(re.findall(rf"(?m)^- `{re.escape(backlink)}`[ \t]*$", text))


def add_backlink(text, backlink):
    count = backlink_count(text, backlink)
    if count > 1:
        raise HandoffError("Ticket contains duplicate receipt backlinks")
    if count:
        return text
    heading = re.search(r"(?m)^## Solve Records[ \t]*$", text)
    if heading:
        next_heading = re.search(r"(?m)^## ", text[heading.end() :])
        insert_at = (
            heading.end() + next_heading.start()
            if next_heading
            else len(text.rstrip())
        )
        return text[:insert_at].rstrip() + f"\n\n- `{backlink}`\n" + text[insert_at:].lstrip("\n")
    return text.rstrip() + f"\n\n## Solve Records\n\n- `{backlink}`\n"


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


def fail_at_boundary(name, member_number):
    value = os.environ.get(name)
    if not value:
        return False
    try:
        return int(value) == member_number
    except ValueError:
        return value == "1" and member_number == 1


def canonical_record(repo, path):
    parser_path = Path(__file__).resolve().parents[2] / "solve-records/scripts/solve-records.py"
    spec = importlib.util.spec_from_file_location("ultra_solve_record_parser", parser_path)
    if spec is None or spec.loader is None:
        raise UnavailableHandoff("canonical Solve Record parser is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    record = module.parse_record(repo, path)
    if record.get("malformed"):
        raise HandoffError(f"candidate receipt is malformed: {record['malformed']}")
    return record


def atomic_write_with_ref_verification(repo, head, observed, path, text):
    injected_head = os.environ.get("ULTRA_REFRESH_ADVANCE_HEAD_TO")
    if injected_head:
        git(repo, "update-ref", f"refs/heads/{head}", injected_head, observed)
    process = subprocess.Popen(
        ["git", "-C", str(repo), "update-ref", "--stdin"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        process.stdin.write(f"start\nverify refs/heads/{head} {observed}\nprepare\n")
        process.stdin.flush()
        responses = [process.stdout.readline().strip(), process.stdout.readline().strip()]
        if responses != ["start: ok", "prepare: ok"]:
            raise HandoffError("candidate head changed while refresh was preparing")
        publication.atomic_write(path, text)
        if os.environ.get("ULTRA_REFRESH_FAIL_AFTER_RECEIPT") == "1":
            raise RetryableHandoff(
                "candidate receipt updated; retry the same refresh input"
            )
        process.stdin.write("commit\n")
        process.stdin.flush()
        if process.stdout.readline().strip() != "commit: ok":
            raise RetryableHandoff("candidate receipt updated but Git ref verification did not commit")
    finally:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        process.wait()


def refresh_candidate(repo, ticket_ids, record_name, observed):
    if not re.fullmatch(r"[0-9a-f]{40}", observed):
        raise HandoffError("observed head SHA must be one full lowercase Git SHA")
    record_path = (repo / record_name).resolve()
    try:
        relative_record = record_path.relative_to(repo).as_posix()
    except ValueError as e:
        raise HandoffError("candidate receipt must be repository-relative") from e
    if not record_path.is_file() or "/solve-records/" not in f"/{relative_record}":
        raise HandoffError("candidate receipt is unavailable")

    with frontier.frontier_lock(repo):
        contract, _contract_text = frontier.read_contract(repo)
        indexed = {
            alias: ticket
            for ticket in frontier.load_tickets(repo, contract)
            for alias in ticket.aliases
        }
        selected = []
        for ticket_id in ticket_ids:
            ticket = indexed.get(ticket_id)
            if ticket is None:
                raise HandoffError(f"candidate Ticket is unavailable: {ticket_id}")
            selected.append(ticket)
        tickets = sorted(
            {ticket.path.resolve(): ticket for ticket in selected}.values(),
            key=lambda item: item.path.relative_to(repo).as_posix(),
        )
        if not tickets or len(tickets) != len(ticket_ids):
            raise HandoffError("candidate Ticket scope contains ambiguous duplicate members")

        old = record_path.read_text(encoding="utf-8")
        record = canonical_record(repo, record_path)
        membership = record["tickets"]
        expected_membership = [ticket.path.relative_to(repo).as_posix() for ticket in tickets]
        if sorted(membership) != expected_membership:
            raise HandoffError("candidate Ticket scope does not match the receipt")
        state = record["state"]
        explicit_outcome = re.findall(r"(?m)^outcome:[ \t]*(\S+)[ \t]*$", old)
        if state != "open" or record.get("outcome") != "candidate":
            raise HandoffError("candidate refresh requires one open candidate receipt")

        head, recorded = record["head"], record["head_sha"]
        if explicit_outcome:
            stored_key = relation_value(old, "handoff_key")
            stored_binding = {
                "repo": str(repo),
                "handoff_key": stored_key,
                "tickets": membership,
                "outcome": "candidate",
                "head": head,
                "head_sha": recorded,
            }
            if re.search(r"(?m)^supersedes:", old):
                stored_binding["supersedes"] = relation_value(old, "supersedes")
            if scalar(old, "binding_digest") != digest(stored_binding):
                raise HandoffError("candidate receipt binding digest failed verification")
            if find_receipt(repo, stored_key) != record_path:
                raise HandoffError("candidate receipt is not canonical for its handoff key")
        identities = set()
        for ticket in tickets:
            if ticket.status != contract.completed_state:
                raise HandoffError("candidate Ticket is not completed")
            if contract.claim_value in ticket.flags:
                raise HandoffError("candidate refresh does not accept an active Claim")
            identities.add(candidate_identity(repo, ticket))
            backlink = Path(os.path.relpath(record_path, ticket.path.parent)).as_posix()
            if backlink_count(ticket.container_text, backlink) != 1:
                raise HandoffError("candidate Ticket backlink does not identify this receipt")
        if len(identities) != 1:
            raise HandoffError("candidate Tickets have mixed retained resource identity")
        live_head, live_sha = identities.pop()
        if live_head != head:
            raise HandoffError("candidate branch does not match the receipt")
        legacy_path = Path(record["worktree"]) if record.get("worktree") else None
        if legacy_path is not None and not legacy_path.is_absolute():
            legacy_path = repo / legacy_path
        if legacy_path is not None and legacy_path.resolve() != Path(tickets[0].worktree).resolve():
            raise HandoffError("candidate worktree does not match the receipt")
        if live_sha != observed:
            raise HandoffError("observed head conflicts with the current candidate worktree")

        if recorded == observed:
            return {
                "schema": SCHEMA,
                "status": "unchanged",
                "receipt": relative_record,
                "head": head,
                "head_sha": observed,
            }
        ancestry = subprocess.run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", recorded, observed],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if ancestry.returncode != 0:
            raise HandoffError("observed head is not a descendant of the receipt head")

        updated = remove_section(old, "Gate Evidence")
        if explicit_outcome:
            updated = replace_frontmatter_scalar(updated, "head_sha", observed)
            key = relation_value(updated, "handoff_key")
            binding = {
                "repo": str(repo),
                "handoff_key": key,
                "tickets": membership,
                "outcome": "candidate",
                "head": head,
                "head_sha": observed,
            }
            if re.search(r"(?m)^supersedes:", updated):
                binding["supersedes"] = relation_value(updated, "supersedes")
            updated = replace_frontmatter_scalar(updated, "binding_digest", digest(binding))
            if any(
                re.search(rf"(?m)^## {name}[ \t]*$", updated)
                for name in ("Verification", "Checks", "Review", "Merge")
            ):
                updated = invalidate_legacy_gate_evidence(updated, observed)
        else:
            updated = invalidate_legacy_gate_evidence(updated, observed)
        atomic_write_with_ref_verification(repo, head, observed, record_path, updated)
        if record_path.read_text(encoding="utf-8") != updated:
            raise RetryableHandoff("candidate refresh postcondition is incomplete")
        return {
            "schema": SCHEMA,
            "status": "refreshed",
            "receipt": relative_record,
            "head": head,
            "previous_head_sha": recorded,
            "head_sha": observed,
            "evidence": "invalidated",
        }


def handoff(repo, ticket_ids, key, outcome, body, next_action, declared, supersedes=""):
    if not key.strip():
        raise HandoffError("handoff key is required")
    if outcome not in {"candidate"} | RECOVERY | TERMINAL:
        raise HandoffError(f"unsupported outcome: {outcome}")
    if not body.strip():
        raise HandoffError("outcome Summary is required")
    with frontier.frontier_lock(repo):
        contract, contract_text = frontier.read_contract(repo)
        indexed = {
            a: t for t in frontier.load_tickets(repo, contract) for a in t.aliases
        }
        if not ticket_ids:
            raise HandoffError("at least one Ticket identity is required")
        selected = []
        for ticket_id in ticket_ids:
            ticket = indexed.get(ticket_id)
            if ticket is None:
                raise HandoffError(f"active Ticket is unavailable: {ticket_id}")
            selected.append(ticket)
        tickets = sorted(
            {ticket.path.resolve(): ticket for ticket in selected}.values(),
            key=lambda item: item.path.relative_to(repo).as_posix(),
        )
        if len(tickets) != len(ticket_ids):
            raise HandoffError("Ticket membership contains ambiguous duplicate members")
        if outcome == "superseded" and len({ticket.status for ticket in tickets}) != 1:
            raise HandoffError("grouped Tickets have incompatible actionable states")
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
                raise UnavailableHandoff("tracker does not support resumable Claims")
            for ticket in tickets:
                verify_resources(repo, ticket, declared)
        elif declared:
            raise HandoffError("retained resources require resume intent")
        rel_tickets = [ticket.path.relative_to(repo).as_posix() for ticket in tickets]
        canonical, found = receipt_path(repo, tickets, key), find_receipt(repo, key)
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
        if found is not None:
            old_membership = ticket_membership(found.read_text())
            if old_membership != rel_tickets:
                return result(
                    "conflict",
                    key,
                    rel_receipt,
                    "handoff key is bound to different immutable facts",
                    "use a new handoff key for changed immutable facts",
                )
        backlinks = {
            ticket.path: Path(os.path.relpath(path, ticket.path.parent)).as_posix()
            for ticket in tickets
        }
        allowed = set(rel_tickets) | {rel_receipt}
        binding = {
            "repo": str(repo),
            "handoff_key": key,
            "tickets": rel_tickets,
            "outcome": outcome,
        }
        predecessor_path = None
        predecessor_text = ""
        if supersedes:
            predecessor_path = (repo / supersedes).resolve()
            try:
                predecessor_rel = predecessor_path.relative_to(repo).as_posix()
            except ValueError as e:
                raise HandoffError("predecessor must be a repository-relative canonical receipt") from e
            if predecessor_path == canonical:
                raise HandoffError("successor cannot refer to itself as predecessor")
            if not predecessor_path.is_file():
                raise HandoffError("predecessor receipt is unavailable")
            predecessor_text, predecessor_facts = predecessor_binding(repo, predecessor_path)
            if predecessor_facts["tickets"] != rel_tickets:
                raise HandoffError("predecessor Ticket membership does not match successor membership")
            predecessor_state = scalar(predecessor_text, "state")
            related_successor = ""
            if re.search(r"(?m)^superseded_by:", predecessor_text):
                related_successor = relation_value(predecessor_text, "superseded_by")
            has_closed_at = bool(
                re.search(r"(?m)^closed_at:[ \t]*\S", predecessor_text)
            )
            if predecessor_state == "open" and (related_successor or has_closed_at):
                raise HandoffError("open predecessor contains a partial successor relation")
            if predecessor_state == "closed" and not (
                related_successor == rel_receipt and has_closed_at
            ):
                raise HandoffError("predecessor is already closed")
            if predecessor_state not in {"open", "closed"}:
                raise HandoffError("predecessor state is malformed")
            binding["supersedes"] = predecessor_rel
            allowed.add(predecessor_rel)
        if candidate:
            identities = {
                candidate_identity(repo, ticket, allowed if path.is_file() else set())
                for ticket in tickets
            }
            if len(identities) != 1:
                raise HandoffError("grouped Tickets have mixed candidate resource evidence")
            head, sha = identities.pop()
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
            stored_tickets = ticket_membership(old)
            stored = {
                "repo": str(repo),
                "handoff_key": stored_key,
                "tickets": stored_tickets,
                "outcome": scalar(old, "outcome"),
            }
            if re.search(r"(?m)^supersedes:", old):
                stored["supersedes"] = relation_value(old, "supersedes")
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
            for ticket in tickets:
                if (
                    ticket.status not in allowed_initial_states
                    or contract.claim_value not in ticket.flags
                    or backlink_count(ticket.container_text, backlinks[ticket.path])
                ):
                    raise HandoffError(
                        "outcome handoff requires valid active grouped Tickets and Claims"
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
            else tickets[0].status
            if outcome == "superseded"
            else contract.ready_state
        )
        initial_states = {contract.ready_state} | (
            set(contract.human_states) if outcome == "superseded" else set()
        )

        def reload_ticket(ticket):
            return next(
                (
                    item
                    for item in frontier.load_tickets(repo, contract)
                    if item.path.resolve() == ticket.path.resolve()
                ),
                None,
            )

        preflight = [reload_ticket(ticket) for ticket in tickets]
        for original, ticket in zip(tickets, preflight):
            if ticket is None:
                return result(
                    "conflict",
                    key,
                    rel_receipt,
                    f"grouped Ticket is unavailable: {original.path.relative_to(repo)}",
                    "restore or inspect grouped Ticket membership manually; do not retry unchanged",
                )
            backlink = backlinks[original.path]
            claimed = contract.claim_value in ticket.flags
            links = backlink_count(ticket.container_text, backlink)
            if (
                ticket.status not in initial_states | {status}
                or claimed not in {True, retain}
                or links not in {0, 1}
            ):
                return result(
                    "conflict",
                    key,
                    rel_receipt,
                    "grouped Ticket state, Claim, or backlink is incompatible with this handoff",
                    "inspect Ticket state, Claim, and backlink manually; do not retry unchanged",
                )

        for member_index, original in enumerate(tickets):
            member_number = member_index + 1
            ticket = reload_ticket(original)
            backlink = backlinks[original.path]
            try:
                if ticket.status != status:
                    current = ticket.path.read_text()
                    inner = frontier.replace_or_insert_field(
                        current[ticket.inner_start : ticket.inner_end],
                        contract.state_fields,
                        ticket.state_field or contract.state_fields[0],
                        status,
                    )
                    publication.atomic_write(
                        ticket.path,
                        current[: ticket.inner_start]
                        + inner
                        + current[ticket.inner_end :],
                    )
                ticket = reload_ticket(original)
                if backlink_count(ticket.container_text, backlink) == 0:
                    if os.environ.get("ULTRA_HANDOFF_FAIL_BEFORE_TICKET_WRITE") == "1":
                        raise OSError("injected Ticket transition failure")
                    publication.atomic_write(ticket.path, add_backlink(ticket.container_text, backlink))
                if fail_at_boundary(
                    "ULTRA_HANDOFF_FAIL_AFTER_BACKLINK", member_number
                ):
                    raise RetryableHandoff("receipt installed but backlink transition was interrupted")
                ticket = reload_ticket(original)
                if (contract.claim_value in ticket.flags) != retain:
                    if fail_at_boundary(
                        "ULTRA_HANDOFF_FAIL_DURING_CLAIM", member_number
                    ):
                        raise OSError("injected Claim transition failure")
                    current = ticket.path.read_text()
                    flags = ", ".join(
                        ticket.flags
                        if retain
                        else [
                            flag
                            for flag in ticket.flags
                            if flag != contract.claim_value
                        ]
                    )
                    inner = frontier.replace_or_insert_field(
                        current[ticket.inner_start : ticket.inner_end],
                        contract.claim_aliases,
                        contract.claim_field,
                        flags,
                    )
                    publication.atomic_write(
                        ticket.path,
                        current[: ticket.inner_start]
                        + inner
                        + current[ticket.inner_end :],
                    )
                if (
                    fail_at_boundary("ULTRA_HANDOFF_FAIL_AFTER_MEMBER", member_number)
                ):
                    raise RetryableHandoff(
                        "receipt installed but grouped member transition was interrupted"
                    )
            except OSError as e:
                raise RetryableHandoff(
                    f"receipt installed but Ticket transition failed: {e}"
                ) from e

        finals = [reload_ticket(ticket) for ticket in tickets]
        if path.read_text() != expected or any(
            final is None
            or final.status != status
            or (contract.claim_value in final.flags) != retain
            or backlink_count(final.container_text, backlinks[original.path]) != 1
            for original, final in zip(tickets, finals)
        ):
            return result(
                "retryable", key, rel_receipt, "handoff postcondition is incomplete"
            )
        if candidate and any(
            candidate_identity(repo, final, allowed)
            != (binding["head"], binding["head_sha"])
            for final in finals
        ):
            return result(
                "retryable",
                key,
                rel_receipt,
                "candidate identity postcondition is incomplete",
            )
        if retain:
            for final in finals:
                verify_resources(repo, final, declared)
        if predecessor_path is not None:
            try:
                if os.environ.get("ULTRA_HANDOFF_FAIL_BEFORE_PREDECESSOR_RELATION_READ") == "1":
                    raise OSError("injected predecessor relation read failure")
                predecessor_text, predecessor_facts = predecessor_binding(
                    repo, predecessor_path
                )
            except OSError as e:
                raise RetryableHandoff(
                    f"successor handoff completed but predecessor relation read failed: {e}"
                ) from e
            predecessor_state = scalar(predecessor_text, "state")
            successor_value = (
                relation_value(predecessor_text, "superseded_by")
                if re.search(r"(?m)^superseded_by:", predecessor_text)
                else ""
            )
            if predecessor_state == "open":
                if os.environ.get("ULTRA_HANDOFF_FAIL_BEFORE_PREDECESSOR_CLOSE") == "1":
                    raise RetryableHandoff(
                        "successor handoff completed but predecessor relation remains open"
                    )
                try:
                    if os.environ.get("ULTRA_HANDOFF_FAIL_DURING_PREDECESSOR_CLOSE") == "1":
                        raise OSError("injected predecessor closure failure")
                    publication.atomic_write(
                        predecessor_path,
                        close_predecessor(predecessor_text, rel_receipt),
                    )
                    if os.environ.get("ULTRA_HANDOFF_FAIL_AFTER_PREDECESSOR_CLOSE") == "1":
                        raise OSError("injected predecessor relation verification failure")
                except OSError as e:
                    raise RetryableHandoff(
                        f"successor handoff completed but predecessor closure failed: {e}"
                    ) from e
                try:
                    predecessor_text, predecessor_facts = predecessor_binding(
                        repo, predecessor_path
                    )
                except OSError as e:
                    raise RetryableHandoff(
                        f"predecessor closed but relation verification failed: {e}"
                    ) from e
                predecessor_state = scalar(predecessor_text, "state")
                successor_value = relation_value(predecessor_text, "superseded_by")
            try:
                if os.environ.get("ULTRA_HANDOFF_FAIL_BEFORE_SUCCESSOR_RELATION_READ") == "1":
                    raise OSError("injected successor relation read failure")
                successor_text = path.read_text()
            except OSError as e:
                raise RetryableHandoff(
                    f"successor handoff completed but successor relation read failed: {e}"
                ) from e
            if (
                predecessor_facts["tickets"] != rel_tickets
                or predecessor_state != "closed"
                or successor_value != rel_receipt
                or not re.search(r"(?m)^closed_at:[ \t]*\S", predecessor_text)
                or relation_value(successor_text, "supersedes") != predecessor_path.relative_to(repo).as_posix()
            ):
                return result(
                    "retryable", key, rel_receipt, "predecessor relation postcondition is incomplete"
                )
        return result("success", key, rel_receipt)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ticket-id", action="append", required=True)
    for name in ("handoff-key", "outcome", "summary"):
        p.add_argument(f"--{name}")
    p.add_argument("--repo", default=".")
    p.add_argument("--refresh-candidate", action="store_true")
    p.add_argument("--record", default="")
    p.add_argument("--observed-head-sha", default="")
    p.add_argument("--recovery-next-action", default="")
    p.add_argument("--retained-resource", action="append", default=[])
    p.add_argument("--supersedes", default="")
    a = p.parse_args()
    try:
        repo = Path(a.repo).resolve()
        if a.refresh_candidate:
            if any((a.handoff_key, a.outcome, a.summary, a.recovery_next_action, a.retained_resource, a.supersedes)):
                raise HandoffError("candidate refresh does not accept outcome handoff inputs")
            if not a.record or not a.observed_head_sha:
                raise HandoffError("candidate refresh requires record and observed head SHA")
            payload = refresh_candidate(repo, a.ticket_id, a.record, a.observed_head_sha)
        else:
            if not all((a.handoff_key, a.outcome, a.summary)):
                raise HandoffError("outcome handoff requires handoff key, outcome, and summary")
            payload = handoff(
                repo,
                a.ticket_id,
                a.handoff_key,
                a.outcome,
                a.summary,
                a.recovery_next_action,
                a.retained_resource,
                a.supersedes,
            )
    except RetryableHandoff as e:
        repo = Path(a.repo).resolve()
        installed = find_receipt(repo, a.handoff_key) if a.handoff_key else None
        receipt = installed.relative_to(repo).as_posix() if installed else ""
        payload = result("retryable", a.handoff_key or "", receipt=receipt, reason=str(e))
    except UnavailableHandoff as e:
        payload = result(
            "unavailable",
            a.handoff_key,
            reason=str(e),
            next_action="restore the required tracker capability, then retry the same key",
        )
    except (HandoffError, frontier.FrontierError, OSError) as e:
        payload = result("conflict", a.handoff_key or "", reason=str(e))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
