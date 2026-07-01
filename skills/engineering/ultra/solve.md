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

Tracker updates should record state-relevant facts, not run logs. Use the tracker state, labels, assignment, or project status for claim/progress when available. Use PRs, commits, branches, and CI/check runs for implementation and validation evidence, linking them from the issue when useful. Use issue comments or local issue notes for blockers, missing requirements, agent decisions, or completion notes only when that is the tracker's normal review surface. Do not copy batch logs or large command output into issues.

## Invocation

```text
/ultra solve [issue-id... | --all] [message]
```

- Explicit issue ids: solve only those issues.
- `--all`: solve every issue currently ready for agent work.
- Free-form message: infer the relevant issues from the conversation and tracker, then state the selection before claiming.
- Merge/apply wording: merge only after the solve pipeline succeeds and the merge gates pass.

## Core Semantics

`/ultra solve` is the coordinator. It must keep five surfaces consistent:

- issue tracker state
- group worktrees and branches
- validation evidence
- solve records
- final target branch

Group worktrees produce candidate changes. The coordinator owns integration and merge. A group worktree must not merge directly into the target branch.

Issues are assumed AFK-ready when they are in `ready-for-agent`: the issue body, acceptance criteria, and any agent brief are treated as approved input. Do not stop the whole batch to ask the user a question unless the issue selection or merge target is ambiguous and cannot be inferred safely.

## State Machine

Use these logical states even if the local tracker stores them with different field names.

```text
ready-for-agent
  -> claim: add solve-in-progress and link solve branch/worktree
      -> completed
      -> completed + agent-decision
      -> ready-for-human + agent-decision
      -> ready-for-human
      -> needs-info
```

State meanings:

- `ready-for-agent`: unclaimed work that another AFK agent may start.
- `solve-in-progress`: a claim flag, added immediately after claim to prevent parallel pickup.
- `completed`: acceptance criteria are implemented and verified.
- `completed + agent-decision`: implemented and verified, but the agent made a low-risk decision that should remain visible.
- `ready-for-human + agent-decision`: a decision affects API, architecture, security, data, product semantics, or user-visible behavior and needs human review.
- `ready-for-human`: semantic conflict, final validation failure, or other non-requirements blocker.
- `needs-info`: core requirement cannot be inferred from the issue, code, or conversation.

Primary states and flags are separate. `ready-for-agent`, `completed`, `ready-for-human`, and `needs-info` are primary states. `solve-in-progress` and `agent-decision` are flags that may be stored as labels, flags, status metadata, or another tracker-specific convention.

Flag lifecycle:

- Add `solve-in-progress` only after a claim succeeds.
- Remove `solve-in-progress` when the issue reaches `completed`, `needs-info`, or `ready-for-human`, unless the branch/worktree is intentionally left as active resumable work for a human conflict resolution.
- If a stale `solve-in-progress` flag references a missing branch or worktree, inspect the issue history and branch refs. Resume, clear, or ask before mutating; do not silently discard it.
- Add `agent-decision` when writing an Agent Decision Log.
- Do not remove `agent-decision` automatically. A human review clears it.

When setting `ready-for-human` or `needs-info`, record a concise blocker reason when the tracker supports state-relevant notes:

- `missing_requirement`: acceptance criteria or core behavior cannot be inferred.
- `semantic_conflict`: product, architecture, API, security, data, or UX judgment is required.
- `verification_failed`: required validation was run and failed.
- `verification_unavailable`: required validation cannot run in the current environment.
- `integration_conflict`: locally valid changes conflict during integration.
- `tooling_unavailable`: required local tools, dependencies, branches, or worktree operations are unavailable.
- `tracker_unavailable`: required tracker mutation is unavailable or unsupported.

A blocker reason explains a state transition; it is not a new state.

Discovery must skip issues carrying `agent-decision` or active `solve-in-progress`, and report them as pending review or already claimed.

## Workflow

### 1. Discover

Select candidate issues from explicit ids, `--all`, or the message. Keep only issues in `ready-for-agent`.

Report skipped issues with a short reason:

- wrong state
- has `agent-decision`
- has active `solve-in-progress`
- stale claim needing manual/resume handling

### 2. Claim

For every selected issue:

- determine the intended solve branch/worktree reference
- re-read the issue and confirm it is still `ready-for-agent` with no active `solve-in-progress` or `agent-decision`
- claim it by adding `solve-in-progress` and recording the intended branch/worktree through the tracker's existing machine-readable claim surface
- create the branch/worktree after the claim succeeds

Do this before code changes. For local markdown, preserve existing structured conventions such as `state`/`status`, `flags`/`labels`, and `branch`/`worktree`/`solve_branch`/`solve_worktree`. Batch or parallel solve requires a machine-readable claim surface. If no reliable claim surface exists, do not run unsafe batch claims; for an explicit single issue, proceed only when user intent is clear and report the claim limitation.

If branch/worktree creation fails after claiming, clear the claim when no resumable work exists. If resumable work exists, record a blocker reason and retain or clear `solve-in-progress` according to whether a human can resume from the linked branch/worktree.

### 3. Assess

For each claimed issue, read the issue body, acceptance criteria, comments, linked docs, and relevant repo context.

Classify it:

- `executable`: enough information exists or can be inferred.
- `needs exploration`: technical details are missing, but the codebase can likely answer them.
- `needs-info`: a core requirement cannot be inferred.
- `ready-for-human`: the issue is really an unapproved architecture/product/security decision.

If an issue becomes `needs-info` or `ready-for-human`, update its state, record the blocker reason, remove `solve-in-progress` unless resumable work is intentionally left active, and continue with the rest of the batch.

### 4. Group

Group executable issues by module, dependency, and likely file overlap.

- Same module or shared files: one group, serial execution.
- Independent modules: separate groups that may be executed in parallel when the runtime supports it.
- Shared migrations, config, generated types, routing, fixtures, dependency versions, or public contracts are coupling signals; group or order them conservatively.

### 4.5 Pre-Execute Gate (mandatory)

Before writing ANY implementation file, the coordinator must verify and report:

- [ ] Group worktree(s) created
- [ ] Group branch(es) created from the target branch when known, otherwise from the declared base HEAD
- [ ] Current working directory is the assigned group worktree, not the invocation checkout
- [ ] `git rev-parse --show-toplevel` equals the assigned group worktree path
- [ ] `git status --short --branch` shows the assigned group branch

Do not edit code, tests, docs, config, migrations, or generated artifacts until this gate passes.

If this gate fails, stop and create or enter the correct group worktree before continuing.

If delegating to a subagent, include the assigned worktree path and branch in the brief. The subagent must run the same gate before editing. If the runtime cannot guarantee the subagent's working directory, do not delegate implementation work; run it serially with tools explicitly pointed at the group worktree.

### 5. Execute Groups

Create one group worktree per group, based on the chosen target branch or the current branch when no merge is requested. Execute only after the Pre-Execute Gate passes for that group.

Suggested names:

- group branch: `solve/<timestamp>-<group-name>`
- group worktree: `worktree-solve-<timestamp>-<group-name>`

For each issue in a group:

1. Decide exploration scope:
   - file paths present: minimal read
   - module names present: narrow search
   - no technical context: broader code exploration
2. Choose execution route. These are optional routing heuristics, not mandatory skill calls:
   - simple clear fix: implement directly
   - unclear bug: prefer the debugging skill (`/ultra diagnosing-bugs`, or a configured alias) in AFK mode when a diagnosis loop would reduce risk
   - medium feature with clear AC: consider `/ultra tdd` in AFK mode when test-first development would help
   - approved refactor with clear AC: implement directly, or consider `/ultra tdd` when behavior coverage is needed
   - speculative architecture change: mark `ready-for-human`
   - docs/config-only issue: edit directly
3. Implement.
4. Verify each acceptance criterion.
5. Record validation evidence as a PR, commit, CI/check, tracker pointer, or final solve summary entry. Avoid putting run logs in issues.
6. Commit verified work to the group branch before leaving the group worktree.

Commit rules:

- Do not leave successful group work as dirty worktree changes. Integration consumes committed group branches, not uncommitted files.
- Split commits by issue, vertical slice, or coherent logical change when that makes review and rollback clearer.
- Keep tightly coupled code, tests, docs, and generated artifacts together when separating them would create broken intermediate commits.
- Avoid both extremes: do not collapse unrelated issues into one large commit, and do not split mechanical fragments so finely that the history stops explaining behavior.
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

Create one integration worktree from the latest target branch. The integration worktree is mandatory whenever more than one group exists or a merge/apply was requested; it is still recommended for a single non-trivial group.

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
- capture the current `base`, `base_sha`, `head`, `head_sha`, issue paths, worktree path, checks status, and validation evidence for solve record creation
- proceed to finalization before marking linked issues completed

If final validation fails:

- identify affected issues when possible
- set them `ready-for-human`
- record the blocker reason and a concise failing command summary or check-run link
- do not merge
- retain `solve-in-progress` only when the branch/worktree is intentionally left for a human to resume

If no meaningful automated check exists or the environment cannot run it, do not call that a pass. When the candidate is otherwise complete, finalization may create a solve record with checks marked `unavailable`; auto-merge remains blocked unless the change is explicitly trivial and low-risk, and the record says why no meaningful check exists, why no manual-review trigger applies, and what evidence still supports the change.

Do not create a solve record for failed required checks. Failed required checks keep work in issue/attempt blocker state, not in the maintainer-facing solve-record queue.

### 8.5 Finalize Solve Record

Create a solve record only after a finished, reviewable merge candidate exists:

- clean, comparable `head`
- known `base` and `head` refs
- recorded `base_sha` and `head_sha`
- linked issue paths
- checks status and validation evidence
- merge-gate disposition
- worktree and cleanup resource notes

Do not create solve records for claim-time state, in-progress attempts, missing requirements, failed required checks, or a human-required decision that prevents the candidate from being finished. If a finished candidate exists but needs human review before merge for product/API/security/data/architecture/rollout risk, create the record as `state: open` with `## Merge` set to `manual required`; do not auto-merge it.

Checks marked `unavailable` block auto-merge unless the change is explicitly trivial and low-risk, and the record says why no meaningful check exists, why no manual-review trigger applies, and what evidence still supports the change.

During the same finalize step:

- create the solve record in `.scratch/<feature>/solve-records/` or `.scratch/solve-records/`
- mark linked issues `completed`
- preserve `agent-decision` on completed low-risk decisions
- append only a solve-record backlink to each issue; do not duplicate record state in the issue
- link implementation and validation evidence where the tracker convention needs it
- remove `solve-in-progress`

The issue `completed` state means acceptance criteria are implemented and verified. The solve record `merged` state means the candidate entered the base branch. Cleanup status remains on the solve record.

### 9. Merge Solve Records If Requested

Merge only when the user explicitly asked to merge, apply, land, push, or equivalent.

The target branch must be explicit or safely inferred from tracker/project context. If ambiguous, ask before merging.

Route requested merge/apply/ship/land wording through the same solve-record gate used by `$solve-records`. Merge eligible records one by one, in dependency order. Explicit set wording such as `all ready records` may process the bounded set one record at a time, but ineligible records must be skipped with reasons. Do not silently merge dependencies unless the user explicitly approves the wider operation.

All record merge gates must pass:

1. No selected issue remains `needs-info`, `ready-for-human`, or pending human review for `agent-decision`.
2. Every group passed its local validation.
3. Every eligible group branch is committed and its worktree is clean.
4. The integration worktree started from the latest target branch and is clean after committed integration changes.
5. All eligible group branches are integrated and final validation passed.
6. No semantic conflict was force-resolved.
7. The solve record was re-read and live Git state still matches recorded `base_sha` and `head_sha`, or the record was revalidated before merge. A changed `head_sha` blocks merge until fresh validation updates the record. A changed `base_sha` may be revalidated only when the recorded base is an ancestor of the live base, the head still matches, preflight merge is clean, and checks are rerun or the unavailable-check low-risk exception is restated against the live base.
8. The record has no manual-review trigger, stale check, stale ref, missing dependency, or unavailable check without the low-risk exception evidence.

If merge succeeds, update the solve record as merged and attempt safe cleanup. If cleanup fails after the merge, do not roll back the code merge; keep the record merged with `cleanup_done: false` and report cleanup blockers.

If merge fails or conflicts before completion, abort the merge when possible, keep the solve record open, write `manual required` in the record, and do not clean up the candidate branch/worktree.

Do not show a full diff by default. Show the issue list, group branches, validation commands and results, pending blockers, and final target branch.

## Agent Decisions

When a decision is needed and impact is low, decide, implement, and record an Agent Decision Log in the issue or linked PR according to the tracker convention:

```markdown
## Agent Decision Log

**Date**: YYYY-MM-DD
**Problem**: The missing decision or ambiguity.
**Options**: Option A / Option B / Option C.
**Decision**: Chosen option.
**Reason**: Why this follows the issue, codebase, or existing conventions.
**Risk**: Why this is safe, or what should be reviewed later.
```

Decision handling:

- Low-risk, AC passes: `completed + agent-decision`.
- API, architecture, security, data, product semantics, or significant UX impact: `ready-for-human + agent-decision`.
- Cannot infer the core requirement: `needs-info` without `agent-decision`.

`ready-for-agent` must never mean "implemented but waiting for review".

## AFK Mode For Routed Skills

When routing to the debugging skill, `/ultra tdd`, or another skill:

- Treat the issue body, acceptance criteria, and agent brief as approved input.
- Do not block waiting for user confirmation.
- If a routed skill reaches an unanswerable decision, update only that issue to `ready-for-human` or `needs-info` and continue the batch.
- Do not let one blocked issue stop unrelated issues.

Architecture proposal skills such as `/ultra improve-codebase-architecture` are analysis-first. Do not silently execute speculative architecture work from solve.

## Upstream Issue Quality

Do not require `to-issues` to emit a dedicated `technical_context` field in v1. If an issue lacks technical detail, solve should infer what it can from the codebase. If missing context blocks completion, set `needs-info` with a blocker reason. If recurring issue-quality gaps appear, mention them in the final solve summary or an existing project issue-generation surface; do not require a new tracker schema.

This is a feedback loop, not a schema gate: `to-issues -> solve notices missing context -> solve reports the gap -> future issue generation improves`.

## Tracker Adapter Compatibility

Current mutation support is local markdown trackers. The conceptual contract for future remote tracker support is:

For local markdown, detect and preserve the repo's existing issue conventions. Existing structured fields may include frontmatter keys such as `state`/`status`, `flags`/`labels`, comments/notes, or branch/worktree links. Existing body-marker conventions may be read and preserved when they are already part of the tracker, but do not invent a new body-note schema for claims. Batch claims require a machine-readable claim surface.

- `list_ready_for_agent(filter)`
- `read_issue(issue_id)`
- `claim_issue(issue_id, branch, worktree)`
- `set_state(issue_id, state)`
- `add_flag(issue_id, flag)`
- `remove_flag(issue_id, flag)`
- `record_blocker(issue_id, reason, evidence_link_or_summary)`
- `record_agent_decision(issue_id, decision_log)`
- `link_change(issue_id, branch_or_worktree_or_commit_or_pr)`
- `link_validation(issue_id, command_or_check_run, status)`
- `close_completed(issue_id)`

Adapters must provide atomic or conflict-detecting claim behavior. If they cannot, solve must not run in batch mode against that tracker. Local markdown adapters may satisfy this by re-reading immediately before claim and detecting file changes before write.
