# Local Markdown Adapter

This document describes the configured `bundled-local-markdown-v1` adapter. The
shared meanings and state vocabulary remain in [the tracker index](../ultra-tracker.md)
and [the base Local Markdown contract](../issue-tracker.md).

## Surface

Tickets are one Markdown file per Ticket under the configured effort directory.
Solve Records and execution context remain separate files below the effort
directory. The adapter discovers only the configured Ticket surface and resolves
the repository from the current working directory unless an explicit repository
argument is supplied.

## Supported operations

- `frontier`: read the complete Ticket surface, validate blockers and publication
  state, and return ready, unclaimed Tickets.
- `claim`: re-read the selected Ticket and snapshot, then atomically add the
  configured Claim branch/worktree metadata when the snapshot still matches.
- `handoff`: accept one candidate or recovery outcome request, derive mechanical
  receipt and candidate fields, write the canonical receipt, apply the required
  Ticket/backlink/Claim transitions, and verify the postcondition.
- `refresh-candidate`: re-read one open Candidate, its exact linked Ticket scope,
  and the retained solve-owned branch/worktree, then atomically advance the same
  receipt to a caller-observed descendant head. Same-head retries are idempotent;
  a changed head clears the previous snapshot's gate evidence.
- `publication register`, `inspect`, `promote`, and `cleanup`: manage the local
  review-pending publication set through the publication journal.
- `publication terminal-repair`: repair only explicitly supported publication
  integrity problems with an expected digest and an audit record. It is not a
  general Ticket editor.
- Solve Record listing, selection, merge-gate, landing-plan, and cleanup-plan
  operations are read-only or gate-producing operations owned by the Solve
  Record facade.

## Unsupported or separate concerns

The adapter does not provide caller-ordered Ticket-state, backlink, Claim, or
receipt mutations. It does not run tests or code review, and handoff does not
grant Candidate Readiness, Candidate Acceptance, merge, landing, deployment,
release, or smoke authority. A general operation for changing an already
published Ticket to `completed` is not currently part of this adapter; one-off
local bookkeeping must not be implemented as Terminal Repair.

## Recovery behavior

Frontier and claim operations fail closed on stale snapshots, blocker ambiguity,
publication drift, or Claim conflicts. Handoff retries reuse the same opaque
`handoff_key`; identity or binding changes are conflicts. Cross-file handoff
inconsistency is reported as retryable attention and converges by retrying the
same request. Terminal Repair uses the expected old digest and refuses guessed
or partial membership changes.

Candidate refresh requires the full SHA observed in the retained worktree. It
fails closed if the live head moved, the observed commit is not a descendant of
the receipt head, the Ticket scope or retained resource metadata differs, the
worktree is dirty or no longer registered, or the receipt is no longer open.
It creates no receipt, Claim, Attempt identity, revision history, or background
maintenance loop.
