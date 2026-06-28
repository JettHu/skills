# Enhancement Profiles

Each profile controls which ultra steps are **available by default** for a target skill. The context sufficiency check (SKILL.md step 2) may skip or narrow these steps if the conversation already provides sufficient context.

**Legend**: `yes` = enabled by default. `cond` = available only when specific conditions are met (see overrides below). `—` = unavailable.

| Skill | code | research | review | code_review | Rationale |
|-------|:----:|:--------:|:------:|:-----------:|-----------|
| improve-codebase-architecture | yes | — | yes | — | Code exploration grounds candidates; review validates safety (risk exclusion + ADR alignment). External research is usually unnecessary for repo-specific architecture work. |
| to-prd | yes | cond | cond | — | **Default: code-only.** Internal validation found that research/review did not improve known-codebase PRD quality enough to justify the token cost. Enable research only for unfamiliar domains / external API standards. Enable review only for high-risk changes or when pre-exploration surfaces major disagreements. |
| diagnosing-bugs | yes | yes | yes | yes | Review catches scope blindness + convention drift; critical for analytical debugging tasks |
| to-issues | yes | yes | yes | — | Research provides decomposition frameworks for complex PRDs; code grounds them |
| triage | yes | — | — | — | Parallel context gathering speeds up reproduce + recommend |
| tdd | — | — | — | yes | TDD self-validates during execution; code review catches what tests miss |
| prototype | — | yes | — | — | Industry research informs design alternatives |
| grill-me | — | — | — | — | 1:1 interactive — pass through |
| grill-with-docs | — | — | — | — | 1:1 interactive — pass through |
| handoff | — | — | — | — | Lightweight synthesis — pass through |

## Skill aliases

Resolve these aliases before profile lookup. Use the canonical profile for ultra behavior; when invoking the target skill, prefer the requested name if it exists locally, otherwise use the canonical name.

| Requested name | Canonical profile | Notes |
|----------------|-------------------|-------|
| diagnose | diagnosing-bugs | Legacy/local name for Matt Pocock's debugging skill |
| write-a-skill | writing-great-skills | Legacy/local name for skill-writing guidance; pass through unless a profile is later added |

## When to skip or narrow pre-exploration

The profile is a **maximum** — step 2 (context sufficiency check) decides the actual scope. Examples:

| Scenario | Skip/Narrow |
|----------|-------------|
| User has been discussing the code area for 20+ messages | Skip code exploration; architecture is already in context |
| A previous `/ultra` run in this conversation explored the same area | Skip code; keep research if the task angle is different |
| User provided a detailed spec with file paths and acceptance criteria | Skip code; may still benefit from research |
| Task is in a completely unfamiliar area | Full exploration per profile |
| Debugging task where the user already traced the code path | Skip architecture; keep risk agent for edge cases |

### to-prd overrides

Default: **Code-only** (architecture + risk agents only).

Internal validation found that research/review did not improve known-codebase PRD quality enough to justify the token cost. Add modules only when specific conditions are met:

**Add Research when:**
- The domain or external convention is unfamiliar and not inferable from repo context
- External API, security, or industry conventions matter (e.g., OAuth, PCI-DSS, AIP standards)
- The user explicitly asks for market, product, or competitor context
- The PRD involves integrating a third-party service with no prior internal precedent

**Add Review when:**
- The PRD is large, ambiguous, or spans multiple subsystems
- Code exploration surfaced conflicting patterns or convention drift
- Implementation risk is high (data migration, breaking API changes, security-critical)

## Suggested agent briefs

These briefs are starting points, not mandatory prompts. Preserve the intent, evidence requirements, and concise output budget, but adapt wording, roles, and exploration split to the task and runtime.

If referenced files such as `CONTEXT.md` or `docs/adr/` do not exist, use the nearest project docs, issue tracker context, or code context instead.

### Architecture agent (code)

> You are exploring a codebase to provide architectural context for an upcoming task.
>
> Task context: {user's task description}
>
> 1. Read CONTEXT.md and any relevant docs/adr/ files
> 2. Explore the modules and files most relevant to this task
> 3. Summarize in under 500 words:
>    - Current architecture in the relevant area
>    - Key abstractions and their responsibilities
>    - Domain vocabulary from CONTEXT.md that applies
>    - Existing patterns the task should follow

### Risk agent (code)

> You are scanning a codebase for risks and dependencies related to an upcoming task.
>
> Task context: {user's task description}
>
> 1. Identify all files and modules that could be affected
> 2. Look for cross-cutting concerns (shared state, event handlers, middleware)
> 3. Summarize in under 500 words:
>    - Files likely to need changes
>    - Dependencies and coupling points
>    - Edge cases and potential breaking changes
>    - Anything surprising that the task owner should know

### Industry agent (research)

> Research how similar problems are solved in the industry.
>
> Task context: {user's task description}
>
> Search for established patterns, common pitfalls, and proven approaches.
> Focus on actionable insights — not comprehensive literature reviews.
> Summarize in under 500 words with source links where available.

### Completeness reviewer (review)

> Review this output for completeness.
>
> Pre-exploration findings: {summaries from step 2, or "skipped — context was already sufficient"}
> Skill output: {output from step 3}
>
> Check: does the output address everything the pre-exploration (or conversation context) surfaced?
> List specific gaps as a checklist. Be concise — flag only genuine omissions.

### Consistency reviewer (review)

> Review this output for consistency with project conventions.
>
> Check against: CONTEXT.md domain vocabulary, docs/adr/ decisions, and existing codebase patterns.
> List specific inconsistencies. Be concise — flag only real conflicts.
