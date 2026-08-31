# Solve Record Format

Read this only when creating or repairing a solve record.

A Solve Record is an Attempt Receipt: a compact, local Markdown handoff when
an Attempt reaches a meaningful outcome. It is not a Claim, PR, MR, run log,
or replacement for the linked Ticket.

Submit a canonical handoff only for one of these outcomes:

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

## Compact canonical receipt

The outcome-handoff adapter is the only canonical writer for every new receipt.
Callers provide a caller-generated opaque handoff key, exact Ticket scope,
semantic outcome, and concise Summary; recovery calls also provide the next
action and complete retained-resource declaration, while successor calls name
the exact predecessor. Callers never prewrite or repair the destination file.

Every new compact canonical receipt uses this common frontmatter:

```yaml
state: open
outcome: candidate
tickets:
  - .scratch/caption/issues/01.md
handoff_key: "opaque-caller-key"
binding_digest: 82b4...f91a
head: solve/20260710-1432-caption-fix
head_sha: def5678
```

`state` is the receipt lifecycle; `outcome` is the creation-time Attempt result.
Keep them separate. `tickets` is the authoritative normalized membership.
`handoff_key` identifies exactly one outcome handoff, and `binding_digest`
detects changes to its immutable binding. Candidate `head` and `head_sha` are
derived from the active claimed worktree, never supplied as receipt text.

The only supported outcomes are:

```text
candidate | blocked | needs-info | ready-for-human | abandoned | superseded
```

Recovery receipts omit candidate Git fields and add the canonical recovery
intent and complete resource declaration:

```yaml
recovery_next_action: "resume"
retained_resources:
  - "solve-owned:branch:solve/20260710-1432-caption-fix"
  - "solve-owned:worktree:/absolute/verified/worktree"
```

The body contains one `## Summary` with the concise completed-work and
validation conclusion, or the recovery finding and next useful action. It does
not mirror Ticket membership, outcome, Git identity, Claim state, or resource
lists. The adapter derives the canonical path, installs a complete Markdown
file atomically, applies Ticket, backlink, Claim and resource transitions, and
returns success only after rereading the whole postcondition.

Exact retries use the same handoff key and immutable binding. A partial
cross-surface transition is retryable handoff attention, not a second receipt
state. Retry the same key; changed membership, outcome, candidate identity,
recovery intent, resources, or predecessor under that key is a conflict.

A resumed Attempt reaching another meaningful outcome uses a new key and new
receipt with `supersedes`. Only successful successor convergence closes the
predecessor with `closed_at` and reciprocal `superseded_by`; the predecessor
keeps its original outcome.

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

### Legacy terminal outcome compatibility

The read-only dashboard also accepts the historical terminal values
`merged`, `landed`, and `completed` when the record has `state: merged`. It
does not rewrite the receipt or treat these values as canonical outcomes. The
record is routed to Recently merged when `cleanup_done: true`, or Cleanup
pending otherwise. The same values remain malformed when paired with an open
or otherwise non-terminal state, so an invalid lifecycle cannot be hidden by
this compatibility path.

### Closed evidence and superseded candidate compatibility

A historical `state: closed`, `outcome: candidate` receipt may omit current
candidate ref fields when its body explicitly records either `Next action:
supersede...` or a zero-diff/evidence-only result with no repository change.
The read-only dashboard treats that receipt as terminal: `cleanup_done: false`
routes to Cleanup pending, and `cleanup_done: true` routes to the terminal
recent view. This is read-only compatibility; new receipts must still use the
canonical outcome-specific contract.

Canonical recovery receipts with `state: closed` and `outcome: superseded` or
`abandoned` use the same terminal routing when their explicit cleanup
disposition is complete. They remain Cleanup pending while `cleanup_done` is
false, and are not treated as active Recovery after cleanup. The outcome still
records why the Attempt ended; it is not rewritten to `candidate` or `merged`.

## Legacy full-format compatibility

Historical full-format records may use this common body header. The parser
continues to normalize it, but the canonical writer does not emit it:

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

### Legacy full-format candidate

This historical shape remains readable for `outcome: candidate`:

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
Requirement-to-evidence audit: passed
- Evidence summary: <concise strongest scope-matched current evidence across the full Ticket and approved source Spec>
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

Historical records may preserve durable Execution Digest decisions here or in
`## Review`. New outcome handoffs put only the concise conclusion in
`## Summary`; later acceptance or landing evidence belongs to its owning gate.

The audit lines are a concise conclusion and evidence summary, not a copied
Ticket, per-requirement checklist, parser field, or second gate. `/ultra solve`
owns the live full-boundary audit before receipt creation; this receipt only
preserves a truthful maintainer-facing handoff of that passed conclusion.

Candidate acceptance review, merge, ship, land, and candidate cleanup require
this candidate-only Git evidence. `post-merge activation required` can be
ready only when the record explains why code merge is safe, the activation,
smoke check, and rollback or disable path.

A manual-gated or blocked Post-Execution Review is not a candidate receipt.
Route the Attempt to the matching recovery outcome and place the finding in
`## Confirmed Findings` or `## Blocker Or Requested Information`.

### Legacy full-format recovery

This historical shape remains readable for non-candidate outcomes:

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
the Needs Attention or Resume view. `abandoned` and creation-time `superseded`
normally close after their disposition is recorded. A resumed Attempt reuses
the recovery context and retained resources, but every new meaningful handoff
uses a new handoff key and a new receipt. The successor receipt records
`supersedes`; only after its handoff postcondition succeeds does the predecessor
close with `closed_at` and reciprocal `superseded_by`. The predecessor keeps
its creation-time outcome and remains open when successor handoff fails.

Historical records may preserve durable Execution Digest decisions in these
sections. New outcome handoffs use the compact `## Summary` body.

Recovery records never enter acceptance, merge, ship, land, or candidate
cleanup gates. Their resource guidance is ownership-based: verify retained
resources and their cleanup evidence directly, leave user-owned resources in
place, and do not borrow candidate merge prerequisites.

### Legacy Ticket backlink shape

Historical Ticket backlinks use this path-only shape. For new handoffs the
adapter writes and verifies it; callers do not append or edit it themselves.

```md
## Comments

### Solve Record

- `../solve-records/20260710-1432-caption-fix.md`
```

If a Ticket has multiple records, use `### Solve Records` with one path-only
bullet per receipt.
