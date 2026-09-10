# Ultra Tracker Extension

Base tracker: docs/agents/issue-tracker.md

This managed extension adds Ultra-specific operations. The base tracker contract and triage documents remain authoritative for their own concerns.

The currently configured Local Markdown adapter is described in
[ultra-tracker/local-markdown.md](ultra-tracker/local-markdown.md). This index
keeps the shared vocabulary and selection rules; adapter-specific details belong
in the capability document.

## Ticket Review Publication

Publication strategy: local-review-pending
Local Ticket representation: file-per-ticket
Local Ticket path: .scratch/<feature>/issues/<ticket-file>.md
Stable identity: every formal Ticket carries unique `Ticket ID` and `Publication Run` metadata.
Draft or review-pending representation: formal Tickets are created at the configured path with `Status: review-pending`; they are the sole source of Ticket content.
Publication journal: `.ultra-publications/<run-id>.json` beside the configured surface records only complete-set membership, reviewed body digests, representation, location, and phase; it is not a Ticket draft.
Publication operation `register`: stage=after formal draft creation and after every semantic repair; inputs=repository, configured representation/location, run ID, and explicit membership-change authorization when needed; success evidence=review-pending phase plus exact member IDs and body digests; errors=structured fail-closed refusal with no Ticket mutation; resume=re-run after repairing the reported contract or artifact; manual fallback=prohibited.
Publication operation `inspect`: stage=review and recovery diagnosis; inputs=repository, configured representation/location, and run ID; success evidence=phase, exact members, canonical statuses, and current bodies matching the registered digests; errors=structured fail-closed refusal with no mutation, including body-digest drift; resume=repair the reported contract or artifact and re-run; manual fallback=prohibited.
Publication operation `promote`: stage=only after semantic review passes; inputs=repository, configured representation/location, and registered run ID; success evidence=promoted phase after complete-set re-verification; errors=structured fail-closed refusal retaining resumable state; resume=re-run the same operation after resolving the reported error; manual fallback=prohibited.
Publication operation `cleanup`: stage=cancelled review-pending run only; inputs=repository, configured representation/location, run ID, and explicit authorization when policy requires it; success evidence=exact cleaned member IDs; errors=structured fail-closed refusal with retained artifacts; resume=repair policy/artifact mismatch or resume promotion as reported; manual fallback=prohibited.
Review update operation: reviewers are read-only; the main Agent semantically repairs the same formal Tickets in place and routes the corrected set through `register`.
Publish or promote operation: route the reviewed registered set through `promote`; the adapter owns all transaction mechanics.
Partial-publish recovery: inspect the durable run, then resume the operation named by its phase; never reproduce transaction mechanics manually.
Claim safety: publication exposes no Claim operation. Route whole-tracker discovery, blockers, snapshots, and conflict-detecting Claim through the configured frontier adapter.
Cancellation policy: retain-until-explicit-cleanup
Cancellation behavior: retain the named review-pending run until explicit cleanup.

## Solve Coordination

Frontier adapter: bundled-local-markdown-v1
Ticket ID field aliases: Ticket ID, ID
Publication Run field aliases: Publication Run
Source field aliases: Source Spec, Parent
Ticket state fields: Status, State
Ticket state values: review-pending, ready-for-agent, completed, ready-for-human, needs-info
Ready state: ready-for-agent
Completed state: completed
Human-blocked states: ready-for-human, needs-info
Blocker metadata fields: Blocked By, Blockers
Blocker body heading: Blocked by
Claim field: Flags
Claim field aliases: Flags, Labels
Claim value: solve-in-progress
Solve branch field: Solve Branch
Solve branch field aliases: Solve Branch, Branch
Solve worktree field: Solve Worktree
Solve worktree field aliases: Solve Worktree, Worktree
Resumable Claims: supported

Claim and release: route the discovery snapshot, ready/blocker/publication re-read, active Claim, and execution branch/worktree assignment through the bundled frontier adapter; release follows the outcome workflow.
State mapping: `review-pending` is an Ultra adapter state, not a sixth global triage role. `ready-for-agent` is the sole claimable state; active Claim and terminal states follow the base tracker contract.
Blocker and frontier lookup: use the base contract's blocker representation. The frontier contains only ready, unblocked, unclaimed Tickets; provisional or staged Tickets remain outside it.
For Local Markdown, the blocker body heading is canonical; metadata blocker fields are legacy fallback only. New Tickets omit the heading when they have no blockers, and never emit the legacy metadata fields. If both forms exist, the body value wins without merging.
Branch/worktree/PR links: during execution, store only configured Claim branch/worktree identity in Ticket metadata. At handoff, resource identity, ownership, and cleanup remain authoritative in the Solve Record or native PR/MR; Ticket notes may add concise lifecycle backlinks but never duplicate those facts.
Solve Record backlinks: add the durable receipt path or URL to the Ticket's configured backlink surface; the receipt remains the outcome record and the Ticket remains the work order.
Open Candidate refresh: route a bounded in-scope descendant head on the same retained solve-owned branch/worktree through `ticket refresh-candidate`; pass the exact receipt, complete linked Ticket scope, and full observed SHA. The adapter keeps the receipt identity, invalidates old snapshot gate evidence, and fails closed on stale or conflicting observations without re-Claiming the Ticket.
Unsupported operations: record any backend capability absent from this extension as unsupported. Batch mutation requires conflict-detecting Claim and safe blocker lookup; otherwise use an explicit single-Ticket path.
