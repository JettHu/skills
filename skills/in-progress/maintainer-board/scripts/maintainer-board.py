#!/usr/bin/env python3
"""Generate a read-only maintainer board snapshot for local .scratch state."""

import argparse
import html
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


ISSUE_BUCKETS = [
    "ready_for_agent",
    "claimed_or_in_progress",
    "needs_human",
    "blocked_or_dependent",
    "completed_with_solve_record",
    "completed_without_solve_record",
    "other",
]

SOLVE_RECORD_BUCKETS = [
    "ready",
    "manual",
    "cleanup",
    "recent",
    "recovery",
    "stale_or_malformed",
]
SOLVE_RECORD_OUTCOMES = {
    "candidate",
    "blocked",
    "needs-info",
    "ready-for-human",
    "abandoned",
    "superseded",
}
RECOVERY_OUTCOMES = SOLVE_RECORD_OUTCOMES - {"candidate"}
COMMON_RECORD_FIELDS = {"id", "kind", "state", "issues", "created_at", "cleanup_done"}
CANDIDATE_RECORD_FIELDS = {"base", "base_sha", "head", "head_sha", "worktree"}
RECOVERY_SECTIONS = {
    "Ticket",
    "Outcome",
    "Attempt Summary",
    "Confirmed Findings",
    "Blocker Or Requested Information",
    "Resume Or Cleanup",
    "Resources",
}
NEW_CANDIDATE_SECTIONS = {
    "Ticket",
    "Outcome",
    "What Changed",
    "Verification",
    "Review",
    "Merge",
    "Resources",
}
NEW_RECEIPT_ONLY_SECTIONS = {"Ticket", "Outcome", "What Changed", "Verification"}
DEFAULT_VISIBLE_ITEMS = 5
DEFAULT_HTML_PATH = Path(".scratch/maintainer-board/index.html")


def run_git(cwd, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git failed")
    return result


def repo_root(path):
    path = Path(path).resolve()
    result = run_git(path, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        raise RuntimeError(f"not a Git repo: {path}")
    return Path(result.stdout.strip()).resolve()


def find_solve_records_helper():
    for parent in Path(__file__).resolve().parents:
        helper_path = parent / "skills/engineering/solve-records/scripts/solve-records.py"
        if helper_path.is_file():
            return helper_path
    return None


def find_local_publication_helper():
    for parent in Path(__file__).resolve().parents:
        helper_path = parent / "skills/engineering/ultra/scripts/local_ticket_publication.py"
        if helper_path.is_file():
            return helper_path
    return None


def load_local_publication_helper():
    helper_path = find_local_publication_helper()
    if not helper_path:
        return None
    if str(helper_path.parent) not in sys.path:
        sys.path.insert(0, str(helper_path.parent))
    spec = importlib.util.spec_from_file_location("local_ticket_publication_helper", helper_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalize_key(key):
    key = key.strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", key)
    return key.strip("_")


def parse_scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in inner.split(",")]
    return value


def parse_yaml_like(lines):
    data = {}
    current_key = None
    for line in lines:
        if not line.strip():
            continue
        if line.startswith((" ", "\t")) and current_key and line.strip().startswith("- "):
            existing = data.get(current_key)
            if not isinstance(existing, list):
                existing = [] if existing in (None, "") else [existing]
            existing.append(parse_scalar(line.strip()[2:]))
            data[current_key] = existing
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = normalize_key(key)
        value = value.strip()
        data[current_key] = [] if value == "" else parse_scalar(value)
    return data


def parse_header_metadata(lines):
    header = []
    for line in lines:
        if not line.strip() or line.startswith("#"):
            break
        if ":" not in line:
            break
        header.append(line)
    return parse_yaml_like(header)


def split_frontmatter(text):
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        return None, text
    metadata = parse_yaml_like(text[4:end].splitlines())
    body = text[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    return metadata, body


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


def discover_issue_paths(repo):
    paths = set(repo.glob(".scratch/*/issues/*.md"))
    paths.update(repo.glob(".scratch/*/issue.md"))
    return sorted(paths)


def local_ticket_contract(repo):
    path = repo / "docs/agents/ultra-tracker.md"
    if not path.is_file():
        return None
    fields = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[normalize_key(key)] = value.strip().strip("`")
    if fields.get("publication_strategy") != "local-review-pending":
        return None
    representation = fields.get("local_ticket_representation")
    location = fields.get("local_ticket_path")
    if representation not in {"file-per-ticket", "tickets-file"} or not location:
        raise RuntimeError("Local Markdown publication contract lacks a safe representation or path")
    return {"representation": representation, "location": location}


def feature_from_path(repo, path):
    rel_parts = path.relative_to(repo).parts
    if len(rel_parts) >= 2 and rel_parts[0] == ".scratch":
        return rel_parts[1]
    return ""


def parse_issue_text(repo, path, text, identity="", metadata_format_hint=""):
    frontmatter, body = split_frontmatter(text)
    metadata = frontmatter if frontmatter is not None else parse_header_metadata(text.splitlines())

    rel = str(path.relative_to(repo)) + (f"#{identity}" if identity else "")
    parent = as_list(metadata.get("parent"))
    if not parent:
        parent = paths_from_lines(
            heading_block(body, lambda level, title: level == 2 and title.lower() == "parent")
        )

    blockers = as_list(metadata.get("blocked_by") or metadata.get("blockers"))
    blockers.extend(
        paths_from_lines(
            heading_block(body, lambda level, title: level == 2 and title.lower() == "blocked by")
        )
    )

    solve_records = as_list(metadata.get("solve_record") or metadata.get("solve_records"))
    solve_records.extend(
        paths_from_lines(
            heading_block(body, lambda _level, title: title.lower() in {"solve record", "solve records"})
        )
    )

    flags = as_list(metadata.get("flags") or metadata.get("labels"), split_words=True)
    status = str(metadata.get("status") or metadata.get("state") or "").strip()
    issue = {
        "path": rel,
        "feature": feature_from_path(repo, path),
        "title": first_heading(body) or first_heading(text) or path.stem,
        "status": status,
        "ticket_id": str(metadata.get("ticket_id") or metadata.get("id") or identity).strip(),
        "publication_run": str(metadata.get("publication_run", "")).strip(),
        "publication_promoted": False,
        "category": str(metadata.get("category", "")).strip(),
        "flags": flags,
        "created": str(metadata.get("created", "")).strip(),
        "solve_branch": str(metadata.get("solve_branch", "")).strip(),
        "solve_worktree": str(metadata.get("solve_worktree", "")).strip(),
        "parent": parent[0] if parent else "",
        "blocked_by": sorted(dict.fromkeys(blockers)),
        "solve_records": sorted(dict.fromkeys(solve_records)),
        "checklist": checklist_counts(body),
        "metadata_format": metadata_format_hint or ("frontmatter" if frontmatter is not None else "header"),
        "source_path": str(path.relative_to(repo)),
        "warnings": [],
    }
    issue["bucket"] = classify_issue(issue)
    return issue


def parse_issue(repo, path):
    return parse_issue_text(repo, path, path.read_text(encoding="utf-8"))


def discover_issues(repo):
    contract = local_ticket_contract(repo)
    paths = set(discover_issue_paths(repo))
    if contract and contract["representation"] == "file-per-ticket":
        pattern = re.sub(r"<[^>]+>", "*", contract["location"])
        pattern_path = Path(pattern)
        if pattern_path.is_absolute() or ".." in pattern_path.parts:
            raise RuntimeError("configured Local Ticket path escapes the repository")
        paths.update(path for path in repo.glob(pattern) if path.is_file())
    issues = [parse_issue(repo, path) for path in sorted(paths)]
    if not contract or contract["representation"] != "tickets-file":
        return issues, contract
    helper = load_local_publication_helper()
    if helper is None:
        raise RuntimeError("Maintainer Board requires the Local Markdown publication adapter for tickets-file discovery")
    pattern = re.sub(r"<[^>]+>", "*", contract["location"])
    for path in sorted(repo.glob(pattern)):
        try:
            tickets = helper.load_tickets_file(path.resolve())
        except helper.AdapterError as error:
            raise RuntimeError(f"unsafe configured tickets-file {path.relative_to(repo)}: {error}") from error
        for ticket in tickets:
            issues.append(
                parse_issue_text(
                    repo,
                    path,
                    ticket.inner,
                    identity=ticket.ticket_id,
                    metadata_format_hint="tickets-file-section",
                )
            )
    return issues, contract


def apply_publication_gates(repo, issues, contract):
    helper = load_local_publication_helper()
    for issue in issues:
        run_id = issue.get("publication_run")
        if not run_id:
            continue
        if helper is None:
            issue["warnings"].append(
                {"code": "publication_adapter_missing", "message": "run-tagged Ticket cannot be verified"}
            )
            continue
        representation = "tickets-file" if issue["metadata_format"] == "tickets-file-section" else "file-per-ticket"
        source = repo / issue["source_path"]
        location = source if representation == "tickets-file" else source.parent
        try:
            _location, tickets, journal = helper.validate_against_journal(
                repo, representation, str(location.relative_to(repo)), run_id
            )
            selected = helper.run_tickets(tickets, run_id)
            promoted = journal.get("phase") == "promoted" and all(
                ticket.status
                in {"ready-for-agent", "completed", "ready-for-human", "needs-info"}
                for ticket in selected
            )
            issue["publication_promoted"] = promoted
            if not promoted:
                issue["warnings"].append(
                    {"code": "publication_not_promoted", "message": "publication run is provisional or incomplete"}
                )
        except (helper.AdapterError, OSError) as error:
            issue["warnings"].append(
                {"code": "publication_invalid", "message": str(error)}
            )


def classify_issue(issue):
    flags = set(issue["flags"])
    status = issue["status"]
    if status == "review-pending" or (
        issue.get("publication_run") and not issue.get("publication_promoted")
    ):
        return "other"
    if "solve-in-progress" in flags:
        return "claimed_or_in_progress"
    if status in {"ready-for-human", "needs-info"}:
        return "needs_human"
    if status == "completed":
        if issue["solve_records"]:
            return "completed_with_solve_record"
        return "completed_without_solve_record"
    if issue["blocked_by"]:
        return "blocked_or_dependent"
    if status == "ready-for-agent":
        return "ready_for_agent"
    return "other"


def ref_map(repo):
    refs = {}
    result = run_git(
        repo,
        "for-each-ref",
        "--format=%(refname)%00%(refname:short)%00%(objectname)",
        "refs/heads",
        "refs/remotes",
        "refs/tags",
        check=False,
    )
    if result.returncode != 0:
        return refs
    for line in result.stdout.splitlines():
        parts = line.split("\0")
        if len(parts) != 3:
            continue
        full_name, short_name, sha = parts
        refs[full_name] = sha
        refs[short_name] = sha
        if full_name.startswith("refs/heads/"):
            refs[full_name[len("refs/heads/") :]] = sha
        elif full_name.startswith("refs/remotes/"):
            refs[full_name[len("refs/remotes/") :]] = sha
        elif full_name.startswith("refs/tags/"):
            refs[full_name[len("refs/tags/") :]] = sha
    return refs


def registered_worktrees(repo):
    result = run_git(repo, "worktree", "list", "--porcelain", check=False)
    worktrees = {}
    if result.returncode != 0:
        return worktrees
    current = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current = Path(line.split(" ", 1)[1]).resolve()
            worktrees[str(current)] = {"path": str(current), "branch": ""}
        elif current and line.startswith("branch "):
            branch = line.split(" ", 1)[1]
            if branch.startswith("refs/heads/"):
                branch = branch[len("refs/heads/") :]
            worktrees[str(current)]["branch"] = branch
    return worktrees


def resolve_worktree(repo, raw_path):
    path = Path(raw_path)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def add_issue_git_warnings(repo, issues):
    refs = ref_map(repo)
    worktrees = registered_worktrees(repo)
    all_warnings = []

    for issue in issues:
        active = issue["bucket"] == "claimed_or_in_progress" or issue["status"] != "completed"
        if not active:
            continue

        warning_start = len(issue["warnings"])
        branch = issue.get("solve_branch")
        if branch and branch not in refs:
            warning = {
                "code": "missing_solve_branch",
                "message": f"solve branch not found: {branch}",
            }
            issue["warnings"].append(warning)

        raw_worktree = issue.get("solve_worktree")
        if raw_worktree:
            worktree = resolve_worktree(repo, raw_worktree)
            registered = worktrees.get(str(worktree))
            if not worktree.exists():
                warning = {
                    "code": "missing_solve_worktree",
                    "message": f"solve worktree not found: {raw_worktree}",
                }
                issue["warnings"].append(warning)
            elif not registered:
                warning = {
                    "code": "unregistered_solve_worktree",
                    "message": f"solve worktree is not registered: {raw_worktree}",
                }
                issue["warnings"].append(warning)
            elif branch and registered.get("branch") and registered["branch"] != branch:
                warning = {
                    "code": "worktree_branch_mismatch",
                    "message": f"worktree branch is {registered['branch']}, expected {branch}",
                }
                issue["warnings"].append(warning)

        for warning in issue["warnings"][warning_start:]:
            all_warnings.append({"path": issue["path"], **warning})

    return all_warnings


def bucket_items(items, buckets):
    result = {bucket: [] for bucket in buckets}
    for item in items:
        result.setdefault(item["bucket"], []).append(item)
    return result


def record_section(text, name):
    marker = f"## {name}\n"
    start = text.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    end = text.find("\n## ", start)
    return text[start:] if end == -1 else text[start:end]


def record_labeled_value(block, label):
    prefix = f"{label.lower()}:"
    for line in block.splitlines():
        normalized = line.strip().lstrip("-* ").strip()
        if normalized.lower().startswith(prefix):
            return normalized.split(":", 1)[1].strip()
    return ""


def record_status(block):
    for line in block.splitlines():
        if line.startswith("Status:"):
            return line.split(":", 1)[1].strip()
    return ""


def record_review_status(block):
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("post-execution review:"):
            return stripped.split(":", 1)[1].strip().lower()
    return ""


def record_missing(record, fields):
    return sorted(field for field in fields if not record.get(field))


def record_has_section(text, name):
    return any(line.strip() == f"## {name}" for line in text.splitlines())


def fallback_body_error(record):
    text = record["text"]
    ticket = record_section(text, "Ticket")
    outcome = record_section(text, "Outcome")
    if not record_has_section(text, "Ticket") or not record_labeled_value(ticket, "Linked Ticket"):
        return "missing linked Ticket"
    if not record_has_section(text, "Outcome"):
        return "missing Outcome section"
    result = record_labeled_value(outcome, "Result").lower()
    if not result:
        return "missing outcome result"
    if result != record["outcome"]:
        return "body/frontmatter outcome conflict"
    if not record_labeled_value(outcome, "Branch/worktree/commit/PR"):
        return "missing retained resource disposition"
    if not record_labeled_value(outcome, "Resource ownership"):
        return "missing resource ownership"
    sections = NEW_CANDIDATE_SECTIONS if result == "candidate" else RECOVERY_SECTIONS
    missing = sorted(section for section in sections if not record_has_section(text, section))
    if missing:
        return "missing sections: " + ",".join(missing)
    if not record_labeled_value(record_section(text, "Resources"), "Cleanup"):
        return "missing resource cleanup disposition"
    if result == "candidate" and record_review_status(record_section(text, "Review")) != "passed":
        return "candidate requires passed Post-Execution Review"
    if result != "candidate" and not record_labeled_value(
        record_section(text, "Resume Or Cleanup"), "Next action"
    ):
        return "missing recovery next action"
    return ""


def fallback_parse_record(repo, path):
    text = path.read_text(encoding="utf-8")
    record = {"path": str(path.relative_to(repo)), "text": text}
    if not text.startswith("---\n"):
        record["malformed"] = "missing frontmatter"
        return record
    end = text.find("\n---", 4)
    if end == -1:
        record["malformed"] = "unclosed frontmatter"
        return record
    current = None
    for line in text[4:end].splitlines():
        if line.startswith("  - ") and current:
            record.setdefault(current, []).append(line[4:].strip())
            continue
        if ":" not in line:
            record["malformed"] = f"invalid frontmatter line: {line}"
            return record
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current = key
        record[key] = [] if key == "issues" and not value else value
    if "issues" in record and not isinstance(record["issues"], list):
        record["issues"] = [record["issues"]] if record["issues"] else []
    missing = record_missing(record, COMMON_RECORD_FIELDS)
    if missing:
        record["malformed"] = "missing " + ",".join(missing)
        return record
    if record.get("kind") != "solve_record":
        record["malformed"] = f"invalid kind: {record.get('kind')}"
        return record
    outcome = str(record.get("outcome", "")).lower()
    if "outcome" not in record:
        missing = record_missing(record, COMMON_RECORD_FIELDS | CANDIDATE_RECORD_FIELDS)
        recovery_only = RECOVERY_SECTIONS - {"Ticket", "Outcome", "Resources"}
        if missing:
            record["malformed"] = "missing outcome and legacy candidate fields: " + ",".join(missing)
            return record
        if any(record_has_section(text, name) for name in NEW_RECEIPT_ONLY_SECTIONS | recovery_only):
            record["malformed"] = "missing outcome for new or recovery-shaped receipt"
            return record
        record["outcome"] = "candidate"
        record["legacy_outcome"] = True
    elif not outcome:
        record["malformed"] = "missing outcome"
        return record
    elif outcome not in SOLVE_RECORD_OUTCOMES:
        record["malformed"] = f"invalid outcome: {outcome}"
        return record
    else:
        record["outcome"] = outcome
        if outcome == "candidate":
            missing = record_missing(record, CANDIDATE_RECORD_FIELDS)
            if missing:
                record["malformed"] = "missing candidate fields: " + ",".join(missing)
                return record
        body_error = fallback_body_error(record)
        if body_error:
            record["malformed"] = body_error
            return record
    ticket = record_section(text, "Ticket")
    outcome_block = record_section(text, "Outcome")
    record.update(
        {
            "linked_ticket": record_labeled_value(ticket, "Linked Ticket"),
            "source_spec": record_labeled_value(ticket, "Source Spec") or record.get("source_spec", ""),
            "resource_ownership": record_labeled_value(outcome_block, "Resource ownership"),
            "retained_resources": record_labeled_value(outcome_block, "Branch/worktree/commit/PR"),
            "checks": record_status(record_section(text, "Verification"))
            or record_status(record_section(text, "Checks")),
            "review": record_review_status(record_section(text, "Review")),
            "merge": record_status(record_section(text, "Merge")),
            "summary_status": record_status(record_section(text, "Summary")),
            "notes": record_section(text, "Notes").lower(),
            "title": first_heading(text),
            "blocker_or_requested_information": record_section(
                text, "Blocker Or Requested Information"
            ).strip(),
            "recovery_action": record_labeled_value(
                record_section(text, "Resume Or Cleanup"), "Next action"
            ),
        }
    )
    return record


def fallback_ref_check(repo, record):
    refs = ref_map(repo)
    for ref_key, sha_key in (("base", "base_sha"), ("head", "head_sha")):
        ref = record.get(ref_key, "")
        expected = str(record.get(sha_key, ""))
        actual = refs.get(ref)
        if not actual:
            result = run_git(repo, "rev-parse", "--verify", ref, check=False)
            actual = result.stdout.strip() if result.returncode == 0 else ""
        if not actual:
            return False, f"{ref} missing"
        if not expected or not (actual == expected or actual.startswith(expected)):
            return False, f"{ref_key} sha mismatch"
    return True, ""


def record_resource_field(record, label):
    value = record_labeled_value(record_section(record.get("text", ""), "Resources"), label)
    if len(value) >= 2 and value[0] == value[-1] == "`":
        return value[1:-1]
    return value


def fallback_rollout_disposition(record):
    block = (record_section(record.get("text", ""), "Merge") + "\n" + record_section(record.get("text", ""), "Notes")).lower()
    for line in block.splitlines():
        normalized = line.strip().lstrip("-*").strip()
        for prefix in ("rollout/config disposition:", "rollout config disposition:", "rollout disposition:", "config disposition:"):
            if prefix in normalized:
                value = normalized.split(prefix, 1)[1].strip()
                for disposition in ("none", "pre-merge action required", "post-merge activation required"):
                    if value == disposition or value.startswith((disposition + ";", disposition + ".", disposition + ",")):
                        return disposition
                return "unknown"
    return ""


def fallback_low_risk_exception(record):
    notes = record.get("notes", "")
    return all(
        fragment in notes
        for fragment in (
            "low-risk",
            "no meaningful automated check exists",
            "no manual-review trigger",
            "evidence:",
        )
    )


def fallback_rollout_gate_reason(record):
    disposition = fallback_rollout_disposition(record)
    if not disposition:
        return "missing rollout/config disposition"
    if disposition == "unknown":
        return "unknown rollout/config disposition"
    if disposition == "pre-merge action required":
        return "rollout/config pre-merge action required"
    if disposition == "post-merge activation required":
        block = (
            record_section(record.get("text", ""), "Merge")
            + "\n"
            + record_section(record.get("text", ""), "Notes")
        ).lower()
        requirements = (
            (("code merge is safe", "code merge safe"), "code-merge-safety rationale"),
            (("activation:",), "activation action"),
            (("rollback:", "disable:"), "rollback or disable note"),
        )
        for fragments, label in requirements:
            if not any(fragment in block for fragment in fragments):
                return f"post-merge activation missing {label}"
        if "smoke:" not in block and "validation:" not in block:
            return "post-merge activation missing smoke or validation check"
    return ""


def fallback_merge_gate(repo, record):
    reasons = []
    refs_ok, ref_reason = fallback_ref_check(repo, record)
    if not refs_ok:
        reasons.append(ref_reason)
    if record.get("state") != "open":
        reasons.append(f"state is {record.get('state')}")
    if record.get("merge") != "ready":
        reasons.append(f"merge status is {record.get('merge') or '<missing>'}")
    if record.get("external_provider") or record.get("external_url"):
        reasons.append("remote-primary record")
    if record.get("checks") == "unavailable":
        if not fallback_low_risk_exception(record):
            reasons.append("unavailable checks without low-risk evidence")
    elif record.get("checks") != "passed":
        reasons.append(f"checks status is {record.get('checks') or '<missing>'}")
    if record.get("merge") == "ready" and record.get("review") != "passed":
        review = record.get("review") or "<missing>"
        reasons.append(f"Post-Execution Review is {review}")
    rollout_reason = fallback_rollout_gate_reason(record)
    if record.get("merge") == "ready" and rollout_reason:
        reasons.append(rollout_reason)
    if not reasons:
        worktree = resolve_worktree(repo, record.get("worktree", ""))
        status = run_git(worktree, "status", "--short", "--untracked-files=all", check=False)
        if status.returncode != 0:
            reasons.append("worktree missing")
        elif status.stdout.strip():
            reasons.append("worktree dirty")
    return {"id": record.get("id"), "path": record.get("path"), "eligible": not reasons, "reasons": reasons}


def fallback_record_summary(repo, record):
    summary = {
        key: record.get(key)
        for key in (
            "path", "id", "title", "state", "outcome", "created_at", "merged_at",
            "merged_sha", "base", "head", "issues", "linked_ticket", "source_spec",
            "worktree", "checks", "review", "merge", "cleanup_done", "resource_ownership",
            "retained_resources", "blocker_or_requested_information", "recovery_action",
            "external_provider", "external_url",
        )
    }
    summary["issues"] = record.get("issues", [])
    summary["legacy_outcome"] = bool(record.get("legacy_outcome"))
    summary["resource_cleanup"] = record_resource_field(record, "Cleanup")
    if record.get("malformed"):
        summary["malformed"] = record["malformed"]
    elif record.get("outcome") == "candidate":
        refs_ok, ref_reason = fallback_ref_check(repo, record)
        summary.update(
            refs_ok=refs_ok,
            ref_reason=ref_reason,
            low_risk_exception=fallback_low_risk_exception(record),
            rollout_config_disposition=fallback_rollout_disposition(record),
        )
        if record.get("summary_status") and record.get("summary_status") != record.get("state"):
            summary["body_conflict"] = "body/frontmatter status conflict"
    else:
        summary["recovery_view"] = "resume" if record.get("outcome") in {
            "blocked", "needs-info", "ready-for-human"
        } else "closed"
    return summary


def fallback_solve_records_dashboard(repo):
    paths = sorted(repo.glob(".scratch/solve-records/*.md"))
    paths += sorted(repo.glob(".scratch/*/solve-records/*.md"))
    records = [fallback_parse_record(repo, path) for path in paths]
    buckets = {bucket: [] for bucket in SOLVE_RECORD_BUCKETS}
    recent = []
    for record in records:
        summary = fallback_record_summary(repo, record)
        if record.get("malformed"):
            buckets["stale_or_malformed"].append(summary)
        elif record.get("outcome") in RECOVERY_OUTCOMES:
            buckets["recovery"].append(summary)
        elif summary.get("body_conflict"):
            summary["stale_reason"] = summary["body_conflict"]
            buckets["stale_or_malformed"].append(summary)
        else:
            refs_ok, ref_reason = fallback_ref_check(repo, record)
            if not refs_ok and record.get("state") == "open":
                summary["stale_reason"] = ref_reason
                buckets["stale_or_malformed"].append(summary)
            elif record.get("state") in {"merged", "closed"} and str(record.get("cleanup_done")).lower() != "true":
                buckets["cleanup"].append(summary)
            elif record.get("state") == "merged":
                recent.append(summary)
            else:
                gate = fallback_merge_gate(repo, record)
                summary["merge_gate"] = gate
                buckets["ready" if gate["eligible"] else "manual"].append(summary)
    buckets["recent"] = sorted(
        recent,
        key=lambda item: (item.get("merged_at") or item.get("created_at") or "", item.get("id") or ""),
        reverse=True,
    )[:10]
    return {"repo": str(repo), "record_count": len(records), "buckets": buckets}


def load_solve_records_dashboard(repo):
    helper_path = find_solve_records_helper()
    if not helper_path:
        return fallback_solve_records_dashboard(repo)
    spec = importlib.util.spec_from_file_location("solve_records_helper", helper_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = module.discover(repo)
    return module.dashboard(repo, records)


def build_snapshot(repo):
    issues, contract = discover_issues(repo)
    apply_publication_gates(repo, issues, contract)
    for issue in issues:
        issue["bucket"] = classify_issue(issue)
    issue_warnings = add_issue_git_warnings(repo, issues)
    issue_buckets = bucket_items(issues, ISSUE_BUCKETS)
    solve_records = load_solve_records_dashboard(repo)
    solve_buckets = solve_records.get("buckets", {})
    solve_count = solve_records.get("record_count", sum(len(solve_buckets.get(bucket, [])) for bucket in solve_buckets))

    return {
        "schema_version": "maintainer-board/v1",
        "repo": str(repo),
        "issues": {
            "count": len(issues),
            "buckets": issue_buckets,
            "counts": {bucket: len(issue_buckets.get(bucket, [])) for bucket in ISSUE_BUCKETS},
            "warnings": issue_warnings,
        },
        "solve_records": {
            "count": solve_count,
            "buckets": {bucket: solve_buckets.get(bucket, []) for bucket in SOLVE_RECORD_BUCKETS},
            "counts": {bucket: len(solve_buckets.get(bucket, [])) for bucket in SOLVE_RECORD_BUCKETS},
        },
    }


def render_pill(value, css_class=""):
    if not value:
        return ""
    class_names = ["pill"]
    if css_class:
        class_names.append(css_class)
    class_names.append(f"label-{slugify(value)}")
    class_attr = " ".join(class_names)
    return f"<span class='{class_attr}'>{html.escape(str(value))}</span>"


def slugify(value):
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "unknown"


def render_pills(values):
    return "".join(render_pill(value) for value in values if value)


def render_detail_rows(rows):
    rendered = []
    for label, value in rows:
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value)
        escaped = html.escape(str(value)).replace("\n", "<br>")
        rendered.append(f"<dt>{html.escape(label)}</dt><dd>{escaped}</dd>")
    if not rendered:
        return ""
    return f"<dl class='details-grid'>{''.join(rendered)}</dl>"


def render_warning_list(warnings):
    if not warnings:
        return ""
    items = "".join(
        f"<li><span class='warn-code'>{html.escape(warning['code'])}</span> {html.escape(warning['message'])}</li>"
        for warning in warnings
    )
    return f"<ul class='warnings'>{items}</ul>"


def record_cleanup_label(record):
    resource_cleanup = record.get("resource_cleanup") or ""
    if resource_cleanup and resource_cleanup != "pending":
        return resource_cleanup
    if str(record.get("cleanup_done")).lower() == "true":
        return "cleanup done"
    return "cleanup pending"


def record_cleanup_ownership(record):
    cleanup = record_cleanup_label(record).lower()
    if "user-owned" in cleanup or "adopted" in cleanup:
        return "user-owned adopted resources"
    if str(record.get("cleanup_done")).lower() == "true":
        return "no solve-owned cleanup pending"
    return "solve-owned cleanup pending"


def render_issue_card(issue, hidden=False):
    search = " ".join(
        str(value)
        for value in [
            issue["title"],
            issue["path"],
            issue["status"],
            issue["category"],
            issue["feature"],
            " ".join(issue["flags"]),
        ]
    )
    checklist = issue["checklist"]
    checklist_text = f"{checklist['done']}/{checklist['total']} checklist" if checklist["total"] else "no checklist"
    warning_text = f"{len(issue['warnings'])} warning" if len(issue["warnings"]) == 1 else f"{len(issue['warnings'])} warnings"
    top_pills = [
        issue["status"],
        issue["category"],
        issue["feature"],
        checklist_text,
        warning_text if issue["warnings"] else "",
        *issue["flags"],
    ]
    detail_rows = [
        ("Path", issue["path"]),
        ("Status", issue["status"]),
        ("Category", issue["category"]),
        ("Feature", issue["feature"]),
        ("Created", issue["created"]),
        ("Metadata format", issue["metadata_format"]),
        ("Parent", issue["parent"]),
        ("Blocked by", issue["blocked_by"]),
        ("Solve branch", issue["solve_branch"]),
        ("Solve worktree", issue["solve_worktree"]),
        ("Solve records", issue["solve_records"]),
        ("Checklist", checklist_text),
    ]
    hidden_attr = " data-overflow='true' hidden" if hidden else ""
    return f"""
<article class="card issue-card" data-search="{html.escape(search.lower())}"{hidden_attr}>
  <h3>{html.escape(issue['title'])}</h3>
  <div class="path">{html.escape(issue['path'])}</div>
  <div class="pills">{render_pills(top_pills)}</div>
  <details class="card-details">
    <summary>Details</summary>
    {render_detail_rows(detail_rows)}
    {render_warning_list(issue['warnings'])}
  </details>
</article>
"""


def render_record_card(record, hidden=False):
    search = " ".join(
        str(value)
        for value in [
            record.get("title", ""),
            record.get("id", ""),
            record.get("path", ""),
            record.get("state", ""),
            record.get("outcome", ""),
            record.get("head", ""),
            record.get("base", ""),
            record.get("resource_cleanup", ""),
            record.get("linked_ticket", ""),
            record.get("blocker_or_requested_information", ""),
            record.get("retained_resources", ""),
            record.get("resource_ownership", ""),
            record.get("recovery_action", ""),
        ]
    )
    cleanup = record_cleanup_label(record)
    cleanup_ownership = record_cleanup_ownership(record)
    top_pills = [
        record.get("state"),
        record.get("outcome"),
        record.get("checks"),
        record.get("merge"),
        cleanup,
    ]
    detail_rows = [
        ("Path", record.get("path")),
        ("ID", record.get("id")),
        ("State", record.get("state")),
        ("Outcome", record.get("outcome")),
        ("Linked Ticket", record.get("linked_ticket") or record.get("issues", [])),
        ("Blocker or requested information", record.get("blocker_or_requested_information")),
        ("Retained resources", record.get("retained_resources")),
        ("Resource owner", record.get("resource_ownership")),
        ("Next resume or cleanup action", record.get("recovery_action")),
        ("Checks", record.get("checks")),
        ("Merge", record.get("merge")),
        ("Cleanup", cleanup),
        ("Cleanup ownership", cleanup_ownership),
        ("Landing branch (base)", record.get("base")),
        ("Candidate branch (head)", record.get("head")),
        ("Worktree", record.get("worktree")),
        ("Issues", record.get("issues", [])),
        ("Stale reason", record.get("stale_reason")),
        ("Malformed", record.get("malformed")),
        ("Refs", record.get("ref_reason")),
    ]
    hidden_attr = " data-overflow='true' hidden" if hidden else ""
    return f"""
<article class="card record-card" data-search="{html.escape(search.lower())}"{hidden_attr}>
  <h3>{html.escape(record.get('title') or record.get('id') or record.get('path') or 'solve record')}</h3>
  <div class="path">{html.escape(record.get('path', ''))}</div>
  <div class="pills">{render_pills(top_pills)}</div>
  <details class="card-details">
    <summary>Details</summary>
    {render_detail_rows(detail_rows)}
  </details>
</article>
"""


def render_bucket(title, items, renderer):
    cards = "".join(
        renderer(item, hidden=index >= DEFAULT_VISIBLE_ITEMS)
        for index, item in enumerate(items)
    )
    empty = "<p class='empty'>none</p>" if not items else ""
    hidden_count = max(0, len(items) - DEFAULT_VISIBLE_ITEMS)
    show_more = (
        f"<button class='show-more' type='button' data-hidden-count='{hidden_count}'>Show {hidden_count} more</button>"
        if hidden_count
        else ""
    )
    return f"""
<section class="bucket" data-expanded="false">
  <header><h2>{html.escape(title)}</h2><span>{len(items)}</span></header>
  <div class="cards">{cards}{empty}</div>
  {show_more}
</section>
"""


def titleize_bucket(bucket):
    return bucket.replace("_", " ").title()


def render_html(snapshot):
    issue_counts = snapshot["issues"]["counts"]
    record_counts = snapshot["solve_records"]["counts"]
    issue_summary = "".join(
        f"<div><strong>{count}</strong><span>{html.escape(titleize_bucket(bucket))}</span></div>"
        for bucket, count in issue_counts.items()
    )
    record_summary = "".join(
        f"<div><strong>{count}</strong><span>{html.escape(titleize_bucket(bucket))}</span></div>"
        for bucket, count in record_counts.items()
    )
    issue_sections = "".join(
        render_bucket(titleize_bucket(bucket), snapshot["issues"]["buckets"].get(bucket, []), render_issue_card)
        for bucket in ISSUE_BUCKETS
    )
    record_sections = "".join(
        render_bucket(titleize_bucket(bucket), snapshot["solve_records"]["buckets"].get(bucket, []), render_record_card)
        for bucket in SOLVE_RECORD_BUCKETS
    )
    repo = html.escape(snapshot["repo"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Maintainer Board</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d8dde5;
      --text: #1d2430;
      --muted: #5e6a7d;
      --green: #1f7a4d;
      --amber: #946200;
      --red: #b42318;
      --blue: #2459a6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 13px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }}
    main {{ padding: 20px; max-width: 1680px; margin: 0 auto; }}
    .topbar {{
      display: flex;
      gap: 16px;
      align-items: flex-end;
      justify-content: space-between;
      margin-bottom: 16px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 24px; font-weight: 720; }}
    .repo {{ color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }}
    input {{
      width: min(460px, 100%);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 11px;
      font: inherit;
      background: var(--panel);
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
      gap: 8px;
      margin: 12px 0 20px;
    }}
    .summary div {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      min-width: 0;
    }}
    .summary strong {{ display: block; font-size: 20px; }}
    .summary span {{ color: var(--muted); font-size: 12px; }}
    .section-title {{
      margin: 22px 0 10px;
      font-size: 17px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 6px;
    }}
    .lane-scroll {{
      overflow-x: auto;
      padding-bottom: 8px;
      scrollbar-gutter: stable;
    }}
    .grid {{
      display: grid;
      grid-auto-flow: column;
      grid-auto-columns: minmax(330px, 380px);
      grid-template-rows: 1fr;
      gap: 12px;
      align-items: start;
      width: max-content;
      min-width: 100%;
    }}
    .bucket {{
      background: #eef1f5;
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
    }}
    .bucket header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
    }}
    .bucket h2 {{ margin: 0; font-size: 13px; }}
    .bucket header span {{
      min-width: 24px;
      text-align: center;
      border-radius: 999px;
      background: var(--panel);
      border: 1px solid var(--line);
      color: var(--muted);
      padding: 1px 7px;
    }}
    .cards {{ display: grid; gap: 8px; padding: 8px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 4px solid var(--blue);
      border-radius: 6px;
      padding: 9px;
      min-width: 0;
    }}
    .record-card {{ border-left-color: var(--green); }}
    .card h3 {{ margin: 0 0 4px; font-size: 13px; line-height: 1.3; }}
    .path {{
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      overflow-wrap: anywhere;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 7px;
      color: var(--muted);
      background: #fbfcfd;
      font-size: 11px;
      font-weight: 620;
    }}
    .label-ready-for-agent,
    .label-ready,
    .label-passed,
    .label-completed,
    .label-cleanup-done {{
      color: #116329;
      background: #dafbe1;
      border-color: #aceebb;
    }}
    .label-solve-in-progress,
    .label-open,
    .label-feature {{
      color: #0969da;
      background: #ddf4ff;
      border-color: #b6e3ff;
    }}
    .label-ready-for-human,
    .label-needs-info,
    .label-manual-required,
    .label-unavailable,
    .label-cleanup-pending,
    .label-documentation {{
      color: #9a6700;
      background: #fff8c5;
      border-color: #f0d98c;
    }}
    .label-stale,
    .label-stale-or-malformed,
    .label-bug {{
      color: #cf222e;
      background: #ffebe9;
      border-color: #ffcecb;
    }}
    .label-merged,
    .label-auto-merged {{
      color: #8250df;
      background: #fbefff;
      border-color: #eac4ff;
    }}
    .pills {{ display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 5px; }}
    .card-details {{
      margin-top: 7px;
      border-top: 1px solid var(--line);
      padding-top: 6px;
    }}
    .card-details summary {{
      cursor: pointer;
      color: var(--blue);
      font-size: 12px;
      font-weight: 650;
    }}
    .details-grid {{
      display: grid;
      grid-template-columns: minmax(86px, max-content) minmax(0, 1fr);
      gap: 5px 10px;
      margin: 7px 0 0;
    }}
    .details-grid dt {{
      color: var(--muted);
      font-size: 11px;
    }}
    .details-grid dd {{
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
    }}
    .warnings {{
      margin: 7px 0 0;
      padding-left: 18px;
      color: var(--red);
    }}
    .warn-code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .show-more {{
      width: calc(100% - 16px);
      margin: 0 8px 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--blue);
      cursor: pointer;
      font: inherit;
      font-size: 12px;
      padding: 6px 8px;
    }}
    .empty {{ margin: 0; color: var(--muted); padding: 6px 2px; }}
  </style>
</head>
<body>
<main>
  <div class="topbar">
    <div>
      <h1>Maintainer Board</h1>
      <div class="repo">{repo}</div>
    </div>
    <input id="search" type="search" placeholder="Filter cards by title, path, status, branch...">
  </div>
  <h2 class="section-title">Issue Summary</h2>
  <div class="summary">{issue_summary}</div>
  <h2 class="section-title">Solve Record Summary</h2>
  <div class="summary">{record_summary}</div>
  <h2 class="section-title">Issues</h2>
  <div class="lane-scroll"><div class="grid">{issue_sections}</div></div>
  <h2 class="section-title">Solve Records</h2>
  <div class="lane-scroll"><div class="grid">{record_sections}</div></div>
</main>
<script>
  const search = document.getElementById('search');
  const cards = [...document.querySelectorAll('.card')];
  const buttons = [...document.querySelectorAll('.show-more')];
  function applyLimit() {{
    const query = search.value.trim().toLowerCase();
    for (const button of buttons) {{
      button.hidden = Boolean(query);
    }}
    for (const card of cards) {{
      const matches = !query || card.dataset.search.includes(query);
      if (query) {{
        card.hidden = !matches;
        continue;
      }}
      const bucket = card.closest('.bucket');
      const limited = card.dataset.overflow === 'true' && bucket.dataset.expanded !== 'true';
      card.hidden = limited;
    }}
  }}
  for (const button of buttons) {{
    const hiddenCount = button.dataset.hiddenCount;
    button.addEventListener('click', () => {{
      const bucket = button.closest('.bucket');
      const expanded = bucket.dataset.expanded === 'true';
      bucket.dataset.expanded = expanded ? 'false' : 'true';
      button.textContent = expanded ? `Show ${{hiddenCount}} more` : 'Show fewer';
      applyLimit();
    }});
  }}
  search.addEventListener('input', () => {{
    applyLimit();
  }});
  applyLimit();
</script>
</body>
</html>
"""


def emit_json(snapshot):
    print(json.dumps(snapshot, indent=2, sort_keys=True))


def write_html(snapshot, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(snapshot), encoding="utf-8")
    return path.resolve()


def main(argv):
    parser = argparse.ArgumentParser(description="Generate a local maintainer board snapshot")
    parser.add_argument("--repo", default=".", help="repository to scan; defaults to the current Git repo")
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    parser.add_argument(
        "--html",
        nargs="?",
        const="",
        help="write static HTML; defaults to <repo>/.scratch/maintainer-board/index.html",
    )
    args = parser.parse_args(argv)

    try:
        repo = repo_root(args.repo)
        snapshot = build_snapshot(repo)
        html_output = None
        if args.html is not None:
            html_output = Path(args.html) if args.html else repo / DEFAULT_HTML_PATH
        elif not args.json:
            html_output = repo / DEFAULT_HTML_PATH

        if html_output:
            written_path = write_html(snapshot, html_output)
            if not args.json:
                print(written_path)
        if args.json:
            emit_json(snapshot)
    except RuntimeError as exc:
        print(f"maintainer-board: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
