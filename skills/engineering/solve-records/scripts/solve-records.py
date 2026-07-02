#!/usr/bin/env python3
"""Read-only helpers for local solve records."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


REQUIRED = {
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

REF_CACHE = {}
REF_MAP_CACHE = {}
COMMON_DIR_CACHE = {}
WORKTREE_INFO_CACHE = {}
REGISTERED_WORKTREES_CACHE = {}
WORKTREE_CLEAN_CACHE = {}
ANCESTOR_CACHE = {}


HARD_STOP_BASENAMES = {
    "package.json",
    "Cargo.toml",
    "Cargo.lock",
    "pyproject.toml",
    "uv.lock",
    "poetry.lock",
    "go.mod",
    "go.sum",
    "Gemfile",
    "Gemfile.lock",
    "pom.xml",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "schema.sql",
    "SKILL.md",
    "AGENTS.md",
    "CLAUDE.md",
}


def run_git(cwd, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git failed")
    return result


def repo_root(path):
    path = path.resolve()
    if (path / ".git").exists():
        return path
    result = run_git(path, "rev-parse", "--show-toplevel", check=False)
    if result.returncode != 0:
        raise RuntimeError(f"not a Git repo: {path}")
    return Path(result.stdout.strip()).resolve()


def common_dir_from_git_marker(cwd):
    marker = cwd / ".git"
    if marker.is_dir():
        return marker.resolve()
    if not marker.is_file():
        return None

    try:
        content = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not content.startswith("gitdir:"):
        return None

    gitdir = Path(content.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = (cwd / gitdir).resolve()
    else:
        gitdir = gitdir.resolve()

    commondir_file = gitdir / "commondir"
    if commondir_file.is_file():
        common = Path(commondir_file.read_text(encoding="utf-8").strip())
        if not common.is_absolute():
            common = (gitdir / common).resolve()
        else:
            common = common.resolve()
        return common

    if gitdir.parent.name == "worktrees":
        return gitdir.parent.parent.resolve()
    return gitdir


def common_dir(cwd):
    cwd = Path(cwd).resolve()
    cache_key = str(cwd)
    if cache_key in COMMON_DIR_CACHE:
        return COMMON_DIR_CACHE[cache_key]

    path = common_dir_from_git_marker(cwd)
    if path is None:
        raw = run_git(cwd, "rev-parse", "--git-common-dir").stdout.strip()
        path = Path(raw)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()

    COMMON_DIR_CACHE[cache_key] = path
    return COMMON_DIR_CACHE[cache_key]


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


def first_heading(text):
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def parse_record(repo, path):
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(repo))
    data = {"path": rel, "text": text}

    if not text.startswith("---\n"):
        data["malformed"] = "missing frontmatter"
        return data

    end = text.find("\n---", 4)
    if end == -1:
        data["malformed"] = "unclosed frontmatter"
        return data

    current = None
    for line in text[4:end].splitlines():
        if line.startswith("  - ") and current:
            data.setdefault(current, []).append(line[4:].strip())
            continue
        if ":" not in line:
            data["malformed"] = f"invalid frontmatter line: {line}"
            return data
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current = key
        data[key] = [] if key == "issues" and not value else value

    missing = sorted(REQUIRED - set(data))
    if missing:
        data["malformed"] = "missing " + ",".join(missing)
        return data
    if data["kind"] != "solve_record":
        data["malformed"] = f"invalid kind: {data['kind']}"
        return data

    data["checks"] = status_line(section(text, "Checks"))
    data["merge"] = status_line(section(text, "Merge"))
    data["summary_status"] = status_line(section(text, "Summary"))
    data["notes"] = section(text, "Notes").lower()
    data["changes"] = section(text, "Changes")
    data["title"] = first_heading(text)
    return data


def discover(repo):
    paths = []
    paths.extend(repo.glob(".scratch/solve-records/*.md"))
    paths.extend(repo.glob(".scratch/*/solve-records/*.md"))
    return [parse_record(repo, path) for path in sorted(paths)]


def is_true(value):
    return str(value).lower() == "true"


def sha_matches(live, recorded):
    return bool(recorded) and (live == recorded or live.startswith(recorded))


def ref_map(repo):
    cache_key = str(repo)
    if cache_key in REF_MAP_CACHE:
        return REF_MAP_CACHE[cache_key]
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
    if result.returncode == 0:
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
    REF_MAP_CACHE[cache_key] = refs
    return refs


def resolve_ref(repo, ref):
    cache_key = (str(repo), ref)
    if cache_key in REF_CACHE:
        return REF_CACHE[cache_key]
    refs = ref_map(repo)
    if ref in refs:
        REF_CACHE[cache_key] = (0, refs[ref], "")
        return REF_CACHE[cache_key]
    result = run_git(repo, "rev-parse", "--verify", ref, check=False)
    REF_CACHE[cache_key] = (result.returncode, result.stdout.strip(), result.stderr.strip())
    return REF_CACHE[cache_key]


def ref_check(repo, record):
    for ref_key, sha_key in (("base", "base_sha"), ("head", "head_sha")):
        returncode, stdout, _stderr = resolve_ref(repo, record[ref_key])
        if returncode != 0:
            return False, f"{record[ref_key]} missing"
        if not sha_matches(stdout, record[sha_key]):
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
    cache_key = str(worktree)
    if cache_key in WORKTREE_CLEAN_CACHE:
        return WORKTREE_CLEAN_CACHE[cache_key]
    if not worktree.exists():
        WORKTREE_CLEAN_CACHE[cache_key] = (False, "worktree missing")
        return WORKTREE_CLEAN_CACHE[cache_key]
    status = run_git(worktree, "status", "--short", "--untracked-files=all", check=False)
    if status.returncode != 0:
        WORKTREE_CLEAN_CACHE[cache_key] = (False, "worktree is not a Git checkout")
        return WORKTREE_CLEAN_CACHE[cache_key]
    if status.stdout.strip():
        WORKTREE_CLEAN_CACHE[cache_key] = (False, "worktree dirty")
        return WORKTREE_CLEAN_CACHE[cache_key]
    WORKTREE_CLEAN_CACHE[cache_key] = (True, "")
    return WORKTREE_CLEAN_CACHE[cache_key]


def diff_paths(repo, before, after):
    result = run_git(repo, "diff", "--name-only", f"{before}..{after}", check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return sorted(path for path in set(result.stdout.splitlines()) if path)


def status_paths(repo):
    result = run_git(repo, "status", "--porcelain=v1", "--untracked-files=all", check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")

    dirty = []
    untracked = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        status = line[:2]
        raw_path = line[3:]
        paths = raw_path.split(" -> ") if " -> " in raw_path else [raw_path]
        if status == "??":
            untracked.extend(paths)
        else:
            dirty.extend(paths)

    return sorted(set(dirty)), sorted(set(untracked))


def paths_overlap(left, right):
    for left_path in left:
        left_norm = left_path.strip("/")
        for right_path in right:
            right_norm = right_path.strip("/")
            if not left_norm or not right_norm:
                continue
            if (
                left_norm == right_norm
                or left_norm.startswith(right_norm + "/")
                or right_norm.startswith(left_norm + "/")
            ):
                return True
    return False


def hard_stop_paths(paths):
    hits = []
    for path in paths:
        normalized = path.strip("/")
        basename = Path(normalized).name
        if not normalized:
            continue
        if basename in HARD_STOP_BASENAMES or basename.endswith(".lock"):
            hits.append(path)
            continue
        if (
            normalized.startswith(".github/")
            or normalized.startswith(".claude-plugin/")
            or normalized.startswith(".codex-plugin/")
            or normalized.endswith("/agents/openai.yaml")
            or "/migrations/" in f"/{normalized}/"
            or "/schema/" in f"/{normalized}/"
            or normalized.startswith("prisma/schema.prisma")
            or basename.startswith("Dockerfile")
            or basename.startswith("docker-compose")
            or basename.startswith("build.gradle")
        ):
            hits.append(path)
    return sorted(set(hits))


def current_branch(repo):
    result = run_git(repo, "branch", "--show-current", check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def live_ref_sha(repo, ref):
    returncode, stdout, stderr = resolve_ref(repo, ref)
    if returncode != 0:
        raise RuntimeError(stderr or f"{ref} missing")
    return stdout


def merge_gate(repo, record):
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


def landing_plan(repo, record, landing_sha=None):
    gate = merge_gate(repo, record)
    result = {
        "id": record.get("id"),
        "path": record.get("path"),
        "status": "blocked",
        "reasons": list(gate["reasons"]),
        "merge_gate": gate,
    }
    if result["reasons"]:
        return result

    base_branch = current_branch(repo)
    expected_base = record["base"]
    if base_branch != expected_base:
        result["reasons"].append(f"base worktree is on {base_branch or '<detached>'}, expected {expected_base}")
        return result

    live_base_sha = live_ref_sha(repo, record["base"])
    live_head_sha = live_ref_sha(repo, record["head"])
    merge_base = run_git(repo, "merge-base", "--is-ancestor", live_base_sha, live_head_sha, check=False)

    if landing_sha:
        landing_ref = landing_sha
        returncode, resolved_landing, stderr = resolve_ref(repo, landing_ref)
        if returncode != 0:
            result["reasons"].append(stderr or f"landing sha missing: {landing_ref}")
            return result
        landing_sha = resolved_landing
        base_reaches_landing = run_git(
            repo, "merge-base", "--is-ancestor", live_base_sha, landing_sha, check=False
        )
        head_reaches_landing = run_git(
            repo, "merge-base", "--is-ancestor", live_head_sha, landing_sha, check=False
        )
        if base_reaches_landing.returncode != 0:
            result["reasons"].append("landing sha is not a descendant of base")
        if head_reaches_landing.returncode != 0:
            result["reasons"].append("landing sha does not contain head")
        if result["reasons"]:
            return result
        landing_type = "provided-landing"
    elif merge_base.returncode == 0:
        landing_sha = live_head_sha
        landing_type = "fast-forward"
    else:
        result.update(
            {
                "status": "needs_landing_construction",
                "reasons": ["non-fast-forward requires a disposable landing commit"],
                "landing_type": "disposable-worktree-required",
                "live_base_sha": live_base_sha,
                "live_head_sha": live_head_sha,
            }
        )
        return result

    write_surface = diff_paths(repo, live_base_sha, landing_sha)
    dirty_paths, untracked_paths = status_paths(repo)
    dirty_overlap = paths_overlap(dirty_paths, write_surface)
    untracked_overlap = paths_overlap(untracked_paths, write_surface)
    hard_stops = hard_stop_paths(write_surface)

    reasons = []
    if dirty_overlap:
        reasons.append("dirty base path overlaps landing write surface")
    if untracked_overlap:
        reasons.append("untracked base path would be overwritten")
    if hard_stops:
        reasons.append("mandatory hard-stop pattern requires manual review")

    result.update(
        {
            "status": "blocked" if reasons else "ready",
            "reasons": reasons,
            "landing_type": landing_type,
            "landing_sha": landing_sha,
            "live_base_sha": live_base_sha,
            "live_head_sha": live_head_sha,
            "write_surface": write_surface,
            "dirty_paths": dirty_paths,
            "untracked_paths": untracked_paths,
            "dirty_overlap": dirty_overlap,
            "untracked_overlap": untracked_overlap,
            "hard_stop_paths": hard_stops,
        }
    )
    return result


def registered_worktree_info(repo):
    cache_key = str(repo)
    if cache_key in WORKTREE_INFO_CACHE:
        return WORKTREE_INFO_CACHE[cache_key]
    output = run_git(repo, "worktree", "list", "--porcelain").stdout.splitlines()
    worktrees = {}
    current = None
    for line in output:
        if line.startswith("worktree "):
            current = Path(line.split(" ", 1)[1]).resolve()
            worktrees[current] = {"branch": ""}
        elif current and line.startswith("branch "):
            branch = line.split(" ", 1)[1]
            if branch.startswith("refs/heads/"):
                branch = branch[len("refs/heads/") :]
            worktrees[current]["branch"] = branch
    WORKTREE_INFO_CACHE[cache_key] = worktrees
    return worktrees


def registered_worktrees(repo):
    cache_key = str(repo)
    if cache_key in REGISTERED_WORKTREES_CACHE:
        return REGISTERED_WORKTREES_CACHE[cache_key]
    REGISTERED_WORKTREES_CACHE[cache_key] = list(registered_worktree_info(repo))
    return REGISTERED_WORKTREES_CACHE[cache_key]


def cleanup_refusal(repo, record):
    worktree = (repo / record["worktree"]).resolve()
    if worktree == repo.resolve():
        return "worktree is repo root"
    worktrees = registered_worktree_info(repo)
    if worktree not in worktrees:
        return "unregistered worktree"
    if common_dir(repo) != common_dir(worktree):
        return "common dir mismatch"
    branch = worktrees[worktree].get("branch")
    if not branch:
        return "worktree branch unavailable"
    if branch != record["head"]:
        return "branch mismatch"
    status = run_git(worktree, "status", "--short", check=False)
    if status.returncode != 0:
        return "worktree status unavailable"
    if status.stdout.strip():
        return "dirty worktree"
    cache_key = (str(repo), record["head"], record["base"])
    if cache_key not in ANCESTOR_CACHE:
        merged = run_git(repo, "merge-base", "--is-ancestor", record["head"], record["base"], check=False)
        ANCESTOR_CACHE[cache_key] = merged.returncode
    if ANCESTOR_CACHE[cache_key] != 0:
        return "branch is not merged"
    return ""


def cleanup_plan(repo, record):
    if record.get("malformed"):
        return {
            "id": record.get("id"),
            "path": record.get("path"),
            "status": "blocked",
            "reason": record["malformed"],
        }
    if record.get("state") not in {"merged", "closed"}:
        return {
            "id": record.get("id"),
            "path": record.get("path"),
            "status": "not_applicable",
            "reason": f"state is {record.get('state')}",
        }
    if is_true(record.get("cleanup_done")):
        return {
            "id": record.get("id"),
            "path": record.get("path"),
            "status": "done",
            "reason": "",
        }
    refusal = cleanup_refusal(repo, record)
    return {
        "id": record.get("id"),
        "path": record.get("path"),
        "status": "blocked" if refusal else "safe",
        "reason": refusal,
        "worktree": record.get("worktree"),
        "head": record.get("head"),
    }


def record_summary(repo, record, include_merge_gate=False):
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
            summary["merge_gate"] = merge_gate(repo, record)
    return summary


def recent_sort_key(summary):
    return (
        summary.get("merged_at") or summary.get("created_at") or "",
        summary.get("id") or "",
        summary.get("path") or "",
    )


def dashboard(repo, records):
    buckets = {
        "ready": [],
        "manual": [],
        "cleanup": [],
        "recent": [],
        "stale_or_malformed": [],
    }

    recent = []
    for record in records:
        summary = record_summary(repo, record)
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
        gate = merge_gate(repo, record)
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


def searchable_text(record):
    fields = [
        record.get("id", ""),
        record.get("path", ""),
        record.get("head", ""),
        record.get("title", ""),
        " ".join(record.get("issues", [])),
        record.get("changes", ""),
    ]
    return " ".join(str(field) for field in fields).lower()


def select_records(records, query):
    parts = query.lower().split()
    matches = []
    for record in records:
        if record.get("malformed"):
            continue
        text = searchable_text(record)
        if all(part in text for part in parts):
            matches.append(record)
    return matches


def find_record(records, selector):
    for record in records:
        if selector in {record.get("id"), record.get("path")}:
            return record
    selected = select_records(records, selector)
    if len(selected) == 1:
        return selected[0]
    if not selected:
        raise RuntimeError(f"no record matches: {selector}")
    labels = ", ".join(record.get("id") or record.get("path", "") for record in selected)
    raise RuntimeError(f"selector is ambiguous: {selector}; matches: {labels}")


def print_dashboard_text(result):
    labels = {
        "ready": "Ready to merge",
        "manual": "Manual merge required",
        "cleanup": "Cleanup pending",
        "recent": "Recently merged",
        "stale_or_malformed": "Stale or malformed",
    }
    for key, label in labels.items():
        print(f"{label}:")
        items = result["buckets"][key]
        if not items:
            print("- none")
            continue
        for item in items:
            marker = item.get("id") or item.get("path")
            detail = item.get("stale_reason") or item.get("malformed") or ""
            suffix = f" ({detail})" if detail else ""
            print(f"- {marker}{suffix}")


def emit(data, as_json):
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    elif isinstance(data, dict) and "buckets" in data:
        print_dashboard_text(data)
    else:
        print(json.dumps(data, indent=2, sort_keys=True))


def load_records(args):
    repo = repo_root(Path(args.repo))
    return repo, discover(repo)


def main(argv):
    parser = argparse.ArgumentParser(description="Read-only solve-record helpers")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.required = True

    def add_common(subparser):
        subparser.add_argument("--repo", default=".", help="Git repo path")
        subparser.add_argument("--json", action="store_true", help="emit JSON")

    dashboard_parser = subparsers.add_parser("dashboard")
    add_common(dashboard_parser)

    list_parser = subparsers.add_parser("list")
    add_common(list_parser)

    select_parser = subparsers.add_parser("select")
    select_parser.add_argument("--query", required=True)
    add_common(select_parser)

    merge_gate_parser = subparsers.add_parser("merge-gate")
    merge_gate_parser.add_argument("--record", required=True)
    add_common(merge_gate_parser)

    cleanup_parser = subparsers.add_parser("cleanup-plan")
    cleanup_parser.add_argument("--record", required=True)
    add_common(cleanup_parser)

    landing_parser = subparsers.add_parser("landing-plan")
    landing_parser.add_argument("--record", required=True)
    landing_parser.add_argument("--landing-sha")
    add_common(landing_parser)

    args = parser.parse_args(argv)

    try:
        repo, records = load_records(args)
        if args.command == "dashboard":
            emit(dashboard(repo, records), args.json)
        elif args.command == "list":
            emit([record_summary(repo, record) for record in records], args.json)
        elif args.command == "select":
            matches = [record_summary(repo, record) for record in select_records(records, args.query)]
            emit({"query": args.query, "count": len(matches), "matches": matches}, args.json)
        elif args.command == "merge-gate":
            record = find_record(records, args.record)
            emit(merge_gate(repo, record), args.json)
        elif args.command == "cleanup-plan":
            record = find_record(records, args.record)
            emit(cleanup_plan(repo, record), args.json)
        elif args.command == "landing-plan":
            record = find_record(records, args.record)
            emit(landing_plan(repo, record, args.landing_sha), args.json)
    except RuntimeError as exc:
        print(f"solve-records: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
