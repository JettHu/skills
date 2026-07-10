# Solve Record Format

Read this only when creating or repairing a solve record.

A Solve Record is an Attempt Receipt: a compact, local Markdown handoff when
an Attempt reaches a meaningful outcome. It is not a Claim, PR, MR, run log,
or replacement for the linked Ticket.

Create a record only for one of these outcomes:

- `candidate`: a finished, checkable delivery candidate.
- `blocked`: substantive work or evidence is retained after a required check,
  integration, or tooling blocker.
- `needs-info`: substantive assessment found information that only a human can
  supply.
- `ready-for-human`: a human-owned product, API, data, security, architecture,
  or significant UX decision stopped the Attempt.
- `abandoned` or `superseded`: retained resources or evidence need a durable
  disposition.

Do not create a record for a transient tool failure, an immediately released
Claim with no useful finding, or fully cleaned work with no recovery value.

## Machine-readable contract

Every new record uses this common frontmatter:

```yaml
id: 20260710-1432-caption-fix
kind: solve_record
state: open
outcome: candidate
issues:
  - .scratch/caption/issues/01.md
created_at: 2026-07-10T14:32:00+08:00
cleanup_done: false
```

`state` is the record lifecycle (`open`, `merged`, or `closed`); `outcome` is
the Attempt result. Keep them separate. `issues` contains one or more linked
Ticket paths or identifiers, even though the common header names the primary
linked Ticket.

The only supported outcomes are:

```text
candidate | blocked | needs-info | ready-for-human | abandoned | superseded
```

Candidate records additionally require these fields because candidate gates
need live Git evidence:

```yaml
base: main
base_sha: abc1234
head: solve/20260710-1432-caption-fix
head_sha: def5678
worktree: ../.agent-worktrees/project/project-solve-caption-fix
```

Recovery records do not require candidate fields. Add only retained resource
references that actually exist, such as `branch`, `worktree`, `commit`, `pr`,
`external_provider`, `external_url`, or `source_spec`. An empty recovery
record is valid when its body makes the no-resource disposition clear.

Optional lifecycle fields remain `merged_at`, `merged_sha`, `closed_at`, and
`updated_at`. Do not introduce a JSON registry or v1-style lifecycle fields
such as `phase`, `merge_mode`, `merge_status`, `review_status`,
`checks_status`, `attempt_id`, `candidate_state`, `human_state`, or
`cleanup_state`.

### Legacy candidate compatibility

Existing records without `outcome` remain candidates without rewriting them
only when they satisfy the complete legacy candidate schema and retain the old
candidate body shape (rather than a new `## Ticket`, `## Outcome`,
`## What Changed`, `## Verification`, or recovery-only body section):

```text
id, kind: solve_record, state, base, base_sha, head, head_sha, issues,
worktree, created_at, cleanup_done
```

The helper reports that mapping as legacy compatibility. A no-discriminator
record shaped like a new receipt or recovery receipt is malformed; never infer
a candidate merely because `outcome` is absent. Legacy `## Issues`,
`## Changes`, and `## Checks` sections remain readable alongside the new names
below.

## Common body header

Every new record starts with this header before its outcome-specific sections:

```md
# Solve Record: <title>

## Ticket
Linked Ticket: `.scratch/caption/issues/01.md`
Source Spec: `.scratch/caption/reference.md` <!-- optional -->

## Outcome
Result: <candidate | blocked | needs-info | ready-for-human | abandoned | superseded>
Branch/worktree/commit/PR: <retained references, or none>
Resource ownership: <solve-owned | user-owned | mixed | no retained resources>; <cleanup responsibility>
```

`Branch/worktree/commit/PR` is descriptive rather than a candidate-gate
substitute. Record only resources that are retained for a future resume,
review, close/supersede decision, or safe cleanup. The ownership line must say
who can remove each retained resource; it must never imply that user-owned
resources are safe to delete.

## Candidate record

Use this shape only for `outcome: candidate`:

```md
# Solve Record: <title>

## Ticket
Linked Ticket: `.scratch/caption/issues/01.md`
Source Spec: `.scratch/caption/reference.md`

## Outcome
Result: candidate
Branch/worktree/commit/PR: `solve/20260710-1432-caption-fix`, `../.agent-worktrees/project/project-solve-caption-fix`
Resource ownership: solve-owned; `$solve-records cleanup` may remove only after candidate cleanup gates pass

## What Changed
- <implementation summary>

## Verification
Status: passed | unavailable | stale
- `<command or check>` - passed | unavailable | stale

## Review
Post-Execution Review: passed
- <integrated-candidate review outcome>

## Merge
Status: ready | auto-merged | manual required
Reason:
- Rollout/config disposition: <none | pre-merge action required | post-merge activation required>; <rationale>
- Activation: <post-merge action or none>
- Smoke: <validation check or none>
- Rollback: <disable or rollback path or none>
- Landing: <fast-forward | merge-commit | resolved-merge-commit | blocked>, `<landing_sha or none>`

## Resources
Base: `<base>`
Base SHA: `<base_sha>`
Head: `<head>`
Head SHA: `<head_sha>`
Worktree: `<repo-relative worktree path>`
Cleanup: pending | done | blocked

## Notes
- <durable low-risk decision, caveat, or none>
```

When the Attempt used an Execution Digest, distill each durable decision or deviation here or in `## Review` with its reason, impact, and evidence. Keep the working Digest only while it retains resume value or repo policy requires it; otherwise delete it after this transfer.

Candidate acceptance review, merge, ship, land, and candidate cleanup require
this candidate-only Git evidence. `post-merge activation required` can be
ready only when the record explains why code merge is safe, the activation,
smoke check, and rollback or disable path.

A manual-gated or blocked Post-Execution Review is not a candidate receipt.
Route the Attempt to the matching recovery outcome and place the finding in
`## Confirmed Findings` or `## Blocker Or Requested Information`.

## Recovery record

Use this shape for every non-candidate outcome:

```md
# Solve Record: <title>

## Ticket
Linked Ticket: `.scratch/caption/issues/01.md`
Source Spec: `.scratch/caption/reference.md` <!-- optional -->

## Outcome
Result: blocked
Branch/worktree/commit/PR: `solve/20260710-1432-caption-fix`, `../.agent-worktrees/project/project-solve-caption-fix`
Resource ownership: mixed; the solve branch is solve-owned, the adopted worktree is user-owned

## Attempt Summary
- <what was assessed or changed before the handoff>

## Confirmed Findings
- <facts, failed validation evidence, or decision constraints>

## Blocker Or Requested Information
- <the blocker, missing information, or human decision>

## Resume Or Cleanup
Next action: resume | provide information | human decision | close | supersede | cleanup
- <safe next step and the evidence/resources it needs>

## Resources
Cleanup: pending | done | blocked | none
- <resource, owner, safety evidence, and whether it is retained>
```

`blocked`, `needs-info`, and `ready-for-human` normally remain open and enter
the Needs Attention or Resume view. `abandoned` and `superseded` normally
close after their disposition is recorded. A resumed Attempt reuses the linked
recovery record only when it keeps the same retained resources and recovery
context; a clean restart closes or supersedes the old receipt first.

When the Attempt used an Execution Digest, distill durable decisions and deviations into `## Attempt Summary` or `## Confirmed Findings` with their reason, impact, and evidence. Keep the working Digest only while the retained recovery context has resume value or repo policy requires it; otherwise delete it after this transfer.

Recovery records never enter acceptance, merge, ship, land, or candidate
cleanup gates. Their resource guidance is ownership-based: verify retained
resources and their cleanup evidence directly, leave user-owned resources in
place, and do not borrow candidate merge prerequisites.

## Ticket backlink

Use a path-only backlink in the Ticket. Keep checks, merge rationale, outcome,
resource ownership, summaries, and record lifecycle in the record itself.

```md
## Comments

### Solve Record

- `../solve-records/20260710-1432-caption-fix.md`
```

If a Ticket has multiple records, use `### Solve Records` with one path-only
bullet per receipt.
