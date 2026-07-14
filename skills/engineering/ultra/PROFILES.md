# Enhancement Profiles

Each profile controls which ultra steps are **available by default** for a target skill. The context sufficiency check (SKILL.md step 2) may skip or narrow these steps if the conversation already provides sufficient context.

**Legend**: `yes` = enabled by default. `cond` = available only when specific conditions are met (see overrides below). `—` = unavailable.

| Skill | code | research | review | code_review | Rationale |
|-------|:----:|:--------:|:------:|:-----------:|-----------|
| improve-codebase-architecture | yes | — | yes | — | Code exploration grounds candidates; review validates safety (risk exclusion + ADR alignment). External research is usually unnecessary for repo-specific architecture work. |
| to-spec | yes | cond | cond | — | **Default: code-only.** Explore current architecture and risks; add external research only when approved local context cannot settle the stated external fact, and fresh-context review only for the stated high-risk boundaries. |
| diagnosing-bugs | yes | yes | yes | yes | Review catches scope blindness + convention drift; critical for analytical debugging tasks |
| to-tickets | yes | cond | yes | — | Code grounds acceptance criteria and blocker edges. Fresh-context review repairs the exact Ticket set; research is limited to unresolved source-verifiable facts that directly determine an acceptance criterion or blocker edge. |
| triage | yes | — | — | — | Parallel context gathering speeds up reproduce + recommend |
| tdd | — | — | — | yes | TDD self-validates during execution; code review catches what tests miss |
| prototype | — | yes | — | — | Industry research informs design alternatives |
| grill-me | — | — | — | — | 1:1 interactive — pass through |
| grill-with-docs | — | — | — | — | 1:1 interactive — pass through |
| handoff | — | — | — | — | Lightweight synthesis — pass through |

## Skill aliases

Resolve these aliases before profile lookup. Use the canonical profile for ultra behavior; when invoking the target skill, prefer the requested name only if it resolves to an available installed skill in the current runtime; otherwise use the canonical name.

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

### to-spec overrides

Default: **Code-only** (architecture + risk agents only).

Add modules only when specific conditions are met:

**Add Research when:**
- An unfamiliar external API, standard, or security requirement affects the Spec and approved local context cannot settle it
- The user explicitly requests external research and approved local context is insufficient

**Add Review when:**
- The Spec is large, ambiguous, cross-system, or high-risk

### to-tickets overrides

Default: **Code exploration plus fresh-context review**.

**Add Research only when:**
- A source-verifiable external fact directly determines an acceptance criterion or blocker edge
- Approved local context cannot settle that fact

Use research for official platform limits, SDK behavior, standards, or compatibility requirements. Keep product semantics, architecture direction, data/security policy, ownership, and release policy with approved input or an explicit human decision; do not use research for generic decomposition frameworks or unrelated open-source examples.
