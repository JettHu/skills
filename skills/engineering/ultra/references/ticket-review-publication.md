# Ticket Review Publication

Read this reference when `to-tickets` will create or update formal Tickets. The
configured `docs/agents/ultra-tracker.md` contract chooses the backend,
representation, draft surface, promotion operation, recovery policy, and Claim
gate. This reference does not replace that project contract.

## Before target invocation

1. Read the base tracker contract and `docs/agents/ultra-tracker.md`. If either
   is missing, incomplete, or names an unsupported mutation, stop before
   publication. Do not invent an adapter.
2. Select or resume one stable publication-run identity. Resume an existing
   run only when its configured surface and approved source still match.
3. Resolve the exact durable draft surface and verify it is writable. For Local
   Markdown, an unwritable surface means `unpublished`; conversation-only review is not a successful tracker mutation.
4. Pass the target the configured representation, location, initial
   `review-pending` state, stable Ticket-ID field, publication-run identity,
   source-pointer and blocker fields, and the rule that it must not publish
   directly as `ready-for-agent`. This is invocation context, not a target-skill
   modification.

The approved Spec or approved conversation already authorizes ordinary Ticket
splitting, merging, sizing, validation detail, and blocker repair. Do not repeat
a default granularity quiz.

## Local Markdown adapter contract

Local Markdown supports only a setup-configured representation:

- `file-per-ticket`: the configured directory contains formal Markdown Ticket
  files. Structured metadata carries `Status`, `Ticket ID`, and
  `Publication Run`.
- `tickets-file`: the configured Markdown file uses exact
  `<!-- ultra-ticket:begin id=<Ticket-ID> -->` and
  `<!-- ultra-ticket:end -->` boundaries. Each section repeats the matching
  structured `Ticket ID`, plus `Status` and `Publication Run`.

The adapter parses `Local Ticket representation` and `Local Ticket path` from
the managed contract before every operation. It resolves the requested CLI
location inside the repository and requires it to match the configured exact
path or single-segment placeholder pattern. For `file-per-ticket`, the final
`<ticket-file>.md` component names files within the authorized directory; it
must occur exactly once and the only other supported placeholder is one
complete `<feature>` segment. Unknown, embedded, repeated, or missing forms
fail closed in both setup and runtime. For
`tickets-file`, the contract identifies one durable file. A representation or
surface mismatch fails before a lock, journal, read result, or Ticket mutation.

For mutation, the adapter resolves the requested surface, locks that resolved
surface, and confirms the same resolution while holding the lock. A symlink
target change causes a bounded retry with the newly resolved lock; continuous
changes fail without a Ticket or run-journal mutation. After confirmation,
Ticket reads, writes, and journal paths use only the pinned resolved surface.

Titles or heading positions are never stable identity. Duplicate/missing IDs,
ambiguous or nested section markers, missing state or run metadata, unresolved
blocker identities, a path outside the repository, or a representation that
does not name conflict-detecting Claim semantics makes the adapter unsafe and
must fail closed without mutation.

Every run has a content-free journal beside the configured surface under
`.ultra-publications/<run-id>.json`. The journal records only representation,
location, complete Ticket-ID membership, reviewed body digests, and phase. It
is coordination metadata, not a Ticket draft or second tracker.

## Review and fix

After target invocation, rediscover the complete set by publication-run
identity from the configured durable surface; never trust returned paths as
the set definition. Register the exact membership while every member is
`review-pending`.

A fresh-context read-only reviewer checks the exact formal artifacts for:

- Spec coverage and canonical Spec/Ticket terminology;
- independently acceptable, context-window-sized Tickets;
- complete acceptance criteria and meaningful validation;
- source pointers and true blocker edges;
- stable identities, complete-set membership, and non-claimable state.

The main Agent fixes every derivable finding in those same formal artifacts.
Re-register an intentionally changed set under the same run identity, re-read
the corrected artifacts, and re-run affected review. Ask the user only for an
unresolved scope, product/API/data/security/architecture/significant-UX,
ownership, or release-policy choice that approved input cannot settle.

## Promotion transaction

Promotion is fail closed and resumable:

1. Acquire the adapter lock and re-read the registered set.
2. Verify exact membership, stable IDs, bodies, source pointers, blocker
   targets, `review-pending` or status-only partial-promotion state, and
   reviewed body digests. Any unrelated concurrent change stops mutation.
3. Atomically mark the journal `promoting`. While it is not `promoted`, every
   member is non-claimable even if a crash left one file with a ready status.
4. Change only the configured status field to `ready-for-agent`, preserving
   unrelated content. File-per-Ticket writes use preimage checks and atomic
   replacement; a tickets-file update replaces its one verified preimage.
5. Re-read the whole set, verify every member and blocker target, then
   atomically mark the journal `promoted` with final reviewed body digests.

Ticket discovery, Maintainer Board readiness, Claim, explicit single-Ticket
solve, and `/ultra solve --all` all require exact `ready-for-agent` state plus a
valid `promoted` journal for run-tagged Tickets. A provisional Ticket carrying
`solve-in-progress` is malformed provisional state, not an active Claim.

Interruption retains the journal and formal Tickets for idempotent resume.
Cancellation uses the managed contract's exact machine-readable policy.
`retain-until-explicit-cleanup` keeps the named run `review-pending` unless
cleanup is explicit; `delete-on-cancel` removes only that named run after the
same exact membership and preimage validation. Missing, duplicate, or unknown
policy values and non-Local publication contracts fail closed even when cleanup
is explicit. Explicit cleanup overrides only the retain choice, never contract
validation. Cleanup requires both the journal and every member to remain
exactly `review-pending`; a `promoting` or `promoted` run must be resumed rather
than deleted. Never silently switch representation or create a parallel
long-lived draft.
