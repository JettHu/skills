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

SOLVE_RECORD_BUCKETS = ["ready", "manual", "cleanup", "recent", "stale_or_malformed"]
DEFAULT_VISIBLE_ITEMS = 5
DEFAULT_HTML_PATH = Path(".scratch/maintainer-board/index.html")
SOLVE_RECORD_REQUIRED = {
    "id",
    "kind",
    "state",
    "base",
    "base_sha",
    "head",
    "head_sha",
    "issues",
    "worktree",
    "created_at",
    "cleanup_done",
}


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


def feature_from_path(repo, path):
    rel_parts = path.relative_to(repo).parts
    if len(rel_parts) >= 2 and rel_parts[0] == ".scratch":
        return rel_parts[1]
    return ""


def parse_issue(repo, path):
    text = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    metadata = frontmatter if frontmatter is not None else parse_header_metadata(text.splitlines())

    rel = str(path.relative_to(repo))
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
    status = str(metadata.get("status", "")).strip()
    issue = {
        "path": rel,
        "feature": feature_from_path(repo, path),
        "title": first_heading(body) or first_heading(text) or path.stem,
        "status": status,
        "category": str(metadata.get("category", "")).strip(),
        "flags": flags,
        "created": str(metadata.get("created", "")).strip(),
        "solve_branch": str(metadata.get("solve_branch", "")).strip(),
        "solve_worktree": str(metadata.get("solve_worktree", "")).strip(),
        "parent": parent[0] if parent else "",
        "blocked_by": sorted(dict.fromkeys(blockers)),
        "solve_records": sorted(dict.fromkeys(solve_records)),
        "checklist": checklist_counts(body),
        "metadata_format": "frontmatter" if frontmatter is not None else "header",
        "warnings": [],
    }
    issue["bucket"] = classify_issue(issue)
    return issue


def classify_issue(issue):
    flags = set(issue["flags"])
    status = issue["status"]
    if "solve-in-progress" in flags:
        return "claimed_or_in_progress"
    if status in {"ready-for-human", "needs-info"} or "agent-decision" in flags:
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


def section(text, name):
    marker = f"## {name}\n"
    start = text.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    end = text.find("\n## ", start)
    if end == -1:
        end = len(text)
    return text[start:end]


def status_line(block):
    for line in block.splitlines():
        if line.startswith("Status:"):
            return line.split(":", 1)[1].strip()
    return ""


def is_true(value):
    return str(value).lower() == "true"


def sha_matches(live, recorded):
    return bool(recorded) and (live == recorded or live.startswith(recorded))


def resolve_ref(repo, ref):
    refs = ref_map(repo)
    if ref in refs:
        return 0, refs[ref], ""
    result = run_git(repo, "rev-parse", "--verify", ref, check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def ref_check(repo, record):
    for ref_key, sha_key in (("base", "base_sha"), ("head", "head_sha")):
        if not record.get(ref_key):
            return False, f"{ref_key} missing"
        returncode, stdout, _stderr = resolve_ref(repo, record[ref_key])
        if returncode != 0:
            return False, f"{record[ref_key]} missing"
        if not sha_matches(stdout, record.get(sha_key)):
            return False, f"{ref_key} sha mismatch"
    return True, ""


def has_low_risk_exception(record):
    notes = record.get("notes", "")
    required_evidence = [
        "low-risk",
        "no meaningful automated check exists",
        "no manual-review trigger",
        "evidence:",
    ]
    return all(fragment in notes for fragment in required_evidence)


def body_frontmatter_conflict(record):
    summary_status = record.get("summary_status")
    if summary_status and summary_status != record.get("state"):
        return "body/frontmatter status conflict"
    return ""


def worktree_clean_check(repo, record):
    worktree = (repo / record["worktree"]).resolve()
    if not worktree.exists():
        return False, "worktree missing"
    status = run_git(worktree, "status", "--short", "--untracked-files=all", check=False)
    if status.returncode != 0:
        return False, "worktree is not a Git checkout"
    if status.stdout.strip():
        return False, "worktree dirty"
    return True, ""


def parse_solve_record(repo, path):
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(repo))
    frontmatter, body = split_frontmatter(text)
    record = {"path": rel, "text": text}
    if frontmatter is None:
        record["malformed"] = "missing frontmatter"
        return record

    record.update(frontmatter)
    missing = sorted(SOLVE_RECORD_REQUIRED - set(record))
    if missing:
        record["malformed"] = "missing " + ",".join(missing)
        return record
    if record["kind"] != "solve_record":
        record["malformed"] = f"invalid kind: {record['kind']}"
        return record

    record["checks"] = status_line(section(body, "Checks"))
    record["merge"] = status_line(section(body, "Merge"))
    record["summary_status"] = status_line(section(body, "Summary"))
    record["notes"] = section(body, "Notes").lower()
    record["changes"] = section(body, "Changes")
    record["title"] = first_heading(body)
    return record


def discover_solve_records(repo):
    paths = []
    paths.extend(repo.glob(".scratch/solve-records/*.md"))
    paths.extend(repo.glob(".scratch/*/solve-records/*.md"))
    return [parse_solve_record(repo, path) for path in sorted(paths)]


def solve_record_merge_gate(repo, record):
    reasons = []
    if record.get("malformed"):
        reasons.append(record["malformed"])
    elif body_frontmatter_conflict(record):
        reasons.append(body_frontmatter_conflict(record))
    else:
        refs_ok, ref_reason = ref_check(repo, record)
        if not refs_ok:
            reasons.append(ref_reason)
        if record.get("state") != "open":
            reasons.append(f"state is {record.get('state')}")
        if record.get("merge") != "ready":
            reasons.append(f"merge status is {record.get('merge') or '<missing>'}")
        if record.get("external_provider") or record.get("external_url"):
            reasons.append("remote-primary record")
        if record.get("checks") == "unavailable":
            if not has_low_risk_exception(record):
                reasons.append("unavailable checks without low-risk evidence")
        elif record.get("checks") != "passed":
            reasons.append(f"checks status is {record.get('checks') or '<missing>'}")
        if not reasons:
            clean, clean_reason = worktree_clean_check(repo, record)
            if not clean:
                reasons.append(clean_reason)

    return {
        "id": record.get("id"),
        "path": record.get("path"),
        "eligible": not reasons,
        "reasons": reasons,
    }


def cleanup_plan(repo, record):
    if record.get("malformed"):
        status = "blocked"
        reason = record["malformed"]
    elif record.get("state") not in {"merged", "closed"}:
        status = "not_applicable"
        reason = f"state is {record.get('state')}"
    elif is_true(record.get("cleanup_done")):
        status = "done"
        reason = ""
    else:
        worktree = (repo / record.get("worktree", "")).resolve()
        if worktree == repo.resolve():
            status = "blocked"
            reason = "worktree is repo root"
        elif not worktree.exists():
            status = "blocked"
            reason = "worktree missing"
        else:
            status = "pending"
            reason = ""

    return {
        "id": record.get("id"),
        "path": record.get("path"),
        "status": status,
        "reason": reason,
        "worktree": record.get("worktree"),
        "head": record.get("head"),
    }


def solve_record_summary(repo, record, include_merge_gate=False):
    summary = {
        "path": record.get("path"),
        "id": record.get("id"),
        "title": record.get("title"),
        "state": record.get("state"),
        "created_at": record.get("created_at"),
        "merged_at": record.get("merged_at"),
        "merged_sha": record.get("merged_sha"),
        "base": record.get("base"),
        "head": record.get("head"),
        "issues": record.get("issues", []),
        "worktree": record.get("worktree"),
        "checks": record.get("checks"),
        "merge": record.get("merge"),
        "cleanup_done": record.get("cleanup_done"),
        "external_provider": record.get("external_provider"),
        "external_url": record.get("external_url"),
    }
    if record.get("malformed"):
        summary["malformed"] = record["malformed"]
    else:
        refs_ok, ref_reason = ref_check(repo, record)
        summary["refs_ok"] = refs_ok
        summary["ref_reason"] = ref_reason
        summary["low_risk_exception"] = has_low_risk_exception(record)
        conflict = body_frontmatter_conflict(record)
        if conflict:
            summary["body_conflict"] = conflict
        if include_merge_gate:
            summary["merge_gate"] = solve_record_merge_gate(repo, record)
    return summary


def recent_sort_key(summary):
    return (
        summary.get("merged_at") or summary.get("created_at") or "",
        summary.get("id") or "",
        summary.get("path") or "",
    )


def fallback_solve_records_dashboard(repo):
    records = discover_solve_records(repo)
    buckets = {bucket: [] for bucket in SOLVE_RECORD_BUCKETS}
    recent = []

    for record in records:
        summary = solve_record_summary(repo, record)
        if record.get("malformed"):
            buckets["stale_or_malformed"].append(summary)
            continue
        conflict = body_frontmatter_conflict(record)
        if conflict:
            summary["stale_reason"] = conflict
            buckets["stale_or_malformed"].append(summary)
            continue
        refs_ok, ref_reason = ref_check(repo, record)
        if not refs_ok and record["state"] == "open":
            summary["stale_reason"] = ref_reason
            buckets["stale_or_malformed"].append(summary)
            continue
        if record["state"] in {"merged", "closed"} and not is_true(record["cleanup_done"]):
            summary["cleanup_plan"] = cleanup_plan(repo, record)
            buckets["cleanup"].append(summary)
            continue
        if record["state"] == "merged":
            recent.append(summary)
            continue
        gate = solve_record_merge_gate(repo, record)
        summary["merge_gate"] = gate
        if gate["eligible"]:
            buckets["ready"].append(summary)
        else:
            buckets["manual"].append(summary)

    buckets["recent"] = sorted(recent, key=recent_sort_key, reverse=True)[:10]
    return {
        "repo": str(repo),
        "record_count": len(records),
        "buckets": buckets,
    }


def bucket_items(items, buckets):
    result = {bucket: [] for bucket in buckets}
    for item in items:
        result.setdefault(item["bucket"], []).append(item)
    return result


def load_solve_records_dashboard(repo):
    helper_path = find_solve_records_helper()
    if helper_path:
        spec = importlib.util.spec_from_file_location("solve_records_helper", helper_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        records = module.discover(repo)
        return module.dashboard(repo, records)
    return fallback_solve_records_dashboard(repo)


def build_snapshot(repo):
    issues = [parse_issue(repo, path) for path in discover_issue_paths(repo)]
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
            record.get("head", ""),
            record.get("base", ""),
        ]
    )
    cleanup = "cleanup done" if str(record.get("cleanup_done")).lower() == "true" else "cleanup pending"
    top_pills = [
        record.get("state"),
        record.get("checks"),
        record.get("merge"),
        cleanup if record.get("cleanup_done") else "",
    ]
    detail_rows = [
        ("Path", record.get("path")),
        ("ID", record.get("id")),
        ("State", record.get("state")),
        ("Checks", record.get("checks")),
        ("Merge", record.get("merge")),
        ("Cleanup", cleanup if record.get("cleanup_done") else ""),
        ("Base", record.get("base")),
        ("Head", record.get("head")),
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
    .label-agent-decision,
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
