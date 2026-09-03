# Ultra Solve

`/ultra solve` is a subcommand of `/ultra`. It picks up AFK-ready Tickets, coordinates execution worktrees, integrates results, validates finished candidates, and creates outcome Solve Records when an Attempt reaches a meaningful candidate or recovery handoff. Claim remains the temporary concurrency lock; it never creates a receipt. The command optionally merges eligible candidates when the user explicitly asks for it.

It has its own state machine and coordination workflow, so handle it before normal target-skill profile lookup.

## Tracker Operations

Ticket is the canonical domain term for a Work Order throughout this runbook. Retain provider-native artifact terminology only when naming the provider artifact itself. Retain the legacy noun only inside established `.scratch/<feature>/issues/` and `.scratch/<feature>/issue.md` storage paths or compatibility identifiers such as `read_issue(issue_id)` whose spelling is an external contract. Prose surrounding every retained path or identifier must still name the domain object as a Ticket.

Use tracker verbs, not hard-coded frontmatter fields, so local markdown trackers and future remote adapters can share the same workflow contract:

- list Tickets ready for agent work
- read Ticket body, acceptance criteria, state, flags, notes/comments, and linked branches/worktrees/changes
- claim Ticket
- set Ticket state
- add or remove Ticket flags
- record Ticket-state-relevant notes, decisions, or blocker reasons
- link branches, worktrees, commits, PRs, solve records, or validation runs
- close completed Tickets

Read `docs/agents/ultra-tracker.md` before discovery. Use only its configured adapter and fail closed when the mutation contract is missing, malformed, or unsupported. Provisional, staged, partially promoted, superseded, or membership-unverified Tickets are outside solve discovery. A remote tracker without a mutation adapter is read-only.

For `Frontier adapter: bundled-local-markdown-v1`, prefer the bundled `scripts/ultra_tracker.py` facade for both explicit and `--all` discovery and Claim (`ticket frontier` and `ticket claim`). The facade delegates to frontier, which exclusively owns whole-tracker discovery, blocker and publication gates, snapshots, conflict detection, and execution branch/worktree assignment. Treat its structured result as authoritative; never rebuild the graph or Claim with Markdown edits. If the facade itself is unavailable, make one explicit handoff to the capability-equivalent bundled direct helper; preserve the completed-operation result and never repeat a completed mutation. Neither route requires a global executable on `PATH`.

Tracker updates record state-relevant facts. During execution, concrete Attempt branch/worktree identities enter only the configured Claim or tracker metadata. At handoff, resource identities, ownership, cleanup, commits, and PR/MR details remain authoritative in the Solve Record or native PR/MR. A concise Ticket note may add a lifecycle backlink, but must not duplicate those resource facts. Keep batch logs and large command output in validation artifacts or the final summary.

## Invocation

```text
/ultra solve [ticket-id... | --all] [--auto-merge] [message]
```

- Explicit Ticket IDs: solve only those Tickets.
- `--all`: repeatedly solve the configured current claimable frontier, re-reading after each completed frontier generation. It never preselects the transitive dependency graph.
- `--auto-merge`: after finished solve records are created, merge eligible records into the local base branch one by one through the merge gate. It does not fetch, push, deploy, or broaden the selected Ticket set.
- Free-form message: infer the relevant Tickets from the conversation and tracker, then state the selection before claiming.
- Merge/apply/ship/land wording: treat as auto-merge intent after the solve pipeline succeeds and the merge gates pass.

## Core Semantics

`/ultra solve` is the coordinator. It must keep six surfaces consistent:

- Ticket tracker state
- group worktrees and branches
- validation evidence
- solve records
- retained Attempt resources
- candidate and landing branches

Group worktrees produce candidate changes. The coordinator owns integration and merge. A group worktree must not merge directly into the target branch.

Default successful completion, when no `--auto-merge` or merge/apply/ship/land intent is present, is a clean committed candidate branch plus an `outcome: candidate` receipt. `head` is the candidate branch whose current head contains finished work. `base` is the landing branch the candidate is meant to enter later. A meaningful stopped Attempt instead creates the matching recovery receipt; a transient or fully cleaned no-value Attempt releases its Claim without leaving a record. Push, deploy, and cleanup happen only when the user's latest wording explicitly asks for them or when a later solve-record command advances the recorded outcome.

Tickets are assumed AFK-ready when they are in `ready-for-agent`: the Ticket body, acceptance criteria, and any Agent Brief are treated as approved input. Continue the batch unless the Ticket selection or merge target is ambiguous and cannot be inferred safely.

An Agent Brief is an optional, non-duplicative delta to the Ticket and source Spec, never a schema gate. If present, use only its constraints, validation guidance, and optional hints during planning; re-check hints against current code and repo conventions before relying on them. If it is absent or empty, infer from the Ticket, codebase, and conversation where possible; missing core requirements become `needs-info`, and human-owned decisions become `ready-for-human`. Agent Brief content never participates in parsing, eligibility, state transitions, or merge gates.

## Stage Ownership

The root Agent coordinates the Attempt. The Pre-Implementation Checkpoint is the single owner of each stage disposition and its current evidence; later stages consume and revalidate that disposition instead of inventing a second routing decision. Express delegation through runtime-neutral capabilities, bounded outcomes, write boundaries, and completion evidence. The active runtime owns tool-specific agent types, model settings, permission profiles, and other execution configuration.

Direct implementation is the narrow branch. It is allowed only when positive current evidence establishes every property: simple, familiar, local, low-risk, fully specified, and obviously verifiable. An unproven property is not negative evidence and does not require a prior root judgment that delegation would help; it keeps read-only exploration and independent review available and selects delegated implementation when its capability and worktree gates pass.

When implementation is not on the direct branch, use exactly one bounded implementation subagent for an assigned worktree when the runtime exposes implementation delegation and that worktree identity can be verified. That subagent is the only active implementation writer in its assigned worktree until explicit handoff. Independent groups may still run in parallel in different assigned worktrees, while dependent stages and shared-worktree stages remain serialized. After handoff, the root re-reads and integrates the committed result; a subagent summary is never final evidence.

Root implementation fallback is limited to these objective conditions:

- implementation delegation is unavailable
- the assigned subagent worktree cannot be verified
- another active writer already owns that worktree
- the stage requires concurrent mutation of non-namespaced shared state outside the worktree

These fallbacks are separate from the direct branch and must be recorded at the Checkpoint with current evidence. An active-writer fallback never permits concurrent writing: wait for explicit handoff or assign a separate verified worktree before the root edits. For bounded exploration, analysis, verification, and independent review, bias toward a suitable read-only subagent when the required capability exists. The root may perform such a stage when current context already supplies its required evidence, the stage is trivial and local, delegation overhead would exceed the work, or no suitable runtime capability is available.

The root always retains sequencing, synthesis, integration, final validation, tracker transitions, Post-Execution Review closure, and Solve Record finalization. Delegating a stage transfers only its stated bounded work, never those responsibilities or landing authority.

## Worktree Boundary

`/ultra solve` owns worktree identity and lifecycle semantics: Ticket grouping, branch-from ref, branch name, worktree path, Claim state, validation, integration, solve-record finalization, and merge gates.

Use native `git worktree add` as the normal creation interface for assigned solve worktrees. If the repo has an `agent-worktree` post-checkout hook installed, Agent payload injection is a repo-local side effect of that native Git operation.

Use the same solve workflow after repo initialization, with or without the `agent-worktree` scaffolding skill loaded. `agent-worktree` must not choose solve branch names, worktree paths, branch-from refs, grouping, merge behavior, cleanup behavior, or validation policy.

When adopting an existing worktree, verify the expected path, branch, and assignment context with raw Git checks. Missing Agent payload is local setup drift; report it only when it affects execution or validation, and continue to use the same solve workflow.

## Adoption Routing

Before claiming, decide the worktree route from the current branch/worktree, selected Tickets, tracker Claim state, dirty status, branch topology, and risk. Adoption is Agent-judged behavior, not a required explicit flag.

Choose exactly one route and state an adoption declaration before implementation:

- `isolated`: create solve-owned candidate worktree(s) and branch(es).
- `adopted-execution`: use the current worktree/branch as the execution or serial group target.
- `adopted-integration`: use temporary group worktrees, then integrate into the current worktree/branch as the final candidate.
- `ask`: stop before claim or implementation and ask the user to choose.

For ordinary AFK pickup with no safely indicated prepared development branch, keep the existing `isolated` solve boundary.

A prepared development branch is the current branch, or a branch clearly identified by the user request, tracker metadata, Codex App setup, or stack topology, as intended for the selected Ticket work. Branch names, commit messages, and Ticket paths may support this judgment, but name similarity alone is not enough. The branch must be non-protected, aligned with the Ticket scope, free of active Claim conflicts, and able to pass entry safety.

The declaration must name:

- candidate branch
- landing branch
- worktree role
- cleanup ownership, distinguishing solve-owned temporary resources from user-owned adopted resources

Use a compact declaration shape such as:

```text
Adoption: <isolated | adopted-execution | adopted-integration | ask>
Candidate branch: <candidate-branch>
Landing branch: <landing-branch>
Worktree role: <role>
Cleanup ownership: <solve-owned temporary resources | user-owned adopted resources | mixed>
```

Use `isolated` when adoption has a safety failure:

- the current branch is a protected baseline such as `main`, `master`, or a project-defined protected release branch
- the current branch/worktree conflicts with tracker Claim metadata or an active Claim
- dirty or untracked paths overlap likely Ticket write paths or may be overwritten
- branch topology, branch-from ref, or candidate identity is unsafe enough that adopting could hide or overwrite work

When creating an isolated worktree because adoption is unsuitable, choose a branch-from ref that preserves the user's current integration context. Prefer the current branch or current HEAD when it is the strongest signal; use Ticket text, tracker metadata, stack relationships, release branches, or repo convention only when they clearly identify a better branch-from ref. When invoked from a protected baseline, default the branch-from ref to the current baseline or HEAD unless the user, tracker, Codex App setup, or stack topology clearly identifies another integration branch for this work. Branch existence alone is insufficient as a switch signal to or away from `main` or `master`.

The branch-from ref is only the starting point for `git worktree add`; it is not necessarily the solve record `base`. In solve records, `base` remains the landing branch the candidate is meant to enter later. For example, if dirty Ticket-scoped work prevents adopting the current `feature/billing` branch, an isolated solve branch may be created from `feature/billing` HEAD while the solve record still uses `base: main` when `main` is the landing branch.

Use `ask` when the current branch/worktree looks plausibly safe but user intent is unclear. Offer context-relevant choices that include:

- adopt the current branch/worktree
- create an isolated solve worktree from the current integration context
- use a user-described alternative

Add branch switch, cleanup, or stash choices only when they fit the observed state.

Adopted worktrees must pass the same entry-safety standard as created solve worktrees. Parallel execution may still create solve-owned temporary group worktrees while an adopted worktree/branch acts as the final integration target.

For `adopted-integration`, use solve-owned temporary group worktrees for parallel groups, then integrate those groups into the adopted branch. The adopted integration branch is the finished candidate branch and remains user-owned.

## State Machine

Use these logical states even if the local tracker stores them with different field names.

```text
ready-for-agent
  -> claim: add solve-in-progress and link solve branch/worktree
      -> completed
      -> ready-for-human
      -> needs-info
      -> ready-for-agent
```

State meanings:

- `ready-for-agent`: unclaimed work that another AFK agent may start.
- `solve-in-progress`: a claim flag, added immediately after claim to prevent parallel pickup.
- `completed`: acceptance criteria are implemented and verified.
- `ready-for-human`: semantic conflict, final validation failure, or other non-requirements blocker.
- `needs-info`: core requirement cannot be inferred from the Ticket, code, or conversation.
- `ready-for-agent`: also receives an abandoned or clean-restart Ticket that remains valid and claimable.

Primary states, Claim flags, and receipt outcomes are separate. `ready-for-agent`, `completed`, `ready-for-human`, and `needs-info` are primary states. `solve-in-progress` is a temporary claim flag that may be stored as a label, flag, status metadata, or another tracker-specific convention. `candidate`, `blocked`, `needs-info`, `ready-for-human`, `abandoned`, and `superseded` are Solve Record outcomes; a recovery outcome does not add a new Ticket state. Record-worthy low-risk decisions belong in the active Execution Digest and then the outcome Solve Record, not in Ticket state or flags.

Flag lifecycle:

- Add `solve-in-progress` only after a claim succeeds.
- Remove `solve-in-progress` whenever the Attempt hands off and no actor remains actively assigned to resume the same retained resources and recovery context. Retain it only when the recovery next action is `resume`, the same assignment is intentionally still active, and the tracker contract supports a resumable Claim; otherwise a later resume must reclaim the Ticket.
- If a stale `solve-in-progress` flag references a missing branch or worktree, inspect the Ticket history and branch refs. Resume, clear, or ask before mutating; do not silently discard it.

When setting `ready-for-human` or `needs-info`, record a concise blocker reason when the tracker supports state-relevant notes:

- `missing_requirement`: acceptance criteria or core behavior cannot be inferred.
- `semantic_conflict`: product, architecture, API, security, data, or UX judgment is required.
- `verification_failed`: required validation was run and failed.
- `verification_unavailable`: required validation cannot run in the current environment.
- `integration_conflict`: locally valid changes conflict during integration.
- `tooling_unavailable`: required local tools, dependencies, branches, or worktree operations are unavailable.
- `tracker_unavailable`: required tracker mutation is unavailable or unsupported.

A blocker reason explains a state transition; it is not a new state.

Discovery must skip Tickets carrying an active `solve-in-progress` Claim and report them as already claimed.

`review-pending` is a Local Markdown adapter state, not a global triage role. It is never claimable. Frontier reports all publication, blocker, state, and Claim diagnostics. Before stopping on a non-frontier result, the coordinator may perform one bounded repair only when the configured contract or adapter explicitly identifies an unambiguous, metadata-only defect and provides the owning operation; then it must rediscover and Claim from a fresh snapshot. A missing stable Ticket ID may be repaired before publication when the configured identity source is exact and unambiguous, then the formal Ticket must go through the normal publication operation. The reviewed semantic digest excludes adapter-owned lifecycle fields, checklist completion marks, and the standard path-only Solve Record backlink. A generic `Ticket content changed after review registration` or body-digest mismatch is not evidence of metadata-only drift and remains fail-closed. Use the tracker adapter for ordinary Ticket edits when available; when it is unavailable or does not cover the edit, the Agent may make the smallest direct change to the canonical Local Markdown surface and re-read it. Never hand-edit publication journals, Claim metadata, receipt transitions, or conflict/resume assignments; promoted-run corrections remain human-owned under the terminal-repair policy.

## Workflow

### 1. Discover

Read the configured Ticket universe through frontier. Select only IDs in its `claimable` result and report its `non_frontier` diagnostics. If a diagnostic is an explicitly supported metadata-only repair, perform that one bounded owning operation and rediscover before Claiming; a generic content-digest or semantic-drift diagnostic remains blocked. Never invent blocker edges from numbering, prose, or likely implementation order.

Explicit Ticket IDs bound the selection universe: intersect exactly those Ticket IDs with the current frontier and report every requested non-frontier Ticket. Never add an unrequested blocker or dependent. `--all` bounds the universe to the configured adapter surface and begins with only its current frontier.

For configured Local Markdown, route both explicit and batch discovery through frontier. Publication exposes no Claim or Claim-check operation.

For configured GitHub or GitLab publication runs, route explicit and batch discovery through the configured remote adapter. It must verify the exact publication-set identity, complete membership, non-claimable/provisional marker removal, configured ready state, verified parent/blocking relationships, and free Claim metadata. Durable local staging is not a remote Ticket surface and must never enter tracker scans. If that adapter cannot establish every gate, report the selected Ticket as non-frontier and do not mutate it.

Report skipped Tickets with a short reason:

- wrong state
- has active `solve-in-progress`
- stale claim needing manual/resume handling
- `review-pending`, incomplete promotion, malformed publication metadata, or an unsafe tickets-file adapter
- human-blocked state
- unresolved blocker or stale blocker state
- dependency cycle or missing blocker target
- unsafe or unsupported blocker/Claim contract

Cycles, self-cycles, missing targets, non-completed blocker states, and Claim conflicts are non-frontier diagnostics. They never justify a speculative Claim. A safe adapter may still return an independent frontier beside graph-invalid Tickets; an unsafe parser or unsupported Claim capability stops the entire batch before mutation. Distinguish a valid empty frontier from an adapter failure.

### 2. Claim

For every selected Ticket:

- determine the adoption route and intended branch/worktree reference
- pass the discovery snapshot back to the adapter and atomically re-read state, blockers, publication gates, and Claim metadata
- confirm the Ticket is still in the current frontier; snapshot drift, a newly unsatisfied blocker, or a concurrent Claim is non-claimable stale work
- claim it in one conflict-detecting mutation by adding the configured Claim value and recording the intended branch/worktree through the declared assignment fields
- create or adopt the assigned branch/worktree after the claim succeeds

Do this before code changes. Pass the exact Ticket ID, discovery snapshot, and intended execution assignment to frontier. Stop on any structured failure; do not fall back to direct metadata edits, even for one explicit Ticket.

If branch/worktree creation or adoption fails after claiming, clean any partial resources and release the Claim when the failure leaves no useful finding or recovery value. When partial resources, evidence, or a durable blocker make the failed Attempt worth handing off, route it through Outcome Finalization as `blocked`; keep `solve-in-progress` only when the same assignment remains actively resumable.

#### `--all` Frontier Loop

Treat one discovery result as one frontier generation:

1. discover and report the configured frontier plus non-frontier diagnostics;
2. Claim only Tickets returned in that generation, re-reading the snapshot before each Claim;
3. execute, review, validate, and finalize those Attempts through the ordinary gates;
4. after their Ticket and Claim states are durable, re-read the same configured universe;
5. continue only with newly claimable Tickets, and stop when the frontier is empty or the adapter becomes unsafe.

Completion can unlock a dependent in the next generation. A failed, recovery, human-blocked, or still-claimed Ticket does not satisfy its dependents. Do not retain the initial transitive graph as a future Claim list, and do not broaden an explicit run into this loop.

### 3. Assess: Pre-Implementation Checkpoint

For each claimed Ticket, run the Pre-Implementation Checkpoint after Claim and before implementation edits. Read the Ticket body, acceptance criteria, comments, linked docs, optional Agent Brief, and enough current repository context to decide whether the Ticket is executable.

Build a compact **Design Context** index before deciding the execution plan. Read the root `AGENTS.md` and `CONTEXT.md` when present, then follow Ticket/source pointers and inspect only the relevant PRD/Spec, `docs/adr/`, `docs/agents/`, or domain documents for the changed surfaces. Treat an explicitly superseded document as historical context, not live requirements. Record the authoritative sources, consulted sources, and any unresolved conflict in the active context; put the index in the Execution Digest only when the Attempt is otherwise digest-worthy. A simple Ticket needs only a one-line index such as `Design Context: CONTEXT.md; ADR-0012; no unresolved conflict`.

Use the smallest preparation tier whose positive predicates fit the Ticket:

- `L0`: one local surface or tightly coupled local slice; complete acceptance; no cross-Ticket dependency, public contract, data/migration, production, external-fact, or non-obvious-validation signal; obvious validation.
- `L1`: ordinary local multi-file work in a known module with no L2/L3 signal; use narrow targeted exploration and one proportional group/final review.
- `L2`: any cross-module or cross-group coupling, public contract, data or migration work, production/configuration effect, external dependency, non-obvious validation, or material recovery decision; use the applicable exploration, Digest, Pre-Edit Plan Review, independent review, integration validation, and Post-Execution Review gates.
- `L3`: model-evaluation, workflow-evidence, merge-policy, or release-policy governance; retain the full evidence and human-boundary requirements declared by the Ticket or repository policy.

All tiers retain frontier snapshot/Claim, dirty-worktree and writer ownership, final validation, outcome finalization, and release-boundary rules whenever those rules apply. Tiering only selects proportional preparation and review; it never turns a Ticket state or a green check into deployment, merge, migration, smoke, or cutover authority.

Map each material predicate to its extra gates: cross-module or cross-group coupling enables targeted exploration, Group Review, integration validation, and Post-Execution Review; public-contract, data, or migration work enables Design Context, independent review, integration/final validation, and explicit migration/evidence disposition; production or configuration effects enable rollout/config review and release-boundary evidence; external dependencies enable conditional source-backed research and corresponding validation; non-obvious validation or recovery value enables the Digest, Pre-Edit Plan Review, and recovery evidence; L3 governance retains the full evidence and human-boundary policy named by the Ticket or repository.

Keep the stage interfaces narrow: Adoption Routing selects the branch/worktree route; the Checkpoint selects enabled preparation and owns the current plan; the Digest preserves only resumable or material decisions; Pre-Edit Plan Review challenges an enabled complex plan; Pre-Execute Gate verifies live branch/worktree/Claim facts. Later stages consume those results instead of restating or re-planning them.

Classify the Ticket disposition:

- `executable`: enough information exists or can be inferred.
- `needs exploration`: technical details are missing, but the codebase can likely answer them.
- `needs-info`: a core requirement cannot be inferred.
- `ready-for-human`: the Ticket is really an unapproved architecture, product, security, data, or significant UX decision.

If a Ticket becomes `needs-info` or `ready-for-human`, record the blocker reason and route the Attempt through Outcome Finalization. A substantive assessment with durable findings creates the matching recovery receipt; an immediate no-value stop releases its Claim without a record. Continue with the rest of the batch after the Ticket, Claim, resources, and backlink reflect that disposition.

The root Agent records, without requesting approval, only the selected preparation decisions and their evidence:

- Design Context index and any unresolved source conflict
- exploration disposition when exploration is needed: `direct root exploration`, `narrow root exploration`, `adaptive read-only subagent fan-out`, or `conditional external research`
- implementation disposition: `direct root implementation`, `one bounded implementation subagent`, or `objective root implementation fallback`, with current evidence for every required predicate or fallback
- bounded analysis, verification, or independent-review dispositions only when those stages are enabled
- validation plan: commands, manual evidence, check-run links, or why no meaningful automated check exists
- Digest disposition: `none` or `digest-worthy`, using the conditional rule below

Direct root implementation requires positive evidence that the Ticket is simple, familiar, local, low-risk, fully specified, and obviously verifiable. Existing high-quality exploration in the active context may satisfy part of that evidence and avoid duplicate fan-out. A clear local fix alone is not enough.

Use adaptive read-only fan-out only when the Ticket's affected surfaces, contracts, risks, dependencies, validation, or external facts are not already covered by the Design Context and current conversation. A simple local Ticket may use direct root exploration or no additional exploration. Subagents return compressed findings—relevant modules, constraints, risks, validation paths, and unresolved questions. The root Agent retains synthesis, integration, final validation, tracker transitions, Post-Execution Review closure, and Solve Record finalization; implementation edits follow the recorded Stage Ownership disposition. Raw exploration output stays outside the Ticket, Execution Digest, and Solve Record.

Use external research only when a source-verifiable external API, framework, standard, platform, compatibility, or security fact affects implementation or validation and local approved context cannot settle it. Link the source and keep the finding factual. Research never substitutes for a human-owned product, architecture, data-policy, or security-policy choice.

### Execution Digest: Conditional Working Memory

An Execution Digest is a separate Ticket-level working file, never a Ticket-body section, tracker state, schema gate, or second requirement source. The default is `Digest: none`. Create it only when at least one positive trigger applies: the Attempt is multi-module, delegated, resumable or likely to be interrupted; validation is non-obvious or externally dependent; or a non-obvious decision/deviation affects acceptance, observable behavior, compatibility, validation, rollout, or recovery. A simple Attempt creates no Digest until its first material decision or deviation; create it at that event without rewriting the Ticket.

Do not create a Digest merely because the Ticket changes multiple files, the Agent performed ordinary exploration, a routine check failed and was fixed, or the implementation is expected to finish in one session. If no trigger applies, record one short reason such as `Digest: none — local, single-module, obvious validation, no material decision`.

For a local Ticket at `.scratch/<feature>/issues/<ticket-file>.md` or `.scratch/<feature>/issue.md`, use exactly:

```text
.scratch/<feature>/execution-digests/<digest-key>.md
```

Derive `digest-key` in this order: use the stable tracker Ticket ID when present and matching `[A-Za-z0-9][A-Za-z0-9._-]*`; otherwise use the local Ticket filename stem when it matches that pattern; otherwise use the full SHA-256 of the canonical Ticket identity (the repo-relative local Ticket path). A feature owns at most one single-Ticket file, and each `.scratch/<feature>/issues/*.md` filename is unique within that feature, so the feature directory plus this key is collision-safe. The derivation never accepts path separators. The directory is outside normal Ticket discovery: discover only `.scratch/*/issues/*.md` and `.scratch/*/issue.md`, never a broad `.scratch/**/*.md` glob.

Keep the file compressed:

```markdown
# Execution Digest: <Ticket>

Strategy:
Touched surfaces:
Key risks:
Validation plan:

## Decisions And Deviations

### <short title>
Context:
Decision:
Reason:
Impact:
Evidence:
Follow-up:
```

Record only a non-obvious decision or deviation that is not settled by the Ticket or source Spec and affects acceptance, observable behavior, compatibility, validation, rollout, or recovery. Do not copy exploration transcripts, raw command output, routine implementation choices, or progress logs into it.

When the same retained branch, worktree, and recovery context resume, reopen and update the same Digest path. At any meaningful outcome handoff, distill only the durable conclusion or deviation needed by the next owner into the concise Summary handoff request; do not author fixed receipt sections. Retain the Digest only while it has resume value or repository policy requires it; otherwise delete it after that durable transfer. If a required Digest cannot be written durably, keep the same compact fields in the active conversation and report the reduced interruption-recovery guarantee.

Complex, delegated, resumable, or digest-worthy Attempts receive a Pre-Edit Plan Review before implementation edits. Follow the Checkpoint's independent-review disposition: prefer a fresh read-only reviewer when that capability exists, and use a recorded root-execution exception only under the Stage Ownership conditions. Check the compressed plan, acceptance criteria, constraints, risks, and validation strategy for omitted steps, unsafe assumptions, and validation gaps. Incorporate findings into the plan or Digest; the review creates no standalone lifecycle artifact and no blanket human approval gate.

Record-worthy low-risk decisions go in the active Digest and, at a meaningful handoff, its concise Summary request. Human-owned product, API, data, security, architecture, or significant UX choices set the Ticket to `ready-for-human`; missing core requirements set it to `needs-info`.

The Pre-Implementation Checkpoint is complete when each claimed Ticket has a Ticket disposition, a Design Context index, an execution and validation plan, the selected stage dispositions, and a Digest decision; any required Digest or Pre-Edit Plan Review is incorporated before implementation edits. Unselected heavy stages are not recreated as empty checklist entries. Later stages must revalidate the recorded evidence when repository state, runtime capability, worktree ownership, or Ticket context changes.

### 4. Group

Group executable Tickets by module, dependency, and likely file overlap.

- Same module or shared files: one group, serial execution.
- Independent modules: separate groups that may be executed in parallel when the runtime supports it.
- Shared migrations, config, generated types, routing, fixtures, dependency versions, or public contracts are coupling signals; group or order them conservatively.

#### Expand-contract exception for wide mechanical refactors

Ordinary work remains tracer-bullet execution: every Ticket is independently demoable, verifiable, and green. Use expand-contract only for one mechanical representation change whose blast radius prevents an ordinary vertical slice from landing green. It is not an exception for broad product, API, data-model, or architecture work; route such a proposal to human review instead.

The approved Ticket graph, not Solver inference from prose or numbering, declares the exception. First, an **expand** Ticket adds the new form beside the old one and verifies that existing callers still work. Every **migration batch** is sized by blast radius, declares expand as a blocker, and migrates only after the expanded compatibility form is present. In the normal form, each batch remains green while the old form is available, and the **contract** Ticket declares every migration batch as a blocker before it removes the old form.

When a migration batch cannot remain green on its own, the graph must additionally declare `Execution mode: shared-integration`, one named shared integration branch/worktree, and one named **final integrate-and-verify** Ticket. Batches still declare expand as a blocker; contract still declares every batch as a blocker; and final integrate-and-verify declares contract as its blocker, so its validation covers the contracted result. The shared branch has one integration owner and serializes writers; frontier siblings never concurrently edit the same worktree. Each non-green batch records scoped mechanical evidence only and may complete its declared migration acceptance, but it must not claim a green result, candidate receipt, landing eligibility, or final validation. The final integrate-and-verify Ticket alone owns the full green guarantee, final validation, Post-Execution Review, candidate receipt, and the ordinary landing and cleanup gates.

A completed blocker is a Claim predicate, not proof that its code exists in a later Ticket's execution base. Before a migration, contract, or final integration Ticket writes, verify that the declared predecessor commits are present on its assigned branch or shared integration branch. Never land an intermediate Ticket merely to satisfy a blocker, silently merge an unresolved dependency, or weaken ordinary review, validation, landing, or cleanup gates. An unexpected scoped-check or integration failure follows the normal blocked/recovery path.

### 4.5 Pre-Execute Gate (mandatory)

The gate confirms no branch/worktree, tracker-claim, or dirty-state drift has occurred since adoption routing.

Before writing ANY implementation file, the coordinator must verify and report:

- [ ] Adoption declaration recorded: candidate branch, landing branch, worktree role, cleanup ownership
- [ ] Group worktree(s) created or adopted
- [ ] Group branch(es) created or adopted from the selected branch-from ref or adopted context
- [ ] Current working directory is the assigned group worktree, not the invocation checkout
- [ ] `git rev-parse --show-toplevel` equals the assigned group worktree path
- [ ] Branch-from, landing, and current context match the solve assignment before implementation commits
- [ ] `git status --short --branch` shows the assigned group branch
- [ ] Tracker claim metadata matches the assigned worktree/branch
- [ ] Dirty and untracked paths are absent, or proven unrelated to the selected Ticket scope before adoption

Do not edit code, tests, docs, config, migrations, or generated artifacts until this gate passes.

If this gate fails, stop and create or enter the correct group worktree before continuing.

Every delegated implementation receives a self-contained stage assignment that names:

- the authoritative Ticket and approved source context
- the current branch, assigned worktree, and source snapshot
- exclusive write ownership and the explicit handoff boundary
- relevant Execution Digest decisions and deviations
- the bounded stage outcome and acceptance criteria
- validation expectations and post-handoff revalidation requirements

The assignment must be sufficient without inherited conversation history. Inherited history is advisory and never supplies missing requirements, constraints, ownership, acceptance criteria, or validation obligations. The implementation subagent must run and report this same Pre-Execute Gate before editing. If the assigned worktree cannot be verified, use the recorded objective root fallback; do not relax the gate or silently redirect the subagent.

### 5. Execute Groups

Create one group worktree per group from the selected branch-from ref, unless the adoption route intentionally uses an existing worktree for that group. Execute only after the Pre-Execute Gate passes for that group.

Suggested names:

- group branch: `solve/<timestamp>-<group-name>`
- group worktree: `worktree-solve-<timestamp>-<group-name>`

Create the assigned worktree with native Git, for example:

```bash
git worktree add -b "<group-branch>" "<group-worktree-path>" "<branch-from-ref>"
```

If the repo-level Agent-ready hook is installed, payload bootstrap happens automatically during `git worktree add`. Solve creates and verifies assigned worktrees with native Git, and removes solve-owned resources through solve-record cleanup gates; `agent-worktree` remains hook/config scaffolding. If native Git cannot create the exact assigned identity, mark only the affected Ticket/group with `tooling_unavailable`.

For `adopted-integration`, temporary group branches are solve-owned resources. The adopted integration branch is the candidate branch and remains user-owned.

For each Ticket in a group:

1. Execute from the Pre-Implementation Checkpoint. Refresh exploration only when code changed since planning or the assigned worktree exposes new facts.
2. Revalidate and follow the Checkpoint's implementation disposition. Do not reclassify a Ticket from a file-type heuristic: docs/config-only work is direct only when all six direct-branch properties have positive current evidence. Optional routed skills may shape the bounded implementation, but they do not replace Stage Ownership:
   - unclear bug: prefer the debugging skill (`/ultra diagnosing-bugs`, or a configured alias) in AFK mode when a diagnosis loop would reduce risk
   - medium feature with clear AC: consider `/ultra tdd` in AFK mode when test-first development would help
   - approved refactor with clear AC: consider `/ultra tdd` when behavior coverage is needed
   - speculative architecture change: mark `ready-for-human`
3. Implement.
4. Verify each acceptance criterion. In a declared shared-integration sequence, a migration batch verifies its scoped mechanical acceptance; only the named final integrate-and-verify Ticket verifies the full integrated green result.
5. Record validation evidence as a PR, commit, CI/check, tracker pointer, or final solve summary entry.
6. Commit verified work to the group branch before leaving the group worktree.

Commit rules:

- Leave successful group work as clean, committed group branches for integration.
- Split commits by Ticket, vertical slice, or coherent logical change when that makes review and rollback clearer.
- Keep tightly coupled code, tests, docs, and generated artifacts together when separating them would create broken intermediate commits.
- Commit granularity should follow coherent behavior and review boundaries: separate unrelated Tickets, and keep mechanical fragments together when they explain one behavior.
- Commit messages should reference the relevant Ticket ID(s) and, when useful, the validation command or evidence.

### 6. Review Groups

Review before integration:

- Simple group: one compact pass against every acceptance criterion.
- Medium group: two review lenses for completeness and consistency.
- Complex or cross-cutting group: stronger independent review when available.

For implementation groups, pin the group review range against the group branch base before reviewing. Follow and revalidate the Checkpoint's independent-review disposition. Treat the following as review lenses, not mandatory output sections. Report real findings under the relevant axis:

- Spec: compare the committed group diff with the originating Ticket body, acceptance criteria, PRD, or Agent Brief. Flag missing requirements, partial implementations, scope creep, and behavior that appears wrong against the spec.
- Standards: compare the committed group diff with documented repo standards, project conventions, ADRs, and nearby code patterns. Flag hard violations separately from judgment calls.

Also check supporting engineering risks only when relevant to the changed files or risk: side effects and regression risk, test/validation coverage, and dependency or compatibility concerns.

Classify every finding first by **Repairability**, then by **Decision Ownership**. Severity labels P0-P3 rank impact only; they never decide whether the Agent fixes a finding. Fix every in-scope P0-P3 finding whose repair is derivable from the approved Ticket, current code, and repository policy, rerun affected validation, and repeat the affected review. A clearly out-of-scope, non-blocking finding may become a follow-up. Reserve user input for genuinely human-owned scope, product, architecture, ownership, release, data, security, or significant UX choices. Any unresolved acceptance-affecting finding blocks candidate handoff and routes the Attempt to the appropriate recovery outcome regardless of severity.

Group Review is complete when the pinned group range has been compared with the authoritative Ticket/Spec and applicable repository standards, every derivable finding is fixed and revalidated, and every remaining finding is either explicitly routed as human-owned or recorded as a non-blocking follow-up without affecting candidate acceptance.

### 7. Integrate

Create one integration worktree from the latest target branch. The integration worktree is mandatory whenever more than one group exists, `--auto-merge` is present, or merge/apply/ship/land was requested; it is still recommended for a single non-trivial group.

Suggested names:

- integration branch: `solve/<timestamp>-integration`
- integration worktree: `worktree-solve-<timestamp>-integration`

Merge or cherry-pick committed, locally validated group branches into integration in dependency order. Each group worktree must be clean before integration starts. For a declared shared-integration sequence, continue from its named shared branch in declared graph order; the final integrate-and-verify Ticket reopens that branch only after contract is completed and runs the full integration validation there.

- Mechanical conflicts: the coordinator may resolve them.
- Semantic conflicts: stop integration for the affected Tickets and route each meaningful stopped Attempt through Outcome Finalization as `ready-for-human`; the remaining batch may continue without those Tickets.
- Any mechanical conflict resolution or integration-only fix must be committed on the integration branch before final validation is considered complete.

The integration stage exists to catch hidden coupling between parallel work: shared types, migrations, router registration, scheduler registration, config defaults, fixtures, generated artifacts, and dependency changes.

### 8. Final Validate

Follow and revalidate the Checkpoint's verification disposition, then run the repo-appropriate validation commands in the integration worktree. The root owns the final validation conclusion even when a bounded verification pass is delegated. Prefer the project's documented commands; otherwise use the narrowest meaningful test/build/lint set first and expand when risk requires it.

Final Validate proves executable validation facts: the required commands/checks, integration result, clean committed candidate, and current evidence status. It does not redo Group Review's local Spec/Standards comparison or decide whether the Ticket was well-shaped.

Populate the executable-evidence side of the final requirement audit from the current integrated head. For every required validation gate and every explicit requirement, acceptance criterion, named artifact, invariant, or required deliverable that depends on executable behavior, record the exact current command, check result, artifact inspection, diff/ref fact, or other authoritative observation that bears on it. Evidence is requirement-specific: a green narrow check proves only its tested scope, and absence of errors proves nothing beyond the operation actually observed. Mark contradictory, incomplete, weak or indirect, stale, and narrower-than-required evidence as such instead of upgrading it to a pass. This population is working review state inside Final Validate and Post-Execution Review, not a new artifact or lifecycle object.

If final validation passes:

- ensure the integration worktree is clean and all intended changes are committed
- have the root re-read the integrated candidate, claimed Tickets, and validation evidence instead of accepting group summaries as final evidence
- have the root confirm delegated evidence still describes the current candidate head and rerun or directly revalidate evidence that is stale, unpinned, or narrower than the requirement it is offered for
- confirm the exact Ticket scope and claimed candidate worktree for outcome handoff; the adapter derives `head` and `head_sha`
- keep detailed validation evidence in the owning Final Validate/Post-Execution Review context. Later Candidate Acceptance or landing owners gather `base`, `base_sha`, merge/rollout evidence, and cleanup facts when those become material
- proceed to finalization before marking linked Tickets completed

If final validation fails:

- identify affected Tickets when possible
- record the blocker reason and a concise failing command summary or check-run link
- route every affected substantive Attempt through Outcome Finalization as `blocked`, with `ready-for-human` as the default actionable Ticket state
- retain `solve-in-progress` only when the same assignment remains actively resumable on the linked resources

If no meaningful automated check exists or the environment cannot run it, do not call that a pass. When the candidate is otherwise complete, submit the unavailable check, its reason, and the strongest remaining evidence as the validation conclusion or uncovered boundary in the concise Summary handoff request. Unavailable validation is an explicit Summary boundary, never a pass. Later Candidate Acceptance and merge owners decide whether their live gates remain blocked or a documented low-risk exception applies.

Failed required checks never produce a candidate receipt. A transient failure that is fully cleaned and leaves no useful evidence releases its Claim without a receipt. A required validation or integration failure with retained evidence, a branch, worktree, or another recovery value produces a `blocked` recovery receipt instead. In a declared shared-integration sequence, only the final integrate-and-verify Ticket can create the candidate receipt; batch and contract handoffs remain non-candidate evidence until that Ticket passes the full green guarantee.

When a blocked, needs-info, ready-for-human, abandoned, superseded, or retained-failure Attempt reaches the outcome-finalization flow, distill the durable blocker, decision, deviation, and next useful action into the concise Summary handoff request. Do not author recovery receipt sections. Retain the Digest only while its linked resources have resume value or repository policy requires it; otherwise delete it after the transfer.

### 8.4 Post-Execution Review

After final validation and before Outcome Finalization, the root re-reads and reviews the integrated candidate against the claimed Tickets, acceptance criteria, source Specs, approved decisions, optional Agent Briefs, applicable living Execution Digests, repository standards, side effects, validation evidence, and receipt readiness. Follow and revalidate the Checkpoint's independent-review disposition: bias independent review toward suitable read-only subagents when available, using the documented root exceptions only when their current evidence still holds. A subagent summary supplements but never replaces the root's integrated-candidate read.

The root now completes the full **requirement-to-evidence audit**. The complete acceptance boundary is every claimed Ticket plus each approved source Spec; context limits, interruptions, execution limits, an easier compatible result, or the available tests never narrow it. Enumerate every explicit requirement, acceptance criterion, named artifact, validation gate, invariant, and required deliverable from that boundary, then map each one to authoritative evidence from the current integrated head. Classify each mapping as:

- **scope-matched proof**: current, authoritative evidence directly covers the requirement's full stated scope
- **contradictory evidence**: a current authoritative observation conflicts with the claimed outcome
- **incomplete, weak, or indirect evidence**: the observation is relevant but does not directly establish the requirement
- **stale delegated evidence**: a delegated result is not pinned to, or no longer describes, the current integrated head
- **narrower-than-required evidence**: the evidence covers only a subset, example, component, or narrow check while the requirement is broader

A plan, Execution Digest, delegated summary, manifest, search result, green narrow check, or absence of errors is an audit input, not proof by itself. It may point to evidence that the root verifies against the current head. The audit passes only when every enumerated item has scope-matched proof, no current contradictory evidence remains, and every stale, weak, indirect, incomplete, or narrow mapping has been replaced by sufficient current evidence or the underlying work has been completed and revalidated. Keep the mapping in active review context; do not copy the Ticket into the Execution Digest, create a Ticket Decision Log or standalone review artifact, or turn the Solve Record into a requirement checklist.

Post-Execution Review consumes the Group Review and Final Validate results; it focuses on integrated-candidate scope, cross-group coupling, side effects/regressions, Design Context or Digest decisions that must be handed off, and whether the proposed handoff Summary is truthful and complete. It does not repeat a clean local Group Review or rerun a validation command unless a finding or changed candidate requires it.

Check for:

- acceptance criteria implemented only partially or differently than approved input
- stale Agent Brief hints or Execution Digest assumptions
- record-worthy low-risk decisions not ready for durable handoff, or human-owned decisions
- side effects, regressions, or public-contract changes not covered by validation
- validation gaps, unavailable required checks, or missing manual gates
- a proposed handoff Summary that would be incomplete or misleading
- an explicit Ticket or approved source-Spec item without scope-matched current evidence, including a broad criterion supported only by a narrow green check

Apply the same Repairability and Decision Ownership rules as group review. Fix every derivable in-scope finding across P0-P3, rerun the relevant validation, and repeat Post-Execution Review on the corrected candidate. Escalate only genuinely human-owned choices. A clearly out-of-scope non-blocking finding may become a follow-up, but any unresolved acceptance-affecting finding blocks candidate handoff and routes the Attempt to the appropriate recovery outcome regardless of severity. Do not submit a `candidate` outcome for that Ticket. During Outcome Finalization, submit a recovery outcome when the stopped Attempt leaves meaningful decision, evidence, or retained-resource context; a transient Attempt that is fully cleaned up stays recordless. If the candidate is finished but still has human acceptance, merge review, rollout approval, or another manual gate, keep the Ticket completed, state that pending boundary concisely in the handoff Summary, and leave later evidence to its acceptance, landing, or release owner.

Post-Execution Review is complete only when the root's full requirement-to-evidence audit passes, no fixable findings remain, unresolved state-relevant residue is routed to the Ticket or handoff, and every record-worthy Digest item needed by the next owner is ready for the concise Summary request. The root owns this conclusion and the semantic outcome; the adapter owns the Ticket transition and receipt write, while delegated reviews supply evidence but cannot advance either boundary.

If an interruption, context boundary, or execution limit arrives before this pass, preserve the same unabridged acceptance boundary. Meaningful unfinished work follows the existing recovery/resume handoff and remains non-candidate; a fully cleaned transient Attempt with no recovery value remains recordless. Resumption re-reads the complete Ticket and approved source Spec, verifies the live head, and refreshes stale evidence rather than treating the prior partial audit as completion.

### 8.5 Outcome Finalization

Every Attempt that stops or hands off routes through this decision once. Read the [Solve Record format](../solve-records/references/record-format.md) before submitting the handoff; it owns the compact receipt contract and legacy normalization. Read the [recovery edge cases](../solve-records/references/edge-cases.md) when resuming, closing, superseding, or cleaning a recovery receipt. This runbook owns **Candidate Readiness** and Attempt classification. The Tracker Facade outcome-handoff adapter is the one canonical writer for the receipt, Ticket backlinks and state, Claim disposition, retained-resource facts, and successor relation.

Classify the handoff before applying any candidate-only Git gate:

| Attempt result | Receipt outcome | Actionable Ticket state | Claim disposition |
| --- | --- | --- | --- |
| Finished, full requirement-to-evidence audit passed, validated, and Post-Execution Review passed | `candidate` | `completed` | release |
| Required validation, integration, or tooling failure with retained evidence or resources | `blocked` | `ready-for-human` unless the tracker contract provides a more specific actionable blocker state | retain only for the same actively assigned resume; otherwise release |
| Substantive assessment discovers missing core information | `needs-info` | `needs-info` | retain only for the same actively assigned resume; otherwise release |
| A human-owned decision or review finding prevents a finished candidate | `ready-for-human` | `ready-for-human` | retain only for the same actively assigned resume; otherwise release |
| The current Attempt is intentionally stopped while the Ticket remains valid | `abandoned` | `ready-for-agent` | release |
| A resumed recovery context reaches another meaningful handoff | the new outcome on a successor receipt; retain the predecessor's original outcome | apply the successor outcome state | apply the successor outcome disposition; close the predecessor only after successor success |
| Immediate Claim release, transient failure, or fully cleaned work with no useful finding | none | restore the prior claimable or actionable state | release |

The meaningful-handoff test is positive: submit a handoff when durable findings, failed-check evidence, retained resources, a requested decision, or resource disposition gives a future maintainer something to resume, review, close, supersede, or clean. When none of those exists, use the configured Claim-release path, remove only safe solve-owned transient resources and stale Attempt links, and leave no receipt or backlink.

Before any handoff side effect, generate and retain a caller-generated opaque handoff key. Submit semantic intent through the configured facade, for example:

```bash
python scripts/ultra_tracker.py ticket handoff \
  --ticket-id <exact-ticket-id> \
  --handoff-key <opaque-key> \
  --outcome <candidate-or-recovery-outcome> \
  --summary <concise-outcome-and-validation-summary>
```

The facade resolves the repository from the current directory. Use
`--repo <repository-path>` only when intentionally invoking it from outside the
target repository.

Repeat `--ticket-id` for a grouped complete set. Recovery handoffs also pass `--recovery-next-action` and the complete `--retained-resource` declaration. A successor uses a new key and passes `--supersedes <canonical-open-recovery-receipt>`. Never prewrite a canonical receipt, choose its path, append its backlink, mutate Ticket or Claim state, or replace a recovery receipt's outcome in place. Draft files, stdin, and long text are request inputs only.

Handle the facade result as a retry contract:

- `success`: accept only the returned canonical receipt identity after the adapter rereads the complete postcondition.
- `retryable`: retry the same handoff key and identical immutable inputs; do not switch writers or create another receipt.
- `conflict`: stop and inspect the named identity or state mismatch; never repurpose the key.
- `unavailable`: report the missing configured capability; there is no manual lifecycle fallback.

Only `success` exits zero with top-level `ok: true`. Every other handoff status
exits nonzero with `ok: false` while retaining its structured status, identity,
reason, and next action for recovery.

The adapter derives candidate Git identity, owns the compact receipt path and binding, applies every Ticket and Claim transition, and verifies grouped uniformity. For open recovery outcomes, it retains the Claim only for `resume` with a complete, live, unambiguous solve-owned resource set. The recovery ownership matrix treats resume without resources, resources with non-resume intent, partial or invalid resource declarations, stale or ambiguous ownership, and mixed grouped disposition as conflicts requiring manual inspection; it releases the Claim only for an empty declaration with non-resume intent. For a successor, it preserves both creation-time outcomes and backlinks, writes the reciprocal `superseded_by` relation, and closes the predecessor only after successor success.

Candidate Readiness requires a finished, reviewable candidate, current `head` identity, passed required validation, a passed full-boundary requirement-to-evidence audit, and passed Post-Execution Review. It does not require Candidate Acceptance Review or Human Acceptance and grants no merge or landing authority, deployment or release authority, smoke result, or cleanup authority. Checks marked `unavailable` remain a later candidate-gate concern and do not become a false pass during readiness.

For resume or clean restart, follow the linked recovery edge cases. Outcome Finalization completes only when the facade reports `success`; its compact receipt is the handoff fact, while later `$solve-records` acceptance, landing, release, and cleanup operations gather and persist their own live evidence without creating a second solve lifecycle.

Adoption mode uses the same handoff interface. The adapter derives `head` from the adopted candidate worktree, while adopted worktrees and branches remain user-owned and outside automatic cleanup.

The Ticket `completed` state means acceptance criteria are implemented and verified. The Solve Record `merged` state means a candidate entered the base branch. Receipt lifecycle and cleanup status remain on the receipt.

### 9. Auto-Merge Solve Records If Requested

Auto-merge only when the user explicitly provided `--auto-merge` or asked to merge, apply, ship, land, or equivalent.

The landing branch must be explicit or safely inferred from tracker/project context. If ambiguous, ask before merging.

In adoption mode, `--auto-merge` means try to land the candidate branch into the landing branch. It never means merge an adopted candidate branch back into itself.

Route requested auto-merge/merge/apply/ship/land wording through the same solve-record landing gate used by `$solve-records`. Merge eligible records one by one, in dependency order. Explicit set wording such as `all ready records` may process the bounded set one record at a time, but ineligible records must be skipped with reasons. Do not silently merge dependencies unless the user explicitly approves the wider operation.

Apply this section only after the Outcome gate re-reads `outcome: candidate`. Recovery receipts remain on their recovery actions even when they retain branches, worktrees, commits, or PRs.

All record merge gates must pass:

1. The selected receipt parses as `outcome: candidate`, and no selected Ticket remains `needs-info` or `ready-for-human`.
2. Every group passed its local validation.
3. Every eligible group branch is committed and its worktree is clean.
4. The integration worktree started from the latest target branch and is clean after committed integration changes.
5. All eligible group branches are integrated and final validation passed.
6. No semantic conflict was force-resolved.
7. The solve record was re-read and live Git state still matches recorded `base_sha` and `head_sha`, or the record was revalidated before merge. A changed `head_sha` blocks merge until fresh validation updates the record. A changed `base_sha` may be revalidated only when the recorded base is an ancestor of the live base, the head still matches, preflight merge is clean, and checks are rerun or the unavailable-check low-risk exception is restated against the live base.
8. The record has no manual-review trigger, stale check, stale ref, missing dependency, missing or blocking rollout/config disposition, or unavailable check without the low-risk exception evidence.

The landing gate constructs `landing_sha` before touching the user's base worktree. Fast-forward candidates use head as `landing_sha`; non-fast-forward candidates and mechanical conflicts must be merged or resolved in a disposable worktree or equivalent throwaway environment. Semantic conflict resolution still stops as `manual required`.

After `landing_sha` exists, the base worktree may only advance with `git merge --ff-only <landing_sha>` or an equivalent ref-safe fast-forward. Dirty or untracked base paths are allowed only when the final landing write surface is proven disjoint from those paths. `/ultra solve --auto-merge` must not fetch, push, deploy, broaden selected Tickets, or silently merge dependencies.

If merge succeeds, update the solve record to `state: merged`, set `merged_at` and `merged_sha` to the landed `landing_sha`, write a concise merge rationale, and then attempt safe cleanup. If cleanup fails after the merge, do not roll back the code merge; keep the record merged with `cleanup_done: false` and report cleanup blockers.

If merge fails or conflicts before completion, abort the merge when possible, keep the solve record open, write `manual required` in the record, do not clean up the candidate branch/worktree, and do not roll linked Tickets back from `completed` unless the candidate itself is invalidated.

By default, show the Ticket list, group branches, validation commands and results, pending blockers, and final target branch. Include a full diff only when the user asks for it or review needs it.

## AFK Mode For Routed Skills

When routing to the debugging skill, `/ultra tdd`, or another skill:

- Treat the Ticket body, acceptance criteria, and Agent Brief as approved input.
- Continue without waiting for user confirmation.
- If a routed skill reaches an unanswerable decision, update only that Ticket to `ready-for-human` or `needs-info` and continue the batch.
- Isolate blocked Tickets and continue unrelated Tickets.

Architecture proposal skills such as `/ultra improve-codebase-architecture` are analysis-first. Solve executes approved ready Tickets; speculative architecture work stays in the proposal/review track.

## Upstream Ticket Quality

`technical_context` is optional in v1. If a Ticket lacks technical detail, solve should infer what it can from the codebase. If missing context blocks completion, set `needs-info` with a blocker reason. If recurring Ticket-quality gaps appear, mention them in the final solve summary or an existing project Ticket-generation surface; Ticket-generation improvements can stay within the existing tracker schema.

This is a feedback loop, not a schema gate: `to-tickets -> solve notices missing context -> solve reports the gap -> future Ticket generation improves`.

## Tracker Adapter Compatibility

Current mutation support is Local Markdown trackers. The following compatibility API identifiers retain their established spellings while operating on Tickets; the conceptual contract for future remote tracker support is:

For Local Markdown, prefer `scripts/ultra_tracker.py` for configured publication, frontier, Claim, and Solve Record helper operations. It centralizes configured publication discovery and result envelopes while the owning adapter or helper retains all semantics. Outcome handoff has no direct-helper or manual fallback: an unavailable facade or configured handoff helper returns `unavailable` before lifecycle mutation. Other operations may make one explicit capability-equivalent direct-helper choice only before the operation begins; never retry or repeat a completed operation through the other route. Contract-bounded normalization applies only to declared presentation aliases; identities remain exact. When an adapter is unavailable or does not cover an ordinary Local Markdown Ticket edit, make the smallest direct edit on the canonical surface, inspect the diff, and re-read the result. Do not use this fallback for Claim, Solve Record, outcome handoff, publication, or terminal-repair transitions.

- `list_ready_for_agent(filter)`
- `read_issue(issue_id)`
- `claim_issue(issue_id, branch, worktree)`
- `set_state(issue_id, state)`
- `add_flag(issue_id, flag)`
- `remove_flag(issue_id, flag)`
- `record_blocker(issue_id, reason, evidence_link_or_summary)`
- `link_change(issue_id, branch_or_worktree_or_commit_or_pr)`
- `link_validation(issue_id, command_or_check_run, status)`
- `close_completed(issue_id)`

Adapters must provide atomic or conflict-detecting claim behavior. If they cannot, solve must not run in batch mode against that tracker. Local markdown adapters may satisfy this by re-reading immediately before claim and detecting file changes before write.
