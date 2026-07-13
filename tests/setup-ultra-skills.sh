#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
CONFIGURE="$REPO_ROOT/skills/engineering/setup-ultra-skills/scripts/configure.py"
ADAPTER="$REPO_ROOT/skills/engineering/ultra/scripts/local_ticket_publication.py"
TMPDIR_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/setup-ultra-skills.XXXXXX")"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

init_repo() {
  local repo="$1"
  mkdir -p "$repo/docs/agents"
  printf '# Issue tracker\n\nBase tracker contract.\n' >"$repo/docs/agents/issue-tracker.md"
  printf '# Project guidance\n\n## Agent skills\n\n### Existing tracker\n\nKeep this paragraph.\n\n## Deployment\n\nKeep this section.\n' >"$repo/AGENTS.md"
}

configure() {
  local repo="$1"
  local preset="$2"
  local strategy="$3"
  shift 3
  python3 "$CONFIGURE" \
    --repo "$repo" \
    --preset "$preset" \
    --publication-strategy "$strategy" \
    --instructions AGENTS.md \
    --apply \
    "$@"
}

local_repo="$TMPDIR_ROOT/local"
local_sections_repo="$TMPDIR_ROOT/local-sections"
local_delete_repo="$TMPDIR_ROOT/local-delete-on-cancel"
local_invalid_policy_repo="$TMPDIR_ROOT/local-invalid-policy"
github_remote_repo="$TMPDIR_ROOT/github-remote"
github_staging_repo="$TMPDIR_ROOT/github-staging"
gitlab_remote_repo="$TMPDIR_ROOT/gitlab-remote"
gitlab_staging_repo="$TMPDIR_ROOT/gitlab-staging"
other_repo="$TMPDIR_ROOT/other"
other_invalid_repo="$TMPDIR_ROOT/other-invalid"
reconfigured_repo="$TMPDIR_ROOT/reconfigured"
unmanaged_repo="$TMPDIR_ROOT/unmanaged"
missing_base_repo="$TMPDIR_ROOT/missing-base"

for repo in "$local_repo" "$local_sections_repo" "$local_delete_repo" "$local_invalid_policy_repo" "$github_remote_repo" "$github_staging_repo" "$gitlab_remote_repo" "$gitlab_staging_repo" "$other_repo" "$other_invalid_repo" "$reconfigured_repo" "$unmanaged_repo"; do
  init_repo "$repo"
done

preview_output="$TMPDIR_ROOT/preview.txt"
python3 "$CONFIGURE" \
  --repo "$local_repo" \
  --preset local-markdown \
  --publication-strategy local-review-pending \
  --instructions AGENTS.md >"$preview_output"
test ! -e "$local_repo/docs/agents/ultra-tracker.md"
grep -Fq -- '--- docs/agents/ultra-tracker.md ---' "$preview_output"
grep -Fq -- '--- AGENTS.md ---' "$preview_output"
if grep -Fq '<!-- setup-ultra-skills:begin -->' "$local_repo/AGENTS.md"; then
  echo "preview fixture unexpectedly changed project instructions" >&2
  exit 1
fi

configure "$local_repo" local-markdown local-review-pending
configure "$local_sections_repo" local-markdown local-review-pending \
  --local-ticket-representation tickets-file \
  --local-ticket-path .scratch/product/tickets.md
configure "$local_delete_repo" local-markdown local-review-pending \
  --cancellation-policy delete-on-cancel
mkdir -p "$local_delete_repo/.scratch/feature/issues"
printf 'Status: review-pending\nTicket ID: SETUP-CANCEL-1\nPublication Run: setup-cancel-run\nSource Spec: docs/spec.md\nBlocked By:\nFlags:\n\n# Setup cancellation integration\n' >"$local_delete_repo/.scratch/feature/issues/SETUP-CANCEL-1.md"
python3 "$ADAPTER" register --repo "$local_delete_repo" --representation file-per-ticket --location .scratch/feature/issues --run-id setup-cancel-run >/dev/null
python3 "$ADAPTER" cleanup --repo "$local_delete_repo" --representation file-per-ticket --location .scratch/feature/issues --run-id setup-cancel-run >/dev/null
test ! -e "$local_delete_repo/.scratch/feature/issues/SETUP-CANCEL-1.md"
if configure "$local_invalid_policy_repo" local-markdown local-review-pending \
  --cancellation-policy arbitrary-prose >"$TMPDIR_ROOT/local-invalid-policy.out" 2>&1; then
  echo "local fixture accepted an unsupported cancellation policy" >&2
  exit 1
fi
test ! -e "$local_invalid_policy_repo/docs/agents/ultra-tracker.md"
configure "$github_remote_repo" github remote-review-pending
configure "$github_staging_repo" github local-staging
configure "$gitlab_remote_repo" gitlab remote-review-pending
configure "$gitlab_staging_repo" gitlab local-staging
custom_policy=$'Draft or review-pending representation: The tracker stores provisional Tickets in its review queue.\nReview update operation: Re-open the same draft by durable identifier.\nPublish or promote operation: Promote the complete reviewed set.\nPartial-publish recovery: Resume from the recorded identifier and missing operations.\nClaim and release: Use the tracker lease API with conflict detection.\nState mapping: review-pending is non-claimable and ready-for-agent is claimable.\nBlocker and frontier lookup: Query open blockers before Claim.\nBranch/worktree/PR links: Store links in the tracker development field.\nSolve Record backlinks: Add the receipt URL to the Ticket.\nUnsupported operations: Batch Claim is unavailable.'
configure "$other_repo" other custom --custom-prose "$custom_policy"

if python3 "$CONFIGURE" \
  --repo "$other_invalid_repo" \
  --preset other \
  --publication-strategy custom \
  --instructions AGENTS.md \
  --custom-prose ok \
  --apply >"$TMPDIR_ROOT/other-invalid.out" 2>&1; then
  echo "other fixture accepted an incomplete custom policy" >&2
  exit 1
fi
test ! -e "$other_invalid_repo/docs/agents/ultra-tracker.md"

printf '# Project guidance\n\n## Agent skills\n\n### Existing tracker\n\nKeep this paragraph.\n\n### Ultra tracker\n\nProject-owned tracker guidance.\n\n## Deployment\n\nKeep this section.\n' >"$unmanaged_repo/AGENTS.md"
configure "$unmanaged_repo" local-markdown local-review-pending

mkdir -p "$missing_base_repo"
printf '# Existing guidance\n' >"$missing_base_repo/AGENTS.md"
if python3 "$CONFIGURE" \
  --repo "$missing_base_repo" \
  --preset local-markdown \
  --publication-strategy local-review-pending \
  --instructions AGENTS.md >"$TMPDIR_ROOT/missing-base.out" 2>&1; then
  echo "missing-base fixture unexpectedly configured a contract" >&2
  exit 1
fi
test ! -e "$missing_base_repo/docs/agents/ultra-tracker.md"
grep -Fq 'missing docs/agents/issue-tracker.md' "$TMPDIR_ROOT/missing-base.out"

configure "$reconfigured_repo" github remote-review-pending
python3 "$CONFIGURE" \
  --repo "$reconfigured_repo" \
  --preset github \
  --publication-strategy local-staging \
  --instructions AGENTS.md >"$TMPDIR_ROOT/reconfigure-preview.txt"
grep -Fq 'Publication strategy: local-staging' "$TMPDIR_ROOT/reconfigure-preview.txt"
grep -Fq 'Publication strategy: remote-review-pending' "$reconfigured_repo/docs/agents/ultra-tracker.md"
configure "$reconfigured_repo" github local-staging

python3 - "$REPO_ROOT" "$local_repo" "$local_sections_repo" "$local_delete_repo" "$github_remote_repo" "$github_staging_repo" "$gitlab_remote_repo" "$gitlab_staging_repo" "$other_repo" "$reconfigured_repo" "$unmanaged_repo" <<'PY'
from pathlib import Path
import sys

catalog, local, local_sections, local_delete, github_remote, github_staging, gitlab_remote, gitlab_staging, other, reconfigured, unmanaged = map(Path, sys.argv[1:])

skill = (catalog / "skills/engineering/setup-ultra-skills/SKILL.md").read_text(encoding="utf-8")
metadata = (catalog / "skills/engineering/setup-ultra-skills/agents/openai.yaml").read_text(encoding="utf-8")
assert "disable-model-invocation: true" in skill
assert "allow_implicit_invocation: false" in metadata
assert "Linear" not in skill

required_sections = (
    "# Ultra Tracker Extension",
    "Base tracker: docs/agents/issue-tracker.md",
    "## Ticket Review Publication",
    "## Solve Coordination",
    "Claim and release:",
    "State mapping:",
    "Blocker and frontier lookup:",
    "Branch/worktree/PR links:",
    "Solve Record backlinks:",
    "Unsupported operations:",
)

for repo in (local, local_sections, github_remote, github_staging, gitlab_remote, gitlab_staging, other, reconfigured, unmanaged):
    contract = (repo / "docs/agents/ultra-tracker.md").read_text(encoding="utf-8")
    instructions = (repo / "AGENTS.md").read_text(encoding="utf-8")
    for section in required_sections:
        assert section in contract, (repo, section)
    assert contract.count("# Ultra Tracker Extension") == 1
    assert instructions.count("<!-- setup-ultra-skills:begin -->") == 1
    assert instructions.count("<!-- setup-ultra-skills:end -->") == 1
    assert "Keep this paragraph." in instructions
    assert "Keep this section." in instructions

local_contract = (local / "docs/agents/ultra-tracker.md").read_text(encoding="utf-8")
assert "Publication strategy: local-review-pending" in local_contract
assert "Local Ticket representation: file-per-ticket" in local_contract
assert "Local Ticket path: .scratch/<feature>/issues/<ticket-file>.md" in local_contract
assert "Status: review-pending" in local_contract
assert "Status: ready-for-agent" in local_contract
assert "not a sixth global triage role" in local_contract
assert "Cancellation policy: retain-until-explicit-cleanup" in local_contract
assert "Cancellation behavior: retain the named review-pending run until explicit cleanup." in local_contract
for field in (
    "Stable identity:",
    "Publication journal:",
    "Claim safety:",
):
    assert field in local_contract

sections_contract = (local_sections / "docs/agents/ultra-tracker.md").read_text(encoding="utf-8")
assert "Local Ticket representation: tickets-file" in sections_contract
assert "Local Ticket path: .scratch/product/tickets.md" in sections_contract
assert "<!-- ultra-ticket:begin id=<Ticket-ID> -->" in sections_contract
assert "heading- or title-based identity is unsafe" in sections_contract

delete_contract = (local_delete / "docs/agents/ultra-tracker.md").read_text(encoding="utf-8")
assert "Cancellation policy: delete-on-cancel" in delete_contract
assert "Cancellation behavior: delete only the named review-pending run after exact membership and preimage validation." in delete_contract

for repo in (github_remote, gitlab_remote):
    contract = (repo / "docs/agents/ultra-tracker.md").read_text(encoding="utf-8")
    assert "Publication strategy: remote-review-pending" in contract
    assert "<!-- ultra-publication-set:<run-id> -->" in contract
    assert "creates only missing members" in contract

for repo in (github_staging, gitlab_staging, reconfigured):
    contract = (repo / "docs/agents/ultra-tracker.md").read_text(encoding="utf-8")
    assert "Publication strategy: local-staging" in contract
    assert ".scratch/.ultra-staging/<run-id>/tickets.md" in contract
    assert "manifest.json" in contract
    assert "Ticket discovery exclusion: skip `.scratch/.ultra-staging/`" in contract
    assert ".scratch/.ultra-staging/" in (repo / ".gitignore").read_text(encoding="utf-8")

other_contract = (other / "docs/agents/ultra-tracker.md").read_text(encoding="utf-8")
assert "Publication strategy: custom" in other_contract
for field in (
    "Draft or review-pending representation:",
    "Review update operation:",
    "Publish or promote operation:",
    "Partial-publish recovery:",
    "Claim and release:",
    "State mapping:",
    "Blocker and frontier lookup:",
    "Branch/worktree/PR links:",
    "Solve Record backlinks:",
    "Unsupported operations:",
):
    assert other_contract.count(field) == 1, field
assert "Project-owned tracker guidance." in (unmanaged / "AGENTS.md").read_text(encoding="utf-8")
assert (unmanaged / "AGENTS.md").read_text(encoding="utf-8").count("### Ultra tracker extension") == 1

reconfigured_instructions = (reconfigured / "AGENTS.md").read_text(encoding="utf-8")
assert reconfigured_instructions.count("### Ultra tracker extension") == 1
assert reconfigured_instructions.count("Publication strategy:") == 0

print("setup-ultra-skills fixture passed")
PY
