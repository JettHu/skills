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

## Context Pointer Contract

`to-tickets` is the sole producer of execution context pointers. Before drafting
each formal Ticket, it selects only the approved source material the executor
needs: a Spec or PRD, related ADRs, `CONTEXT.md`, `CONTEXT-MAP.md`, or an
equivalent domain document. The thin `ultra-to-tickets` wrapper only delegates
to this route; it does not gather context or define a second shaping workflow.

When a Ticket has selected source material, write one optional compact
`## Context` section. Preserve each actionable pointer with its classification,
its exact source branch/ref, and why it matters, for example:

```markdown
## Context

- Source Spec (authoritative; ref: `main`): `docs/prd/publish.md` — defines accepted behavior and validation.
- Decisions (authoritative; ref: `feature/publish-boundary`): `docs/adr/0042-publish.md` — fixes the permission and recovery boundary.
- Domain Context (nonessential; ref: `main`): `CONTEXT.md` — names the domain vocabulary used by the changed module.
```

`Source Spec`, `Decisions`, and `Domain Context` are navigation labels, not a
new required schema. Keep existing configured source metadata authoritative for
adapter operations. Omit an empty Context section: a Ticket with no additional
selected context remains executable. Do not copy source bodies, inject an
unrelated repository index, or make the section a parser or publication gate.

Mark a pointer `authoritative` when execution must read that exact source to
honor approved scope or a binding decision. Mark it `nonessential` when it is
helpful background whose absence does not affect safe execution. A known source
that cannot be resolved uniquely is not repaired by guessing. Every pointer
names one document and one source branch/ref; a repository document must not use
a glob or silently fall back to the executor's current `HEAD`. `to-tickets` must
not guess, replace, or broaden a pointer with another document or ref. Repair a
known omission during Ticket review when it preserves the approved scope; route
any scope or semantic change to its human owner.

## GitHub and GitLab remote adapter contract

For a configured GitHub or GitLab backend, select exactly the publication
strategy named by `docs/agents/ultra-tracker.md`; do not silently substitute the
other remote strategy. The provider-native API or CLI is the mutation surface.
Before any mutation, read the configured provisional marker, ready-state
operation, stable publication-set marker, relationship operation, supersession
policy, and Claim/frontier lookup. An adapter is safe only when it can re-read
those fields and detect a concurrent or partial run.

`remote-review-pending` creates or rediscovers every remote Ticket carrying the
same stable body marker and a configured non-claimable marker. It must not infer
provisional state from the absence of `ready-for-agent`. The main Agent reviews
the exact remote bodies, fixes them in place, records created IDs before the
next operation, wires configured native parent/blocking relationships when
available, and otherwise writes a configured textual fallback that it can
re-read exactly. It verifies complete-set membership, bodies, relationships,
and provisional markers before promoting the whole set. A review-driven split
or merge supersedes obsolete members according to the configured project policy
without making them ready. Any interrupted phase resumes from the run marker
and recorded IDs; it never creates duplicate Tickets or promotes a subset.

`local-staging` uses the configured ignored root (normally
`.scratch/.ultra-staging/<run-id>/`). `tickets.md` is the review surface and
`manifest.json` is the recovery surface. The manifest records stable local
keys, provider IDs, created status, relationship and body verification,
promotion status, supersession, and remaining recovery work. Review and
main-Agent fixes finish there before any formal remote Ticket is created. The
publisher then creates unready remote Tickets, persists each ID before
continuing, wires and re-reads relationships, verifies the complete remote set,
and only then promotes it. Delete staging only after a final complete-set ready
state re-read. Create, map, wire, verify, and promote failure each retain the
manifest and resume idempotently. Conversation-only staging is a reduced
recovery fallback only when the configured staging surface is unreachable or
unwritable; report that degradation and never silently switch to
`remote-review-pending`.

Both remote strategies exclude provisional, partially promoted, superseded, and
staged Tickets from explicit and batch `/ultra solve` discovery. A remote
adapter without conflict-detecting Claim plus exact ready-state verification is
read-only and must fail closed before mutation.

## Local Markdown adapter contract

Use only the configured representation and authorized path. `file-per-ticket`
stores one formal Ticket per configured file; `tickets-file` uses the exact,
case-sensitive `<!-- ultra-ticket:begin id=<Ticket-ID> -->` and
`<!-- ultra-ticket:end -->` boundaries. Titles and headings are never identity.

Metadata keys accept only contract-declared aliases, with harmless key casing
and separator differences normalized. State presentation variants map to the
declared canonical values. Singular/plural compatibility is explicit per field,
never inferred. Duplicate aliases (including blank or equal values), unknown
states, undeclared aliases, ambiguous mappings, or conflicting values are
structured failures. Ticket IDs, Publication Run IDs, blocker IDs, authorized
paths, representation names, and marker IDs remain exact and case-sensitive.

Publication owns complete-set registration, review integrity, promotion,
cancellation, concurrency safety, and idempotent recovery. Frontier owns the
whole-tracker ready/blocker/publication-gate snapshot and conflict-detecting
Claim with branch/worktree assignment. Never reproduce either adapter's
transaction mechanics in Agent prose or manual file edits.

Prefer the bundled `scripts/ultra_tracker.py` facade for configured Local
Markdown publication and frontier operations. It discovers only the configured
publication coordinates, preserves the owning helper result in its versioned
envelope, and does not add state-machine authority. If the facade is
unavailable before an operation starts, make one explicit handoff to the same
bundled helper; never retry a completed operation through the other route.

### Publication operation contract

| Operation | Stage and required inputs | Success evidence | Error and resume boundary |
| --- | --- | --- | --- |
| `register` | After draft creation and every semantic repair; repository, configured representation/location, stable run ID, and explicit membership-change authorization when needed | `review-pending` phase with exact member IDs and reviewed content evidence | Fail closed without Ticket mutation; repair the reported artifact/contract and re-run `register` |
| `inspect` | Review or recovery diagnosis; repository, configured representation/location, run ID | Current phase, exact members, canonical statuses, and current bodies matching registered digests | Read-only structured refusal, including digest drift; repair the reported mismatch and re-run |
| `promote` | Only after semantic review passes; repository, configured representation/location, registered run ID | `promoted` phase after complete-set verification | Retain resumable state; fix the reported failure and re-run the same `promote` |
| `cleanup` | Cancelled review-pending run only; repository, configured representation/location, run ID, and explicit authorization when policy requires | Exact cleaned member IDs | Retain artifacts; repair policy/artifact mismatch, or resume promotion when instructed |
| `terminal-repair` | Human-authorized integrity repair on a promoted/completed run; exact Ticket ID, expected current digest, typed repair, and reason | Current repaired digest and one additive audit while the original snapshot stays immutable | Stale digest/membership is a conflict; malformed partial state requires attention; retry the identical operation after an adapter interruption |

Manual fallback is prohibited for every operation. Publication has no public
`claim-check` or `claim`; both are unsupported and must not mutate Tickets.

`terminal-repair` is not a general editor. It accepts only stable Ticket-ID,
blocker-target, configured publication-metadata spelling, or canonical Solve
Record backlink-structure repairs. Scope, acceptance criteria, technical
decisions, ADR/PRD conclusions, and business meaning require a separately
published erratum or superseding Ticket. Never edit the journal to recover a
repair; `inspect`, frontier, and Maintainer Board consume the audited current
digest and fail closed on an incomplete or malformed repair.

## Review and fix

After target invocation, rediscover the complete set by publication-run
identity from the configured durable surface; never trust returned paths as
the set definition. Route the exact membership through `register` while every
member is `review-pending`.

A fresh-context read-only reviewer checks the exact formal artifacts for:

- Spec coverage and canonical Spec/Ticket terminology;
- independently acceptable, context-window-sized Tickets;
- complete acceptance criteria and meaningful validation;
- source pointers and true blocker edges;
- stable identities, complete-set membership, and non-claimable state.

The main Agent fixes every derivable finding in those same formal artifacts,
then re-runs `register` and the affected review. Ask the user only for an
unresolved scope, product/API/data/security/architecture/significant-UX,
ownership, or release-policy choice that approved input cannot settle.

## Promotion and recovery meaning

After review passes, invoke `promote` and accept only its complete promoted
evidence. A partial or interrupted run remains non-claimable and resumable; use
`inspect`, then resume the operation named by the phase. Cancellation follows
the exact configured policy through `cleanup`. A promoting or promoted run is
resumed, never manually deleted. Missing, duplicate, unknown, or mismatched
contract values fail closed.

For run-tagged Tickets, explicit and batch solve both route through frontier.
Exact ready state alone is insufficient: frontier also verifies publication,
blockers, free Claim metadata, and its discovery snapshot before Claim.
