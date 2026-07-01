#!/usr/bin/env bash
set -euo pipefail

TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

REPO="$TMPDIR_ROOT/project"

git init -b master "$REPO" >/dev/null
git -C "$REPO" config user.email "solve-records@example.test"
git -C "$REPO" config user.name "Solve Records Test"

common_dir() {
  local cwd="$1"
  local raw
  raw="$(git -C "$cwd" rev-parse --git-common-dir)"
  if [[ "$raw" = /* ]]; then
    realpath "$raw"
  else
    realpath "$cwd/$raw"
  fi
}

printf 'base\n' >"$REPO/app.txt"
git -C "$REPO" add app.txt
git -C "$REPO" commit -m "base" >/dev/null
BASE_SHA="$(git -C "$REPO" rev-parse master)"

make_branch() {
  local branch="$1"
  local file="$2"
  local text="$3"
  git -C "$REPO" checkout -b "$branch" master >/dev/null 2>&1
  printf '%s\n' "$text" >"$REPO/$file"
  git -C "$REPO" add "$file"
  git -C "$REPO" commit -m "$branch" >/dev/null
  git -C "$REPO" rev-parse "$branch"
  git -C "$REPO" checkout master >/dev/null 2>&1
}

READY_HEAD="$(make_branch solve/20260701-1432-caption-fix caption.txt caption)"
MANUAL_HEAD="$(make_branch solve/20260701-1500-manual-contract contract.txt contract)"
SHA_DRIFT_HEAD="$(make_branch solve/20260701-1506-sha-drift sha-drift.txt sha-drift)"
DIRTY_HEAD="$(make_branch solve/20260701-1510-dirty-cleanup dirty.txt dirty)"
UNMERGED_HEAD="$(make_branch solve/20260701-1520-unmerged-cleanup unmerged.txt unmerged)"
MISMATCH_HEAD="$(make_branch solve/20260701-1530-branch-mismatch mismatch.txt mismatch)"
MISMATCH_TARGET_HEAD="$(make_branch solve/20260701-1531-branch-mismatch-target mismatch-target.txt mismatch-target)"
MISMATCH_WORKTREE_HEAD="$(make_branch solve/20260701-1532-branch-mismatch-worktree mismatch-worktree.txt mismatch-worktree)"
RECENT_HEAD="$(make_branch solve/20260701-1540-recent-merged recent.txt recent)"
LOW_RISK_HEAD="$(make_branch solve/20260701-1545-low-risk-unavailable low-risk.txt low-risk)"
WEAK_LOW_RISK_HEAD="$(make_branch solve/20260701-1546-weak-low-risk weak-low-risk.txt weak-low-risk)"
CLOSE_HEAD="$(make_branch solve/20260701-1555-abandoned abandoned.txt abandoned)"
REMOTE_HEAD="$(make_branch solve/20260701-1600-remote-pr remote.txt remote)"
CONFLICT_HEAD="$(make_branch solve/20260701-1605-body-conflict body-conflict.txt body-conflict)"

git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-ready" solve/20260701-1432-caption-fix >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-dirty" solve/20260701-1510-dirty-cleanup >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-unmerged" solve/20260701-1520-unmerged-cleanup >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-branch-mismatch" solve/20260701-1532-branch-mismatch-worktree >/dev/null 2>&1
printf 'dirty\n' >>"$TMPDIR_ROOT/wt-dirty/dirty.txt"

mkdir -p "$REPO/.scratch/caption/issues"
mkdir -p "$REPO/.scratch/caption/solve-records"
mkdir -p "$REPO/.scratch/solve-records"

cat >"$REPO/.scratch/caption/issues/01.md" <<'EOF'
Status: completed

# Caption issue

## Comments

### Solve Record

- `../solve-records/20260701-1432-caption-fix.md`
EOF
printf 'Status: completed\n\n# Manual issue\n' >"$REPO/.scratch/caption/issues/02.md"

write_record() {
  local path="$1"
  local id="$2"
  local state="$3"
  local head="$4"
  local head_sha="$5"
  local issue="$6"
  local worktree="$7"
  local cleanup_done="$8"
  local title="$9"
  local checks="${10}"
  local merge="${11}"
  local notes="${12:-fixture}"
  mkdir -p "$(dirname "$path")"
  cat >"$path" <<EOF
---
id: $id
kind: solve_record
state: $state
base: master
base_sha: $BASE_SHA
head: $head
head_sha: $head_sha
issues:
  - $issue
worktree: $worktree
created_at: 2026-07-01T14:32:00+08:00
cleanup_done: $cleanup_done
---

# Solve Record: $title

## Summary
Status: $state
Next action: merge

## Issues
- \`$issue\` - completed

## Changes
- $title

## Checks
Status: $checks
- \`fixture\` - $checks

## Merge
Status: $merge
Gate:
- [ ] Required checks passed
Reason:
- fixture reason

## Resources
Base: \`master\`
Base SHA: \`$BASE_SHA\`
Head: \`$head\`
Head SHA: \`$head_sha\`
Worktree: \`$worktree\`
Cleanup: pending

## Notes
- $notes
EOF
}

write_record "$REPO/.scratch/caption/solve-records/20260701-1432-caption-fix.md" \
  "20260701-1432-caption-fix" open solve/20260701-1432-caption-fix "$READY_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Caption fix" passed ready

write_record "$REPO/.scratch/solve-records/20260701-1500-manual-contract.md" \
  "20260701-1500-manual-contract" open solve/20260701-1500-manual-contract "$MANUAL_HEAD" \
  ".scratch/caption/issues/02.md" "../wt-ready" false "Manual contract change" unavailable "manual required"

write_record "$REPO/.scratch/solve-records/20260701-1505-stale-ref.md" \
  "20260701-1505-stale-ref" open solve/missing-ref deadbeef \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Stale ref" passed ready

write_record "$REPO/.scratch/solve-records/20260701-1506-sha-drift.md" \
  "20260701-1506-sha-drift" open solve/20260701-1506-sha-drift "$MANUAL_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "SHA drift" passed ready

write_record "$REPO/.scratch/solve-records/20260701-1510-dirty-cleanup.md" \
  "20260701-1510-dirty-cleanup" merged solve/20260701-1510-dirty-cleanup "$DIRTY_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-dirty" false "Dirty cleanup" passed "auto-merged"

write_record "$REPO/.scratch/solve-records/20260701-1515-unregistered-cleanup.md" \
  "20260701-1515-unregistered-cleanup" merged solve/20260701-1510-dirty-cleanup "$DIRTY_HEAD" \
  ".scratch/caption/issues/01.md" "../not-registered" false "Unregistered cleanup" passed "auto-merged"

write_record "$REPO/.scratch/solve-records/20260701-1520-unmerged-cleanup.md" \
  "20260701-1520-unmerged-cleanup" merged solve/20260701-1520-unmerged-cleanup "$UNMERGED_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-unmerged" false "Unmerged cleanup" passed "auto-merged"

write_record "$REPO/.scratch/solve-records/20260701-1530-branch-mismatch.md" \
  "20260701-1530-branch-mismatch" merged solve/20260701-1530-branch-mismatch "$MISMATCH_HEAD" \
  ".scratch/caption/issues/01.md" "." false "Branch mismatch cleanup" passed "auto-merged"

write_record "$REPO/.scratch/solve-records/20260701-1531-branch-mismatch-real.md" \
  "20260701-1531-branch-mismatch-real" merged solve/20260701-1531-branch-mismatch-target "$MISMATCH_TARGET_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-branch-mismatch" false "Real branch mismatch cleanup" passed "auto-merged"

write_record "$REPO/.scratch/solve-records/20260701-1540-recent-merged.md" \
  "20260701-1540-recent-merged" merged solve/20260701-1540-recent-merged "$RECENT_HEAD" \
  ".scratch/caption/issues/01.md" "." true "Recent merged" passed "auto-merged"

write_record "$REPO/.scratch/solve-records/20260701-1545-low-risk-unavailable.md" \
  "20260701-1545-low-risk-unavailable" open solve/20260701-1545-low-risk-unavailable "$LOW_RISK_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Low risk unavailable check" unavailable ready \
  "low-risk trivial docs-only change; no meaningful automated check exists; no manual-review trigger applies; evidence: record-format-only fixture"

write_record "$REPO/.scratch/solve-records/20260701-1546-weak-low-risk.md" \
  "20260701-1546-weak-low-risk" open solve/20260701-1546-weak-low-risk "$WEAK_LOW_RISK_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Weak low risk unavailable check" unavailable ready \
  "low-risk"

write_record "$REPO/.scratch/solve-records/20260701-1555-abandoned.md" \
  "20260701-1555-abandoned" open solve/20260701-1555-abandoned "$CLOSE_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Abandoned candidate" passed "manual required"

write_record "$REPO/.scratch/solve-records/20260701-1600-remote-pr.md" \
  "20260701-1600-remote-pr" open solve/20260701-1600-remote-pr "$REMOTE_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Remote PR candidate" passed ready
python3 - "$REPO/.scratch/solve-records/20260701-1600-remote-pr.md" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "cleanup_done: false\n---",
    "cleanup_done: false\nexternal_provider: github\nexternal_url: https://example.test/pull/1\n---",
    1,
)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/solve-records/20260701-1605-body-conflict.md" \
  "20260701-1605-body-conflict" open solve/20260701-1605-body-conflict "$CONFLICT_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Body conflict" passed ready
python3 - "$REPO/.scratch/solve-records/20260701-1605-body-conflict.md" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("## Summary\nStatus: open", "## Summary\nStatus: merged", 1)
path.write_text(text, encoding="utf-8")
PY

cat >"$REPO/.scratch/solve-records/20260701-1550-malformed.md" <<'EOF'
# Missing frontmatter
This malformed record should not hide valid records.
EOF

python3 - "$REPO" <<'PY'
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()

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


def run_git(cwd, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr.strip() or "git failed")
    return result


def common_dir(cwd):
    raw = run_git(cwd, "rev-parse", "--git-common-dir").stdout.strip()
    path = Path(raw)
    if not path.is_absolute():
        path = Path(cwd) / path
    return path.resolve()


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


def parse_record(path):
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(repo))
    if not text.startswith("---\n"):
        return {"path": rel, "malformed": "missing frontmatter", "text": text}
    end = text.find("\n---", 4)
    if end == -1:
        return {"path": rel, "malformed": "unclosed frontmatter", "text": text}
    raw = text[4:end].splitlines()
    data = {"path": rel, "text": text}
    current = None
    for line in raw:
        if line.startswith("  - ") and current:
            data.setdefault(current, []).append(line[4:].strip())
            continue
        if ":" not in line:
            return {"path": rel, "malformed": f"invalid frontmatter line: {line}", "text": text}
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current = key
        data[key] = [] if key == "issues" and not value else value
    missing = sorted(REQUIRED - set(data))
    if missing:
        return {"path": rel, "malformed": "missing " + ",".join(missing), "text": text}
    data["checks"] = status_line(section(text, "Checks"))
    data["merge"] = status_line(section(text, "Merge"))
    data["summary_status"] = status_line(section(text, "Summary"))
    data["notes"] = section(text, "Notes").lower()
    data["title"] = text.splitlines()[text.splitlines().index("") + 1] if "" in text.splitlines() else ""
    return data


def discover():
    paths = []
    paths.extend(repo.glob(".scratch/solve-records/*.md"))
    paths.extend(repo.glob(".scratch/*/solve-records/*.md"))
    return [parse_record(path) for path in sorted(paths)]


def ref_matches(record):
    for ref_key, sha_key in (("base", "base_sha"), ("head", "head_sha")):
        result = run_git(repo, "rev-parse", "--verify", record[ref_key], check=False)
        if result.returncode != 0:
            return False, f"{record[ref_key]} missing"
        if result.stdout.strip() != record[sha_key]:
            return False, f"{ref_key} sha mismatch"
    return True, ""


def is_true(value):
    return str(value).lower() == "true"


def has_low_risk_exception(record):
    notes = record["notes"]
    required_evidence = [
        "low-risk",
        "no meaningful automated check exists",
        "no manual-review trigger",
        "evidence:",
    ]
    return all(fragment in notes for fragment in required_evidence)


def dashboard(records):
    buckets = {
        "ready": [],
        "manual": [],
        "cleanup": [],
        "recent": [],
        "stale_or_malformed": [],
    }
    for record in records:
        if record.get("malformed"):
            buckets["stale_or_malformed"].append(record["path"])
            continue
        if record.get("summary_status") and record["summary_status"] != record["state"]:
            buckets["stale_or_malformed"].append(record["path"] + ":body/frontmatter status conflict")
            continue
        refs_ok, reason = ref_matches(record)
        if not refs_ok and record["state"] == "open":
            buckets["stale_or_malformed"].append(record["path"] + ":" + reason)
            continue
        if record["state"] in {"merged", "closed"} and not is_true(record["cleanup_done"]):
            buckets["cleanup"].append(record["id"])
            continue
        if record["state"] == "merged":
            buckets["recent"].append(record["id"])
            continue
        unavailable_low_risk = record["checks"] == "unavailable" and has_low_risk_exception(record)
        if record["merge"] == "ready" and (record["checks"] == "passed" or unavailable_low_risk):
            buckets["ready"].append(record["id"])
        else:
            buckets["manual"].append(record["id"])
    return buckets


def select(records, query):
    query = query.lower()
    matches = []
    for record in records:
        if record.get("malformed"):
            continue
        fields = [
            record["id"],
            record["path"],
            record["head"],
            record.get("title", ""),
            " ".join(record.get("issues", [])),
            section(record["text"], "Changes"),
        ]
        if all(part in " ".join(fields).lower() for part in query.split()):
            matches.append(record["id"])
    return matches


def can_merge(record):
    if record.get("malformed"):
        return False
    refs_ok, _ = ref_matches(record)
    if not refs_ok:
        return False
    if record["state"] != "open":
        return False
    if record["merge"] != "ready":
        return False
    if record["checks"] != "passed":
        return record["checks"] == "unavailable" and has_low_risk_exception(record)
    return True


def can_revalidate_base_only(record, live_base_sha, recorded_base_is_ancestor, preflight_clean, checks_rerun):
    if record.get("malformed"):
        return False
    head_result = run_git(repo, "rev-parse", "--verify", record["head"], check=False)
    if head_result.returncode != 0 or head_result.stdout.strip() != record["head_sha"]:
        return False
    if record["base_sha"] == live_base_sha:
        return True
    if not recorded_base_is_ancestor or not preflight_clean:
        return False
    if record["checks"] == "passed":
        return checks_rerun
    if record["checks"] == "unavailable":
        return has_low_risk_exception(record)
    return False


def close_record(record, reason):
    if record.get("malformed"):
        return None
    return {
        "state": "closed",
        "closed_at": "2026-07-01T16:30:00+08:00",
        "reason": reason,
        "issue_state_changed": False,
        "cleanup_attempted": False,
    }


def remote_boundary(record):
    if record.get("external_provider") and record.get("external_url"):
        return "remote primary"
    return "local primary"


def registered_worktrees():
    output = run_git(repo, "worktree", "list", "--porcelain").stdout.splitlines()
    paths = []
    for line in output:
        if line.startswith("worktree "):
            paths.append(Path(line.split(" ", 1)[1]).resolve())
    return paths


def cleanup_refusal(record, registered=None, common_dir_for=common_dir):
    worktree = (repo / record["worktree"]).resolve()
    if worktree == repo.resolve():
        return "worktree is repo root"
    if registered is None:
        registered = registered_worktrees()
    if worktree not in registered:
        return "unregistered worktree"
    if common_dir_for(repo) != common_dir_for(worktree):
        return "common dir mismatch"
    branch = run_git(worktree, "branch", "--show-current").stdout.strip()
    if branch != record["head"]:
        return "branch mismatch"
    if run_git(worktree, "status", "--short").stdout.strip():
        return "dirty worktree"
    merged = run_git(repo, "merge-base", "--is-ancestor", record["head"], record["base"], check=False)
    if merged.returncode != 0:
        return "branch is not merged"
    return ""


def finalize_attempt(finished, checks, human_review, low_risk_unavailable=False):
    if not finished:
        return None
    if checks == "failed":
        return None
    if human_review:
        merge = "manual required"
    elif checks == "unavailable" and not low_risk_unavailable:
        merge = "manual required"
    else:
        merge = "ready"
    return {
        "record_created": True,
        "issue_state": "completed",
        "issue_backlink_only": True,
        "merge": merge,
        "auto_merge_eligible": merge == "ready",
    }


def can_merge_without_live_verify(record):
    if record.get("malformed"):
        return False
    return (
        record["state"] == "open"
        and record["merge"] == "ready"
        and record["checks"] == "passed"
    )


def can_merge_with_weak_low_risk_exception(record):
    if record.get("malformed"):
        return False
    refs_ok, _ = ref_matches(record)
    if not refs_ok:
        return False
    if record["state"] != "open" or record["merge"] != "ready":
        return False
    if record["checks"] == "passed":
        return True
    return record["checks"] == "unavailable" and "low-risk" in record["notes"]


def unsafe_first_match_for_state_change(records, query):
    matches = select(records, query)
    return matches[0] if matches else None


def explicit_set_matches(records, query):
    query = query.lower()
    if "all" not in query:
        return []
    if "low-risk" in query:
        return [
            record["id"]
            for record in records
            if not record.get("malformed") and "low-risk" in record["notes"]
        ]
    return []


records = discover()
by_id = {record.get("id", record["path"]): record for record in records}
buckets = dashboard(records)
issue_text = (repo / ".scratch/caption/issues/01.md").read_text(encoding="utf-8")

assert any(path.startswith(".scratch/caption/solve-records/") for path in [r["path"] for r in records])
assert any(path.startswith(".scratch/solve-records/") for path in [r["path"] for r in records])

assert "20260701-1432-caption-fix" in buckets["ready"], buckets
assert "20260701-1500-manual-contract" in buckets["manual"], buckets
assert any("stale-ref" in item for item in buckets["stale_or_malformed"]), buckets
assert any("sha-drift" in item for item in buckets["stale_or_malformed"]), buckets
assert any("malformed" in item for item in buckets["stale_or_malformed"]), buckets
assert any("body-conflict" in item for item in buckets["stale_or_malformed"]), buckets
assert "20260701-1510-dirty-cleanup" in buckets["cleanup"], buckets
assert "20260701-1515-unregistered-cleanup" in buckets["cleanup"], buckets
assert "20260701-1520-unmerged-cleanup" in buckets["cleanup"], buckets
assert "20260701-1530-branch-mismatch" in buckets["cleanup"], buckets
assert "20260701-1531-branch-mismatch-real" in buckets["cleanup"], buckets
assert "20260701-1540-recent-merged" in buckets["recent"], buckets
assert "20260701-1545-low-risk-unavailable" in buckets["ready"], buckets
assert "20260701-1546-weak-low-risk" in buckets["manual"], buckets

assert select(records, "20260701-1432-caption-fix") == ["20260701-1432-caption-fix"]
assert select(records, ".scratch/caption/solve-records/20260701-1432-caption-fix.md") == ["20260701-1432-caption-fix"]
assert select(records, ".scratch/caption/issues/01.md")
assert select(records, "solve/20260701-1432-caption-fix") == ["20260701-1432-caption-fix"]
assert "20260701-1432-caption-fix" in select(records, "caption")
assert select(records, "caption fix") == ["20260701-1432-caption-fix"]

low_risk_set = explicit_set_matches(records, "ship all the low-risk ones")
assert low_risk_set == ["20260701-1545-low-risk-unavailable", "20260701-1546-weak-low-risk"], low_risk_set
assert [
    record_id for record_id in low_risk_set if can_merge(by_id[record_id])
] == ["20260701-1545-low-risk-unavailable"]

assert can_merge(by_id["20260701-1432-caption-fix"]) is True
assert can_merge(by_id["20260701-1500-manual-contract"]) is False
assert can_merge(by_id["20260701-1505-stale-ref"]) is False
assert can_merge(by_id["20260701-1506-sha-drift"]) is False
assert can_merge(by_id["20260701-1545-low-risk-unavailable"]) is True
assert can_merge(by_id["20260701-1546-weak-low-risk"]) is False

advanced_base_sha = "f" * 40
assert can_revalidate_base_only(
    by_id["20260701-1432-caption-fix"],
    advanced_base_sha,
    recorded_base_is_ancestor=True,
    preflight_clean=True,
    checks_rerun=True,
) is True
assert can_revalidate_base_only(
    by_id["20260701-1432-caption-fix"],
    advanced_base_sha,
    recorded_base_is_ancestor=False,
    preflight_clean=True,
    checks_rerun=True,
) is False
assert can_revalidate_base_only(
    by_id["20260701-1432-caption-fix"],
    advanced_base_sha,
    recorded_base_is_ancestor=True,
    preflight_clean=True,
    checks_rerun=False,
) is False
assert can_revalidate_base_only(
    by_id["20260701-1506-sha-drift"],
    advanced_base_sha,
    recorded_base_is_ancestor=True,
    preflight_clean=True,
    checks_rerun=True,
) is False

assert cleanup_refusal(by_id["20260701-1510-dirty-cleanup"]) == "dirty worktree"
assert cleanup_refusal(by_id["20260701-1515-unregistered-cleanup"]) == "unregistered worktree"
assert cleanup_refusal(by_id["20260701-1530-branch-mismatch"]) == "worktree is repo root"
assert cleanup_refusal(by_id["20260701-1531-branch-mismatch-real"]) == "branch mismatch"
assert cleanup_refusal(by_id["20260701-1520-unmerged-cleanup"]) == "branch is not merged"

dirty_cleanup = by_id["20260701-1510-dirty-cleanup"]
dirty_worktree = (repo / dirty_cleanup["worktree"]).resolve()


def synthetic_common_dir(path):
    path = Path(path).resolve()
    if path == repo.resolve():
        return Path("/synthetic/repo-common")
    if path == dirty_worktree:
        return Path("/synthetic/foreign-common")
    return common_dir(path)


common_dir_mismatch_guard = (
    cleanup_refusal(
        dirty_cleanup,
        registered=[dirty_worktree],
        common_dir_for=synthetic_common_dir,
    )
    == "common dir mismatch"
)
assert common_dir_mismatch_guard

assert "Status: completed" in issue_text
assert "../solve-records/20260701-1432-caption-fix.md" in issue_text
assert "auto-merged" not in issue_text

success = finalize_attempt(finished=True, checks="passed", human_review=False)
assert success and success["record_created"]
assert success["issue_state"] == "completed"
assert success["issue_backlink_only"] is True
assert success["auto_merge_eligible"] is True

assert finalize_attempt(finished=True, checks="failed", human_review=False) is None

unavailable = finalize_attempt(finished=True, checks="unavailable", human_review=False)
assert unavailable and unavailable["merge"] == "manual required"
assert unavailable["auto_merge_eligible"] is False

human_required = finalize_attempt(finished=True, checks="passed", human_review=True)
assert human_required and human_required["merge"] == "manual required"
assert human_required["auto_merge_eligible"] is False

closed = close_record(by_id["20260701-1555-abandoned"], "candidate replaced")
assert closed and closed["state"] == "closed"
assert closed["issue_state_changed"] is False
assert closed["cleanup_attempted"] is False

assert remote_boundary(by_id["20260701-1600-remote-pr"]) == "remote primary"

ablation = {
    "without_live_verify_stale_ref_would_reach_merge": (
        can_merge_without_live_verify(by_id["20260701-1505-stale-ref"])
        and not can_merge(by_id["20260701-1505-stale-ref"])
    ),
    "without_live_verify_sha_drift_would_reach_merge": (
        can_merge_without_live_verify(by_id["20260701-1506-sha-drift"])
        and not can_merge(by_id["20260701-1506-sha-drift"])
    ),
    "without_low_risk_evidence_guard_weak_exception_would_auto_merge": (
        can_merge_with_weak_low_risk_exception(by_id["20260701-1546-weak-low-risk"])
        and not can_merge(by_id["20260701-1546-weak-low-risk"])
    ),
    "without_selector_confirmation_short_query_is_ambiguous": (
        len(select(records, "caption")) > 1
        and unsafe_first_match_for_state_change(records, "caption") is not None
    ),
    "without_explicit_set_processing_valid_low_risk_member_is_blocked_by_weak_member": (
        len(low_risk_set) == 2
        and [record_id for record_id in low_risk_set if can_merge(by_id[record_id])]
        == ["20260701-1545-low-risk-unavailable"]
    ),
    "without_base_only_revalidation_forward_base_blocks_valid_candidate": (
        can_revalidate_base_only(
            by_id["20260701-1432-caption-fix"],
            advanced_base_sha,
            recorded_base_is_ancestor=True,
            preflight_clean=True,
            checks_rerun=True,
        )
    ),
    "without_cleanup_registration_guard_unregistered_path_is_targeted": (
        cleanup_refusal(by_id["20260701-1515-unregistered-cleanup"]) == "unregistered worktree"
    ),
    "without_cleanup_clean_guard_dirty_worktree_is_targeted": (
        cleanup_refusal(by_id["20260701-1510-dirty-cleanup"]) == "dirty worktree"
    ),
    "without_cleanup_merged_guard_unmerged_branch_is_deleted": (
        cleanup_refusal(by_id["20260701-1520-unmerged-cleanup"]) == "branch is not merged"
    ),
    "without_cleanup_repo_root_guard_invocation_checkout_is_targeted": (
        cleanup_refusal(by_id["20260701-1530-branch-mismatch"]) == "worktree is repo root"
    ),
    "without_cleanup_common_dir_guard_foreign_registered_path_is_targeted": common_dir_mismatch_guard,
    "without_cleanup_branch_guard_wrong_worktree_branch_is_targeted": (
        cleanup_refusal(by_id["20260701-1531-branch-mismatch-real"]) == "branch mismatch"
    ),
    "without_body_frontmatter_conflict_detection_stale_summary_looks_ready": (
        any("body-conflict" in item for item in buckets["stale_or_malformed"])
    ),
}
assert all(ablation.values()), ablation

print("solve-records fixture passed")
PY

if [[ ! -d "$TMPDIR_ROOT/wt-dirty" ]]; then
  echo "refusal fixture: dirty worktree was removed" >&2
  exit 1
fi
if [[ ! -d "$TMPDIR_ROOT/wt-unmerged" ]]; then
  echo "refusal fixture: unmerged worktree was removed" >&2
  exit 1
fi
if [[ ! -d "$TMPDIR_ROOT/wt-branch-mismatch" ]]; then
  echo "refusal fixture: branch mismatch worktree was removed" >&2
  exit 1
fi
git -C "$REPO" rev-parse --verify solve/20260701-1510-dirty-cleanup >/dev/null
git -C "$REPO" rev-parse --verify solve/20260701-1520-unmerged-cleanup >/dev/null
git -C "$REPO" rev-parse --verify solve/20260701-1530-branch-mismatch >/dev/null
git -C "$REPO" rev-parse --verify solve/20260701-1531-branch-mismatch-target >/dev/null
git -C "$REPO" rev-parse --verify solve/20260701-1532-branch-mismatch-worktree >/dev/null

SAFE_REPO="$TMPDIR_ROOT/cleanup-project"
SAFE_WORKTREE="$TMPDIR_ROOT/wt-safe-cleanup"
SAFE_BRANCH="solve/20260701-1600-safe-cleanup"

git init -b master "$SAFE_REPO" >/dev/null
git -C "$SAFE_REPO" config user.email "solve-records@example.test"
git -C "$SAFE_REPO" config user.name "Solve Records Test"
printf 'base\n' >"$SAFE_REPO/app.txt"
git -C "$SAFE_REPO" add app.txt
git -C "$SAFE_REPO" commit -m "base" >/dev/null

git -C "$SAFE_REPO" checkout -b "$SAFE_BRANCH" master >/dev/null 2>&1
printf 'safe cleanup\n' >"$SAFE_REPO/safe.txt"
git -C "$SAFE_REPO" add safe.txt
git -C "$SAFE_REPO" commit -m "safe cleanup candidate" >/dev/null
git -C "$SAFE_REPO" checkout master >/dev/null 2>&1
git -C "$SAFE_REPO" merge --no-ff "$SAFE_BRANCH" -m "merge safe cleanup candidate" >/dev/null
git -C "$SAFE_REPO" worktree add "$SAFE_WORKTREE" "$SAFE_BRANCH" >/dev/null 2>&1

registered_path_found="$(
  git -C "$SAFE_REPO" worktree list --porcelain |
    awk '/^worktree / {print substr($0, 10)}' |
    while IFS= read -r path; do
      if [[ "$(realpath "$path")" == "$(realpath "$SAFE_WORKTREE")" ]]; then
        printf 'yes'
        break
      fi
    done
)"
if [[ "$registered_path_found" != "yes" ]]; then
  echo "safe cleanup fixture: worktree is not registered" >&2
  exit 1
fi
if [[ "$(common_dir "$SAFE_REPO")" != "$(common_dir "$SAFE_WORKTREE")" ]]; then
  echo "safe cleanup fixture: common dir mismatch" >&2
  exit 1
fi
if [[ "$(git -C "$SAFE_WORKTREE" branch --show-current)" != "$SAFE_BRANCH" ]]; then
  echo "safe cleanup fixture: branch mismatch" >&2
  exit 1
fi
if [[ -n "$(git -C "$SAFE_WORKTREE" status --short)" ]]; then
  echo "safe cleanup fixture: worktree should be clean" >&2
  exit 1
fi
git -C "$SAFE_REPO" merge-base --is-ancestor "$SAFE_BRANCH" master

git -C "$SAFE_REPO" worktree remove "$SAFE_WORKTREE"
git -C "$SAFE_REPO" worktree prune
git -C "$SAFE_REPO" branch -d "$SAFE_BRANCH" >/dev/null

if [[ -e "$SAFE_WORKTREE" ]]; then
  echo "safe cleanup fixture: worktree path still exists" >&2
  exit 1
fi
if git -C "$SAFE_REPO" rev-parse --verify "$SAFE_BRANCH" >/dev/null 2>&1; then
  echo "safe cleanup fixture: branch still exists" >&2
  exit 1
fi

echo "solve-records safe cleanup fixture passed"

MERGE_REPO="$TMPDIR_ROOT/merge-project"
MERGE_BRANCH="solve/20260701-1610-safe-merge"

git init -b master "$MERGE_REPO" >/dev/null
git -C "$MERGE_REPO" config user.email "solve-records@example.test"
git -C "$MERGE_REPO" config user.name "Solve Records Test"
printf 'base\n' >"$MERGE_REPO/app.txt"
git -C "$MERGE_REPO" add app.txt
git -C "$MERGE_REPO" commit -m "base" >/dev/null

git -C "$MERGE_REPO" checkout -b "$MERGE_BRANCH" master >/dev/null 2>&1
printf 'safe merge\n' >"$MERGE_REPO/merged.txt"
git -C "$MERGE_REPO" add merged.txt
git -C "$MERGE_REPO" commit -m "safe merge candidate" >/dev/null
MERGE_HEAD_SHA="$(git -C "$MERGE_REPO" rev-parse "$MERGE_BRANCH")"
git -C "$MERGE_REPO" checkout master >/dev/null 2>&1

if [[ -n "$(git -C "$MERGE_REPO" status --short)" ]]; then
  echo "safe merge fixture: base worktree should be clean" >&2
  exit 1
fi
git -C "$MERGE_REPO" rev-parse --verify master >/dev/null
git -C "$MERGE_REPO" rev-parse --verify "$MERGE_BRANCH" >/dev/null
if git -C "$MERGE_REPO" merge-base --is-ancestor "$MERGE_BRANCH" master; then
  echo "safe merge fixture: candidate should not be merged yet" >&2
  exit 1
fi

git -C "$MERGE_REPO" merge --no-ff "$MERGE_BRANCH" -m "merge safe candidate" >/dev/null

if [[ "$(cat "$MERGE_REPO/merged.txt")" != "safe merge" ]]; then
  echo "safe merge fixture: merged file missing from base" >&2
  exit 1
fi
git -C "$MERGE_REPO" merge-base --is-ancestor "$MERGE_HEAD_SHA" master

echo "solve-records safe merge fixture passed"
