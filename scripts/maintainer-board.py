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


def repo_self_root():
    return Path(__file__).resolve().parents[1]


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


def load_solve_records_dashboard(repo):
    helper_path = repo_self_root() / "skills/engineering/solve-records/scripts/solve-records.py"
    if not helper_path.is_file():
        return {
            "repo": str(repo),
            "record_count": 0,
            "buckets": {bucket: [] for bucket in SOLVE_RECORD_BUCKETS},
            "error": f"solve-records helper not found: {helper_path}",
        }

    spec = importlib.util.spec_from_file_location("solve_records_helper", helper_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    records = module.discover(repo)
    return module.dashboard(repo, records)


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


def compact_meta(item, keys):
    parts = []
    for key in keys:
        value = item.get(key)
        if not value:
            continue
        if isinstance(value, list):
            value = ", ".join(str(part) for part in value)
        parts.append(f"{key.replace('_', ' ')}: {value}")
    return parts


def render_warning_list(warnings):
    if not warnings:
        return ""
    items = "".join(
        f"<li><span class='warn-code'>{html.escape(warning['code'])}</span> {html.escape(warning['message'])}</li>"
        for warning in warnings
    )
    return f"<ul class='warnings'>{items}</ul>"


def render_issue_card(issue):
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
    meta = compact_meta(
        issue,
        [
            "status",
            "category",
            "feature",
            "created",
            "metadata_format",
            "solve_branch",
            "solve_worktree",
        ],
    )
    flags = "".join(f"<span class='pill'>{html.escape(flag)}</span>" for flag in issue["flags"])
    links = []
    if issue["parent"]:
        links.append(f"parent: {issue['parent']}")
    for blocker in issue["blocked_by"]:
        links.append(f"blocked by: {blocker}")
    for record in issue["solve_records"]:
        links.append(f"solve record: {record}")
    link_html = "".join(f"<div class='path'>{html.escape(link)}</div>" for link in links)
    checklist = issue["checklist"]
    checklist_text = f"{checklist['done']}/{checklist['total']} checklist" if checklist["total"] else "no checklist"
    meta_html = "".join(f"<span>{html.escape(part)}</span>" for part in meta)
    return f"""
<article class="card issue-card" data-search="{html.escape(search.lower())}">
  <h3>{html.escape(issue['title'])}</h3>
  <div class="path">{html.escape(issue['path'])}</div>
  <div class="meta">{meta_html}<span>{html.escape(checklist_text)}</span></div>
  <div class="pills">{flags}</div>
  {link_html}
  {render_warning_list(issue['warnings'])}
</article>
"""


def render_record_card(record):
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
    meta = compact_meta(
        record,
        [
            "state",
            "checks",
            "merge",
            "cleanup_done",
            "base",
            "head",
            "worktree",
        ],
    )
    details = []
    for issue in record.get("issues", []):
        details.append(f"issue: {issue}")
    if record.get("stale_reason"):
        details.append(f"stale: {record['stale_reason']}")
    if record.get("malformed"):
        details.append(f"malformed: {record['malformed']}")
    if record.get("ref_reason"):
        details.append(f"refs: {record['ref_reason']}")
    meta_html = "".join(f"<span>{html.escape(part)}</span>" for part in meta)
    detail_html = "".join(f"<div class='path'>{html.escape(detail)}</div>" for detail in details)
    return f"""
<article class="card record-card" data-search="{html.escape(search.lower())}">
  <h3>{html.escape(record.get('title') or record.get('id') or record.get('path') or 'solve record')}</h3>
  <div class="path">{html.escape(record.get('path', ''))}</div>
  <div class="meta">{meta_html}</div>
  {detail_html}
</article>
"""


def render_bucket(title, items, renderer):
    cards = "".join(renderer(item) for item in items)
    empty = "<p class='empty'>none</p>" if not items else ""
    return f"""
<section class="bucket">
  <header><h2>{html.escape(title)}</h2><span>{len(items)}</span></header>
  <div class="cards">{cards}{empty}</div>
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
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
      gap: 12px;
      align-items: start;
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
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin: 7px 0;
    }}
    .meta span, .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 7px;
      color: var(--muted);
      background: #fbfcfd;
      font-size: 11px;
    }}
    .pills {{ display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 5px; }}
    .warnings {{
      margin: 7px 0 0;
      padding-left: 18px;
      color: var(--red);
    }}
    .warn-code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .empty {{ margin: 0; color: var(--muted); padding: 6px 2px; }}
    .hidden {{ display: none !important; }}
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
  <div class="grid">{issue_sections}</div>
  <h2 class="section-title">Solve Records</h2>
  <div class="grid">{record_sections}</div>
</main>
<script>
  const search = document.getElementById('search');
  const cards = [...document.querySelectorAll('.card')];
  search.addEventListener('input', () => {{
    const query = search.value.trim().toLowerCase();
    for (const card of cards) {{
      card.classList.toggle('hidden', query && !card.dataset.search.includes(query));
    }}
  }});
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


def main(argv):
    parser = argparse.ArgumentParser(description="Generate a local maintainer board snapshot")
    parser.add_argument("--repo", default=".", help="repository to scan")
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    parser.add_argument("--html", help="write static HTML to this path")
    args = parser.parse_args(argv)

    if not args.json and not args.html:
        parser.error("choose at least one output mode: --json or --html <path>")

    try:
        repo = repo_root(args.repo)
        snapshot = build_snapshot(repo)
        if args.html:
            write_html(snapshot, args.html)
        if args.json:
            emit_json(snapshot)
    except RuntimeError as exc:
        print(f"maintainer-board: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
