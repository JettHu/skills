#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
BOARD_SCRIPT="$REPO_ROOT/skills/in-progress/maintainer-board/scripts/maintainer-board.py"
SOLVE_RECORDS_SCRIPT="$REPO_ROOT/skills/engineering/solve-records/scripts/solve-records.py"
LOCAL_PUBLICATION_SCRIPT="$REPO_ROOT/skills/engineering/ultra/scripts/local_ticket_publication.py"
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
ADOPTED_HEAD="$(make_branch feature/adopted-current adopted.txt adopted)"

git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-claim" solve/claim >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-ready" solve/ready >/dev/null 2>&1
git -C "$REPO" worktree add "$TMPDIR_ROOT/wt-adopted-current" feature/adopted-current >/dev/null 2>&1

mkdir -p "$REPO/.scratch/feature-a/issues"
mkdir -p "$REPO/.scratch/feature-a/execution-digests"
mkdir -p "$REPO/.scratch/feature-a/solve-records"
mkdir -p "$REPO/.scratch/feature-b"
mkdir -p "$REPO/.scratch/solve-records"
mkdir -p "$REPO/docs/agents"

cat >"$REPO/docs/agents/ultra-tracker.md" <<'EOF'
# Ultra Tracker Extension

Publication strategy: local-review-pending
Local Ticket representation: tickets-file
Local Ticket path: .scratch/feature-a/tickets.md
EOF

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

cat >"$REPO/.scratch/feature-a/issues/08-review-pending.md" <<'EOF'
Status: review-pending
Ticket ID: RP-1
Publication Run: incomplete-run
Source Spec: docs/spec.md
Flags: solve-in-progress
Category: feature
Created: 2026-07-02

# Review-pending must not be claimed
EOF

cat >"$REPO/.scratch/feature-a/tickets.md" <<'EOF'
# Section Tickets

<!-- ultra-ticket:begin id=TF-1 -->
Status: review-pending
Ticket ID: TF-1
Publication Run: tickets-file-run
Source Spec: docs/spec.md
Blocked By:
Category: feature
Created: 2026-07-02

## Ticket TF-1

- [ ] section-backed acceptance
<!-- ultra-ticket:end -->
EOF

python3 "$LOCAL_PUBLICATION_SCRIPT" register \
  --repo "$REPO" --representation tickets-file \
  --location .scratch/feature-a/tickets.md --run-id tickets-file-run >/dev/null
python3 "$LOCAL_PUBLICATION_SCRIPT" promote \
  --repo "$REPO" --representation tickets-file \
  --location .scratch/feature-a/tickets.md --run-id tickets-file-run >/dev/null

cat >"$REPO/.scratch/feature-b/issue.md" <<'EOF'
---
status: ready-for-agent
category: feature
created: 2026-07-02
---

# Single issue file
EOF

cat >"$REPO/.scratch/feature-a/execution-digests/03-needs-human.md" <<'EOF'
# Execution Digest: Must not be discovered

Strategy: fixture only
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
  local cleanup_resource="${11:-pending}"
  mkdir -p "$(dirname "$path")"
  cat >"$path" <<EOF
---
id: $id
kind: solve_record
state: $state
outcome: candidate
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

## Ticket
Linked Ticket: \`.scratch/feature-a/issues/05-completed-linked.md\`

## Outcome
Result: candidate
Branch/worktree/commit/PR: \`$head\`, \`$worktree\`
Resource ownership: solve-owned

## What Changed
- fixture

## Verification
Status: $checks
- \`fixture\` - $checks

## Review
Post-Execution Review: passed
- fixture

## Merge
Status: $merge
Gate:
- [ ] Required checks passed
Reason:
- Rollout/config disposition: none; fixture

## Resources
Base: \`master\`
Base SHA: \`$BASE_SHA\`
Head: \`$head\`
Head SHA: \`$head_sha\`
Worktree: \`$worktree\`
Cleanup: $cleanup_resource

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

write_record "$REPO/.scratch/feature-a/solve-records/20260703-adopted-current.md" \
  "20260703-adopted-current" open feature/adopted-current "$ADOPTED_HEAD" "../wt-adopted-current" true "Adopted current branch" passed "manual required" \
  "done; adopted worktree and candidate branch are user-owned"

cat >"$REPO/.scratch/feature-a/solve-records/20260703-needs-info.md" <<'EOF'
---
id: 20260703-needs-info
kind: solve_record
state: open
outcome: needs-info
issues:
  - .scratch/feature-a/issues/03-needs-human.md
created_at: 2026-07-03T10:00:00+08:00
cleanup_done: true
---

# Solve Record: Needs information receipt

## Ticket
Linked Ticket: `.scratch/feature-a/issues/03-needs-human.md`

## Outcome
Result: needs-info
Branch/worktree/commit/PR: none retained
Resource ownership: none

## Attempt Summary
- Investigated the available repository facts.

## Confirmed Findings
- The required API contract is absent from the approved Ticket.

## Blocker Or Requested Information
- Confirm the external API contract before implementation resumes.

## Resume Or Cleanup
Next action: maintainers provide the API contract, then resume from the Ticket.

## Resources
Cleanup: complete; no resources retained
EOF

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
mkdir -p "$(dirname "$STANDALONE_SCRIPT")/skills/engineering/solve-records/scripts"
cp "$SOLVE_RECORDS_SCRIPT" "$(dirname "$STANDALONE_SCRIPT")/skills/engineering/solve-records/scripts/solve-records.py"
mkdir -p "$(dirname "$STANDALONE_SCRIPT")/skills/engineering/ultra/scripts"
cp "$LOCAL_PUBLICATION_SCRIPT" "$(dirname "$STANDALONE_SCRIPT")/skills/engineering/ultra/scripts/local_ticket_publication.py"
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
assert data["issues"]["count"] == 15
assert data["issues"]["counts"]["ready_for_agent"] == 3
assert data["issues"]["counts"]["claimed_or_in_progress"] == 2
assert data["issues"]["counts"]["needs_human"] == 1
assert data["issues"]["counts"]["blocked_or_dependent"] == 1
assert data["issues"]["counts"]["completed_with_solve_record"] == 1
assert data["issues"]["counts"]["completed_without_solve_record"] == 6
assert data["issues"]["counts"]["other"] == 1
assert "Execution Digest: Must not be discovered" not in {
    issue["title"]
    for bucket in data["issues"]["buckets"].values()
    for issue in bucket
}

ready = data["issues"]["buckets"]["ready_for_agent"]
assert {issue["metadata_format"] for issue in ready} == {"header", "frontmatter", "tickets-file-section"}

claimed = data["issues"]["buckets"]["claimed_or_in_progress"]
warnings = [warning["code"] for issue in claimed for warning in issue["warnings"]]
assert "missing_solve_branch" in warnings
assert "missing_solve_worktree" in warnings
assert all(issue["title"] != "Review-pending must not be claimed" for issue in ready + claimed)
provisional = data["issues"]["buckets"]["other"][0]
assert provisional["title"] == "Review-pending must not be claimed"
assert "publication_invalid" in {warning["code"] for warning in provisional["warnings"]}

completed = data["issues"]["buckets"]["completed_with_solve_record"][0]
assert completed["solve_records"] == ["../solve-records/20260702-ready.md"]
assert completed["checklist"] == {"total": 0, "done": 0, "open": 0}

ready_issue = next(issue for issue in ready if issue["title"] == "Ready issue")
assert ready_issue["checklist"] == {"total": 2, "done": 1, "open": 1}

records = data["solve_records"]
assert records["count"] == 6
assert records["counts"]["ready"] == 1
assert records["counts"]["manual"] == 2
assert records["counts"]["recent"] == 1
assert records["counts"]["recovery"] == 1
assert records["counts"]["stale_or_malformed"] == 1
adopted = next(
    record for record in records["buckets"]["manual"] if record["id"] == "20260703-adopted-current"
)
assert adopted["base"] == "master"
assert adopted["head"] == "feature/adopted-current"
assert "user-owned" in adopted["resource_cleanup"]
recovery = records["buckets"]["recovery"][0]
assert recovery["id"] == "20260703-needs-info"
assert recovery["outcome"] == "needs-info"
assert recovery["recovery_action"].startswith("maintainers provide")

assert "Maintainer Board" in html
assert "Ready issue" in html
assert "Ready record" in html
assert "Adopted current branch" in html
assert "Needs information receipt" in html
assert "Landing branch (base)" in html
assert "Candidate branch (head)" in html
assert "Cleanup ownership" in html
assert "user-owned adopted resources" in html
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

CONFIGURED_FILE_REPO="$TMPDIR_ROOT/configured-file-per"
git init -b master "$CONFIGURED_FILE_REPO" >/dev/null
git -C "$CONFIGURED_FILE_REPO" config user.email "maintainer-board@example.test"
git -C "$CONFIGURED_FILE_REPO" config user.name "Maintainer Board Test"
mkdir -p "$CONFIGURED_FILE_REPO/docs/agents" "$CONFIGURED_FILE_REPO/.tracker/tickets"
cat >"$CONFIGURED_FILE_REPO/docs/agents/ultra-tracker.md" <<'EOF'
# Ultra Tracker Extension

Publication strategy: local-review-pending
Local Ticket representation: file-per-ticket
Local Ticket path: .tracker/tickets/<ticket-file>.md
EOF
cat >"$CONFIGURED_FILE_REPO/.tracker/tickets/CONFIG-1.md" <<'EOF'
State: review-pending
Ticket ID: CONFIG-1
Publication Run: configured-run
Source Spec: docs/spec.md
Blocked By:
Labels:

# Configured file-per Ticket
EOF
python3 "$LOCAL_PUBLICATION_SCRIPT" register \
  --repo "$CONFIGURED_FILE_REPO" --representation file-per-ticket \
  --location .tracker/tickets --run-id configured-run >/dev/null
python3 "$BOARD_SCRIPT" --repo "$CONFIGURED_FILE_REPO" --json >"$TMPDIR_ROOT/configured-provisional.json"
python3 "$LOCAL_PUBLICATION_SCRIPT" promote \
  --repo "$CONFIGURED_FILE_REPO" --representation file-per-ticket \
  --location .tracker/tickets --run-id configured-run >/dev/null
python3 "$BOARD_SCRIPT" --repo "$CONFIGURED_FILE_REPO" --json >"$TMPDIR_ROOT/configured-promoted.json"
python3 - "$CONFIGURED_FILE_REPO/.tracker/tickets/CONFIG-1.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text(
    path.read_text(encoding="utf-8").replace("State: ready-for-agent", "State: completed", 1),
    encoding="utf-8",
)
PY
python3 "$BOARD_SCRIPT" --repo "$CONFIGURED_FILE_REPO" --json >"$TMPDIR_ROOT/configured-completed.json"
python3 - "$TMPDIR_ROOT/configured-provisional.json" "$TMPDIR_ROOT/configured-promoted.json" "$TMPDIR_ROOT/configured-completed.json" <<'PY'
import json
import sys
from pathlib import Path

provisional = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
promoted = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
completed = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
assert provisional["issues"]["counts"]["ready_for_agent"] == 0
assert provisional["issues"]["counts"]["other"] == 1
ready = promoted["issues"]["buckets"]["ready_for_agent"]
assert len(ready) == 1
assert ready[0]["path"] == ".tracker/tickets/CONFIG-1.md"
terminal = completed["issues"]["buckets"]["completed_without_solve_record"]
assert len(terminal) == 1
assert terminal[0]["status"] == "completed"
PY

python3 -m py_compile "$BOARD_SCRIPT"

echo "maintainer-board fixture passed"
