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
