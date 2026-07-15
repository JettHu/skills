---
name: ultra
description: Multi-agent enhancement wrapper for agent skills and ultra subcommands. Preserves target-native workflows and adds only profile-declared evidence passes, and supports /ultra solve for AFK-ready Ticket execution with outcome receipts. Use when user says "/ultra skill-name" or "/ultra solve", wants complementary analysis before a skill runs, wants distinct review after, or wants to execute ready-for-agent issues. Examples — /ultra to-spec, /ultra diagnosing-bugs, /ultra to-tickets, /ultra solve --all.
---

# Ultra

Wrap an agent skill with complementary enhancement. The target skill runs unmodified and owns its native exploration, research, review, code-review, and delegation. Ultra adds a stage only when the selected profile declares a distinct evidence goal.

## Usage

`/ultra <skill-name> [skill-args...]`

## Subcommands

If the first argument is `solve`, dispatch directly to the [solve.md](solve.md) ultra subcommand. `solve` has its own state machine outside [PROFILES.md](PROFILES.md).

## Runtime adaptivity

This skill is capability-oriented. The workflow describes outcomes; parenthetical hints describe the *capability needed*, not a specific tool. "Spawn agents" means "run exploration or review passes; use parallel subagents when available, otherwise serial passes."

If a named tool is unavailable, use the nearest equivalent workflow (serial passes, direct file reads, manual diff inspection) and state the substitution briefly. A missing specific tool is never by itself a blocker.

Fallback examples:
- Parallel exploration or review -> run the same passes serially with available read/search tools.
- Web-search agent -> use direct web-search/fetch tools when available; if unavailable and research is optional or low-value, state the skip.
- Team review -> run a manual two-lens review: completeness, then consistency.

Example runtime mappings, not requirements: `parallel codebase exploration` -> Agent tool with `subagent_type=Explore`; `with web search` -> Agent tool with `subagent_type=general-purpose`; multi-reviewer code review -> TeamCreate/TeamDelete.

## Workflow

### 0. Dispatch subcommands

If the first argument is `solve`, follow [solve.md](solve.md) and stop this wrapper workflow. `solve` has its own state machine outside profile-driven execution.

### 1. Look up the enhancement profile

Extract the target skill name from arguments. Look up its profile in [PROFILES.md](PROFILES.md).

Before lookup, resolve compatibility aliases from [PROFILES.md](PROFILES.md) `Skill aliases`. Use the canonical name for profile lookup. When invoking the target skill later, prefer the user's requested name only if it resolves to an available installed skill in the current runtime; otherwise invoke the canonical name. State the alias resolution briefly.

Project-local guidance from `AGENTS.md`, `CONTEXT.md`, ADRs, issue briefs, or tracker conventions should guide the actual run when present; profiles provide portable defaults.

If the skill has no profile or its Ultra additions are unavailable (grill-me, grill-with-docs, handoff), invoke it directly — no enhancement overhead.

For every native capability and possible Ultra addition, take the disposition directly from the profile: `target-native`, `ultra-additive`, or `unavailable`. Do not rediscover target ownership from the target runbook at runtime. Target-native stages remain owned by the target and run according to its instructions. Ultra-additive stages are eligible only under their declared trigger. Unavailable stages do not run.

Create a small stage ledger keyed by the profile's evidence goals. A goal may have only one owner and must run at most once. If a target-native stage and a possible Ultra stage would collect the same evidence, keep the target-native stage and suppress the Ultra stage. When the profile has `code_review: ultra-additive`, record the current HEAD commit SHA (`base_sha`) now. This is needed in step 5 to detect code changes produced by the target skill.

### 2. Context sufficiency check

Assess current task-relevant evidence against the selected profile's declared goal. Evidence is sufficient only when it is current, traceable to an approved artifact or repository observation, and covers all three dimensions needed by that goal:

1. affected surfaces and governing contracts;
2. material risks, dependencies, or unresolved facts;
3. a credible validation path for the requested outcome.

Short evidence that covers these dimensions can justify narrowing or skipping an eligible Ultra pass. Long discussion, message count, broad familiarity, a prior `/ultra` run, or the mere presence of a detailed request cannot. Stale or unrelated evidence does not cover a current goal.

**If the goal is evidence-complete**: Mark the eligible Ultra-additive stage `covered` in the stage ledger and do not run it. State which current evidence covers the declared goal.

**If the goal is partially covered**: Narrow the Ultra-additive stage to the missing dimensions only. State the covered and missing evidence.

**If the goal is not covered**: Run the eligible Ultra-additive stage at its declared scope.

This sufficiency check never suppresses an unconditional target-native stage. Conditional target-native stages remain governed by the target. Missing evidence in conversation context is not, by itself, a trigger for a conditional Ultra-additive pass; the profile's objective trigger must also match.

### 3. Pre-exploration (parallel agents, adaptive scope)

Run only eligible `ultra-additive` pre-target stages whose objective trigger matches and whose evidence goal is not already covered. Each pass returns a concise summary (under 500 words). These summaries become conversation context that the target skill benefits from naturally. Record the goal as completed so no later pass repeats it.

For conditionally exploring targets such as `to-spec` and `to-tickets`, absence of prior exploration is never enough to add an Ultra code pass. The profile must name an independent lens and an objective task condition that makes its evidence distinct from the target's optional exploration.

When cited `CONTEXT.md` or `docs/adr/` files are absent, use the nearest project docs, tracker context, or code context.

**When the profile declares an Ultra-additive code pass** — spawn only the lenses named by its evidence goal, up to two code-exploration agents:

- **Architecture agent** (parallel codebase exploration): Read CONTEXT.md, relevant ADRs, and the modules the task touches. Summarize the current architecture, key abstractions, relevant domain vocabulary, and patterns to follow.
- **Risk agent** (parallel codebase exploration): Identify affected files, cross-cutting dependencies, edge cases, breaking changes, and unexpected constraints.

These are default exploration roles, not a fixed taxonomy. For tasks with a clearer split, replace or narrow them while staying within the total pre-exploration cap.

**When the profile declares an Ultra-additive research pass** — spawn one additional agent only after its objective trigger matches:

- **Industry agent** (with web search): Search for how similar problems are solved elsewhere — established patterns, common pitfalls, design trade-offs. Focus on actionable insights, not surveys, and cite sources when available.

Within the total cap, adapt the exploration roles to the specific task — don't limit yourself to the default profile template. For example:
- A debugging task might benefit from a "similar bug patterns" search agent
- A `to-spec` task in an unfamiliar domain might need an external-API research agent
- An architecture task spanning multiple subsystems might need agents split by subsystem

Cap Ultra additions at 3 pre-exploration agents total. Target-native delegation is outside this cap and remains intact. If the runtime cannot delegate, execute the capability-equivalent stage serially; do not omit it or transfer its ownership to Ultra.

For `diagnosing-bugs`, invoke the target first so it can build and run its red-capable feedback loop. Research is unavailable until that loop produces a concrete evidence-backed question; only then may the profile's conditional Ultra research pass answer that question. Do not explore toward hypotheses before the target-owned loop exists.

### 4. Invoke the target skill

For `to-tickets`, first read and follow [Ticket Review Publication](references/ticket-review-publication.md) and the configured tracker extension. Pass the target the configured durable draft surface, representation, `review-pending` state, stable identities, and no-direct-ready rule. Route Local Markdown publication only through its declared operations, preferably through the bundled `scripts/ultra_tracker.py` facade; it delegates only to the declared owning helpers. If the facade is unavailable, use one explicit capability-equivalent direct-helper handoff before the operation begins and never repeat a completed operation. For GitHub or GitLab, use only the configured strategy. If the durable surface is unwritable, report the degradation; never substitute a strategy or manual transaction.

Invoke the target skill unmodified, passing through any remaining arguments (e.g., via Skill tool, or by reading its SKILL.md and following it directly). The conversation now has richer context from step 3 (or from existing conversation context if step 3 was skipped).

### 5. Post-review

**When the profile declares an Ultra-additive review** — run the declared distinct review goal after the skill completes, using these lenses only when they contribute to that goal:

- **Completeness reviewer**: Cross-reference the skill's output against pre-exploration findings (or conversation context). Flag only concrete omissions, especially *scope blindness* — issues or edge cases raised during exploration that the skill output silently dropped.
- **Consistency reviewer**: Check that the output uses correct domain vocabulary (CONTEXT.md), respects ADRs, and follows project conventions. Flag only real *convention drift* — patterns, naming, or structures that deviate without justification.

For canonical shaping targets `to-spec` and `to-tickets`, review the exact generated artifact on its configured durable surface. For `to-tickets`, route complete-set registration through the publication adapter and keep the set non-claimable during review. The fresh-context reviewer checks Spec coverage, canonical terminology, independent acceptance, context-window sizing, validation, source pointers, and true blocker edges. The main Agent fixes every derivable finding in those same artifacts, re-registers the repaired set, and re-runs affected review. Ask only for unresolved human-owned scope, product/API/data/security/architecture/significant-UX, ownership, release-policy, or missing-core-requirement choices.

For `to-tickets`, the main Agent then selects the configured promotion operation from [Ticket Review Publication](references/ticket-review-publication.md), accepts only its declared complete-set evidence, and stops on structured failure. Interrupted or cancelled runs remain durably resumable and non-claimable; only verified promotion yields `ready-for-agent`.

For other targets, present findings as a brief checklist of potential gaps. Do not auto-fix them through this generic review step.

**When `code_review: ultra-additive`** — only if the skill produced code changes:

If step 1 did not record `base_sha`, report that the change-detection baseline is missing and use the safest fixed point available (for example, an explicit user-supplied base or the current branch merge-base).

Check for changes using these read-only checks:

```bash
git diff <base_sha> HEAD --quiet 2>/dev/null &&
git diff --quiet &&
git diff --cached --quiet
```

This catches committed changes (`git diff <base_sha> HEAD`), unstaged changes (`git diff`), and staged changes (`git diff --cached`). If all three commands succeed (no changes at all), skip the review.

If changes exist, pin and report the review range before starting review. Prefer an explicit fixed point when the user supplied one; otherwise use `base_sha`. Pass reviewers the diff command, commit list, and any staged/uncommitted diff status so all review passes inspect the same change set.

Conduct a proportional, findings-first code review (e.g., via TeamCreate or parallel review passes). Treat these as internal review lenses, not mandatory output sections or a checklist to enumerate. Report real findings only. If there are no findings, give a short pass summary that names only the relevant axes. Include a no-op section such as "Dependencies: no impact" only when that fact is unusually important for the diff.

Primary axes to consider:

1. Spec: functional correctness, requirement coverage, missing/partial requirements, and scope creep against the originating issue, PRD, acceptance criteria, or user request
2. Standards: documented coding standards, project conventions, ADRs, nearby patterns, code quality, and naming

Supporting checks to apply only when relevant to the changed files or risk:

3. Side effects and regression risk
4. Test and validation coverage
5. Dependencies and compatibility

Each reviewer outputs findings independently. Consolidate with cross-review, tag each finding P0/P1/P2/P3. Apply P0 fixes. Present P1 for user decision. Defer P2+. Release review resources when done.
