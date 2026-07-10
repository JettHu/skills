# Ultra Solve

`/ultra solve` is a subcommand of `/ultra`. It picks up AFK-ready issues, coordinates execution worktrees, integrates results, validates the final branch, creates solve records for finished candidates, updates issue state, and optionally merges when the user explicitly asks for it.

It has its own state machine and coordination workflow, so handle it before normal target-skill profile lookup.

## Tracker Operations

Use tracker verbs, not hard-coded frontmatter fields, so local markdown trackers and future remote adapters can share the same workflow contract:

- list issues ready for agent work
- read issue body, acceptance criteria, state, flags, notes/comments, and linked branches/worktrees/changes
- claim issue
- set issue state
- add or remove issue flags
- record issue-state-relevant notes, decisions, or blocker reasons
- link branches, worktrees, commits, PRs, solve records, or validation runs
- close completed issues

Current mutation support is local markdown trackers, such as `.scratch/<feature>/issues/*.md` or `.scratch/<feature>/issue.md`. If the tracker is remote and no adapter is available, you may read issue context, but stop before claim/update/close operations and report that a remote tracker adapter is needed.

Tracker updates should record state-relevant facts. Use the tracker state, labels, assignment, or project status for claim/progress when available. Use PRs, commits, branches, and CI/check runs for implementation and validation evidence, linking them from the issue when useful. Use issue comments or local issue notes for requirement clarification, concise blockers, human decisions, or completion notes only when that is the tracker's normal review surface. Keep batch logs and large command output in the final solve summary or validation artifacts.

## Invocation

```text
/ultra solve [issue-id... | --all] [--auto-merge] [message]
```

- Explicit issue ids: solve only those issues.
- `--all`: solve every issue currently ready for agent work.
- `--auto-merge`: after finished solve records are created, merge eligible records into the local base branch one by one through the merge gate. It does not fetch, push, deploy, or broaden the selected issue set.
- Free-form message: infer the relevant issues from the conversation and tracker, then state the selection before claiming.
- Merge/apply/ship/land wording: treat as auto-merge intent after the solve pipeline succeeds and the merge gates pass.

## Core Semantics

`/ultra solve` is the coordinator. It must keep five surfaces consistent:

- issue tracker state
- group worktrees and branches
- validation evidence
- solve records
- candidate and landing branches

Group worktrees produce candidate changes. The coordinator owns integration and merge. A group worktree must not merge directly into the target branch.

Default completion, when no `--auto-merge` or merge/apply/ship/land intent is present, is a clean committed candidate branch plus a solve record. `head` is the candidate branch whose current head contains finished work. `base` is the landing branch the candidate is meant to enter later. Push, deploy, and cleanup happen only when the user's latest wording explicitly asks for them or when a later solve-record command advances the candidate.

Issues are assumed AFK-ready when they are in `ready-for-agent`: the issue body, acceptance criteria, and any agent brief are treated as approved input. Continue the batch unless the issue selection or merge target is ambiguous and cannot be inferred safely.

An Agent Brief is an optional, non-duplicative delta to the issue and source Spec, never a schema gate. If present, use only its constraints, validation guidance, and optional hints during planning; re-check hints against current code and repo conventions before relying on them. If it is absent or empty, infer from the issue, codebase, and conversation where possible; missing core requirements become `needs-info`, and human-owned decisions become `ready-for-human`. Agent Brief content never participates in parsing, eligibility, state transitions, or merge gates.

## Worktree Boundary

`/ultra solve` owns worktree identity and lifecycle semantics: issue grouping, branch-from ref, branch name, worktree path, claim state, validation, integration, solve-record finalization, and merge gates.

Use native `git worktree add` as the normal creation interface for assigned solve worktrees. If the repo has an `agent-worktree` post-checkout hook installed, Agent payload injection is a repo-local side effect of that native Git operation.

Use the same solve workflow after repo initialization, with or without the `agent-worktree` scaffolding skill loaded. `agent-worktree` must not choose solve branch names, worktree paths, branch-from refs, grouping, merge behavior, cleanup behavior, or validation policy.

When adopting an existing worktree, verify the expected path, branch, and assignment context with raw Git checks. Missing Agent payload is local setup drift; report it only when it affects execution or validation, and continue to use the same solve workflow.

## Adoption Routing

Before claiming, decide the worktree route from the current branch/worktree, selected issues, tracker claim state, dirty status, branch topology, and risk. Adoption is Agent-judged behavior, not a required explicit flag.

Choose exactly one route and state an adoption declaration before implementation:

- `isolated`: create solve-owned candidate worktree(s) and branch(es).
- `adopted-execution`: use the current worktree/branch as the execution or serial group target.
- `adopted-integration`: use temporary group worktrees, then integrate into the current worktree/branch as the final candidate.
- `ask`: stop before claim or implementation and ask the user to choose.

For ordinary AFK pickup with no safely indicated prepared development branch, keep the existing `isolated` solve boundary.

A prepared development branch is the current branch, or a branch clearly identified by the user request, tracker metadata, Codex App setup, or stack topology, as intended for the selected issue work. Branch names, commit messages, and issue paths may support this judgment, but name similarity alone is not enough. The branch must be non-protected, aligned with the issue scope, free of active claim conflicts, and able to pass entry safety.

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
- the current branch/worktree conflicts with tracker claim metadata or an active claim
- dirty or untracked paths overlap likely issue write paths or may be overwritten
- branch topology, branch-from ref, or candidate identity is unsafe enough that adopting could hide or overwrite work

When creating an isolated worktree because adoption is unsuitable, choose a branch-from ref that preserves the user's current integration context. Prefer the current branch or current HEAD when it is the strongest signal; use issue text, tracker metadata, stack relationships, release branches, or repo convention only when they clearly identify a better branch-from ref. When invoked from a protected baseline, default the branch-from ref to the current baseline or HEAD unless the user, tracker, Codex App setup, or stack topology clearly identifies another integration branch for this work. Branch existence alone is insufficient as a switch signal to or away from `main` or `master`.

The branch-from ref is only the starting point for `git worktree add`; it is not necessarily the solve record `base`. In solve records, `base` remains the landing branch the candidate is meant to enter later. For example, if dirty issue-scoped work prevents adopting the current `feature/billing` branch, an isolated solve branch may be created from `feature/billing` HEAD while the solve record still uses `base: main` when `main` is the landing branch.

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
```

State meanings:

- `ready-for-agent`: unclaimed work that another AFK agent may start.
- `solve-in-progress`: a claim flag, added immediately after claim to prevent parallel pickup.
- `completed`: acceptance criteria are implemented and verified.
- `ready-for-human`: semantic conflict, final validation failure, or other non-requirements blocker.
- `needs-info`: core requirement cannot be inferred from the issue, code, or conversation.

Primary states and flags are separate. `ready-for-agent`, `completed`, `ready-for-human`, and `needs-info` are primary states. `solve-in-progress` is a temporary claim flag that may be stored as a label, flag, status metadata, or another tracker-specific convention. Record-worthy low-risk decisions belong in the active Execution Digest and then the outcome Solve Record, not in Ticket state or flags.

Flag lifecycle:

- Add `solve-in-progress` only after a claim succeeds.
- Remove `solve-in-progress` when the issue reaches `completed`, `needs-info`, or `ready-for-human`, unless the branch/worktree is intentionally left as active resumable work for a human conflict resolution.
- If a stale `solve-in-progress` flag references a missing branch or worktree, inspect the issue history and branch refs. Resume, clear, or ask before mutating; do not silently discard it.

When setting `ready-for-human` or `needs-info`, record a concise blocker reason when the tracker supports state-relevant notes:

- `missing_requirement`: acceptance criteria or core behavior cannot be inferred.
- `semantic_conflict`: product, architecture, API, security, data, or UX judgment is required.
- `verification_failed`: required validation was run and failed.
- `verification_unavailable`: required validation cannot run in the current environment.
- `integration_conflict`: locally valid changes conflict during integration.
- `tooling_unavailable`: required local tools, dependencies, branches, or worktree operations are unavailable.
- `tracker_unavailable`: required tracker mutation is unavailable or unsupported.

A blocker reason explains a state transition; it is not a new state.

Discovery must skip issues carrying an active `solve-in-progress` claim and report them as already claimed.

## Workflow

### 1. Discover

Select candidate issues from explicit ids, `--all`, or the message. Keep only issues in `ready-for-agent`.

Report skipped issues with a short reason:

- wrong state
- has active `solve-in-progress`
- stale claim needing manual/resume handling

### 2. Claim

For every selected issue:

- determine the adoption route and intended branch/worktree reference
- re-read the issue and confirm it is still `ready-for-agent` with no active `solve-in-progress`
- claim it by adding `solve-in-progress` and recording the intended branch/worktree through the tracker's existing machine-readable claim surface
- create or adopt the assigned branch/worktree after the claim succeeds

Do this before code changes. For local markdown, preserve existing structured conventions such as `state`/`status`, `flags`/`labels`, and `branch`/`worktree`/`solve_branch`/`solve_worktree`. Batch or parallel solve requires a machine-readable claim surface. If no reliable claim surface exists, do not run unsafe batch claims; for an explicit single issue, proceed only when user intent is clear and report the claim limitation.

If branch/worktree creation or adoption fails after claiming, clear the claim when no resumable work exists. If resumable work exists, record a blocker reason and retain or clear `solve-in-progress` according to whether a human can resume from the linked branch/worktree.

### 3. Assess: Pre-Implementation Checkpoint

For each claimed issue, run the Pre-Implementation Checkpoint after claim and before implementation edits. Read the issue body, acceptance criteria, comments, linked docs, optional Agent Brief, and enough current repository context to decide whether the issue is executable.

Classify the issue disposition:

- `executable`: enough information exists or can be inferred.
- `needs exploration`: technical details are missing, but the codebase can likely answer them.
- `needs-info`: a core requirement cannot be inferred.
- `ready-for-human`: the issue is really an unapproved architecture, product, security, data, or significant UX decision.

If an issue becomes `needs-info` or `ready-for-human`, update its state, record the blocker reason, remove `solve-in-progress` unless resumable work is intentionally left active, and continue with the rest of the batch.

The main Agent records, without requesting approval:

- exploration disposition: `direct main-Agent execution`, `narrow main-Agent exploration`, `adaptive read-only subagent fan-out`, or `conditional external research`
- validation plan: commands, manual evidence, check-run links, or why no meaningful automated check exists
- Digest disposition: `simple` or `digest-worthy`

Direct main-Agent execution requires positive evidence that the issue is simple, familiar, local, low-risk, fully specified, and obviously verifiable. Existing high-quality exploration in the active context may satisfy part of that evidence and avoid duplicate fan-out. A clear local fix alone is not enough.

Bias most non-trivial or uncertain issues toward adaptive read-only subagent fan-out. Use task-shaped lenses only when they add independent evidence: affected modules, contracts, risks, dependencies, validation, or relevant external facts. Subagents return compressed findings—relevant modules, constraints, risks, validation paths, and unresolved questions. The main Agent retains synthesis, implementation edits, validation, tracker transitions, and solve-record finalization. Raw exploration output stays outside the issue, Execution Digest, and Solve Record.

Use external research only when a source-verifiable external API, framework, standard, platform, compatibility, or security fact affects implementation or validation and local approved context cannot settle it. Link the source and keep the finding factual. Research never substitutes for a human-owned product, architecture, data-policy, or security-policy choice.

### Execution Digest: Conditional Working Memory

An Execution Digest is a separate ticket-level working file, never a Ticket-body section, tracker state, schema gate, or second requirement source. Create it at the start of a digest-worthy Attempt: a multi-module, delegated, resumable, interrupted, non-obvious-validation, or likely record-worthy-decision Attempt. A simple Attempt creates no Digest until its first material decision or deviation; create it at that event without rewriting the Ticket.

For a local Ticket at `.scratch/<feature>/issues/<ticket-file>.md` or `.scratch/<feature>/issue.md`, use exactly:

```text
.scratch/<feature>/execution-digests/<digest-key>.md
```

Derive `digest-key` in this order: use the stable tracker Ticket ID when present and matching `[A-Za-z0-9][A-Za-z0-9._-]*`; otherwise use the local Ticket filename stem when it matches that pattern; otherwise use the full SHA-256 of the canonical Ticket identity (the repo-relative local Ticket path). A feature owns one `issue.md` and each `issues/*.md` filename is unique within that feature, so the feature directory plus this key is collision-safe. The derivation never accepts path separators. The directory is outside normal Ticket discovery: discover only `.scratch/*/issues/*.md` and `.scratch/*/issue.md`, never a broad `.scratch/**/*.md` glob.

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

When the same retained branch, worktree, and recovery context resume, reopen and update the same Digest path. At candidate handoff, distill durable decisions and deviations into `## Review` or `## Notes`; at recovery handoff, distill them into `## Attempt Summary` or `## Confirmed Findings`. Retain the Digest only while it has resume value or repository policy requires it; otherwise delete it after that durable transfer. If a required Digest cannot be written durably, keep the same compact fields in the active conversation and report the reduced interruption-recovery guarantee.

Complex, delegated, resumable, or digest-worthy Attempts receive a Pre-Edit Plan Review before implementation edits. Prefer a fresh read-only reviewer when that capability exists; otherwise the main Agent performs the equivalent findings-first review. Check the compressed plan, acceptance criteria, constraints, risks, and validation strategy for omitted steps, unsafe assumptions, and validation gaps. Incorporate findings into the plan or Digest; the review creates no standalone lifecycle artifact and no blanket human approval gate.

Record-worthy low-risk decisions go in the active Digest and outcome Solve Record. Human-owned product, API, data, security, architecture, or significant UX choices set the issue to `ready-for-human`; missing core requirements set it to `needs-info`.

The Pre-Implementation Checkpoint is complete when each claimed issue has an issue disposition, exploration disposition, validation plan, Digest disposition, and any required Digest or Pre-Edit Plan Review incorporated before implementation edits.

### 4. Group

Group executable issues by module, dependency, and likely file overlap.

- Same module or shared files: one group, serial execution.
- Independent modules: separate groups that may be executed in parallel when the runtime supports it.
- Shared migrations, config, generated types, routing, fixtures, dependency versions, or public contracts are coupling signals; group or order them conservatively.

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
- [ ] Dirty and untracked paths are absent, or proven unrelated to the selected issue scope before adoption

Do not edit code, tests, docs, config, migrations, or generated artifacts until this gate passes.

If this gate fails, stop and create or enter the correct group worktree before continuing.

If delegating to a subagent, include the assigned worktree path and branch in the brief. The subagent must run the same gate before editing. If the runtime cannot guarantee the subagent's working directory, do not delegate implementation work; run it serially with tools explicitly pointed at the group worktree.

### 5. Execute Groups

Create one group worktree per group from the selected branch-from ref, unless the adoption route intentionally uses an existing worktree for that group. Execute only after the Pre-Execute Gate passes for that group.

Suggested names:

- group branch: `solve/<timestamp>-<group-name>`
- group worktree: `worktree-solve-<timestamp>-<group-name>`

Create the assigned worktree with native Git, for example:

```bash
git worktree add -b "<group-branch>" "<group-worktree-path>" "<branch-from-ref>"
```

If the repo-level Agent-ready hook is installed, payload bootstrap happens automatically during `git worktree add`. Solve creates and verifies assigned worktrees with native Git, and removes solve-owned resources through solve-record cleanup gates; `agent-worktree` remains hook/config scaffolding. If native Git cannot create the exact assigned identity, mark only the affected issue/group with `tooling_unavailable`.

For `adopted-integration`, temporary group branches are solve-owned resources. The adopted integration branch is the candidate branch and remains user-owned.

For each issue in a group:

1. Execute from the Pre-Implementation Checkpoint. Refresh exploration only when code changed since planning or the assigned worktree exposes new facts.
2. Choose execution route. These are optional routing heuristics, not mandatory skill calls:
   - direct execution: only when the Checkpoint recorded every required simple-ticket predicate
   - unclear bug: prefer the debugging skill (`/ultra diagnosing-bugs`, or a configured alias) in AFK mode when a diagnosis loop would reduce risk
   - medium feature with clear AC: consider `/ultra tdd` in AFK mode when test-first development would help
   - approved refactor with clear AC: implement directly, or consider `/ultra tdd` when behavior coverage is needed
   - speculative architecture change: mark `ready-for-human`
   - docs/config-only issue: edit directly
3. Implement.
4. Verify each acceptance criterion.
5. Record validation evidence as a PR, commit, CI/check, tracker pointer, or final solve summary entry.
6. Commit verified work to the group branch before leaving the group worktree.

Commit rules:

- Leave successful group work as clean, committed group branches for integration.
- Split commits by issue, vertical slice, or coherent logical change when that makes review and rollback clearer.
- Keep tightly coupled code, tests, docs, and generated artifacts together when separating them would create broken intermediate commits.
- Commit granularity should follow coherent behavior and review boundaries: separate unrelated issues, and keep mechanical fragments together when they explain one behavior.
- Commit messages should reference the relevant issue id(s) and, when useful, the validation command or evidence.

### 6. Review Groups

Review before integration:

- Simple group: coordinator self-check against every acceptance criterion.
- Medium group: two-pass review for completeness and consistency.
- Complex or cross-cutting group: stronger multi-review when available.

For implementation groups, pin the group review range against the group branch base before reviewing. Treat the following as review lenses, not mandatory output sections. Report real findings under the relevant axis:

- Spec: compare the committed group diff with the originating issue body, acceptance criteria, PRD, or agent brief. Flag missing requirements, partial implementations, scope creep, and behavior that appears wrong against the spec.
- Standards: compare the committed group diff with documented repo standards, project conventions, ADRs, and nearby code patterns. Flag hard violations separately from judgment calls.

Also check supporting engineering risks only when relevant to the changed files or risk: side effects and regression risk, test/validation coverage, and dependency or compatibility issues.

Fix blocking review findings before integration, then commit the fixes to the relevant group branch with the same split-commit rules. If a finding requires human judgment, mark the issue `ready-for-human`, remove or retain `solve-in-progress` according to resumability, and exclude it from merge gates.

### 7. Integrate

Create one integration worktree from the latest target branch. The integration worktree is mandatory whenever more than one group exists, `--auto-merge` is present, or merge/apply/ship/land was requested; it is still recommended for a single non-trivial group.

Suggested names:

- integration branch: `solve/<timestamp>-integration`
- integration worktree: `worktree-solve-<timestamp>-integration`

Merge or cherry-pick committed, locally validated group branches into integration in dependency order. Each group worktree must be clean before integration starts.

- Mechanical conflicts: the coordinator may resolve them.
- Semantic conflicts: stop integration for the affected issues, set them `ready-for-human`, and do not force a merge.
- Any mechanical conflict resolution or integration-only fix must be committed on the integration branch before final validation is considered complete.

The integration stage exists to catch hidden coupling between parallel work: shared types, migrations, router registration, scheduler registration, config defaults, fixtures, generated artifacts, and dependency changes.

### 8. Final Validate

Run the repo-appropriate validation commands in the integration worktree. Prefer the project's documented commands; otherwise use the narrowest meaningful test/build/lint set first and expand when risk requires it.

If final validation passes:

- ensure the integration worktree is clean and all intended changes are committed
- capture the landing `base`, `base_sha`, candidate `head`, `head_sha`, issue paths, worktree path, checks status, validation evidence, rollout/config disposition, and cleanup ownership for solve record creation
- proceed to finalization before marking linked issues completed

If final validation fails:

- identify affected issues when possible
- set them `ready-for-human`
- record the blocker reason and a concise failing command summary or check-run link
- do not merge
- retain `solve-in-progress` only when the branch/worktree is intentionally left for a human to resume

If no meaningful automated check exists or the environment cannot run it, do not call that a pass. When the candidate is otherwise complete, finalization may create a solve record with checks marked `unavailable`; auto-merge remains blocked unless the change is explicitly trivial and low-risk, and the record says why no meaningful check exists, why no manual-review trigger applies, and what evidence still supports the change.

Do not create a candidate solve record for failed required checks. A transient failure with no retained evidence or resources stays in issue/attempt blocker state. A required validation or integration failure that retains evidence, a branch, worktree, or another recovery value reaches the outcome-finalization flow as a recovery record instead.

When a blocked, needs-info, ready-for-human, abandoned, superseded, or retained-failure Attempt reaches the outcome-finalization flow, distill durable Digest decisions and deviations into its recovery record's `## Attempt Summary` or `## Confirmed Findings`. Retain the Digest only while its linked resources have resume value or repository policy requires it; otherwise delete it after the transfer.

### 8.4 Post-Execution Review

After final validation and before solve-record finalization, review the integrated candidate against the claimed issues, acceptance criteria, optional Agent Briefs, living Execution Digests, side effects, validation evidence, and solve-record readiness. Use reviewer subagents when that improves coverage; otherwise run the same review in the main agent.

Check for:

- acceptance criteria implemented only partially or differently than approved input
- stale Agent Brief hints or Execution Digest assumptions
- record-worthy low-risk decisions not ready for durable handoff, or human-owned decisions
- side effects, regressions, or public-contract changes not covered by validation
- validation gaps, unavailable required checks, or missing manual gates
- solve-record evidence that would be incomplete or misleading

Fix actionable findings directly, rerun the relevant validation, and repeat Post-Execution Review on the corrected candidate. If a finding prevents a finished candidate and cannot be resolved without human input, record the blocker on the issue, set the issue to `ready-for-human` or `needs-info`, and create no solve record for that issue. If the candidate is finished but still has human acceptance, merge review, rollout approval, or another manual gate, keep the issue completed and record the gate in the solve record.

Post-Execution Review is complete when no fixable findings remain, unresolved state-relevant residue is routed to the issue or solve record, and every record-worthy Digest item is ready to distill into the applicable outcome section.

### 8.5 Finalize Solve Record

Create a candidate Solve Record only after a finished, reviewable merge candidate exists:

- clean, comparable `head` candidate branch
- known `base` landing branch and `head` candidate branch refs
- recorded `base_sha` and `head_sha`
- linked issue paths
- checks status and validation evidence
- Post-Execution Review outcome
- merge-gate disposition
- rollout/config disposition in the record body
- worktree and cleanup resource notes

Create a recovery Solve Record only through the outcome-finalization flow when a blocked, needs-info, ready-for-human, abandoned, superseded, or retained-failure Attempt has a meaningful handoff outcome. Keep transient claim-time failures and fully cleaned work with no recovery value recordless.

Do not create candidate solve records for claim-time state, in-progress attempts, missing requirements, failed required checks, unresolved Post-Execution Review findings that prevent a finished candidate, or a human-required decision that prevents the candidate from being finished. The outcome-finalization flow may create the matching recovery record when retained evidence or resources give the Attempt handoff value. If a finished candidate exists but needs human review before merge for product/API/security/data/architecture/rollout risk, create the record as `state: open` with `## Merge` set to `manual required`; do not auto-merge it.

Checks marked `unavailable` block auto-merge unless the change is explicitly trivial and low-risk, and the record says why no meaningful check exists, why no manual-review trigger applies, and what evidence still supports the change.

Before creating an auto-mergeable or ready solve record, explicitly consider rollout/config/operator-action signals. Use already-known project context when it is sufficient; otherwise scan the changed files and nearby docs for generic signals such as config files, environment variables, feature flags, migrations, deployment docs, and runbooks. Record one body-prose disposition under `## Merge` or `## Notes`: `none`, `pre-merge action required`, or `post-merge activation required`. `pre-merge action required` means `manual required`; `post-merge activation required` can remain ready only when the record explains why code merge is safe, what action activates the change, how to smoke-check or validate it, and how to roll back or disable it.

Adoption mode still creates solve records for finished candidates. When an adopted branch is the candidate branch, `head` is that branch and `base` is the landing branch; the record must not imply a merge back into the same branch. If development-environment deployment or human acceptance is pending, mark linked issues `completed` when acceptance criteria are verified, but set the solve record merge gate to `manual required` and record the pending evidence in `## Checks` or `## Merge`. A later `$solve-records` acceptance review may update `## Merge` from `manual required` to `ready` after live verification, while keeping `state: open`; landing remains reserved for explicit merge, ship, or land intent.

Do not clean up successful solve worktrees during ordinary finalization. The candidate branch and worktree remain review context until auto-merge, merge/apply/ship/land, or an explicit cleanup request advances the solve record. Adopted worktrees and adopted candidate branches are user-owned resources; record them as not cleanup-owned and do not schedule them for automatic cleanup.

During the same finalize step:

- create the solve record in `.scratch/<feature>/solve-records/` or `.scratch/solve-records/`
- mark linked issues `completed`
- append only a solve-record backlink to each issue; record state stays in the solve record
- link implementation and validation evidence where the tracker convention needs it
- remove `solve-in-progress`
- distill each durable Digest decision or deviation into candidate `## Review` or `## Notes`; retain the Digest only when it still has resume value or repo policy requires it, otherwise delete it

The issue `completed` state means acceptance criteria are implemented and verified. The solve record `merged` state means the candidate entered the base branch. Cleanup status remains on the solve record.

### 9. Auto-Merge Solve Records If Requested

Auto-merge only when the user explicitly provided `--auto-merge` or asked to merge, apply, ship, land, or equivalent.

The landing branch must be explicit or safely inferred from tracker/project context. If ambiguous, ask before merging.

In adoption mode, `--auto-merge` means try to land the candidate branch into the landing branch. It never means merge an adopted candidate branch back into itself.

Route requested auto-merge/merge/apply/ship/land wording through the same solve-record landing gate used by `$solve-records`. Merge eligible records one by one, in dependency order. Explicit set wording such as `all ready records` may process the bounded set one record at a time, but ineligible records must be skipped with reasons. Do not silently merge dependencies unless the user explicitly approves the wider operation.

All record merge gates must pass:

1. No selected issue remains `needs-info` or `ready-for-human`.
2. Every group passed its local validation.
3. Every eligible group branch is committed and its worktree is clean.
4. The integration worktree started from the latest target branch and is clean after committed integration changes.
5. All eligible group branches are integrated and final validation passed.
6. No semantic conflict was force-resolved.
7. The solve record was re-read and live Git state still matches recorded `base_sha` and `head_sha`, or the record was revalidated before merge. A changed `head_sha` blocks merge until fresh validation updates the record. A changed `base_sha` may be revalidated only when the recorded base is an ancestor of the live base, the head still matches, preflight merge is clean, and checks are rerun or the unavailable-check low-risk exception is restated against the live base.
8. The record has no manual-review trigger, stale check, stale ref, missing dependency, missing or blocking rollout/config disposition, or unavailable check without the low-risk exception evidence.

The landing gate constructs `landing_sha` before touching the user's base worktree. Fast-forward candidates use head as `landing_sha`; non-fast-forward candidates and mechanical conflicts must be merged or resolved in a disposable worktree or equivalent throwaway environment. Semantic conflict resolution still stops as `manual required`.

After `landing_sha` exists, the base worktree may only advance with `git merge --ff-only <landing_sha>` or an equivalent ref-safe fast-forward. Dirty or untracked base paths are allowed only when the final landing write surface is proven disjoint from those paths. `/ultra solve --auto-merge` must not fetch, push, deploy, broaden selected issues, or silently merge dependencies.

If merge succeeds, update the solve record to `state: merged`, set `merged_at` and `merged_sha` to the landed `landing_sha`, write a concise merge rationale, and then attempt safe cleanup. If cleanup fails after the merge, do not roll back the code merge; keep the record merged with `cleanup_done: false` and report cleanup blockers.

If merge fails or conflicts before completion, abort the merge when possible, keep the solve record open, write `manual required` in the record, do not clean up the candidate branch/worktree, and do not roll linked issues back from `completed` unless the candidate itself is invalidated.

By default, show the issue list, group branches, validation commands and results, pending blockers, and final target branch. Include a full diff only when the user asks for it or review needs it.

## AFK Mode For Routed Skills

When routing to the debugging skill, `/ultra tdd`, or another skill:

- Treat the issue body, acceptance criteria, and agent brief as approved input.
- Continue without waiting for user confirmation.
- If a routed skill reaches an unanswerable decision, update only that issue to `ready-for-human` or `needs-info` and continue the batch.
- Isolate blocked issues and continue unrelated issues.

Architecture proposal skills such as `/ultra improve-codebase-architecture` are analysis-first. Solve executes approved ready issues; speculative architecture work stays in the proposal/review track.

## Upstream Issue Quality

`technical_context` is optional in v1. If an issue lacks technical detail, solve should infer what it can from the codebase. If missing context blocks completion, set `needs-info` with a blocker reason. If recurring issue-quality gaps appear, mention them in the final solve summary or an existing project issue-generation surface; issue-generation improvements can stay within the existing tracker schema.

This is a feedback loop, not a schema gate: `to-issues -> solve notices missing context -> solve reports the gap -> future issue generation improves`.

## Tracker Adapter Compatibility

Current mutation support is local markdown trackers. The conceptual contract for future remote tracker support is:

For local markdown, detect and preserve the repo's existing issue conventions. Existing structured fields may include frontmatter keys such as `state`/`status`, `flags`/`labels`, comments/notes, or branch/worktree links. Use existing body-marker conventions only when they are already part of the tracker. Batch claims require a machine-readable claim surface.

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
