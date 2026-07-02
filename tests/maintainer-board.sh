#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
BOARD_SCRIPT="$REPO_ROOT/skills/in-progress/maintainer-board/scripts/maintainer-board.py"
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

REPO="$TMPDIR_ROOT/project"

git init -b master "$REPO" >/dev/null
git -C "$REPO" config user.email "maintainer-board@example.test"
git -C "$REPO" config user.name "Maintainer Board Test"

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

CLAIM_HEAD="$(make_branch solve/claim claim.txt claim)"
READY_HEAD="$(make_branch solve/ready ready.txt ready)"
MANUAL_HEAD="$(make_branch solve/manual manual.txt manual)"
RECENT_HEAD="$(make_branch solve/recent recent.txt recent)"

git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-claim" solve/claim >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-ready" solve/ready >/dev/null 2>&1

mkdir -p "$REPO/.scratch/feature-a/issues"
mkdir -p "$REPO/.scratch/feature-a/solve-records"
mkdir -p "$REPO/.scratch/feature-b"
mkdir -p "$REPO/.scratch/solve-records"

cat >"$REPO/.scratch/feature-a/issues/01-ready.md" <<'EOF'
Status: ready-for-agent
Category: feature
Created: 2026-07-02

# Ready issue

## Acceptance criteria

- [ ] does the thing
- [x] keeps the old thing
EOF

cat >"$REPO/.scratch/feature-a/issues/02-claimed.md" <<EOF
Status: ready-for-agent
Flags: solve-in-progress
Solve Branch: solve/claim
Solve Worktree: $TMPDIR_ROOT/wt-claim
Category: feature
Created: 2026-07-02

# Claimed issue
EOF

cat >"$REPO/.scratch/feature-a/issues/03-needs-human.md" <<'EOF'
---
status: needs-info
category: bug
flags:
  - agent-decision
created: 2026-07-02
---

# Needs human issue
EOF

cat >"$REPO/.scratch/feature-a/issues/04-blocked.md" <<'EOF'
Status: ready-for-agent
Category: feature
Created: 2026-07-02

# Blocked issue

## Blocked by

- `.scratch/feature-a/issues/01-ready.md`
EOF

cat >"$REPO/.scratch/feature-a/issues/05-completed-linked.md" <<'EOF'
Status: completed
Category: feature
Created: 2026-07-02

# Completed linked issue

## Comments

### Solve Record

- `../solve-records/20260702-ready.md`
EOF

cat >"$REPO/.scratch/feature-a/issues/06-completed-unlinked.md" <<'EOF'
Status: completed
Category: documentation
Created: 2026-07-02

# Completed unlinked issue
EOF

for n in 1 2 3 4 5; do
  cat >"$REPO/.scratch/feature-a/issues/06-extra-completed-$n.md" <<EOF
Status: completed
Category: documentation
Created: 2026-07-02

# Extra completed unlinked issue $n
EOF
done

cat >"$REPO/.scratch/feature-a/issues/07-missing-worktree.md" <<'EOF'
Status: ready-for-agent
Flags: solve-in-progress
Solve Branch: solve/missing
Solve Worktree: ../missing-worktree
Category: feature
Created: 2026-07-02

# Missing worktree issue
EOF

cat >"$REPO/.scratch/feature-b/issue.md" <<'EOF'
---
status: ready-for-agent
category: feature
created: 2026-07-02
---

# Single issue file
EOF

write_record() {
  local path="$1"
  local id="$2"
  local state="$3"
  local head="$4"
  local head_sha="$5"
  local worktree="$6"
  local cleanup_done="$7"
  local title="$8"
  local checks="$9"
  local merge="${10}"
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
  - .scratch/feature-a/issues/05-completed-linked.md
worktree: $worktree
created_at: 2026-07-02T10:00:00+08:00
cleanup_done: $cleanup_done
---

# Solve Record: $title

## Summary
Status: $state
Next action: merge

## Issues
- \`.scratch/feature-a/issues/05-completed-linked.md\` - completed

## Changes
- fixture

## Checks
Status: $checks
- \`fixture\` - $checks

## Merge
Status: $merge
Gate:
- [ ] Required checks passed
Reason:
- fixture

## Resources
Base: \`master\`
Base SHA: \`$BASE_SHA\`
Head: \`$head\`
Head SHA: \`$head_sha\`
Worktree: \`$worktree\`
Cleanup: pending

## Notes
- fixture
EOF
}

write_record "$REPO/.scratch/feature-a/solve-records/20260702-ready.md" \
  "20260702-ready" open solve/ready "$READY_HEAD" "../wt-ready" false "Ready record" passed ready

write_record "$REPO/.scratch/solve-records/20260702-manual.md" \
  "20260702-manual" open solve/manual "$MANUAL_HEAD" "../wt-ready" false "Manual record" unavailable "manual required"

write_record "$REPO/.scratch/solve-records/20260702-stale.md" \
  "20260702-stale" open solve/missing deadbeef "../wt-ready" false "Stale record" passed ready

write_record "$REPO/.scratch/solve-records/20260702-recent.md" \
  "20260702-recent" merged solve/recent "$RECENT_HEAD" "." true "Recent record" passed "auto-merged"

JSON_OUT="$TMPDIR_ROOT/board.json"
HTML_OUT="$TMPDIR_ROOT/board.html"
DEFAULT_HTML_OUT="$(git -C "$REPO" rev-parse --show-toplevel)/.scratch/maintainer-board/index.html"
FALLBACK_JSON_OUT="$TMPDIR_ROOT/fallback-board.json"
STANDALONE_SCRIPT="$TMPDIR_ROOT/standalone/maintainer-board.py"

python3 "$BOARD_SCRIPT" --repo "$REPO" --json >"$JSON_OUT"
python3 "$BOARD_SCRIPT" --repo "$REPO" --html "$HTML_OUT" >"$TMPDIR_ROOT/html-path.txt"
DEFAULT_STDOUT="$(cd "$REPO" && python3 "$BOARD_SCRIPT")"
mkdir -p "$(dirname "$STANDALONE_SCRIPT")"
cp "$BOARD_SCRIPT" "$STANDALONE_SCRIPT"
python3 "$STANDALONE_SCRIPT" --repo "$REPO" --json >"$FALLBACK_JSON_OUT"

if [[ "$DEFAULT_STDOUT" != "$DEFAULT_HTML_OUT" ]]; then
  echo "expected default HTML path '$DEFAULT_HTML_OUT', got '$DEFAULT_STDOUT'" >&2
  exit 1
fi

python3 - "$JSON_OUT" "$HTML_OUT" "$DEFAULT_HTML_OUT" "$FALLBACK_JSON_OUT" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
html = Path(sys.argv[2]).read_text(encoding="utf-8")
default_html = Path(sys.argv[3]).read_text(encoding="utf-8")
fallback = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))

assert data["schema_version"] == "maintainer-board/v1"
assert data["issues"]["count"] == 13
assert data["issues"]["counts"]["ready_for_agent"] == 2
assert data["issues"]["counts"]["claimed_or_in_progress"] == 2
assert data["issues"]["counts"]["needs_human"] == 1
assert data["issues"]["counts"]["blocked_or_dependent"] == 1
assert data["issues"]["counts"]["completed_with_solve_record"] == 1
assert data["issues"]["counts"]["completed_without_solve_record"] == 6

ready = data["issues"]["buckets"]["ready_for_agent"]
assert {issue["metadata_format"] for issue in ready} == {"header", "frontmatter"}

claimed = data["issues"]["buckets"]["claimed_or_in_progress"]
warnings = [warning["code"] for issue in claimed for warning in issue["warnings"]]
assert "missing_solve_branch" in warnings
assert "missing_solve_worktree" in warnings

completed = data["issues"]["buckets"]["completed_with_solve_record"][0]
assert completed["solve_records"] == ["../solve-records/20260702-ready.md"]
assert completed["checklist"] == {"total": 0, "done": 0, "open": 0}

ready_issue = next(issue for issue in ready if issue["title"] == "Ready issue")
assert ready_issue["checklist"] == {"total": 2, "done": 1, "open": 1}

records = data["solve_records"]
assert records["count"] == 4
assert records["counts"]["ready"] == 1
assert records["counts"]["manual"] == 1
assert records["counts"]["recent"] == 1
assert records["counts"]["stale_or_malformed"] == 1

assert "Maintainer Board" in html
assert "Ready issue" in html
assert "Ready record" in html
assert "Filter cards" in html
assert "missing_solve_branch" in html
assert "Show 1 more" in html
assert "card-details" in html
assert "lane-scroll" in html
assert "grid-auto-flow: column" in html
assert "label-ready-for-agent" in html
assert "label-needs-info" in html
assert "label-manual-required" in html
assert "status:" not in html.lower()
assert default_html == html
assert fallback["issues"]["counts"] == data["issues"]["counts"]
assert fallback["solve_records"]["counts"] == data["solve_records"]["counts"]
PY

python3 -m py_compile "$BOARD_SCRIPT"

echo "maintainer-board fixture passed"
