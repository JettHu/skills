---
name: ultra
description: Multi-agent enhancement wrapper for agent skills and ultra subcommands. Adds parallel codebase exploration before and structured review after skill execution, and supports /ultra solve for AFK-ready issue execution. Use when user says "/ultra skill-name" or "/ultra solve", wants deeper analysis before a skill runs, wants multi-perspective review after, or wants to execute ready-for-agent issues. Examples — /ultra to-prd, /ultra diagnosing-bugs, /ultra to-issues, /ultra solve --all.
---

# Ultra

Wrap an agent skill with adaptive pre-exploration and post-review. The target skill runs unmodified — ultra adds richer context before it and validation after.

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

If the skill has no profile or all flags are off (grill-me, grill-with-docs, handoff), invoke it directly — no enhancement overhead.

If the profile has `code_review: true`, record the current HEAD commit SHA (`base_sha`) now. This is needed in step 5 to detect code changes produced by the target skill.

### 2. Context sufficiency check

Before spawning exploration agents, assess whether the current conversation already contains sufficient context for the task:

- Has the user already discussed the relevant code areas in this conversation?
- Are there recent exploration results in context that cover the target modules?
- Has the user provided detailed requirements that reduce ambiguity?

**If context is already sufficient**: Skip pre-exploration entirely and proceed to step 4 (invoke the target skill). State briefly why you're skipping (e.g., "Skipping pre-exploration — the conversation already covers the review_status code path in detail").

**If context is partially sufficient**: Narrow the exploration scope. Only spawn agents for the dimensions the profile enables *and* that are actually lacking from context. State what you're spawning and why, and what you're omitting and why. For example: "Architecture is covered in context; spawning only Industry agent for batch-operation patterns."

**If context is insufficient**: Proceed with full pre-exploration per the profile.

**Safety rule**: Default to exploration until *specific* prior messages or explore results prove the target area is already covered. A redundant exploration costs tokens; a skipped necessary exploration costs quality.

### 3. Pre-exploration (parallel agents, adaptive scope)

Spawn agents based on the profile flags AND the context sufficiency assessment AND the profile's task-specific rationale. Each agent returns a concise summary (under 500 words). These summaries become conversation context that the target skill benefits from naturally.

**Profile flag semantics**: `yes` = enabled by default. `cond` = disabled unless the profile's override conditions match (see PROFILES.md). `—` = unavailable.

**Task-specific narrowing**: The profile's Rationale column may specify conditions under which certain modules should be narrowed even when context is insufficient. For example, the to-prd profile defaults to code-only for known-codebase PRDs; research and review are enabled only for specific conditions (unfamiliar domain, external API standards, high-risk changes). Apply these task-specific rules before spawning agents.

When cited `CONTEXT.md` or `docs/adr/` files are absent, use the nearest project docs, tracker context, or code context.

**When `code: true`** — by default, spawn up to two code-exploration agents:

- **Architecture agent** (parallel codebase exploration): Read CONTEXT.md, relevant ADRs, and the modules the task touches. Summarize the current architecture, key abstractions, relevant domain vocabulary, and patterns to follow.
- **Risk agent** (parallel codebase exploration): Identify affected files, cross-cutting dependencies, edge cases, breaking changes, and unexpected constraints.

These are default exploration roles, not a fixed taxonomy. For tasks with a clearer split, replace or narrow them while staying within the total pre-exploration cap.

**When `research: true`** — spawn one additional agent:

- **Industry agent** (with web search): Search for how similar problems are solved elsewhere — established patterns, common pitfalls, design trade-offs. Focus on actionable insights, not surveys, and cite sources when available.

Within the total cap, adapt the exploration roles to the specific task — don't limit yourself to the default profile template. For example:
- A debugging task might benefit from a "similar bug patterns" search agent
- A to-prd task in an unfamiliar domain might need a "competitor analysis" agent
- An architecture task spanning multiple subsystems might need agents split by subsystem

Cap at 3 pre-exploration agents total. Run them in parallel when available; otherwise run the same passes serially.

### 4. Invoke the target skill

Invoke the target skill unmodified, passing through any remaining arguments (e.g., via Skill tool, or by reading its SKILL.md and following it directly). The conversation now has richer context from step 3 (or from existing conversation context if step 3 was skipped).

### 5. Post-review

**When `review: true`** — run two review passes after the skill completes, in parallel when available:

- **Completeness reviewer**: Cross-reference the skill's output against pre-exploration findings (or conversation context). Flag only concrete omissions, especially *scope blindness* — issues or edge cases raised during exploration that the skill output silently dropped.
- **Consistency reviewer**: Check that the output uses correct domain vocabulary (CONTEXT.md), respects ADRs, and follows project conventions. Flag only real *convention drift* — patterns, naming, or structures that deviate without justification.

Present findings as a brief checklist of potential gaps. Don't auto-fix — let the user decide.

**When `code_review: true`** — only if the skill produced code changes:

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
