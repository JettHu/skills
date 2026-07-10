#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SOLVE_RECORDS_SCRIPT="$REPO_ROOT/skills/engineering/solve-records/scripts/solve-records.py"
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
  mkdir -p "$(dirname "$REPO/$file")"
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
CONFIG_MISSING_HEAD="$(make_branch solve/20260707-1519-config-missing-disposition config/direct-mode.env config-missing)"
CONFIG_PREMERGE_HEAD="$(make_branch solve/20260707-1520-config-premerge config/direct-mode-premerge.env config-premerge)"
CONFIG_POST_ACTIVATION_HEAD="$(make_branch solve/20260707-1521-config-post-activation config/direct-mode-post.env config-post)"
REVIEW_BLOCKED_HEAD="$(make_branch solve/20260708-1000-review-blocked review/blocked.txt review-blocked)"
ACCEPTANCE_PENDING_HEAD="$(make_branch solve/20260707-1530-acceptance-pending acceptance/pending.txt acceptance-pending)"
ACCEPTANCE_PREMERGE_HEAD="$(make_branch solve/20260707-1531-acceptance-premerge acceptance/premerge.txt acceptance-premerge)"
CLOSE_HEAD="$(make_branch solve/20260701-1555-abandoned abandoned.txt abandoned)"
REMOTE_HEAD="$(make_branch solve/20260701-1600-remote-pr remote.txt remote)"
CONFLICT_HEAD="$(make_branch solve/20260701-1605-body-conflict body-conflict.txt body-conflict)"
ADOPTED_CURRENT_HEAD="$(make_branch feature/adopted-current adopted-current.txt adopted-current)"
PROTECTED_BASELINE_HEAD="$(make_branch solve/20260703-1745-protected-baseline protected-baseline.txt protected-baseline)"

git -C "$REPO" checkout -b feature/adopted-integration master >/dev/null 2>&1
git -C "$REPO" checkout -b solve/20260703-1745-group-a feature/adopted-integration >/dev/null 2>&1
printf 'group a\n' >"$REPO/group-a.txt"
git -C "$REPO" add group-a.txt
git -C "$REPO" commit -m "group a candidate" >/dev/null
GROUP_A_HEAD="$(git -C "$REPO" rev-parse solve/20260703-1745-group-a)"
git -C "$REPO" checkout -b solve/20260703-1745-group-b feature/adopted-integration >/dev/null 2>&1
printf 'group b\n' >"$REPO/group-b.txt"
git -C "$REPO" add group-b.txt
git -C "$REPO" commit -m "group b candidate" >/dev/null
GROUP_B_HEAD="$(git -C "$REPO" rev-parse solve/20260703-1745-group-b)"
git -C "$REPO" checkout feature/adopted-integration >/dev/null 2>&1
git -C "$REPO" merge --no-ff solve/20260703-1745-group-a -m "integrate group a" >/dev/null
git -C "$REPO" merge --no-ff solve/20260703-1745-group-b -m "integrate group b" >/dev/null
ADOPTED_INTEGRATION_HEAD="$(git -C "$REPO" rev-parse feature/adopted-integration)"
git -C "$REPO" checkout master >/dev/null 2>&1

git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-ready" solve/20260701-1432-caption-fix >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-dirty" solve/20260701-1510-dirty-cleanup >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-unmerged" solve/20260701-1520-unmerged-cleanup >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-branch-mismatch" solve/20260701-1532-branch-mismatch-worktree >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-adopted-current" feature/adopted-current >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-protected-baseline" solve/20260703-1745-protected-baseline >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-adopted-integration" feature/adopted-integration >/dev/null 2>&1
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
cat >"$REPO/.scratch/caption/issues/03-adopted-current.md" <<'EOF'
Status: completed

# Adopted current issue

## Comments

### Solve Record

- `../solve-records/20260703-1745-adopted-current.md`
EOF

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
  local cleanup_resource="${13:-pending}"
  local rollout_note=""
  if [[ "$notes" != *"Rollout/config disposition:"* ]]; then
    rollout_note="- Rollout/config disposition: none; no rollout/config/operator action is needed."
  fi
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

## Review
Post-Execution Review: passed
- Fixture review passed.

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
Cleanup: $cleanup_resource

## Notes
- $notes
$rollout_note
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

for n in $(seq 1 11); do
  printf -v minute "%02d" "$n"
  recent_record="$REPO/.scratch/solve-records/20260701-17${minute}-recent-${minute}.md"
  write_record "$recent_record" \
    "20260701-17${minute}-recent-${minute}" merged solve/20260701-1540-recent-merged "$RECENT_HEAD" \
    ".scratch/caption/issues/01.md" "." true "Recent merged ${minute}" passed "auto-merged"
  python3 - "$recent_record" "$minute" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
minute = sys.argv[2]
text = path.read_text(encoding="utf-8")
text = text.replace(
    "cleanup_done: true\n---",
    f"cleanup_done: true\nmerged_at: 2026-07-01T17:{minute}:00+08:00\n---",
    1,
)
path.write_text(text, encoding="utf-8")
PY
done

newer_merged_at_record="$REPO/.scratch/solve-records/20260701-1501-recent-newer-merged-at.md"
write_record "$newer_merged_at_record" \
  "20260701-1501-recent-newer-merged-at" merged solve/20260701-1540-recent-merged "$RECENT_HEAD" \
  ".scratch/caption/issues/01.md" "." true "Recent newer merged_at" passed "auto-merged"
python3 - "$newer_merged_at_record" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "cleanup_done: true\n---",
    "cleanup_done: true\nmerged_at: 2026-07-01T18:00:00+08:00\n---",
    1,
)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/solve-records/20260701-1545-low-risk-unavailable.md" \
  "20260701-1545-low-risk-unavailable" open solve/20260701-1545-low-risk-unavailable "$LOW_RISK_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Low risk unavailable check" unavailable ready \
  "low-risk trivial docs-only change; no meaningful automated check exists; no manual-review trigger applies; evidence: record-format-only fixture"

write_record "$REPO/.scratch/solve-records/20260701-1546-weak-low-risk.md" \
  "20260701-1546-weak-low-risk" open solve/20260701-1546-weak-low-risk "$WEAK_LOW_RISK_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Weak low risk unavailable check" unavailable ready \
  "low-risk"

write_record "$REPO/.scratch/solve-records/20260707-1519-config-missing-disposition.md" \
  "20260707-1519-config-missing-disposition" open solve/20260707-1519-config-missing-disposition "$CONFIG_MISSING_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Config signal missing disposition" passed ready
python3 - "$REPO/.scratch/solve-records/20260707-1519-config-missing-disposition.md" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("\n- Rollout/config disposition: none; no rollout/config/operator action is needed.", "", 1)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/solve-records/20260707-1520-config-premerge.md" \
  "20260707-1520-config-premerge" open solve/20260707-1520-config-premerge "$CONFIG_PREMERGE_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Config pre-merge action" passed ready \
  "Rollout/config disposition: pre-merge action required; operator must enable required config before merge."

write_record "$REPO/.scratch/solve-records/20260707-1521-config-post-activation.md" \
  "20260707-1521-config-post-activation" open solve/20260707-1521-config-post-activation "$CONFIG_POST_ACTIVATION_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Config post-merge activation" passed ready \
  "Rollout/config disposition: post-merge activation required; code merge is safe because the default remains disabled. Activation: enable DIRECT_MODE after merge. Smoke: run the direct-mode staging request. Rollback: disable DIRECT_MODE."

write_record "$REPO/.scratch/solve-records/20260708-1000-review-blocked.md" \
  "20260708-1000-review-blocked" open solve/20260708-1000-review-blocked "$REVIEW_BLOCKED_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Post-execution review blocked" passed ready
python3 - "$REPO/.scratch/solve-records/20260708-1000-review-blocked.md" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "Post-Execution Review: passed\n- Fixture review passed.",
    "Post-Execution Review: blocked\n- Review found an unresolved acceptance gap.",
    1,
)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/solve-records/20260707-1530-acceptance-pending.md" \
  "20260707-1530-acceptance-pending" open solve/20260707-1530-acceptance-pending "$ACCEPTANCE_PENDING_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Acceptance pending candidate" passed "manual required" \
  "human acceptance pending; Rollout/config disposition: none; no rollout/config/operator action is needed."

write_record "$REPO/.scratch/solve-records/20260707-1531-acceptance-premerge.md" \
  "20260707-1531-acceptance-premerge" open solve/20260707-1531-acceptance-premerge "$ACCEPTANCE_PREMERGE_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Acceptance still manual candidate" passed "manual required" \
  "Rollout/config disposition: pre-merge action required; operator must enable required config before merge."

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

write_record "$REPO/.scratch/caption/solve-records/20260703-1745-adopted-current.md" \
  "20260703-1745-adopted-current" open feature/adopted-current "$ADOPTED_CURRENT_HEAD" \
  ".scratch/caption/issues/03-adopted-current.md" "../wt-adopted-current" true "Adopted current dev branch" passed "manual required" \
  "adopted worktree and candidate branch are user-owned; development environment validation pending" \
  "done; adopted worktree and candidate branch are user-owned"

write_record "$REPO/.scratch/caption/solve-records/20260703-1745-adopted-cleanup.md" \
  "20260703-1745-adopted-cleanup" merged feature/adopted-current "$ADOPTED_CURRENT_HEAD" \
  ".scratch/caption/issues/03-adopted-current.md" "../wt-adopted-current" true "Adopted cleanup preserved" passed "auto-merged" \
  "adopted worktree and candidate branch are user-owned" \
  "done; adopted worktree and candidate branch are user-owned"

write_record "$REPO/.scratch/caption/solve-records/20260703-1745-protected-baseline.md" \
  "20260703-1745-protected-baseline" open solve/20260703-1745-protected-baseline "$PROTECTED_BASELINE_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-protected-baseline" false "Protected baseline isolated fallback" passed ready

write_record "$REPO/.scratch/caption/solve-records/20260703-1745-adopted-integration.md" \
  "20260703-1745-adopted-integration" open feature/adopted-integration "$ADOPTED_INTEGRATION_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-adopted-integration" false "Adopted integration target" passed ready \
  "temporary group branches integrated into adopted candidate branch"

cat >"$REPO/.scratch/solve-records/20260701-1550-malformed.md" <<'EOF'
# Missing frontmatter
This malformed record should not hide valid records.
EOF

write_record "$REPO/.scratch/solve-records/20260701-1551-wrong-kind.md" \
  "20260701-1551-wrong-kind" open solve/20260701-1432-caption-fix "$READY_HEAD" \
  ".scratch/caption/issues/01.md" "../wt-ready" false "Wrong kind" passed ready
python3 - "$REPO/.scratch/solve-records/20260701-1551-wrong-kind.md" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("kind: solve_record", "kind: issue_note", 1)
path.write_text(text, encoding="utf-8")
PY

python3 - "$REPO" "$SOLVE_RECORDS_SCRIPT" <<'PY'
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
tool = Path(sys.argv[2]).resolve()

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

COMMON_DIR_CACHE = {}
REF_CACHE = {}
REF_MAP_CACHE = {}
REGISTERED_WORKTREES_CACHE = None


def run_git(cwd, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr.strip() or "git failed")
    return result


def common_dir_from_git_marker(cwd):
    marker = cwd / ".git"
    if marker.is_dir():
        return marker.resolve()
    if not marker.is_file():
        return None

    content = marker.read_text(encoding="utf-8").strip()
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
    return path


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
    if data["kind"] != "solve_record":
        return {"path": rel, "malformed": f"invalid kind: {data['kind']}", "text": text}
    data["checks"] = status_line(section(text, "Checks"))
    data["review"] = post_execution_review_line(section(text, "Review"))
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


def ref_map():
    if "value" in REF_MAP_CACHE:
        return REF_MAP_CACHE["value"]
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
    REF_MAP_CACHE["value"] = refs
    return refs


def resolve_ref(ref):
    if ref in REF_CACHE:
        return REF_CACHE[ref]
    refs = ref_map()
    if ref in refs:
        REF_CACHE[ref] = (0, refs[ref])
        return REF_CACHE[ref]
    result = run_git(repo, "rev-parse", "--verify", ref, check=False)
    REF_CACHE[ref] = (result.returncode, result.stdout.strip())
    return REF_CACHE[ref]


def ref_matches(record):
    for ref_key, sha_key in (("base", "base_sha"), ("head", "head_sha")):
        returncode, live_sha = resolve_ref(record[ref_key])
        if returncode != 0:
            return False, f"{record[ref_key]} missing"
        if live_sha != record[sha_key]:
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


ROLLOUT_CONFIG_DISPOSITIONS = {
    "none",
    "pre-merge action required",
    "post-merge activation required",
}


POST_EXECUTION_REVIEW_STATUSES = {
    "passed",
    "manual gate",
    "blocked",
}


def post_execution_review_line(block):
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("post-execution review:"):
            return stripped.split(":", 1)[1].strip().lower()
    return ""


def post_execution_review_gate_reason(record):
    review = record.get("review", "")
    if not review:
        return "missing Post-Execution Review outcome"
    if review not in POST_EXECUTION_REVIEW_STATUSES:
        return "unknown Post-Execution Review outcome"
    if review != "passed":
        return f"Post-Execution Review is {review}"
    return ""


def rollout_config_block(record):
    return (section(record["text"], "Merge") + "\n" + section(record["text"], "Notes")).lower()


def rollout_config_disposition(record):
    prefixes = (
        "rollout/config disposition:",
        "rollout config disposition:",
        "rollout disposition:",
        "config disposition:",
    )
    for line in rollout_config_block(record).splitlines():
        normalized = line.strip().lstrip("-*").strip()
        for prefix in prefixes:
            if prefix not in normalized:
                continue
            value = normalized.split(prefix, 1)[1].strip()
            for disposition in ROLLOUT_CONFIG_DISPOSITIONS:
                if value == disposition or value.startswith((disposition + ";", disposition + ".", disposition + ",")):
                    return disposition
            return "unknown"
    return ""


def rollout_config_gate_reason(record):
    disposition = rollout_config_disposition(record)
    if not disposition:
        return "missing rollout/config disposition"
    if disposition == "unknown":
        return "unknown rollout/config disposition"
    if disposition == "pre-merge action required":
        return "rollout/config pre-merge action required"
    if disposition == "post-merge activation required":
        block = rollout_config_block(record)
        required = [
            (("code merge is safe", "code merge safe"), "code-merge-safety rationale"),
            (("activation:",), "activation action"),
            (("rollback:", "disable:"), "rollback or disable note"),
        ]
        for fragments, label in required:
            if not any(fragment in block for fragment in fragments):
                return f"post-merge activation missing {label}"
        if "smoke:" not in block and "validation:" not in block:
            return "post-merge activation missing smoke or validation check"
    return ""


def recent_sort_key(record_or_id):
    if isinstance(record_or_id, str):
        record = by_id[record_or_id]
    else:
        record = record_or_id
    return (
        record.get("merged_at") or record.get("created_at") or "",
        record.get("id") or "",
        record.get("path") or "",
    )


def dashboard(records):
    buckets = {
        "ready": [],
        "manual": [],
        "cleanup": [],
        "recent": [],
        "stale_or_malformed": [],
    }
    recent = []
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
            recent.append(record["id"])
            continue
        unavailable_low_risk = record["checks"] == "unavailable" and has_low_risk_exception(record)
        rollout_ready = not rollout_config_gate_reason(record)
        review_ready = not post_execution_review_gate_reason(record)
        if (
            record["merge"] == "ready"
            and rollout_ready
            and review_ready
            and (record["checks"] == "passed" or unavailable_low_risk)
        ):
            buckets["ready"].append(record["id"])
        else:
            buckets["manual"].append(record["id"])
    buckets["recent"] = sorted(recent, key=recent_sort_key, reverse=True)[:10]
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
    if post_execution_review_gate_reason(record):
        return False
    if rollout_config_gate_reason(record):
        return False
    if record["checks"] != "passed":
        return record["checks"] == "unavailable" and has_low_risk_exception(record)
    return True


def can_revalidate_base_only(record, live_base_sha, recorded_base_is_ancestor, preflight_clean, checks_rerun):
    if record.get("malformed"):
        return False
    returncode, live_head_sha = resolve_ref(record["head"])
    if returncode != 0 or live_head_sha != record["head_sha"]:
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
    global REGISTERED_WORKTREES_CACHE
    if REGISTERED_WORKTREES_CACHE is not None:
        return REGISTERED_WORKTREES_CACHE
    output = run_git(repo, "worktree", "list", "--porcelain").stdout.splitlines()
    paths = []
    for line in output:
        if line.startswith("worktree "):
            paths.append(Path(line.split(" ", 1)[1]).resolve())
    REGISTERED_WORKTREES_CACHE = paths
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
    if post_execution_review_gate_reason(record):
        return False
    if record["checks"] == "passed":
        return True
    return record["checks"] == "unavailable" and "low-risk" in record["notes"]


def can_merge_without_rollout_config_gate(record):
    if record.get("malformed"):
        return False
    refs_ok, _ = ref_matches(record)
    if not refs_ok:
        return False
    if record["state"] != "open" or record["merge"] != "ready":
        return False
    if post_execution_review_gate_reason(record):
        return False
    if record["checks"] != "passed":
        return record["checks"] == "unavailable" and has_low_risk_exception(record)
    return True


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


def run_tool(*args):
    result = subprocess.run(
        [sys.executable, str(tool), *args, "--repo", str(repo), "--json"],
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return json.loads(result.stdout)


tool_spec = importlib.util.spec_from_file_location("solve_records_tool", str(tool))
tool_module = importlib.util.module_from_spec(tool_spec)
tool_spec.loader.exec_module(tool_module)
tool_records = tool_module.discover(repo)
tool_by_id = {record.get("id", record["path"]): record for record in tool_records}
tool_dashboard = tool_module.dashboard(repo, tool_records)
tool_dashboard_cli = run_tool("dashboard")
tool_select = {"matches": tool_module.select_records(tool_records, "caption fix")}
tool_merge_gate_ready = tool_module.merge_gate(repo, tool_by_id["20260701-1432-caption-fix"])
tool_merge_gate_weak = tool_module.merge_gate(repo, tool_by_id["20260701-1546-weak-low-risk"])
tool_merge_gate_config_missing = tool_module.merge_gate(repo, tool_by_id["20260707-1519-config-missing-disposition"])
tool_merge_gate_config_premerge = tool_module.merge_gate(repo, tool_by_id["20260707-1520-config-premerge"])
tool_merge_gate_config_post_activation = tool_module.merge_gate(
    repo, tool_by_id["20260707-1521-config-post-activation"]
)
tool_merge_gate_review_blocked = tool_module.merge_gate(repo, tool_by_id["20260708-1000-review-blocked"])
tool_cleanup_dirty = tool_module.cleanup_plan(repo, tool_by_id["20260701-1510-dirty-cleanup"])
tool_cleanup_adopted = tool_module.cleanup_plan(repo, tool_by_id["20260703-1745-adopted-cleanup"])
tool_landing_ready = tool_module.landing_plan(repo, tool_by_id["20260701-1432-caption-fix"])


def acceptance_review_exact_path(record_path):
    path = (repo / record_path).resolve()
    record = tool_module.parse_record(repo, path)
    if record.get("state") != "open":
        return {"updated": False, "reasons": [f"state is {record.get('state')}"]}
    if record.get("merge") not in {"manual required", "ready"}:
        return {"updated": False, "reasons": [f"merge status is {record.get('merge') or '<missing>'}"]}

    candidate = dict(record)
    candidate["merge"] = "ready"
    candidate["text"] = record["text"].replace("Status: manual required", "Status: ready", 1)
    gate = tool_module.merge_gate(repo, candidate)
    if not gate["eligible"]:
        return {"updated": False, "reasons": gate["reasons"]}

    updated_text = candidate["text"].replace(
        "- fixture reason",
        "- Acceptance review passed: exact-path record, refs, checks, worktree, and manual-review triggers were verified.",
        1,
    )
    path.write_text(updated_text, encoding="utf-8")
    updated = tool_module.parse_record(repo, path)
    return {
        "updated": True,
        "state": updated["state"],
        "merge": updated["merge"],
        "cleanup_done": updated["cleanup_done"],
        "cleanup_plan": tool_module.cleanup_plan(repo, updated),
    }


acceptance_ready = acceptance_review_exact_path(".scratch/solve-records/20260707-1530-acceptance-pending.md")
acceptance_still_manual = acceptance_review_exact_path(".scratch/solve-records/20260707-1531-acceptance-premerge.md")
expected_recent = ["20260701-1501-recent-newer-merged-at"] + [
    f"20260701-17{minute:02d}-recent-{minute:02d}"
    for minute in range(11, 2, -1)
]

assert any(path.startswith(".scratch/caption/solve-records/") for path in [r["path"] for r in records])
assert any(path.startswith(".scratch/solve-records/") for path in [r["path"] for r in records])

assert "20260701-1432-caption-fix" in buckets["ready"], buckets
assert "20260701-1500-manual-contract" in buckets["manual"], buckets
assert any("stale-ref" in item for item in buckets["stale_or_malformed"]), buckets
assert any("sha-drift" in item for item in buckets["stale_or_malformed"]), buckets
assert any("malformed" in item for item in buckets["stale_or_malformed"]), buckets
assert any("wrong-kind" in item for item in buckets["stale_or_malformed"]), buckets
assert any("body-conflict" in item for item in buckets["stale_or_malformed"]), buckets
assert "20260701-1510-dirty-cleanup" in buckets["cleanup"], buckets
assert "20260701-1515-unregistered-cleanup" in buckets["cleanup"], buckets
assert "20260701-1520-unmerged-cleanup" in buckets["cleanup"], buckets
assert "20260701-1530-branch-mismatch" in buckets["cleanup"], buckets
assert "20260701-1531-branch-mismatch-real" in buckets["cleanup"], buckets
assert buckets["recent"] == expected_recent, buckets["recent"]
assert buckets["recent"][0] == "20260701-1501-recent-newer-merged-at", buckets["recent"]
assert "20260701-1540-recent-merged" not in buckets["recent"], buckets
assert "20260701-1702-recent-02" not in buckets["recent"], buckets
assert "20260701-1551-wrong-kind" not in buckets["ready"] + buckets["manual"], buckets
assert "20260701-1545-low-risk-unavailable" in buckets["ready"], buckets
assert "20260701-1546-weak-low-risk" in buckets["manual"], buckets
assert "20260707-1519-config-missing-disposition" in buckets["manual"], buckets
assert "20260707-1520-config-premerge" in buckets["manual"], buckets
assert "20260707-1521-config-post-activation" in buckets["ready"], buckets
assert "20260703-1745-adopted-current" in buckets["manual"], buckets
assert "20260703-1745-protected-baseline" in buckets["ready"], buckets
assert "20260703-1745-adopted-integration" in buckets["ready"], buckets
assert "20260703-1745-adopted-cleanup" not in buckets["cleanup"], buckets

default_isolated = by_id["20260701-1432-caption-fix"]
assert default_isolated["head"].startswith("solve/"), default_isolated

adopted_current = by_id["20260703-1745-adopted-current"]
assert adopted_current["head"] == "feature/adopted-current", adopted_current
assert not adopted_current["head"].startswith("solve/"), adopted_current
assert adopted_current["base"] == "master", adopted_current
assert adopted_current["merge"] == "manual required", adopted_current
assert "development environment validation pending" in adopted_current["notes"], adopted_current
assert run_git(
    repo,
    "show-ref",
    "--verify",
    "--quiet",
    "refs/heads/solve/20260703-1745-adopted-current",
    check=False,
).returncode != 0

protected_baseline = by_id["20260703-1745-protected-baseline"]
assert protected_baseline["base"] == "master", protected_baseline
assert protected_baseline["head"].startswith("solve/"), protected_baseline

adopted_integration = by_id["20260703-1745-adopted-integration"]
assert adopted_integration["head"] == "feature/adopted-integration", adopted_integration
assert run_git(
    repo,
    "merge-base",
    "--is-ancestor",
    "solve/20260703-1745-group-a",
    adopted_integration["head"],
    check=False,
).returncode == 0
assert run_git(
    repo,
    "merge-base",
    "--is-ancestor",
    "solve/20260703-1745-group-b",
    adopted_integration["head"],
    check=False,
).returncode == 0

assert tool_dashboard["record_count"] == len(records)
assert tool_dashboard_cli["record_count"] == len(records)
tool_recent_ids = [item["id"] for item in tool_dashboard["buckets"]["recent"]]
assert tool_recent_ids == expected_recent, tool_recent_ids
tool_ready_ids = [item["id"] for item in tool_dashboard["buckets"]["ready"]]
assert "20260701-1432-caption-fix" in tool_ready_ids, tool_dashboard["buckets"]["ready"]
assert "20260701-1545-low-risk-unavailable" in tool_ready_ids, tool_dashboard["buckets"]["ready"]
assert "20260707-1521-config-post-activation" in tool_ready_ids, tool_dashboard["buckets"]["ready"]
assert "20260707-1519-config-missing-disposition" not in tool_ready_ids, tool_dashboard["buckets"]["ready"]
assert "20260707-1520-config-premerge" not in tool_ready_ids, tool_dashboard["buckets"]["ready"]
assert "20260708-1000-review-blocked" not in tool_ready_ids, tool_dashboard["buckets"]["ready"]
assert "20260701-1551-wrong-kind" not in tool_ready_ids, tool_dashboard["buckets"]["ready"]
assert any(
    item["id"] == "20260701-1551-wrong-kind"
    and item.get("malformed") == "invalid kind: issue_note"
    for item in tool_dashboard["buckets"]["stale_or_malformed"]
), tool_dashboard["buckets"]["stale_or_malformed"]
assert any(
    item["id"] == "20260701-1546-weak-low-risk"
    for item in tool_dashboard["buckets"]["manual"]
), tool_dashboard["buckets"]["manual"]
tool_adopted = next(
    item for item in tool_dashboard["buckets"]["manual"] if item["id"] == "20260703-1745-adopted-current"
)
assert "user-owned" in tool_adopted["resource_cleanup"], tool_adopted
assert [
    item["id"] for item in tool_select["matches"]
] == ["20260701-1432-caption-fix"], tool_select
assert tool_merge_gate_ready["eligible"] is True, tool_merge_gate_ready
assert tool_merge_gate_weak["eligible"] is False, tool_merge_gate_weak
assert "unavailable checks without low-risk evidence" in tool_merge_gate_weak["reasons"]
assert tool_merge_gate_config_missing["eligible"] is False, tool_merge_gate_config_missing
assert "missing rollout/config disposition" in tool_merge_gate_config_missing["reasons"]
assert tool_merge_gate_config_premerge["eligible"] is False, tool_merge_gate_config_premerge
assert "rollout/config pre-merge action required" in tool_merge_gate_config_premerge["reasons"]
assert tool_merge_gate_config_post_activation["eligible"] is True, tool_merge_gate_config_post_activation
assert tool_merge_gate_review_blocked["eligible"] is False, tool_merge_gate_review_blocked
assert "Post-Execution Review is blocked" in tool_merge_gate_review_blocked["reasons"]
assert tool_cleanup_dirty["status"] == "blocked", tool_cleanup_dirty
assert tool_cleanup_dirty["reason"] == "dirty worktree", tool_cleanup_dirty
assert tool_cleanup_adopted["status"] == "done", tool_cleanup_adopted
assert (repo / by_id["20260703-1745-adopted-cleanup"]["worktree"]).resolve().exists()
assert resolve_ref("feature/adopted-current")[0] == 0
assert tool_landing_ready["status"] == "ready", tool_landing_ready
assert tool_landing_ready["landing_type"] == "fast-forward", tool_landing_ready
assert tool_landing_ready["landing_sha"] == by_id["20260701-1432-caption-fix"]["head_sha"], tool_landing_ready
assert "caption.txt" in tool_landing_ready["write_surface"], tool_landing_ready
assert acceptance_ready["updated"] is True, acceptance_ready
assert acceptance_ready["state"] == "open", acceptance_ready
assert acceptance_ready["merge"] == "ready", acceptance_ready
assert acceptance_ready["cleanup_done"] == "false", acceptance_ready
assert acceptance_ready["cleanup_plan"]["status"] == "not_applicable", acceptance_ready
acceptance_ready_text = (repo / ".scratch/solve-records/20260707-1530-acceptance-pending.md").read_text(
    encoding="utf-8"
)
assert "Status: ready" in acceptance_ready_text, acceptance_ready_text
assert "state: open" in acceptance_ready_text, acceptance_ready_text
assert acceptance_still_manual["updated"] is False, acceptance_still_manual
assert "rollout/config pre-merge action required" in acceptance_still_manual["reasons"], acceptance_still_manual
assert "Status: manual required" in (
    repo / ".scratch/solve-records/20260707-1531-acceptance-premerge.md"
).read_text(encoding="utf-8")

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
assert can_merge(by_id["20260707-1519-config-missing-disposition"]) is False
assert can_merge(by_id["20260707-1520-config-premerge"]) is False
assert can_merge(by_id["20260707-1521-config-post-activation"]) is True
assert can_merge(by_id["20260708-1000-review-blocked"]) is False

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
adopted_issue_text = (repo / ".scratch/caption/issues/03-adopted-current.md").read_text(encoding="utf-8")
assert "Status: completed" in adopted_issue_text
assert "../solve-records/20260703-1745-adopted-current.md" in adopted_issue_text

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
    "without_rollout_config_disposition_gate_config_signal_looks_ready": (
        can_merge_without_rollout_config_gate(by_id["20260707-1519-config-missing-disposition"])
        and not can_merge(by_id["20260707-1519-config-missing-disposition"])
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
remaining_branches="$(git -C "$REPO" for-each-ref --format='%(refname:short)' refs/heads)"
for branch in \
  solve/20260701-1510-dirty-cleanup \
  solve/20260701-1520-unmerged-cleanup \
  solve/20260701-1530-branch-mismatch \
  solve/20260701-1531-branch-mismatch-target \
  solve/20260701-1532-branch-mismatch-worktree; do
  if ! grep -Fxq "$branch" <<<"$remaining_branches"; then
    echo "refusal fixture: branch was removed: $branch" >&2
    exit 1
  fi
done

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
if git -C "$SAFE_REPO" show-ref --verify --quiet "refs/heads/$SAFE_BRANCH"; then
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
git -C "$MERGE_REPO" show-ref --verify --quiet refs/heads/master
git -C "$MERGE_REPO" show-ref --verify --quiet "refs/heads/$MERGE_BRANCH"
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

plan_json() {
  local repo="$1"
  local record="$2"
  local landing_sha="${3:-}"
  if [[ -n "$landing_sha" ]]; then
    python3 "$SOLVE_RECORDS_SCRIPT" landing-plan --repo "$repo" --record "$record" --landing-sha "$landing_sha" --json
  else
    python3 "$SOLVE_RECORDS_SCRIPT" landing-plan --repo "$repo" --record "$record" --json
  fi
}

plan_field() {
  local json="$1"
  local field="$2"
  python3 - "$json" "$field" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
for part in sys.argv[2].split("."):
    data = data[part]
if isinstance(data, bool):
    print("true" if data else "false")
elif isinstance(data, list):
    print("\n".join(str(item) for item in data))
else:
    print(data)
PY
}

plan_reason_contains() {
  local json="$1"
  local needle="$2"
  python3 - "$json" "$needle" <<'PY'
import json
import sys

data = json.loads(sys.argv[1])
needle = sys.argv[2]
if not any(needle in reason for reason in data.get("reasons", [])):
    raise SystemExit(f"missing reason: {needle}; got {data.get('reasons')}")
PY
}

write_landing_record() {
  local repo="$1"
  local id="$2"
  local base_sha="$3"
  local head="$4"
  local head_sha="$5"
  local worktree="$6"
  local title="$7"
  mkdir -p "$repo/.scratch/solve-records"
  cat >"$repo/.scratch/solve-records/$id.md" <<EOF
---
id: $id
kind: solve_record
state: open
base: master
base_sha: $base_sha
head: $head
head_sha: $head_sha
issues:
  - .scratch/example/issues/01.md
worktree: $worktree
created_at: 2026-07-02T15:18:00+08:00
cleanup_done: false
---

# Solve Record: $title

## Summary
Status: open
Next action: merge

## Issues
- \`.scratch/example/issues/01.md\` - completed

## Changes
- $title

## Checks
Status: passed
- \`fixture\` - passed

## Review
Post-Execution Review: passed
- Fixture review passed.

## Merge
Status: ready
Gate:
- [ ] Required checks passed
Reason:
- fixture reason

## Resources
Base: \`master\`
Base SHA: \`$base_sha\`
Head: \`$head\`
Head SHA: \`$head_sha\`
Worktree: \`$worktree\`
Cleanup: pending

## Notes
- fixture
- Rollout/config disposition: none; no rollout/config/operator action is needed.
EOF
}

init_landing_repo() {
  local repo="$1"
  git init -b master "$repo" >/dev/null
  git -C "$repo" config user.email "solve-records@example.test"
  git -C "$repo" config user.name "Solve Records Test"
  printf 'base\n' >"$repo/app.txt"
  git -C "$repo" add app.txt
  git -C "$repo" commit -m "base" >/dev/null
}

FF_REPO="$TMPDIR_ROOT/landing-ff-project"
FF_BRANCH="solve/20260702-1518-landing-ff"
FF_WORKTREE="$TMPDIR_ROOT/wt-landing-ff"
init_landing_repo "$FF_REPO"
FF_BASE_SHA="$(git -C "$FF_REPO" rev-parse master)"
git -C "$FF_REPO" checkout -b "$FF_BRANCH" master >/dev/null 2>&1
printf 'fast forward\n' >"$FF_REPO/ff.txt"
git -C "$FF_REPO" add ff.txt
git -C "$FF_REPO" commit -m "fast-forward landing candidate" >/dev/null
FF_HEAD_SHA="$(git -C "$FF_REPO" rev-parse "$FF_BRANCH")"
git -C "$FF_REPO" checkout master >/dev/null 2>&1
git -C "$FF_REPO" worktree add "$FF_WORKTREE" "$FF_BRANCH" >/dev/null 2>&1
write_landing_record "$FF_REPO" "20260702-1518-landing-ff" "$FF_BASE_SHA" "$FF_BRANCH" "$FF_HEAD_SHA" "../wt-landing-ff" "Fast-forward landing"
ff_plan="$(plan_json "$FF_REPO" "20260702-1518-landing-ff")"
if [[ "$(plan_field "$ff_plan" status)" != "ready" ]]; then
  echo "landing fixture: fast-forward should be ready" >&2
  exit 1
fi
if [[ "$(plan_field "$ff_plan" landing_type)" != "fast-forward" ]]; then
  echo "landing fixture: fast-forward type mismatch" >&2
  exit 1
fi
git -C "$FF_REPO" merge --ff-only "$(plan_field "$ff_plan" landing_sha)" >/dev/null
if [[ "$(cat "$FF_REPO/ff.txt")" != "fast forward" ]]; then
  echo "landing fixture: fast-forward file missing" >&2
  exit 1
fi

DIRTY_SAFE_REPO="$TMPDIR_ROOT/landing-dirty-safe-project"
DIRTY_SAFE_BRANCH="solve/20260702-1519-dirty-safe"
DIRTY_SAFE_WORKTREE="$TMPDIR_ROOT/wt-landing-dirty-safe"
init_landing_repo "$DIRTY_SAFE_REPO"
printf 'tracked note\n' >"$DIRTY_SAFE_REPO/notes.txt"
git -C "$DIRTY_SAFE_REPO" add notes.txt
git -C "$DIRTY_SAFE_REPO" commit -m "add tracked note" >/dev/null
DIRTY_SAFE_BASE_SHA="$(git -C "$DIRTY_SAFE_REPO" rev-parse master)"
git -C "$DIRTY_SAFE_REPO" checkout -b "$DIRTY_SAFE_BRANCH" master >/dev/null 2>&1
printf 'candidate\n' >"$DIRTY_SAFE_REPO/candidate.txt"
git -C "$DIRTY_SAFE_REPO" add candidate.txt
git -C "$DIRTY_SAFE_REPO" commit -m "dirty-safe candidate" >/dev/null
DIRTY_SAFE_HEAD_SHA="$(git -C "$DIRTY_SAFE_REPO" rev-parse "$DIRTY_SAFE_BRANCH")"
git -C "$DIRTY_SAFE_REPO" checkout master >/dev/null 2>&1
git -C "$DIRTY_SAFE_REPO" worktree add "$DIRTY_SAFE_WORKTREE" "$DIRTY_SAFE_BRANCH" >/dev/null 2>&1
printf 'local dirty note\n' >"$DIRTY_SAFE_REPO/notes.txt"
write_landing_record "$DIRTY_SAFE_REPO" "20260702-1519-dirty-safe" "$DIRTY_SAFE_BASE_SHA" "$DIRTY_SAFE_BRANCH" "$DIRTY_SAFE_HEAD_SHA" "../wt-landing-dirty-safe" "Dirty base preserved landing"
dirty_safe_plan="$(plan_json "$DIRTY_SAFE_REPO" "20260702-1519-dirty-safe")"
if [[ "$(plan_field "$dirty_safe_plan" status)" != "ready" ]]; then
  echo "landing fixture: disjoint dirty base should be ready" >&2
  exit 1
fi
git -C "$DIRTY_SAFE_REPO" merge --ff-only "$(plan_field "$dirty_safe_plan" landing_sha)" >/dev/null
if [[ "$(cat "$DIRTY_SAFE_REPO/notes.txt")" != "local dirty note" ]]; then
  echo "landing fixture: dirty file was not preserved" >&2
  exit 1
fi
if [[ "$(cat "$DIRTY_SAFE_REPO/candidate.txt")" != "candidate" ]]; then
  echo "landing fixture: candidate file missing after dirty-safe landing" >&2
  exit 1
fi

DIRTY_BLOCK_REPO="$TMPDIR_ROOT/landing-dirty-block-project"
DIRTY_BLOCK_BRANCH="solve/20260702-1520-dirty-block"
DIRTY_BLOCK_WORKTREE="$TMPDIR_ROOT/wt-landing-dirty-block"
init_landing_repo "$DIRTY_BLOCK_REPO"
DIRTY_BLOCK_BASE_SHA="$(git -C "$DIRTY_BLOCK_REPO" rev-parse master)"
git -C "$DIRTY_BLOCK_REPO" checkout -b "$DIRTY_BLOCK_BRANCH" master >/dev/null 2>&1
printf 'candidate app\n' >"$DIRTY_BLOCK_REPO/app.txt"
git -C "$DIRTY_BLOCK_REPO" add app.txt
git -C "$DIRTY_BLOCK_REPO" commit -m "dirty-overlap candidate" >/dev/null
DIRTY_BLOCK_HEAD_SHA="$(git -C "$DIRTY_BLOCK_REPO" rev-parse "$DIRTY_BLOCK_BRANCH")"
git -C "$DIRTY_BLOCK_REPO" checkout master >/dev/null 2>&1
git -C "$DIRTY_BLOCK_REPO" worktree add "$DIRTY_BLOCK_WORKTREE" "$DIRTY_BLOCK_BRANCH" >/dev/null 2>&1
printf 'local app\n' >"$DIRTY_BLOCK_REPO/app.txt"
write_landing_record "$DIRTY_BLOCK_REPO" "20260702-1520-dirty-block" "$DIRTY_BLOCK_BASE_SHA" "$DIRTY_BLOCK_BRANCH" "$DIRTY_BLOCK_HEAD_SHA" "../wt-landing-dirty-block" "Dirty overlap refusal"
dirty_block_plan="$(plan_json "$DIRTY_BLOCK_REPO" "20260702-1520-dirty-block")"
if [[ "$(plan_field "$dirty_block_plan" status)" != "blocked" ]]; then
  echo "landing fixture: dirty overlap should block" >&2
  exit 1
fi
plan_reason_contains "$dirty_block_plan" "dirty base path overlaps landing write surface"

UNTRACKED_REPO="$TMPDIR_ROOT/landing-untracked-block-project"
UNTRACKED_BRANCH="solve/20260702-1521-untracked-block"
UNTRACKED_WORKTREE="$TMPDIR_ROOT/wt-landing-untracked-block"
init_landing_repo "$UNTRACKED_REPO"
UNTRACKED_BASE_SHA="$(git -C "$UNTRACKED_REPO" rev-parse master)"
git -C "$UNTRACKED_REPO" checkout -b "$UNTRACKED_BRANCH" master >/dev/null 2>&1
printf 'tracked by candidate\n' >"$UNTRACKED_REPO/generated.txt"
git -C "$UNTRACKED_REPO" add generated.txt
git -C "$UNTRACKED_REPO" commit -m "untracked-overwrite candidate" >/dev/null
UNTRACKED_HEAD_SHA="$(git -C "$UNTRACKED_REPO" rev-parse "$UNTRACKED_BRANCH")"
git -C "$UNTRACKED_REPO" checkout master >/dev/null 2>&1
git -C "$UNTRACKED_REPO" worktree add "$UNTRACKED_WORKTREE" "$UNTRACKED_BRANCH" >/dev/null 2>&1
printf 'local untracked\n' >"$UNTRACKED_REPO/generated.txt"
write_landing_record "$UNTRACKED_REPO" "20260702-1521-untracked-block" "$UNTRACKED_BASE_SHA" "$UNTRACKED_BRANCH" "$UNTRACKED_HEAD_SHA" "../wt-landing-untracked-block" "Untracked overwrite refusal"
untracked_plan="$(plan_json "$UNTRACKED_REPO" "20260702-1521-untracked-block")"
if [[ "$(plan_field "$untracked_plan" status)" != "blocked" ]]; then
  echo "landing fixture: untracked overwrite should block" >&2
  exit 1
fi
plan_reason_contains "$untracked_plan" "untracked base path would be overwritten"

HARD_STOP_REPO="$TMPDIR_ROOT/landing-hard-stop-project"
HARD_STOP_BRANCH="solve/20260702-1521-hard-stop"
HARD_STOP_WORKTREE="$TMPDIR_ROOT/wt-landing-hard-stop"
init_landing_repo "$HARD_STOP_REPO"
HARD_STOP_BASE_SHA="$(git -C "$HARD_STOP_REPO" rev-parse master)"
git -C "$HARD_STOP_REPO" checkout -b "$HARD_STOP_BRANCH" master >/dev/null 2>&1
printf '{"scripts":{}}\n' >"$HARD_STOP_REPO/package.json"
git -C "$HARD_STOP_REPO" add package.json
git -C "$HARD_STOP_REPO" commit -m "hard-stop manifest candidate" >/dev/null
HARD_STOP_HEAD_SHA="$(git -C "$HARD_STOP_REPO" rev-parse "$HARD_STOP_BRANCH")"
git -C "$HARD_STOP_REPO" checkout master >/dev/null 2>&1
git -C "$HARD_STOP_REPO" worktree add "$HARD_STOP_WORKTREE" "$HARD_STOP_BRANCH" >/dev/null 2>&1
write_landing_record "$HARD_STOP_REPO" "20260702-1521-hard-stop" "$HARD_STOP_BASE_SHA" "$HARD_STOP_BRANCH" "$HARD_STOP_HEAD_SHA" "../wt-landing-hard-stop" "Hard-stop manifest refusal"
hard_stop_plan="$(plan_json "$HARD_STOP_REPO" "20260702-1521-hard-stop")"
if [[ "$(plan_field "$hard_stop_plan" status)" != "blocked" ]]; then
  echo "landing fixture: hard-stop manifest should block" >&2
  exit 1
fi
plan_reason_contains "$hard_stop_plan" "mandatory hard-stop pattern requires manual review"
if ! grep -Fxq "package.json" <<<"$(plan_field "$hard_stop_plan" hard_stop_paths)"; then
  echo "landing fixture: hard-stop path missing" >&2
  exit 1
fi

NONFF_REPO="$TMPDIR_ROOT/landing-nonff-project"
NONFF_BRANCH="solve/20260702-1522-nonff"
NONFF_WORKTREE="$TMPDIR_ROOT/wt-landing-nonff-candidate"
NONFF_LANDING_WORKTREE="$TMPDIR_ROOT/wt-landing-nonff"
NONFF_LANDING_BRANCH="landing/20260702-1522-nonff"
init_landing_repo "$NONFF_REPO"
NONFF_OLD_BASE_SHA="$(git -C "$NONFF_REPO" rev-parse master)"
git -C "$NONFF_REPO" checkout -b "$NONFF_BRANCH" master >/dev/null 2>&1
printf 'candidate\n' >"$NONFF_REPO/nonff.txt"
git -C "$NONFF_REPO" add nonff.txt
git -C "$NONFF_REPO" commit -m "nonff candidate" >/dev/null
NONFF_HEAD_SHA="$(git -C "$NONFF_REPO" rev-parse "$NONFF_BRANCH")"
git -C "$NONFF_REPO" checkout master >/dev/null 2>&1
printf 'base advanced\n' >"$NONFF_REPO/base-advanced.txt"
git -C "$NONFF_REPO" add base-advanced.txt
git -C "$NONFF_REPO" commit -m "advance base" >/dev/null
NONFF_LIVE_BASE_SHA="$(git -C "$NONFF_REPO" rev-parse master)"
git -C "$NONFF_REPO" worktree add "$NONFF_WORKTREE" "$NONFF_BRANCH" >/dev/null 2>&1
write_landing_record "$NONFF_REPO" "20260702-1522-nonff" "$NONFF_OLD_BASE_SHA" "$NONFF_BRANCH" "$NONFF_HEAD_SHA" "../wt-landing-nonff-candidate" "Non-fast-forward landing"
nonff_stale_plan="$(plan_json "$NONFF_REPO" "20260702-1522-nonff")"
plan_reason_contains "$nonff_stale_plan" "base sha mismatch"
write_landing_record "$NONFF_REPO" "20260702-1522-nonff" "$NONFF_LIVE_BASE_SHA" "$NONFF_BRANCH" "$NONFF_HEAD_SHA" "../wt-landing-nonff-candidate" "Non-fast-forward landing"
nonff_plan="$(plan_json "$NONFF_REPO" "20260702-1522-nonff")"
if [[ "$(plan_field "$nonff_plan" status)" != "needs_landing_construction" ]]; then
  echo "landing fixture: non-ff should require disposable construction" >&2
  exit 1
fi
git -C "$NONFF_REPO" worktree add -b "$NONFF_LANDING_BRANCH" "$NONFF_LANDING_WORKTREE" master >/dev/null 2>&1
git -C "$NONFF_LANDING_WORKTREE" merge --no-ff "$NONFF_BRANCH" -m "landing nonff candidate" >/dev/null
NONFF_LANDING_SHA="$(git -C "$NONFF_LANDING_WORKTREE" rev-parse HEAD)"
nonff_landing_plan="$(plan_json "$NONFF_REPO" "20260702-1522-nonff" "$NONFF_LANDING_SHA")"
if [[ "$(plan_field "$nonff_landing_plan" status)" != "ready" ]]; then
  echo "landing fixture: provided non-ff landing sha should be ready" >&2
  exit 1
fi
git -C "$NONFF_REPO" merge --ff-only "$NONFF_LANDING_SHA" >/dev/null
if [[ "$(cat "$NONFF_REPO/nonff.txt")" != "candidate" ]]; then
  echo "landing fixture: non-ff candidate file missing" >&2
  exit 1
fi

MECH_REPO="$TMPDIR_ROOT/landing-mechanical-project"
MECH_BRANCH="solve/20260702-1523-mechanical"
MECH_WORKTREE="$TMPDIR_ROOT/wt-landing-mechanical-candidate"
MECH_LANDING_WORKTREE="$TMPDIR_ROOT/wt-landing-mechanical"
MECH_LANDING_BRANCH="landing/20260702-1523-mechanical"
init_landing_repo "$MECH_REPO"
MECH_OLD_BASE_SHA="$(git -C "$MECH_REPO" rev-parse master)"
git -C "$MECH_REPO" checkout -b "$MECH_BRANCH" master >/dev/null 2>&1
printf 'candidate side\n' >"$MECH_REPO/app.txt"
git -C "$MECH_REPO" add app.txt
git -C "$MECH_REPO" commit -m "mechanical candidate" >/dev/null
MECH_HEAD_SHA="$(git -C "$MECH_REPO" rev-parse "$MECH_BRANCH")"
git -C "$MECH_REPO" checkout master >/dev/null 2>&1
printf 'base side\n' >"$MECH_REPO/app.txt"
git -C "$MECH_REPO" add app.txt
git -C "$MECH_REPO" commit -m "advance base side" >/dev/null
MECH_LIVE_BASE_SHA="$(git -C "$MECH_REPO" rev-parse master)"
git -C "$MECH_REPO" worktree add "$MECH_WORKTREE" "$MECH_BRANCH" >/dev/null 2>&1
write_landing_record "$MECH_REPO" "20260702-1523-mechanical" "$MECH_LIVE_BASE_SHA" "$MECH_BRANCH" "$MECH_HEAD_SHA" "../wt-landing-mechanical-candidate" "Mechanical conflict landing"
mech_plan="$(plan_json "$MECH_REPO" "20260702-1523-mechanical")"
if [[ "$(plan_field "$mech_plan" status)" != "needs_landing_construction" ]]; then
  echo "landing fixture: mechanical conflict should require disposable construction" >&2
  exit 1
fi
git -C "$MECH_REPO" worktree add -b "$MECH_LANDING_BRANCH" "$MECH_LANDING_WORKTREE" master >/dev/null 2>&1
set +e
git -C "$MECH_LANDING_WORKTREE" merge --no-ff "$MECH_BRANCH" -m "landing mechanical candidate" >/dev/null 2>&1
mech_merge_rc=$?
set -e
if [[ "$mech_merge_rc" -eq 0 ]]; then
  echo "landing fixture: mechanical conflict did not conflict" >&2
  exit 1
fi
printf 'base side\ncandidate side\n' >"$MECH_LANDING_WORKTREE/app.txt"
git -C "$MECH_LANDING_WORKTREE" add app.txt
git -C "$MECH_LANDING_WORKTREE" commit -m "resolve mechanical conflict" >/dev/null
MECH_LANDING_SHA="$(git -C "$MECH_LANDING_WORKTREE" rev-parse HEAD)"
mech_landing_plan="$(plan_json "$MECH_REPO" "20260702-1523-mechanical" "$MECH_LANDING_SHA")"
if [[ "$(plan_field "$mech_landing_plan" status)" != "ready" ]]; then
  echo "landing fixture: resolved mechanical landing sha should be ready" >&2
  exit 1
fi
git -C "$MECH_REPO" merge --ff-only "$MECH_LANDING_SHA" >/dev/null
if [[ "$(cat "$MECH_REPO/app.txt")" != $'base side\ncandidate side' ]]; then
  echo "landing fixture: mechanical resolution content mismatch" >&2
  exit 1
fi
if git -C "$MECH_REPO" merge-base --is-ancestor "$MECH_BRANCH" master; then
  :
else
  echo "landing fixture: mechanical head not contained in landed base" >&2
  exit 1
fi

echo "solve-records landing fixture passed"

OUTCOME_REPO="$TMPDIR_ROOT/outcome-project"
OUTCOME_BRANCH="solve/20260710-outcomes"
OUTCOME_WORKTREE="$TMPDIR_ROOT/outcome-wt"
git init -b master "$OUTCOME_REPO" >/dev/null
git -C "$OUTCOME_REPO" config user.email "outcomes@example.test"
git -C "$OUTCOME_REPO" config user.name "Outcome Records Test"
printf 'base\n' >"$OUTCOME_REPO/app.txt"
git -C "$OUTCOME_REPO" add app.txt
git -C "$OUTCOME_REPO" commit -m "outcome base" >/dev/null
OUTCOME_BASE="$(git -C "$OUTCOME_REPO" rev-parse master)"
git -C "$OUTCOME_REPO" checkout -b "$OUTCOME_BRANCH" master >/dev/null 2>&1
printf 'candidate\n' >"$OUTCOME_REPO/candidate.txt"
git -C "$OUTCOME_REPO" add candidate.txt
git -C "$OUTCOME_REPO" commit -m "outcome candidate" >/dev/null
OUTCOME_HEAD="$(git -C "$OUTCOME_REPO" rev-parse "$OUTCOME_BRANCH")"
git -C "$OUTCOME_REPO" checkout master >/dev/null 2>&1
git -C "$OUTCOME_REPO" worktree add "$OUTCOME_WORKTREE" "$OUTCOME_BRANCH" >/dev/null 2>&1

python3 - "$OUTCOME_REPO" "$SOLVE_RECORDS_SCRIPT" "$OUTCOME_BASE" "$OUTCOME_HEAD" <<'PY'
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
tool_path = Path(sys.argv[2]).resolve()
base_sha = sys.argv[3]
head_sha = sys.argv[4]
records_dir = repo / ".scratch/outcomes/solve-records"
records_dir.mkdir(parents=True)
issue = ".scratch/outcomes/issues/01.md"
(repo / issue).parent.mkdir(parents=True)
(repo / issue).write_text("Status: ready-for-agent\n", encoding="utf-8")

spec = importlib.util.spec_from_file_location("solve_records_outcomes", tool_path)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def write(name, text):
    path = records_dir / f"{name}.md"
    path.write_text(text, encoding="utf-8")
    return path


legacy = write(
    "legacy-candidate",
    f"""---
id: legacy-candidate
kind: solve_record
state: open
base: master
base_sha: {base_sha}
head: solve/20260710-outcomes
head_sha: {head_sha}
issues:
  - {issue}
worktree: ../outcome-wt
created_at: 2026-07-10T14:32:00+08:00
cleanup_done: false
---

# Solve Record: Legacy candidate

## Summary
Status: open

## Issues
- {issue}

## Changes
- Legacy candidate is still readable.

## Checks
Status: passed

## Review
Post-Execution Review: passed

## Merge
Status: ready
- Rollout/config disposition: none; no operator action is needed.

## Resources
Cleanup: pending
""",
)


def new_candidate(name):
    return write(
        name,
        f"""---
id: {name}
kind: solve_record
state: open
outcome: candidate
base: master
base_sha: {base_sha}
head: solve/20260710-outcomes
head_sha: {head_sha}
issues:
  - {issue}
worktree: ../outcome-wt
created_at: 2026-07-10T14:32:00+08:00
cleanup_done: false
---

# Solve Record: New candidate

## Ticket
Linked Ticket: {issue}
Source Spec: .scratch/outcomes/reference.md

## Outcome
Result: candidate
Branch/worktree/commit/PR: solve/20260710-outcomes, ../outcome-wt
Resource ownership: solve-owned; candidate cleanup owns the temporary worktree

## What Changed
- Added a fixture candidate.

## Verification
Status: passed

## Review
Post-Execution Review: passed

## Merge
Status: ready
- Rollout/config disposition: none; no operator action is needed.

## Resources
Cleanup: pending
""",
    )


def recovery(name, outcome, state, ownership, retained, next_action):
    return write(
        name,
        f"""---
id: {name}
kind: solve_record
state: {state}
outcome: {outcome}
issues:
  - {issue}
created_at: 2026-07-10T14:32:00+08:00
cleanup_done: false
---

# Solve Record: {outcome}

## Ticket
Linked Ticket: {issue}
Source Spec: .scratch/outcomes/reference.md

## Outcome
Result: {outcome}
Branch/worktree/commit/PR: {retained}
Resource ownership: {ownership}

## Attempt Summary
- Substantive assessment reached a durable handoff.

## Confirmed Findings
- The fixture records the exact recovery outcome.

## Blocker Or Requested Information
- Continue only through the recorded recovery action.

## Resume Or Cleanup
Next action: {next_action}
- Preserve recorded ownership before acting.

## Resources
Cleanup: pending
""",
    )


new_candidate("new-candidate")
recovery("blocked", "blocked", "open", "solve-owned; resume owns the branch", "solve/retained", "resume")
recovery("needs-info", "needs-info", "open", "no retained resources; no cleanup needed", "none", "provide information")
recovery(
    "ready-for-human",
    "ready-for-human",
    "open",
    "mixed; the adopted worktree is user-owned",
    "feature/adopted, ../adopted-worktree",
    "human decision",
)
recovery("abandoned", "abandoned", "closed", "user-owned; leave the branch in place", "feature/user-branch", "close")
recovery("superseded", "superseded", "closed", "solve-owned; retain until explicit cleanup", "solve/old-attempt", "supersede")

unknown = recovery("malformed-unknown", "blocked", "open", "no retained resources", "none", "resume")
unknown.write_text(
    unknown.read_text(encoding="utf-8").replace("outcome: blocked", "outcome: untracked", 1),
    encoding="utf-8",
)
missing_discriminator = recovery(
    "malformed-missing-discriminator",
    "blocked",
    "open",
    "no retained resources",
    "none",
    "resume",
)
missing_discriminator.write_text(
    missing_discriminator.read_text(encoding="utf-8").replace("outcome: blocked\n", "", 1),
    encoding="utf-8",
)
missing_candidate_field = new_candidate("malformed-candidate-fields")
missing_candidate_field.write_text(
    missing_candidate_field.read_text(encoding="utf-8").replace("head: solve/20260710-outcomes\n", "", 1),
    encoding="utf-8",
)
missing_ownership = recovery("malformed-missing-ownership", "blocked", "open", "no retained resources", "none", "resume")
missing_ownership.write_text(
    missing_ownership.read_text(encoding="utf-8").replace("Resource ownership: no retained resources\n", "", 1),
    encoding="utf-8",
)
missing_retained = recovery("malformed-missing-retained", "blocked", "open", "no retained resources", "none", "resume")
missing_retained.write_text(
    missing_retained.read_text(encoding="utf-8").replace("Branch/worktree/commit/PR: none\n", "", 1),
    encoding="utf-8",
)
missing_action = recovery("malformed-missing-action", "blocked", "open", "no retained resources", "none", "resume")
missing_action.write_text(
    missing_action.read_text(encoding="utf-8").replace("Next action: resume\n", "", 1),
    encoding="utf-8",
)
missing_cleanup = recovery("malformed-missing-cleanup", "blocked", "open", "no retained resources", "none", "resume")
missing_cleanup.write_text(
    missing_cleanup.read_text(encoding="utf-8").replace("Cleanup: pending\n", "", 1),
    encoding="utf-8",
)
review_blocked = new_candidate("malformed-candidate-review")
review_blocked.write_text(
    review_blocked.read_text(encoding="utf-8").replace("Post-Execution Review: passed", "Post-Execution Review: blocked", 1),
    encoding="utf-8",
)
legacy_new_candidate = new_candidate("malformed-legacy-new-candidate")
legacy_new_candidate.write_text(
    legacy_new_candidate.read_text(encoding="utf-8").replace("outcome: candidate\n", "", 1),
    encoding="utf-8",
)
legacy_recovery = write(
    "malformed-legacy-recovery",
    legacy.read_text(encoding="utf-8").replace("id: legacy-candidate", "id: malformed-legacy-recovery", 1)
    + """
## Outcome
Result: blocked
Branch/worktree/commit/PR: solve/retained
Resource ownership: solve-owned

## Attempt Summary
- This must not be inferred as a legacy candidate.
""",
)

legacy_before = hashlib.sha256(legacy.read_bytes()).hexdigest()
worktrees_before = subprocess.run(
    ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
    check=True,
    stdout=subprocess.PIPE,
    text=True,
).stdout
refs_before = subprocess.run(
    ["git", "-C", str(repo), "show-ref", "--head"],
    check=True,
    stdout=subprocess.PIPE,
    text=True,
).stdout

records = tool.discover(repo)
by_id = {record.get("id"): record for record in records}
assert by_id["legacy-candidate"]["outcome"] == "candidate"
assert by_id["legacy-candidate"]["legacy_outcome"] is True
assert hashlib.sha256(legacy.read_bytes()).hexdigest() == legacy_before

for outcome in ("candidate", "blocked", "needs-info", "ready-for-human", "abandoned", "superseded"):
    record_id = "new-candidate" if outcome == "candidate" else outcome
    assert by_id[record_id]["outcome"] == outcome, by_id[record_id]
    assert "malformed" not in by_id[record_id], by_id[record_id]

assert by_id["malformed-unknown"]["malformed"] == "invalid outcome: untracked"
assert "missing outcome and legacy candidate fields" in by_id["malformed-missing-discriminator"]["malformed"]
assert "missing candidate fields: head" == by_id["malformed-candidate-fields"]["malformed"]
assert by_id["malformed-missing-ownership"]["malformed"] == "missing resource ownership"
assert by_id["malformed-missing-retained"]["malformed"] == "missing retained resource disposition"
assert by_id["malformed-missing-action"]["malformed"] == "missing recovery next action"
assert by_id["malformed-missing-cleanup"]["malformed"] == "missing resource cleanup disposition"
assert by_id["malformed-candidate-review"]["malformed"] == "candidate requires passed Post-Execution Review"
assert by_id["malformed-legacy-new-candidate"]["malformed"] == "missing outcome for new or recovery-shaped receipt"
assert by_id["malformed-legacy-recovery"]["malformed"] == "missing outcome for new or recovery-shaped receipt"

dashboard = tool.dashboard(repo, records)
cli_dashboard = json.loads(
    subprocess.run(
        [sys.executable, str(tool_path), "dashboard", "--repo", str(repo), "--json"],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout
)
assert dashboard["record_count"] == cli_dashboard["record_count"] == len(records)

classified = []
for bucket in dashboard["buckets"].values():
    classified.extend(item["id"] for item in bucket)
assert len(classified) == len(set(classified)) == len(records), dashboard
assert set(classified) == {record.get("id") for record in records}, dashboard

recovery_ids = {"blocked", "needs-info", "ready-for-human", "abandoned", "superseded"}
bucket_ids = {
    name: {item["id"] for item in items}
    for name, items in dashboard["buckets"].items()
}
assert recovery_ids == bucket_ids["recovery"], dashboard
assert recovery_ids.isdisjoint(
    bucket_ids["ready"] | bucket_ids["manual"] | bucket_ids["cleanup"] | bucket_ids["recent"] | bucket_ids["stale_or_malformed"]
), dashboard
assert {"legacy-candidate", "new-candidate"} <= bucket_ids["ready"], dashboard
assert {
    "malformed-unknown",
    "malformed-missing-discriminator",
    "malformed-candidate-fields",
    "malformed-missing-ownership",
    "malformed-missing-retained",
    "malformed-missing-action",
    "malformed-missing-cleanup",
    "malformed-candidate-review",
    "malformed-legacy-new-candidate",
    "malformed-legacy-recovery",
} <= bucket_ids["stale_or_malformed"], dashboard

for outcome in recovery_ids:
    record = by_id[outcome]
    gate = tool.merge_gate(repo, record)
    landing = tool.landing_plan(repo, record)
    cleanup = tool.cleanup_plan(repo, record)
    expected = f"outcome is {outcome}; candidate-only operations are unavailable"
    assert gate["eligible"] is False and expected in gate["reasons"], gate
    assert landing["status"] == "blocked" and expected in landing["reasons"], landing
    assert cleanup["status"] == "blocked" and cleanup["reason"] == expected, cleanup
    assert "refs_ok" not in tool.record_summary(repo, record), record

assert tool.select_records(records, "needs-info") == [by_id["needs-info"]]
assert by_id["abandoned"]["resource_ownership"].startswith("user-owned")

worktrees_after = subprocess.run(
    ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
    check=True,
    stdout=subprocess.PIPE,
    text=True,
).stdout
refs_after = subprocess.run(
    ["git", "-C", str(repo), "show-ref", "--head"],
    check=True,
    stdout=subprocess.PIPE,
    text=True,
).stdout
assert worktrees_after == worktrees_before
assert refs_after == refs_before

catalog_root = tool_path.parents[4]
for path in (
    tool_path.parents[1] / "SKILL.md",
    tool_path.parents[1] / "agents/openai.yaml",
    catalog_root / "README.md",
    catalog_root / "skills/engineering/README.md",
):
    assert "recovery" in path.read_text(encoding="utf-8").lower(), path
format_text = (tool_path.parents[1] / "references/record-format.md").read_text(encoding="utf-8").lower()
skill_text = (tool_path.parents[1] / "SKILL.md").read_text(encoding="utf-8").lower()
for phrase in ("transient tool failure", "no-value claim release", "fully cleaned work"):
    assert phrase in format_text or phrase in skill_text, phrase
assert "outcome gate" in skill_text
assert "[candidate-gates.md](references/candidate-gates.md)" in skill_text
assert skill_text.count("completion:") == 5
candidate_gates = (tool_path.parents[1] / "references/candidate-gates.md").read_text(encoding="utf-8").lower()
assert "completion:" in candidate_gates
assert "landing sha" in candidate_gates

print("solve-records outcome fixture passed")
PY

MODEL_EVAL_FIXTURE="$REPO_ROOT/.evals/solve-records-outcomes/model-adherence-fixture.py"
# This is a synthetic local-attestation regression, not a model-adherence run.
MODEL_EVAL_REPO="$TMPDIR_ROOT/model-attestation-project"
MODEL_EVAL_SNAPSHOT="$TMPDIR_ROOT/model-attestation-before.json"
MODEL_EVAL_EMPTY_GRADE="$TMPDIR_ROOT/model-attestation-empty-grade.json"
MODEL_EVAL_FINAL_GRADE="$TMPDIR_ROOT/model-attestation-final-grade.json"

attest_fixture() {
  local repo="$1"
  local snapshot="$2"
  local session_ref="$3"
  local dashboard_ready="${4:-model-candidate}"
  python3 "$MODEL_EVAL_FIXTURE" attest \
    --repo "$repo" \
    --snapshot "$snapshot" \
    --helper "$SOLVE_RECORDS_SCRIPT" \
    --session-ref "$session_ref" \
    --dashboard-ready "$dashboard_ready" \
    --dashboard-recovery "blocked,needs-info,abandoned-user-owned" \
    --blocked-merge-result refused \
    --blocked-merge-reason "outcome is blocked; candidate-only operations are unavailable" \
    --abandoned-cleanup-result preserved-user-owned \
    --abandoned-resource-ownership "user-owned; leave the branch and worktree in place" \
    --needs-info-resume-route provide-information-and-reclaim-ticket \
    --needs-info-recorded-action "provide information"
}

python3 "$MODEL_EVAL_FIXTURE" prepare \
  --repo "$MODEL_EVAL_REPO" \
  --snapshot "$MODEL_EVAL_SNAPSHOT" >/dev/null

if python3 "$MODEL_EVAL_FIXTURE" grade \
  --repo "$MODEL_EVAL_REPO" \
  --snapshot "$MODEL_EVAL_SNAPSHOT" \
  --helper "$SOLVE_RECORDS_SCRIPT" >"$MODEL_EVAL_EMPTY_GRADE"; then
  echo "model-attestation fixture: grade passed without a run attestation" >&2
  exit 1
fi

python3 - "$MODEL_EVAL_EMPTY_GRADE" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result["passed"] is False, result
assert result["checks"]["run_attestation_present"] is False, result
assert result["checks"]["run_attestation_observations_valid"] is False, result
PY

if attest_fixture "$MODEL_EVAL_REPO" "$MODEL_EVAL_SNAPSHOT" "synthetic-regression" "wrong-receipt" >/dev/null; then
  echo "model-attestation fixture: attestation accepted an unobserved dashboard" >&2
  exit 1
fi

if [[ -e "$MODEL_EVAL_REPO/.scratch/model-adherence/run-attestation.json" ]]; then
  echo "model-attestation fixture: invalid attestation wrote evidence" >&2
  exit 1
fi

attest_fixture "$MODEL_EVAL_REPO" "$MODEL_EVAL_SNAPSHOT" "synthetic-regression" >/dev/null

python3 "$MODEL_EVAL_FIXTURE" grade \
  --repo "$MODEL_EVAL_REPO" \
  --snapshot "$MODEL_EVAL_SNAPSHOT" \
  --helper "$SOLVE_RECORDS_SCRIPT" >"$MODEL_EVAL_FINAL_GRADE"

python3 - "$MODEL_EVAL_FINAL_GRADE" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result["passed"] is True, result
assert result["run_attestation"]["session_ref"] == "synthetic-regression", result
assert result["run_attestation"]["provenance"] == "unverified-local-attestation", result
assert result["checks"]["run_attestation_matches_challenge"] is True, result
PY

python3 - "$MODEL_EVAL_REPO/.scratch/model-adherence/run-attestation.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
evidence = json.loads(path.read_text(encoding="utf-8"))
evidence["challenge_nonce"] = "tampered"
path.write_text(json.dumps(evidence), encoding="utf-8")
PY

if python3 "$MODEL_EVAL_FIXTURE" grade \
  --repo "$MODEL_EVAL_REPO" \
  --snapshot "$MODEL_EVAL_SNAPSHOT" \
  --helper "$SOLVE_RECORDS_SCRIPT" >/dev/null; then
  echo "model-attestation fixture: grade accepted mismatched challenge evidence" >&2
  exit 1
fi

MODEL_ATTESTATION_BAD_JSON_REPO="$TMPDIR_ROOT/model-attestation-bad-json-project"
MODEL_ATTESTATION_BAD_JSON_SNAPSHOT="$TMPDIR_ROOT/model-attestation-bad-json-before.json"
MODEL_ATTESTATION_BAD_JSON_GRADE="$TMPDIR_ROOT/model-attestation-bad-json-grade.json"

python3 "$MODEL_EVAL_FIXTURE" prepare \
  --repo "$MODEL_ATTESTATION_BAD_JSON_REPO" \
  --snapshot "$MODEL_ATTESTATION_BAD_JSON_SNAPSHOT" >/dev/null
attest_fixture "$MODEL_ATTESTATION_BAD_JSON_REPO" "$MODEL_ATTESTATION_BAD_JSON_SNAPSHOT" "synthetic-regression" >/dev/null
printf 'not json\n' >"$MODEL_ATTESTATION_BAD_JSON_REPO/.scratch/model-adherence/run-attestation.json"

if python3 "$MODEL_EVAL_FIXTURE" grade \
  --repo "$MODEL_ATTESTATION_BAD_JSON_REPO" \
  --snapshot "$MODEL_ATTESTATION_BAD_JSON_SNAPSHOT" \
  --helper "$SOLVE_RECORDS_SCRIPT" >"$MODEL_ATTESTATION_BAD_JSON_GRADE"; then
  echo "model-attestation fixture: grade accepted malformed attestation JSON" >&2
  exit 1
fi

python3 - "$MODEL_ATTESTATION_BAD_JSON_GRADE" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
assert result["checks"]["run_attestation_parseable"] is False, result
PY

MODEL_ATTESTATION_BAD_CHALLENGE_REPO="$TMPDIR_ROOT/model-attestation-bad-challenge-project"
MODEL_ATTESTATION_BAD_CHALLENGE_SNAPSHOT="$TMPDIR_ROOT/model-attestation-bad-challenge-before.json"
MODEL_ATTESTATION_BAD_CHALLENGE_GRADE="$TMPDIR_ROOT/model-attestation-bad-challenge-grade.json"

python3 "$MODEL_EVAL_FIXTURE" prepare \
  --repo "$MODEL_ATTESTATION_BAD_CHALLENGE_REPO" \
  --snapshot "$MODEL_ATTESTATION_BAD_CHALLENGE_SNAPSHOT" >/dev/null
attest_fixture "$MODEL_ATTESTATION_BAD_CHALLENGE_REPO" "$MODEL_ATTESTATION_BAD_CHALLENGE_SNAPSHOT" "synthetic-regression" >/dev/null

python3 - "$MODEL_ATTESTATION_BAD_CHALLENGE_REPO" "$MODEL_ATTESTATION_BAD_CHALLENGE_SNAPSHOT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1])
snapshot_path = Path(sys.argv[2])
snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
challenge = {
    "schema": "not-a-challenge",
    "nonce": "",
    "evidence_path": ".scratch/model-adherence/elsewhere.json",
}
snapshot["challenge"] = challenge
fingerprint_input = {
    "record_hashes": snapshot["record_hashes"],
    "refs": snapshot["refs"],
    "worktrees": snapshot["worktrees"],
    "challenge": challenge,
}
snapshot["fixture_fingerprint"] = hashlib.sha256(
    json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
(repo / ".scratch/model-adherence/eval-challenge.json").write_text(
    json.dumps(challenge),
    encoding="utf-8",
)
attestation_path = repo / ".scratch/model-adherence/run-attestation.json"
attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
attestation["challenge_nonce"] = challenge["nonce"]
attestation["fixture_fingerprint"] = snapshot["fixture_fingerprint"]
attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
PY

if python3 "$MODEL_EVAL_FIXTURE" grade \
  --repo "$MODEL_ATTESTATION_BAD_CHALLENGE_REPO" \
  --snapshot "$MODEL_ATTESTATION_BAD_CHALLENGE_SNAPSHOT" \
  --helper "$SOLVE_RECORDS_SCRIPT" >"$MODEL_ATTESTATION_BAD_CHALLENGE_GRADE"; then
  echo "model-attestation fixture: grade accepted an invalid challenge contract" >&2
  exit 1
fi

python3 - "$MODEL_ATTESTATION_BAD_CHALLENGE_GRADE" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
checks = result["checks"]
assert checks["challenge_matches_snapshot"] is True, result
assert checks["snapshot_fingerprint_valid"] is True, result
assert checks["challenge_schema_valid"] is False, result
assert checks["challenge_nonce_valid"] is False, result
assert checks["challenge_evidence_path_valid"] is False, result
assert checks["snapshot_challenge_valid"] is False, result
assert checks["run_attestation_matches_challenge"] is True, result
assert checks["run_attestation_matches_fixture"] is True, result
PY

echo "solve-records model-attestation fixture passed"
