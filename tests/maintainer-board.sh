#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
BOARD_SCRIPT="$REPO_ROOT/skills/in-progress/maintainer-board/scripts/maintainer-board.py"
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
Cancellation policy: retain-until-explicit-cleanup
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

write_record "$REPO/.scratch/feature-a/solve-records/20260702-grouped.md" \
  "20260702-grouped" open solve/ready "$READY_HEAD" "../wt-ready" false "Grouped ready record" passed ready
python3 - "$REPO/.scratch/feature-a/solve-records/20260702-grouped.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace(
    "  - .scratch/feature-a/issues/05-completed-linked.md\n",
    "  - .scratch/feature-a/issues/05-completed-linked.md\n"
    "  - .scratch/feature-a/issues/06-completed-unlinked.md\n",
    1,
)
text = text.replace(
    "Linked Ticket: `.scratch/feature-a/issues/05-completed-linked.md`",
    "Linked Tickets: `.scratch/feature-a/issues/05-completed-linked.md`, "
    "`.scratch/feature-a/issues/06-completed-unlinked.md`",
    1,
)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/solve-records/20260702-manual.md" \
  "20260702-manual" open solve/manual "$MANUAL_HEAD" "../wt-ready" false "Manual record" unavailable "manual required"

write_record "$REPO/.scratch/solve-records/20260702-stale.md" \
  "20260702-stale" open solve/missing deadbeef "../wt-ready" false "Stale record" passed ready

write_record "$REPO/.scratch/solve-records/20260702-recent.md" \
  "20260702-recent" merged solve/recent "$RECENT_HEAD" "." true "Recent record" passed "auto-merged"

write_record "$REPO/.scratch/solve-records/20260702-cleanup.md" \
  "20260702-cleanup" merged solve/ready "$READY_HEAD" "../wt-ready" false "Cleanup record" passed "auto-merged"
python3 - "$REPO/.scratch/solve-records/20260702-cleanup.md" "$BASE_SHA" "$READY_HEAD" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
base_sha, ready_head = sys.argv[2:]
text = path.read_text(encoding="utf-8")
text = text.replace("base: master", "base: solve/ready", 1)
text = text.replace(f"base_sha: {base_sha}", f"base_sha: {ready_head}", 1)
text = text.replace("Base: `master`", "Base: `solve/ready`", 1)
text = text.replace(f"Base SHA: `{base_sha}`", f"Base SHA: `{ready_head}`", 1)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/feature-a/solve-records/20260703-adopted-current.md" \
  "20260703-adopted-current" open feature/adopted-current "$ADOPTED_HEAD" "../wt-adopted-current" true "Adopted current branch" passed "manual required" \
  "done; adopted worktree and candidate branch are user-owned"

write_record "$REPO/.scratch/feature-a/solve-records/20260703-low-risk.md" \
  "20260703-low-risk" open solve/ready "$READY_HEAD" "../wt-ready" false "Low-risk unavailable candidate" unavailable ready
python3 - "$REPO/.scratch/feature-a/solve-records/20260703-low-risk.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8").replace(
    "## Notes\n- fixture",
    "## Notes\n- low-risk; no meaningful automated check exists; no manual-review trigger; evidence: deterministic inspection",
)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/feature-a/solve-records/20260703-post-activation.md" \
  "20260703-post-activation" open solve/ready "$READY_HEAD" "../wt-ready" false "Post-activation candidate" passed ready
python3 - "$REPO/.scratch/feature-a/solve-records/20260703-post-activation.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8").replace(
    "- Rollout/config disposition: none; fixture",
    "- Rollout/config disposition: post-merge activation required; code merge is safe before activation.\n- Activation: enable the fixture flag.\n- Smoke: inspect the fixture board.\n- Rollback: disable the fixture flag.",
)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/feature-a/solve-records/20260703-remote-primary.md" \
  "20260703-remote-primary" open solve/ready "$READY_HEAD" "../wt-ready" false "Remote-primary candidate" passed ready
python3 - "$REPO/.scratch/feature-a/solve-records/20260703-remote-primary.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8").replace(
    "cleanup_done: false\n",
    "cleanup_done: false\nexternal_provider: github\nexternal_url: https://example.test/pull/1\n",
    1,
)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/feature-a/solve-records/20260703-bulleted-status.md" \
  "20260703-bulleted-status" open solve/ready "$READY_HEAD" "../wt-ready" false "Bulleted status candidate" passed ready
python3 - "$REPO/.scratch/feature-a/solve-records/20260703-bulleted-status.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8").replace("Status: passed", "- Status: passed", 1)
text = text.replace("Status: ready", "- Status: ready", 1)
path.write_text(text, encoding="utf-8")
PY

write_record "$REPO/.scratch/feature-a/solve-records/20260703-bulleted-cleanup.md" \
  "20260703-bulleted-cleanup" open solve/ready "$READY_HEAD" "../wt-ready" false "Bulleted cleanup candidate" passed "manual required" \
  "done; adopted worktree and candidate branch are user-owned"
python3 - "$REPO/.scratch/feature-a/solve-records/20260703-bulleted-cleanup.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8").replace(
    "Cleanup: done; adopted worktree and candidate branch are user-owned",
    "- Cleanup: done; adopted worktree and candidate branch are user-owned",
    1,
)
path.write_text(text, encoding="utf-8")
PY

cat >"$REPO/.scratch/feature-a/solve-records/20260703-legacy.md" <<EOF
---
id: 20260703-legacy
kind: solve_record
state: open
base: master
base_sha: $BASE_SHA
head: solve/ready
head_sha: $READY_HEAD
issues:
  - .scratch/feature-a/issues/05-completed-linked.md
worktree: ../wt-ready
created_at: 2026-07-03T10:00:00+08:00
cleanup_done: false
---

# Solve Record: Legacy candidate

## Changes
- Legacy candidate remains readable.

## Checks
Status: passed

## Review
Post-Execution Review: passed

## Merge
Status: ready
- Rollout/config disposition: none; fixture

## Resources
Cleanup: pending

## Notes
- fixture
EOF

write_recovery_record() {
  local path="$1"
  local id="$2"
  local state="$3"
  local outcome="$4"
  local retained="$5"
  local ownership="$6"
  local blocker="$7"
  local action="$8"
  local cleanup="$9"
  cat >"$path" <<EOF
---
id: $id
kind: solve_record
state: $state
outcome: $outcome
issues:
  - .scratch/feature-a/issues/03-needs-human.md
created_at: 2026-07-03T10:00:00+08:00
cleanup_done: $cleanup
---

# Solve Record: $outcome receipt

## Ticket
Linked Ticket: \`.scratch/feature-a/issues/03-needs-human.md\`

## Outcome
Result: $outcome
Branch/worktree/commit/PR: $retained
Resource ownership: $ownership

## Attempt Summary
- Investigated the available repository facts.

## Confirmed Findings
- Confirmed finding for $outcome.

## Blocker Or Requested Information
- $blocker

## Resume Or Cleanup
Next action: $action

## Resources
Cleanup: $([[ "$cleanup" == true ]] && echo "complete; no resources retained" || echo "pending; follow recorded ownership")
EOF
}

write_recovery_record "$REPO/.scratch/feature-a/solve-records/20260703-blocked.md" \
  "20260703-blocked" open blocked '`solve/blocked`, `../wt-blocked`' "solve-owned by the resumable Attempt" \
  "dependency is unavailable" "resume after the dependency is restored" false
write_recovery_record "$REPO/.scratch/feature-a/solve-records/20260703-needs-info.md" \
  "20260703-needs-info" open needs-info "none retained" "no retained resources" \
  "confirm the external API <contract>" "maintainers provide the API contract, then resume from the Ticket" true
write_recovery_record "$REPO/.scratch/feature-a/solve-records/20260703-ready-for-human.md" \
  "20260703-ready-for-human" open ready-for-human '`feature/human-choice`' "user-owned branch" \
  "choose the public API behavior" "record the human decision, then resume" false
write_recovery_record "$REPO/.scratch/feature-a/solve-records/20260703-abandoned.md" \
  "20260703-abandoned" closed abandoned '`solve/abandoned`' "solve-owned cleanup" \
  "the Attempt was intentionally abandoned" "remove the retained branch after ownership verification" false
write_recovery_record "$REPO/.scratch/feature-a/solve-records/20260703-superseded.md" \
  "20260703-superseded" closed superseded "none retained" "no retained resources" \
  "a newer Attempt replaced this one" "no action; follow the newer receipt" true

write_recovery_record "$REPO/.scratch/feature-a/solve-records/20260703-invalid-frontmatter.md" \
  "20260703-invalid-frontmatter" open blocked "none retained" "no retained resources" \
  "this record must stay malformed" "do not classify this corrupt receipt" true
python3 - "$REPO/.scratch/feature-a/solve-records/20260703-invalid-frontmatter.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8").replace(
    "kind: solve_record\n",
    "kind: solve_record\nTHIS IS INVALID\n",
    1,
)
path.write_text(text, encoding="utf-8")
PY

cat >"$REPO/.scratch/solve-records/20260703-malformed.md" <<'EOF'
---
id: 20260703-malformed
kind: wrong_kind
state: open
issues:
  - .scratch/feature-a/issues/03-needs-human.md
created_at: 2026-07-03T10:00:00+08:00
cleanup_done: false
---

# Solve Record: malformed receipt
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
mkdir -p "$(dirname "$STANDALONE_SCRIPT")/skills/engineering/ultra/scripts"
cp "$LOCAL_PUBLICATION_SCRIPT" "$(dirname "$STANDALONE_SCRIPT")/skills/engineering/ultra/scripts/local_ticket_publication.py"
cp "$(dirname "$LOCAL_PUBLICATION_SCRIPT")/local_ticket_surface.py" "$(dirname "$STANDALONE_SCRIPT")/skills/engineering/ultra/scripts/local_ticket_surface.py"
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
assert records["count"] == 20
assert records["counts"]["ready"] == 5
assert records["counts"]["manual"] == 5
assert records["counts"]["cleanup"] == 1
assert records["counts"]["recent"] == 1
assert records["counts"]["recovery"] == 5
assert records["counts"]["stale_or_malformed"] == 3
cleanup = records["buckets"]["cleanup"][0]
assert cleanup["id"] == "20260702-cleanup"
assert cleanup["cleanup_plan"] == {
    "id": "20260702-cleanup",
    "path": ".scratch/solve-records/20260702-cleanup.md",
    "status": "safe",
    "reason": "",
    "worktree": "../wt-ready",
    "head": "solve/ready",
}
adopted = next(
    record for record in records["buckets"]["manual"] if record["id"] == "20260703-adopted-current"
)
assert adopted["base"] == "master"
assert adopted["head"] == "feature/adopted-current"
assert "user-owned" in adopted["resource_cleanup"]
assert "20260703-remote-primary" in {
    record["id"] for record in records["buckets"]["manual"]
}
assert "20260703-bulleted-status" in {
    record["id"] for record in records["buckets"]["manual"]
}
bulleted_cleanup = next(
    record
    for record in records["buckets"]["manual"]
    if record["id"] == "20260703-bulleted-cleanup"
)
assert bulleted_cleanup["resource_cleanup"] == ""
recovery = {record["outcome"]: record for record in records["buckets"]["recovery"]}
assert set(recovery) == {"blocked", "needs-info", "ready-for-human", "abandoned", "superseded"}
assert recovery["needs-info"]["recovery_action"].startswith("maintainers provide")
assert "external API <contract>" in recovery["needs-info"]["blocker_or_requested_information"]
assert recovery["blocked"]["retained_resources"] == "`solve/blocked`, `../wt-blocked`"
assert recovery["ready-for-human"]["resource_ownership"] == "user-owned branch"
assert all(not record.get("malformed") for record in recovery.values())
ready_records = {record["id"]: record for record in records["buckets"]["ready"]}
assert {
    "20260702-ready",
    "20260702-grouped",
    "20260703-low-risk",
    "20260703-post-activation",
    "20260703-legacy",
} == set(ready_records)
assert ready_records["20260702-grouped"]["issues"] == [
    ".scratch/feature-a/issues/05-completed-linked.md",
    ".scratch/feature-a/issues/06-completed-unlinked.md",
]
assert ready_records["20260703-low-risk"]["low_risk_exception"] is True
assert ready_records["20260703-post-activation"]["rollout_config_disposition"] == "post-merge activation required"
assert ready_records["20260703-legacy"]["legacy_outcome"] is True
malformed_records = {
    record["id"]: record for record in records["buckets"]["stale_or_malformed"]
}
assert malformed_records["20260703-invalid-frontmatter"]["malformed"] == (
    "invalid frontmatter line: THIS IS INVALID"
)

def flattened(snapshot):
    return [
        record
        for bucket in snapshot["solve_records"]["buckets"].values()
        for record in bucket
    ]

for snapshot in (data, fallback):
    items = flattened(snapshot)
    ids = [record["id"] for record in items]
    assert len(ids) == len(set(ids)) == snapshot["solve_records"]["count"]
    recovery_ids = {record["id"] for record in snapshot["solve_records"]["buckets"]["recovery"]}
    candidate_lane_ids = {
        record["id"]
        for bucket in ("ready", "manual", "cleanup", "recent")
        for record in snapshot["solve_records"]["buckets"][bucket]
    }
    assert recovery_ids.isdisjoint(candidate_lane_ids)

assert fallback["solve_records"]["counts"] == records["counts"]
for bucket in records["buckets"]:
    helper_items = {record["id"]: record for record in records["buckets"][bucket]}
    fallback_items = {record["id"]: record for record in fallback["solve_records"]["buckets"][bucket]}
    assert helper_items.keys() == fallback_items.keys(), bucket
    for record_id in helper_items:
        for field in (
            "outcome",
            "linked_ticket",
            "issues",
            "blocker_or_requested_information",
            "retained_resources",
            "resource_ownership",
            "recovery_action",
            "resource_cleanup",
            "cleanup_plan",
            "low_risk_exception",
            "rollout_config_disposition",
            "legacy_outcome",
            "malformed",
        ):
            assert fallback_items[record_id].get(field) == helper_items[record_id].get(field), (
                bucket,
                record_id,
                field,
            )

assert "Maintainer Board" in html
assert "Ready issue" in html
assert "Ready record" in html
assert "Adopted current branch" in html
assert "needs-info receipt" in html
assert "Blocked receipt" in html or "blocked receipt" in html
assert "external API &lt;contract&gt;" in html
assert "Blocker or requested information" in html
assert "Retained resources" in html
assert "Resource owner" in html
assert "Next resume or cleanup action" in html
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
Cancellation policy: retain-until-explicit-cleanup
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
