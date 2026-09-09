---
name: ultra
description: Multi-agent enhancement wrapper for agent skills and ultra subcommands. Preserves target-native workflows and adds only profile-declared evidence passes, and supports /ultra solve for AFK-ready Ticket execution with outcome receipts. Use for an explicit /ultra invocation, an explicit Ultra wrapper delegation, or a request to add complementary analysis or distinct review to a named skill. Dispatch solve only when the user requests Ticket execution through Ultra; explaining Tickets or reviewing work is not a solve request.
---

# Ultra

Wrap an agent skill with complementary enhancement. The target skill runs unmodified and owns its native exploration, research, review, code-review, and delegation. Ultra adds a stage only when the selected profile declares a distinct evidence goal.

## Usage

`/ultra <skill-name> [skill-args...]`

## Subcommands

If the first argument is `solve`, dispatch directly to the [solve.md](solve.md) ultra subcommand. `solve` has its own state machine outside [PROFILES.md](PROFILES.md).

## Runtime adaptivity

This skill is capability-oriented. The workflow describes outcomes; parenthetical hints describe the *capability needed*, not a specific tool. "Spawn agents" means delegate exploration or review passes when the runtime offers delegation, running independent passes in parallel when useful or ordered passes serially. If the runtime offers no delegation, the root Agent executes the capability-equivalent passes serially.

Delegation availability and parallel scheduling are separate. A pass may use a delegated Agent even when it must run serially. When a declared review goal requires an independent lens, available delegation cannot be replaced by root self-review.

If a named tool is unavailable, use the nearest equivalent workflow (serial passes, direct file reads, manual diff inspection) and state the substitution briefly. A missing specific tool is never by itself a blocker.

Fallback examples:
- Parallel exploration or review -> delegate the same passes serially when delegation is available; use root read/search tools only when delegation is unavailable.
- Web-search agent -> use direct web-search/fetch tools when available; if unavailable and research is optional or low-value, state the skip.
- Team review -> use one independent reviewer Agent for the required lenses; only without delegation, run a manual root two-lens review: completeness, then consistency.

Example runtime mappings, not requirements: `parallel codebase exploration` -> Agent tool with `subagent_type=Explore`; `with web search` -> Agent tool with `subagent_type=general-purpose`; multi-reviewer code review -> TeamCreate/TeamDelete.

## Workflow

### 0. Dispatch subcommands

If the first argument is `solve`, follow [solve.md](solve.md) and stop this wrapper workflow. `solve` has its own state machine outside profile-driven execution.

### 1. Look up the enhancement profile

Extract the target skill name from arguments. Look up its profile in [PROFILES.md](PROFILES.md).

Before lookup, resolve compatibility aliases using [PROFILES.md](PROFILES.md) `Skill aliases`, including its installed-target and missing-dependency rules. Use the canonical name for profile lookup and report the selected installed target.

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

Run only eligible `ultra-additive` pre-target stages whose objective trigger matches and whose evidence goal is not already covered. Each eligible pre-target pass must complete before the target workflow and any target-native stage begins; its result becomes input context for the target. Each pass returns a concise summary (under 500 words). These summaries become conversation context that the target skill benefits from naturally. Record the goal as completed so no later pass repeats it.

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

For `to-tickets`, first read and follow [Ticket Review Publication](references/ticket-review-publication.md), the shared tracker index, and its selected adapter capability document before handling the durable artifact. Pass the target the configured draft surface, representation, review-pending state, stable identities, source-pointer and blocker fields, and no-direct-ready rule. The reference's **Context Pointer Contract** makes `to-tickets` the sole producer of actionable execution pointers; this wrapper dispatches the target and does not define a second shaping workflow. Use the operations declared by the selected capability document and stop on their structured failure; Route Local Markdown publication only through its declared operations: route complete-set registration through the publication adapter. Do not create a second publication workflow here.

Invoke the target skill unmodified, passing through any remaining arguments (e.g., via Skill tool, or by reading its SKILL.md and following it directly). The conversation now has richer context from step 3 (or from existing conversation context if step 3 was skipped).

### 5. Post-review

**When the profile declares an Ultra-additive review** — run the declared distinct review goal after the skill completes, using these lenses only when they contribute to that goal:

When delegation is available, assign every Ultra-additive post-review to an independent reviewer Agent and consume its returned findings. Root self-review does not complete that stage. Only when delegation is unavailable may the root Agent run the same review lenses serially; record that capability fallback before reporting the review complete.

- **Completeness reviewer**: Cross-reference the skill's output against pre-exploration findings (or conversation context). Flag only concrete omissions, especially *scope blindness* — issues or edge cases raised during exploration that the skill output silently dropped.
- **Consistency reviewer**: Check that the output uses correct domain vocabulary (CONTEXT.md), respects ADRs, and follows project conventions. Flag only real *convention drift* — patterns, naming, or structures that deviate without justification.

For canonical shaping targets `to-spec` and `to-tickets`, review the exact generated artifact on its configured durable surface. For `to-tickets`, the publication reference owns complete-set registration and promotion. The fresh-context reviewer checks Spec coverage, canonical terminology, independent acceptance, context-window sizing, validation, source pointers, and true blocker edges when those are the profile-declared evidence goal. The main Agent fixes every derivable finding in those same artifacts, re-registers the repaired set, and re-runs affected review, then consumes the result according to that target's repair rules. Ask only for unresolved human-owned scope, product/API/data/security/architecture/significant-UX, ownership, release-policy, or missing-core-requirement choices.

For `to-tickets`, the main Agent then selects the configured promotion operation from [Ticket Review Publication](references/ticket-review-publication.md), accepts only its declared complete-set evidence, and stops on structured failure. Interrupted or cancelled runs remain durably resumable and non-claimable; only verified promotion yields `ready-for-agent`.

For other targets, the generic reviewer remains read-only and returns concrete findings to the coordinator. The coordinator completes the original request according to its authorization:

- **Implementation request**: repair findings within the requested scope whose resolution follows from authoritative requirements and repository evidence. Run the affected validation and return the changed scope to the selected review owner when needed to resolve its findings. Finish when the requested outcome and required checks are satisfied, or report the precise unresolved finding, unavailable evidence, or human-owned choice. Repair does not authorize merge, push, deployment, or unrelated changes.
- **Review-only request**: report findings without modifying the reviewed artifacts. Review findings do not grant implementation authority.
- **Human-owned choice**: ask for unresolved product, API, data, security, architecture, significant UX, ownership, or release-policy decisions; continue independent authorized work. Do not invent such decisions to close findings.

Use the same completion rules when consuming code-review findings below. Target-native review retains its ownership; consume existing evidence for the same goal instead of adding another equivalent review.

**When `code_review: ultra-additive`** — only if the skill produced code changes:

If step 1 did not record `base_sha`, report that the change-detection baseline is missing and use the safest fixed point available (for example, an explicit user-supplied base or the current branch merge-base).

Check for changes using these read-only checks:

```bash
git diff <base_sha> HEAD --quiet 2>/dev/null &&
git diff --quiet &&
git diff --cached --quiet
```

This catches committed changes (`git diff <base_sha> HEAD`), unstaged changes (`git diff`), and staged changes (`git diff --cached`). If all three commands succeed (no changes at all), skip the review.

If changes exist, pin and report the review range before starting review. Prefer an explicit fixed point when the user supplied one; otherwise use `base_sha`. Pass the fixed range to the selected reviewer so it inspects the same change set.

Conduct a proportional, findings-first review through the selected target-native or Ultra reviewer. Keep the review read-only and report concrete findings only. The selected review owner defines its detailed axes and output format; Ultra only consumes the result, applies its repairability and decision-ownership rules, and releases review resources when done.
