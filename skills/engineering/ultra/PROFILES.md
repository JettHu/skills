# Complementary Enhancement Profiles

This table is the durable ownership contract for profile-driven Ultra runs. The root Agent selects the declared disposition directly; it does not rediscover target ownership at runtime.

**Dispositions**: `target-native` = the target owns and schedules the stage; `ultra-additive` = Ultra may add the declared distinct goal when its trigger matches; `unavailable` = neither the target nor Ultra has a stage for that capability. A target-native stage is the sole pass for its evidence goal. Native delegation requirements remain intact and use a capability-equivalent serial pass when delegation is unavailable.

| Skill | Target-native ownership | Native delegation | Ultra-additive behavior | Objective trigger and distinct evidence goal | Code review |
|-------|-------------------------|-------------------|-------------------------|----------------------------------------------|-------------|
| improve-codebase-architecture | Exploration is `target-native` and unconditional: scope/hot-spot selection, glossary/ADR reading, organic architecture scan, and candidate discovery. Research and code review are `unavailable`. | The architecture scan uses target-native Explore delegation; run the same scan serially when delegation is unavailable. | Post-artifact review is `ultra-additive`. No Ultra pre-exploration. Independent reviewer Agent when delegation is available; root serial fallback only when delegation is unavailable. | Always review the produced candidate set once for risk exclusions, ADR alignment, and whether each proposed seam has repository evidence. This goal is distinct from discovering candidates. | unavailable |
| to-spec | Repository exploration is conditional `target-native`; the target runs it when current codebase understanding is absent. There is no target-native research or code-review stage. | Preserve any target-selected repository exploration; use a capability-equivalent serial pass when delegation is unavailable. | Independent code lens, external research, and fresh-context Spec review are conditional `ultra-additive`. | Add the code lens only when the Spec's requested change affects two or more subsystems, or a security/data boundary, and an independent dependency-and-validation-path pass supplies evidence distinct from the target's architecture understanding. Add research only for an unresolved source-verifiable external fact that directly determines the Spec. Review once only when the Spec is large, ambiguous, cross-system, or high-risk; verify outcome coverage and test seams. | unavailable |
| diagnosing-bugs | The red-capable feedback loop, reproduction, minimisation, hypotheses, instrumentation, fix, regression test, and cleanup are `target-native`. Initial exploration toward a theory is owned by that loop, not Ultra. | Preserve any target-selected execution or instrumentation delegation; use capability-equivalent serial work when delegation is unavailable. | Question-driven research and post-fix scope review are conditional `ultra-additive`. No Ultra pre-exploration before the feedback loop. | Research only after the running red-capable loop yields a concrete evidence-backed question whose answer is absent locally. After actual code changes, review once for symptom coverage, regression risk, and convention drift without repeating diagnosis. | ultra-additive |
| to-tickets | Context gathering and repository exploration are conditional `target-native`; drafting and blocker assignment are `target-native`. There is no target-native research or code-review stage. | Preserve any target-selected exploration; use a capability-equivalent serial pass when delegation is unavailable. | Independent code lens, exact-artifact review/repair, and publication/promotion are conditional or unconditional `ultra-additive` as declared here. | Add the code lens only when the source outcome spans two or more subsystems or a security/data boundary and a dependency/blocker-validation pass supplies distinct evidence. Research only when a source-verifiable external fact directly determines acceptance or a blocker. Always review the complete Ticket set once, repair derivable defects, re-review affected repairs, and publish/promote through the configured adapter. | unavailable |
| triage | Issue/PR gathering, repository exploration, redundancy/prior-rejection checks, claim verification, and recommendation are unconditional `target-native`. Research, review, and code review are `unavailable`. | Preserve target-native exploration and verification delegation; use capability-equivalent serial passes when delegation is unavailable. | No Ultra exploration or review. | No distinct additive evidence goal is declared. | unavailable |
| tdd | Seam agreement and the red-green vertical-slice loop are `target-native`. Exploration, research, and post-review are `unavailable`. | Preserve target-selected test/implementation execution; use capability-equivalent serial work when delegation is unavailable. | Proportional review after actual code changes is `ultra-additive`. | Review once for behavior at the agreed seam, regression risk, and repository conventions; do not repeat the red-green loop. | ultra-additive |
| prototype | Branch selection, prototype construction, state surfacing, capture, and decision recording are `target-native`. Exploration, review, and code review are `unavailable`. | Preserve target-selected implementation delegation; use capability-equivalent serial work when delegation is unavailable. | External research is conditional `ultra-additive`. | Research only when a named external convention or platform constraint would materially distinguish prototype variants and local evidence cannot answer it. | unavailable |
| grill-me | Interview and decision sharpening are `target-native`; exploration, research, review, and code review are `unavailable`. | Preserve the target's interactive sequence. | No Ultra addition. | Pass through. | unavailable |
| grill-with-docs | Interview, decision sharpening, and document updates are `target-native`; exploration, research, review, and code review are `unavailable`. | Preserve the target's interactive sequence. | No Ultra addition. | Pass through. | unavailable |
| handoff | Handoff synthesis is `target-native`; exploration, research, review, and code review are `unavailable`. | No delegation requirement. | No Ultra addition. | Pass through. | unavailable |

## Skill aliases

Resolve these aliases before profile lookup. Use the canonical profile for ultra behavior; when invoking the target skill, prefer the requested name only if it resolves to an available installed skill in the current runtime; otherwise use the canonical name.

| Requested name | Canonical profile | Notes |
|----------------|-------------------|-------|
| diagnose | diagnosing-bugs | Legacy/local name for Matt Pocock's debugging skill |
| write-a-skill | writing-great-skills | Legacy/local name for skill-writing guidance; pass through unless a profile is later added |

## Pre-target pass scheduling

An eligible Ultra-additive pre-target pass must complete before the target workflow and any target-native stage begins. Its result becomes input context for the target; it is not a parallel or post-target activity.

## Evidence-based context sufficiency

An eligible Ultra-additive stage may narrow or skip only when current, traceable evidence covers its declared goal: affected surfaces and contracts, material risks or dependencies, and a credible validation path. Evidence may be concise. Conversation length, message count, broad familiarity, a prior run, and stale or irrelevant discussion are never proxies for coverage.

| Scenario | Disposition |
|----------|-------------|
| A short current artifact names affected modules and contracts, material dependency risks, and an executable validation path | Mark that additive goal covered; skip it |
| A long prior discussion covers architecture but predates a changed contract and supplies no current validation path | Run the missing additive pass if its objective trigger matches |
| A detailed request names files but not cross-system dependencies or validation | Narrow an eligible additive pass to dependencies and validation |
| A target owns unconditional exploration | Run the target-native stage regardless of prior context |
| A conditional shaping target has no prior exploration, but no objective additive trigger matches | Let the target decide its native exploration; do not add Ultra exploration |

The profile rows above contain the complete normative target conditions and evidence
goals. Apply the evidence-sufficiency examples only to narrow or cover an eligible
goal; they never create another trigger or routing rule.
