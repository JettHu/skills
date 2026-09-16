#!/usr/bin/env python3
"""One read-only full Tracker Snapshot, owned by the canonical tracker facade."""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time

import local_outcome_handoff as handoff
import local_ticket_frontier as frontier
import local_ticket_publication as publication
import tracker_contract

SCHEMA = "tracker-snapshot/v1"
SEMANTIC_VERSION = "tracker-snapshot-semantics/v3"


class SnapshotError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def diagnostic(code, message, source, effect="route-to-attention", severity="warning"):
    return dict(code=code, message=message, source=source, effect=effect, severity=severity)


def safe_path(repo, path):
    resolved = path.resolve()
    if not resolved.is_relative_to(repo):
        raise SnapshotError("path-escape", f"source escapes repository: {path}; pass the canonical tracker repository explicitly")
    return resolved


def repository(path):
    root = Path(path).resolve()
    if not root.is_dir():
        raise SnapshotError("repository-unavailable", f"repository unavailable: {root}")
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            root = Path(result.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    # No guessed worktree fallback: a shared symlink requires an explicit canonical repo.
    safe_path(root, root / tracker_contract.INDEX)
    safe_path(root, root / ".scratch")
    return root


def records_helper():
    path = Path(__file__).resolve().parents[2] / "solve-records/scripts/solve-records.py"
    if not path.is_file():
        raise SnapshotError("helper-unavailable", f"canonical Solve Record helper unavailable: {path}")
    spec = importlib.util.spec_from_file_location("snapshot_records", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def bounded_git(cwd, *args, check=True):
        result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(cwd), *args], capture_output=True, text=True, timeout=3)
        if check and result.returncode:
            raise RuntimeError(result.stderr.strip() or "Git observation failed")
        return result
    module.run_git = bounded_git  # Observation-only dependency; mutation module unchanged.
    return module  # Fresh owner caches for every observation, including retries.


def git_observation(repo):
    observations = {}; diagnostics = []
    for name, args in (("refs", ["for-each-ref", "--format=%(refname)%00%(refname:short)%00%(objectname)"]), ("worktrees", ["worktree", "list", "--porcelain"])):
        try:
            result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo), *args], capture_output=True, text=True, timeout=5)
            if result.returncode:
                raise OSError(result.stderr.strip() or "Git observation failed")
            observations[name] = result.stdout
        except (OSError, subprocess.TimeoutExpired) as error:
            observations[name] = None
            diagnostics.append(diagnostic("git-unavailable", str(error), name, "snapshot-incomplete"))
    observations["worktree_status"] = {}
    for line in (observations["worktrees"] or "").splitlines():
        if not line.startswith("worktree "): continue
        location = line[9:]
        try:
            result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", location, "status", "--porcelain"], capture_output=True, text=True, timeout=5)
            if result.returncode: raise OSError("worktree status unavailable: " + location)
            observations["worktree_status"][location] = result.stdout
        except (OSError, subprocess.TimeoutExpired) as error:
            observations["worktree_status"][location] = None
            diagnostics.append(diagnostic("git-unavailable", str(error), "worktrees", "snapshot-incomplete"))
    return observations, diagnostics


def git_facts(observations):
    refs = {}; worktrees = {}; current = None
    for line in (observations["refs"] or "").splitlines():
        parts = line.split("\0")
        if len(parts) == 3:
            name, short, sha = parts
            refs[name] = refs[short] = sha
            if name.startswith("refs/heads/"): refs[name[11:]] = sha
    for line in (observations["worktrees"] or "").splitlines():
        if line.startswith("worktree "):
            current = str(Path(line[9:]).resolve())
            worktrees[current] = {"path": current, "branch": ""}
        elif current and line.startswith("branch "):
            worktrees[current]["branch"] = line[7:].removeprefix("refs/heads/")
        elif current and line.startswith("HEAD "):
            worktrees[current]["head_sha"] = line[5:]
    return refs, worktrees


def receipt_locations(repo, contract):
    if contract.representation != "file-per-ticket":
        return [handoff.receipt_directory(repo, contract.representation, [])]
    # Receipt roots survive removal of their Ticket surface. Enumerate only the
    # parent pattern authorized by this contract, then ask the placement owner.
    pattern = re.sub(r"<[^>]+>", "*", contract.location_pattern)
    parent_pattern = Path(pattern).parent.parent.as_posix()
    locations = set()
    for parent in repo.glob(parent_pattern):
        if not parent.is_dir(): continue
        safe_path(repo, parent)
        coordinate = parent / Path(pattern).parent.name / "unused.md"
        locations.add(handoff.receipt_directory(repo, contract.representation, [coordinate]))
    return sorted(locations)


def source_paths(repo, contract):
    pattern = re.sub(r"<[^>]+>", "*", contract.location_pattern)
    sources = {safe_path(repo, repo / tracker_contract.INDEX)}
    documents = tracker_contract.read(repo)
    sources.add(safe_path(repo, documents.capability_path))
    for path in repo.glob(pattern):
        safe_path(repo, path)
        if path.is_file(): sources.add(path.resolve())
    for pattern in (".scratch/solve-records/*.md", ".scratch/*/solve-records/*.md"):
        for path in repo.glob(pattern):
            sources.add(safe_path(repo, path))
    for directory in receipt_locations(repo, contract):
        safe_path(repo, directory)
        for path in directory.glob("*.md"):
            sources.add(safe_path(repo, path))
    for location in surfaces(repo, contract):
        directory = publication.journal_dir(location, contract.representation)
        safe_path(repo, directory)
        for path in directory.rglob("*.json"):
            sources.add(safe_path(repo, path))
    return sorted(sources)


def source_digest(repo, paths, observations):
    entries = []
    for path in paths:
        entries.append((path.relative_to(repo).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    return hashlib.sha256(json.dumps([entries, observations], sort_keys=True).encode()).hexdigest()


def surfaces(repo, contract):
    pattern = re.sub(r"<[^>]+>", "*", contract.location_pattern)
    if contract.representation == "file-per-ticket": pattern = str(Path(pattern).parent)
    return sorted(safe_path(repo, path) for path in repo.glob(pattern) if path.is_dir() or path.is_file())


def as_list(value, split_words=False):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if split_words:
        return [item for item in re.split(r"[,\s]+", text) if item]
    return [item.strip() for item in text.split(",") if item.strip()]


def first_heading(text):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def heading_block(text, predicate):
    lines = text.splitlines()
    block = []
    collecting = False
    current_level = 0
    for line in lines:
        match = re.match(r"^(#+)\s+(.*)$", line)
        if match:
            level = len(match.group(1))
            title = match.group(2).strip()
            if collecting and level <= current_level:
                break
            if not collecting and predicate(level, title):
                collecting = True
                current_level = level
                continue
        if collecting:
            block.append(line)
    return block


def paths_from_lines(lines):
    paths = []
    for line in lines:
        for value in re.findall(r"`([^`]+)`", line):
            value = value.strip()
            if value:
                paths.append(value)
        if "`" in line:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if value:
                paths.append(value)
    return paths


def checklist_counts(text):
    total = 0
    done = 0
    for line in text.splitlines():
        match = re.match(r"^\s*-\s+\[([ xX])\]", line)
        if not match:
            continue
        total += 1
        if match.group(1).lower() == "x":
            done += 1
    return {"total": total, "done": done, "open": total - done}


def resolve_worktree(repo, raw_path):
    path = Path(raw_path)
    return (path if path.is_absolute() else repo / path).resolve()


def handoff_consistency(repo, issues, records, refs, live_worktrees, contract):
    records_by_path = {record["path"]: record for record in records}
    issues_by_path = {issue["path"]: issue for issue in issues}
    for record in records:
        outcome = record.get("outcome")
        if record.get("malformed"):
            record["handoff_projection"] = "inconsistent_handoff_attention"
            continue
        recovery_outcomes = {"blocked", "needs-info", "ready-for-human"}
        terminal_outcomes = {"abandoned", "superseded"}
        if outcome not in recovery_outcomes | terminal_outcomes | {"candidate"}:
            continue
        linked = [issues_by_path.get(path) for path in record.get("issues", [])]
        identities = record.get("retained_resource_identities") or []
        resource_values = {identity["kind"]: identity["value"] for identity in identities}
        resources_valid = set(resource_values) == {"branch", "worktree"}
        if resources_valid:
            declared_worktree = resolve_worktree(repo, resource_values["worktree"])
            registered = live_worktrees.get(str(declared_worktree))
            resources_valid = bool(
                declared_worktree.exists()
                and registered
                and registered.get("branch") == resource_values["branch"]
                and resource_values["branch"] in refs
                and all(
                    issue
                    and issue.get("solve_branch") == resource_values["branch"]
                    and resolve_worktree(repo, issue.get("solve_worktree")) == declared_worktree
                    for issue in linked
                )
            )
        backlinks_valid = bool(linked) and all(
            issue and any(
                (repo / issue["path"]).parent.joinpath(backlink).resolve()
                == (repo / record["path"]).resolve()
                for backlink in issue.get("solve_records", [])
            )
            for issue in linked
        )
        def relation_backlinks_valid(other):
            other_linked = [
                issues_by_path.get(path) for path in other.get("issues", [])
            ]
            return bool(other_linked) and all(
                issue and any(
                    (repo / issue["path"]).parent.joinpath(backlink).resolve()
                    == (repo / other["path"]).resolve()
                    for backlink in issue.get("solve_records", [])
                )
                for issue in other_linked
            )

        predecessor = records_by_path.get(record.get("supersedes"))
        relation_consistent = not record.get("supersedes") or bool(
            predecessor
            and not predecessor.get("malformed")
            and predecessor.get("state") == "closed"
            and predecessor.get("closed_at")
            and predecessor.get("superseded_by") == record.get("path")
            and predecessor.get("issues") == record.get("issues")
            and relation_backlinks_valid(predecessor)
        )
        if outcome == "candidate":
            candidate_consistent = (
                record.get("state") == "open"
                and backlinks_valid
                and all(
                    issue
                    and issue.get("status") == contract.completed_state
                    and contract.claim_value not in issue.get("flags", [])
                    for issue in linked
                )
                and refs.get(record.get("head")) == record.get("head_sha")
                and relation_consistent
            )
            record["handoff_projection"] = (
                "normal_candidate"
                if candidate_consistent
                else "inconsistent_handoff_attention"
            )
            continue
        if record.get("state") == "closed" and record.get("superseded_by"):
            successor = records_by_path.get(record.get("superseded_by"))
            predecessor_consistent = bool(
                record.get("closed_at")
                and successor
                and not successor.get("malformed")
                and successor.get("supersedes") == record.get("path")
                and successor.get("issues") == record.get("issues")
                and backlinks_valid
                and relation_backlinks_valid(successor)
            )
            record["handoff_projection"] = (
                "closed_predecessor_history"
                if predecessor_consistent
                else "inconsistent_handoff_attention"
            )
            continue
        if outcome in terminal_outcomes:
            allowed_statuses = (
                {"ready-for-agent"}
                if outcome == "abandoned"
                else {"ready-for-agent", "ready-for-human", "needs-info"}
            )
            terminal_consistent = (
                record.get("state") == "closed"
                and backlinks_valid
                and all(
                    issue
                    and issue.get("status") in allowed_statuses
                    and contract.claim_value not in issue.get("flags", [])
                    for issue in linked
                )
                and relation_consistent
            )
            record["handoff_projection"] = (
                "closed_terminal_history"
                if terminal_consistent
                else "inconsistent_handoff_attention"
            )
            continue

        expected_status = "needs-info" if outcome == "needs-info" else "ready-for-human"
        action = record.get("recovery_action")
        retained = record.get("retained_resources") or []
        recovery_consistent = (
            record.get("state") == "open"
            and backlinks_valid
            and all(
                issue
                and issue.get("status") == expected_status
                and ((contract.claim_value in issue.get("flags", [])) == (action == "resume"))
                for issue in linked
            )
            and (
                (action == "resume" and resources_valid)
                or (action != "resume" and not retained)
            )
            and relation_consistent
        )
        if not recovery_consistent:
            record["handoff_projection"] = "inconsistent_handoff_attention"
        elif action == "resume":
            record["handoff_projection"] = "retained_recovery_ownership"
        else:
            record["handoff_projection"] = "normal_active_recovery"


def ticket_facts(repo, item):
    text = item.container_text[item.inner_start:item.inner_end]
    values, _ = frontier.parse_metadata(text, multiline_lists=True)
    def value(name): return values.get(frontier.normalize_key(name), "")
    source = item.path.relative_to(repo).as_posix()
    locator = source + ("#" + item.identity if item.representation == "tickets-file" else "")
    parents = as_list(value("parent")) or paths_from_lines(heading_block(text, lambda level, name: level == 2 and name.lower() == "parent"))
    receipts = as_list(value("solve_record") or value("solve_records"))
    receipts += paths_from_lines(heading_block(text, lambda level, name: name.lower() in {"solve record", "solve records"}))
    phase = None
    if item.publication_run:
        location = item.path.parent if item.representation == "file-per-ticket" else item.path
        try:
            phase = publication.read_journal(publication.journal_path(location, item.representation, item.publication_run)).get("phase")
        except (publication.AdapterError, OSError):
            pass
    return dict(publication_phase=phase, path=locator, source_path=source, title=first_heading(text) or item.path.stem,
                ticket_id=item.identity, status=item.status, flags=item.flags,
                solve_branch=item.branch, solve_worktree=item.worktree,
                publication_run=item.publication_run, publication_promoted=item.publication_ready and bool(item.publication_run),
                publication_digest=item.publication_digest, publication_original_digest=item.publication_original_digest,
                category=str(value("category")), created=str(value("created")),
                feature=Path(source).parts[1] if source.startswith(".scratch/") and len(Path(source).parts) > 2 else "",
                parent=parents[0] if parents else "", source_spec=str(value("source_spec")),
                blocked_by=item.blockers, solve_records=sorted(set(receipts)), checklist=checklist_counts(text),
                metadata_format="frontmatter" if text.lstrip().startswith("---") else "header", warnings=[])


def reserve_identities(repo, paths, contract):
    """Malformed sources still reserve extractable formal IDs; ambiguity is global."""
    owners = {}
    for path in paths:
        try: text = path.read_text()
        except (OSError, UnicodeError): continue
        sections = [(path.relative_to(repo).as_posix(), text, "")]
        if contract.representation == "tickets-file":
            starts = list(frontier.BEGIN.finditer(text))
            sections = []
            for index, marker in enumerate(starts):
                end = frontier.END.search(text, marker.end())
                chunk = text[marker.end():end.start() if end else len(text)]
                sections.append((path.relative_to(repo).as_posix() + "#" + marker.group(1) + f":{index}", chunk, marker.group(1)))
        for locator, chunk, marker_id in sections:
            identities = set()
            try:
                start, end = frontier.metadata_region(chunk)
            except frontier.FrontierError:
                start = end = 0
            identity_fields = {frontier.normalize_key(field) for field in contract.identity_fields}
            for line in chunk[start:end].splitlines():
                if ":" not in line: continue
                name, value = line.split(":", 1)
                if frontier.normalize_key(name) not in identity_fields: continue
                identity = frontier.parse_scalar(value)
                if isinstance(identity, str) and frontier.SAFE_ID.fullmatch(identity): identities.add(identity)
            if marker_id: identities.add(marker_id)
            if len(identities) > 1:
                raise SnapshotError("ambiguous-identity", f"conflicting Ticket identities at {locator}: {sorted(identities)}")
            for identity in identities:
                if identity in owners:
                    raise SnapshotError("ambiguous-identity", f"duplicate Ticket identity {identity}: {owners[identity]}, {locator}")
                owners[identity] = locator
    return owners


def normalize_ticket(issue, item, contract, eligibility, by_id, aliases, receipts):
    warnings = issue["warnings"]
    reasons = list(eligibility["non_frontier"].get(item.identity, []))
    legacy = item.identity == issue["source_path"]
    text = item.container_text[item.inner_start:item.inner_end]
    start, end = frontier.metadata_region(text)
    if re.search(r"(?m)^\s+-\s+", text[start:end]):
        reasons.append("readonly-metadata-syntax")
        warnings.append(diagnostic("readonly-metadata-syntax", "Block-list metadata is readable; canonical mutation syntax must be normalized before Claim", issue["path"], "exclude-from-frontier"))
    if legacy and item.status != contract.completed_state:
        reasons.append("missing-stable-identity")
        warnings.append(diagnostic("missing-stable-identity", "Ticket has no exact stable ID; retained as a legacy locator", issue["path"], "exclude-from-frontier", "error"))
    publication_status = "not-applicable"
    if item.publication_run:
        publication_status = "verified" if item.publication_ready else "invalid"
        if not item.publication_ready:
            code = "publication_not_promoted" if item.publication_reason == "publication-not-promoted" else "publication_invalid"
            warnings.append(diagnostic(code, item.publication_reason, issue["path"], "exclude-from-frontier", "error"))
    blockers = []
    for reference in item.blockers:
        target = aliases.get(reference); linked = by_id.get(target)
        satisfied = bool(linked and linked.status == contract.completed_state and linked.publication_ready)
        blockers.append(dict(reference=reference, ticket_key=target, state=linked.status if linked else None, satisfied=satisfied))
    for reason in reasons:
        if reason.startswith(("missing-blocker", "dependency-cycle", "blocked-by")):
            warnings.append(diagnostic(reason.split(":")[0], reason, issue["path"], "exclude-from-frontier"))
    receipt_keys = []
    for backlink in issue["solve_records"]:
        target = (Path(issue["source_path"]).parent / backlink).as_posix()
        resolved = (Path(issue["source_path"]).parent / backlink)
        # Resolve relative syntax against canonical repo in the cross-link pass.
        matching = [record["path"] for record in receipts if issue["path"] in record.get("issues", []) and Path(record["path"]).name == Path(target).name]
        receipt_keys.extend(matching)
    return dict(key=item.identity, ticket_id="" if legacy else item.identity, identity_quality="legacy-locator" if legacy else "stable-id",
                locator=issue["path"], source_locator=issue["source_path"], title=issue["title"], feature=issue["feature"],
                category=issue["category"], created=issue["created"], state=item.status, metadata_format=issue["metadata_format"],
                contract=dict(effective_text=item.inner if item.publication_ready else None, amendment=item.amendment, parent=issue["parent"], source_spec=issue["source_spec"], checklist=issue["checklist"], completed=item.status == contract.completed_state and item.publication_ready),
                publication=dict(run_id=item.publication_run, phase=issue["publication_phase"], status=publication_status, verified=item.publication_ready if item.publication_run else None,
                                 current_digest=item.publication_digest, original_digest=item.publication_original_digest, reason=item.publication_reason),
                blockers=blockers, claim=dict(active=contract.claim_value in item.flags, flags=item.flags, branch=item.branch, worktree=item.worktree),
                eligibility=dict(claimable=not reasons, reasons=sorted(set(reasons))), receipt_keys=sorted(set(receipt_keys)),
                receipt_references=issue["solve_records"], diagnostics=warnings)


def _observe(repo, contract, contract_text, paths, observations, git_diagnostics):
    errors = []
    ticket_paths = frontier.configured_paths(repo, contract)
    identity_sources = reserve_identities(repo, ticket_paths, contract)
    tickets = frontier.load_tickets(repo, contract, readonly_errors=errors)
    frontier.apply_publication_gates(repo, tickets, contract)
    eligibility, by_id = frontier.evaluate_frontier(tickets, contract, contract_text, [])
    aliases = {alias: item.identity for item in tickets for alias in item.aliases}
    issues = [ticket_facts(repo, item) for item in tickets]
    refs, worktrees = git_facts(observations)
    git_available = not git_diagnostics
    helper = records_helper()
    records = helper.discover(repo, extra_locations=receipt_locations(repo, contract))
    normalized = []
    seen = set()
    for record in records:
        key = record["path"]
        safe_path(repo, repo / key)
        if key in seen:
            raise SnapshotError("ambiguous-identity", f"duplicate receipt locator: {key}")
        seen.add(key)
        try:
            summary = helper.record_summary(repo, record, include_merge_gate=git_available)
            summary["cleanup_plan"] = helper.cleanup_plan(repo, record) if git_available else {"status": "unavailable", "reason": "Git observation unavailable"}
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            summary = {name: value for name, value in record.items() if name != "text"}
            summary["cleanup_plan"] = {"status": "unavailable", "reason": str(error)}
            git_diagnostics.append(diagnostic("readiness-unavailable", str(error), record["path"], "snapshot-incomplete"))
        summary.pop("terminal_view", None); summary.pop("recovery_view", None)
        summary.update(head_sha=record.get("head_sha"), base_sha=record.get("base_sha"))
        normalized.append(summary)
    for issue in issues:
        if not git_available:
            issue["warnings"].append(diagnostic("git-unavailable", "Git drift observations unavailable", issue["path"], "snapshot-incomplete"))
            continue
        branch, raw = issue["solve_branch"], issue["solve_worktree"]
        if branch and branch not in refs:
            issue["warnings"].append(diagnostic("missing_solve_branch", f"solve branch not found: {branch}", issue["path"]))
        if raw:
            wt = resolve_worktree(repo, raw); registered = worktrees.get(str(wt))
            if not wt.exists(): code, message = "missing_solve_worktree", f"solve worktree not found: {raw}"
            elif not registered: code, message = "unregistered_solve_worktree", f"solve worktree is not registered: {raw}"
            elif branch and registered["branch"] != branch: code, message = "worktree_branch_mismatch", f"worktree branch is {registered['branch']}, expected {branch}"
            else: continue
            issue["warnings"].append(diagnostic(code, message, issue["path"]))
    handoff_consistency(repo, issues, normalized, refs, worktrees, contract)
    entities = [normalize_ticket(issue, item, contract, eligibility, by_id, aliases, normalized) for issue, item in zip(issues, tickets)]
    locator_keys = {item["locator"]: item["key"] for item in entities}
    by_locator = {item["locator"]: item for item in entities}
    for record in normalized:
        projection = record.pop("handoff_projection", "not-applicable")
        diagnostics = []
        if record.get("malformed"):
            diagnostics.append(diagnostic("malformed-receipt", str(record["malformed"]), record["path"], "route-to-attention", "error"))
        if projection == "inconsistent_handoff_attention":
            diagnostics.append(diagnostic("inconsistent-handoff", "Ticket, receipt, refs or successor handoff facts disagree", record["path"], "snapshot-incomplete", "error"))
        record["handoff_consistency"] = dict(status="unavailable" if not git_available else "inconsistent" if projection == "inconsistent_handoff_attention" else "consistent" if projection != "not-applicable" else "not-applicable", classification=projection.replace("_attention", ""))
        record["key"] = record["locator"] = record["path"]
        record["ticket_keys"] = [locator_keys.get(path, path) for path in record.get("issues", [])]
        record["diagnostics"] = diagnostics
        record["operation_readiness"] = dict(merge=record.pop("merge_gate", None), cleanup=record.pop("cleanup_plan", None), observational=True)
        for locator in record.get("issues", []):
            entity = by_locator.get(locator)
            if entity:
                if record["key"] not in entity["receipt_keys"]: entity["receipt_keys"].append(record["key"])
            else: diagnostics.append(diagnostic("unresolved-ticket", f"linked Ticket unavailable: {locator}", record["path"]))
    for entity in entities:
        entity["receipt_keys"].sort()
        for reference in entity["receipt_references"]:
            resolved = (repo / entity["source_locator"]).parent.joinpath(reference).resolve()
            found = next((r for r in normalized if (repo / r["locator"]).resolve() == resolved), None)
            if not found or entity["locator"] not in found.get("issues", []):
                entity["diagnostics"].append(diagnostic("receipt-backlink-inconsistent", f"unresolved or non-reciprocal receipt link: {reference}", entity["locator"]))
    for error in errors:
        entities.append(dict(key="malformed:" + error["locator"], identity_candidates=sorted(identity for identity, locator in identity_sources.items() if locator == error["locator"] or locator.startswith(error["locator"] + ":")), ticket_id="", locator=error["locator"], source_locator=error["source"], title=Path(error["source"]).stem,
                             state=None, eligibility=dict(claimable=False, reasons=["malformed-ticket"]), diagnostics=[diagnostic("malformed-ticket", error["message"], error["locator"], "exclude-from-frontier", "error")]))
    entities.sort(key=lambda item: item["key"]); normalized.sort(key=lambda item: item["key"])
    all_diagnostics = git_diagnostics + [d for entity in entities + normalized for d in entity["diagnostics"]]
    incomplete = any(d["effect"] == "snapshot-incomplete" for d in all_diagnostics)
    degraded = {"tickets": bool(errors), "receipts": any(record["diagnostics"] for record in normalized), "publication": any(d["code"].startswith("publication_") for d in all_diagnostics)}
    source_status = [dict(name=name, status="unavailable" if name in {d["source"] for d in git_diagnostics} else "degraded" if degraded.get(name) else "ok") for name in ("tickets", "publication", "receipts", "refs", "worktrees")]
    return dict(schema_version=SCHEMA, repository=dict(root=str(repo), representation=contract.representation, location=contract.location_pattern),
                source_fingerprint="", sources=source_status,
                tickets=entities, receipts=normalized, diagnostics=git_diagnostics,
                summary=dict(ticket_count=len(entities), receipt_count=len(normalized), claimable_count=sum(e["eligibility"]["claimable"] for e in entities),
                             states=dict(sorted(Counter(e["state"] or "malformed" for e in entities).items())), diagnostic_severity=dict(sorted(Counter(d["severity"] for d in all_diagnostics).items())), incomplete=incomplete))


def normalize_selection(selection):
    """None means full scope; an explicit empty sequence means return no entities."""
    if selection is None:
        return None
    if not isinstance(selection, (list, tuple)) or any(not isinstance(key, str) or not key for key in selection):
        raise SnapshotError("invalid-selection", "selection must be a sequence of nonempty exact Ticket keys")
    return sorted(set(selection))


def selected_result(full, selection):
    """Filter only after the full graph and fatal checks; relation facts retain source truth."""
    result = json.loads(json.dumps(full))
    tickets = result["tickets"]; receipts = result["receipts"]
    ticket_index = {token: item for item in tickets for token in [item["key"], item["locator"], *item.get("identity_candidates", [])]}
    receipt_index = {item["key"]: item for item in receipts}
    requested = [item["key"] for item in tickets] if selection is None else selection
    # Stable keys are the selection interface; aliases only resolve source relationships.
    by_key = {token: item for item in tickets for token in [item["key"], *item.get("identity_candidates", [])]}
    matched = {by_key[token]["key"] for token in requested if token in by_key}
    returned_receipts = {item["key"] for item in receipts if selection is None or any(ticket_index.get(reference) and ticket_index[reference]["key"] in matched for reference in item.get("issues", []))}
    def ticket_relation(reference):
        entity = ticket_index.get(reference)
        return dict(reference=reference, ticket_key=entity["key"] if entity else None,
                    resolution="invalid-source" if entity and entity["key"].startswith("malformed:") else "resolved" if entity else "source-missing",
                    returned=bool(entity and entity["key"] in matched))
    def receipt_relation(reference):
        entity = receipt_index.get(reference)
        return dict(reference=reference, receipt_key=entity["key"] if entity else None,
                    resolution="invalid-source" if entity and entity.get("malformed") else "resolved" if entity else "source-missing",
                    returned=bool(entity and entity["key"] in returned_receipts))
    for item in tickets:
        for blocker in item.get("blockers", []):
            relation = ticket_relation(blocker.get("ticket_key") or blocker["reference"])
            blocker.update(resolution=relation["resolution"], returned=relation["returned"], source_ticket_key=relation["ticket_key"])
        item["receipt_relations"] = [receipt_relation(key) for key in item.get("receipt_keys", [])]
        for reference in item.get("receipt_references", []):
            resolved = (Path(full["repository"]["root"]) / item["source_locator"]).parent.joinpath(reference).resolve()
            found = next((receipt for receipt in receipts if (Path(full["repository"]["root"]) / receipt["locator"]).resolve() == resolved), None)
            relation = receipt_relation(found["key"] if found else reference)
            relation["reference"] = reference
            item["receipt_relations"].append(relation)
    for item in receipts:
        item["ticket_relations"] = [ticket_relation(reference) for reference in item.get("issues", [])]
        item["successor_relation"] = {name: receipt_relation(item[field]) if item.get(field) else None for name, field in (("predecessor", "supersedes"), ("successor", "superseded_by"))}
    result["tickets"] = [item for item in tickets if item["key"] in matched]
    result["receipts"] = [item for item in receipts if item["key"] in returned_receipts]
    result["selection"] = dict(mode="all" if selection is None else "exact", requested=selection,
                               matched=sorted(matched), resolved={token: by_key[token]["key"] for token in requested if token in by_key}, missing=sorted(set(requested) - by_key.keys()),
                               returned_ticket_count=len(result["tickets"]), returned_receipt_count=len(result["receipts"]))
    return result


def snapshot(repo, selection=None):
    """Observe the complete configured tracker, with bounded owner locks and retries."""
    selected = normalize_selection(selection)
    repo = repository(repo)
    try:
        for _attempt in range(2):
            contract, contract_text = frontier.read_contract(repo)
            locations = surfaces(repo, contract)
            with ExitStack() as stack:
                lock_observations = [stack.enter_context(frontier.frontier_lock(repo, timeout=0.5, readonly=True))]
                deadline = time.monotonic() + 0.5
                for location in locations:
                    lock_observations.append(stack.enter_context(publication.mutation_lock(location, contract.representation, timeout=max(0, deadline - time.monotonic()), readonly=True)))
                live_contract, live_text = frontier.read_contract(repo)
                if live_contract != contract or surfaces(repo, contract) != locations or not all(publication.lock_unchanged(lock) for lock in lock_observations): continue
                paths = source_paths(repo, contract)
                before_git, git_diagnostics = git_observation(repo)
                before = source_digest(repo, paths, before_git)
                result = _observe(repo, contract, live_text, paths, before_git, git_diagnostics)
                after_git, _ = git_observation(repo)
                if source_paths(repo, contract) != paths or source_digest(repo, paths, after_git) != before or not all(publication.lock_unchanged(lock) for lock in lock_observations): continue
                # Include all semantic observations, including readiness, but no wall clock.
                result["semantic_version"] = SEMANTIC_VERSION
                result["source_fingerprint"] = hashlib.sha256(json.dumps([before, result], sort_keys=True).encode()).hexdigest()
                return selected_result(result, selected)
        raise SnapshotError("incoherent-read", "canonical sources changed during both bounded observation attempts")
    except SnapshotError:
        raise
    except (frontier.FrontierError, publication.AdapterError, tracker_contract.TrackerContractError, OSError, UnicodeError, ValueError, subprocess.SubprocessError) as error:
        code = "observation-busy" if "lock timeout" in str(error) else "invalid-tracker"
        raise SnapshotError(code, str(error)) from error
