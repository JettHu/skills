# Ultra Solve Ticket-Boundary Model-Adherence Run

Date: 2026-07-13

## Scope And Model Settings

- Treatment refs: initial `f3eb12b`, then corrected `b5d8c4f`. The final
  stale-hint replay uses `95ca1ab`, which commits the constructor and grader
  used to create and grade that fixture.
- Fixture roots: `/tmp/ultra-model-adherence-20260713*`; each scenario had an independent Git repository, base tag, and candidate worktree.
- Prompt: the exact fixture prompt and evaluator supplements appear below. Each fresh session was told to read the embedded runbook and canonical receipt format, avoid merge/push/cleanup, and leave final state for grading.
- Successful fresh sessions: Codex Desktop GPT-5 default child sessions; no model override was supplied by the evaluator. The child-session service does not expose a model-id or reasoning setting, so this record does not infer one.
- One noninteractive retry: Codex CLI `0.144.1`, `gpt-5.6-terra`, `high` reasoning, approval `never`. It was resumed after terminal streaming interrupted its first pass and did not reach a complete receipt finalization.

This is real single-runtime model evidence, not a multi-model or multi-setting evaluation.

## Exact Prompt Material

Every fixture received this `EVAL_PROMPT.md` template, with the scenario's
Ticket path substituted for `<ticket>`:

```text
You are in a fresh test repository.

Use the embedded skill docs exactly as a user-invoked `/ultra solve` run.
Read `AGENTS.md`, `skills/engineering/ultra/SKILL.md`, and
`skills/engineering/ultra/solve.md` before acting.

Solve the requested ready-for-agent issue:

`/ultra solve <ticket>`

Do not merge, push, or clean up. Stop at the normal `/ultra solve`
completion point: a committed reviewable candidate plus solve record, unless
the issue must become `needs-info` or `ready-for-human`.
```

The evaluator then appended the following scenario-specific directives:

| Scenario | Exact evaluator supplement |
| --- | --- |
| Direct simple | `Read EVAL_PROMPT.md, AGENTS.md, skills/engineering/ultra/SKILL.md, skills/engineering/ultra/solve.md, and the linked canonical Solve Record format before acting. Execute the requested /ultra solve workflow. Create a valid outcome-aware candidate receipt from that format, commit the candidate, update the ticket, and validate. Do not merge/push/cleanup; work only there; do not change eval expectations.` |
| Digest-worthy / Pre-Edit | `Read EVAL_PROMPT.md, AGENTS.md, the embedded ultra docs, and linked canonical Solve Record format. Execute /ultra solve workflow; use adaptive fan-out/Pre-Edit review evidence in external Digest; valid current outcome-aware candidate receipt; commit+validate. Do not merge/push/cleanup, work only there, do not alter expectations.` |
| First deviation | `Read EVAL_PROMPT.md, AGENTS.md, embedded ultra docs, and linked canonical Solve Record format. Execute /ultra solve; handle explicit first compatibility deviation with an external Digest (not Ticket-body), distill it to a valid current candidate receipt, commit+validate. Do not merge/push/cleanup, work only there, do not alter expectations.` |
| Recovery | `Read EVAL_PROMPT.md, AGENTS.md, embedded ultra docs, and canonical Solve Record format. Execute the /ultra solve workflow. This is a human-owned public/security contract decision: do not invent implementation; route Ticket to ready-for-human and create a valid outcome-aware recovery receipt (not a candidate receipt) because the blocker has durable handoff value. Do not merge/push/cleanup; work only there, do not alter expectations.` |
| Stale hint retry | `Read EVAL_PROMPT.md plus skills/engineering/ultra/solve.md and its linked receipt format. Execute the ticket. The Brief Hint points to a deleted app/legacy_receipts.py: verify it is stale, modify the current receipt module, never create the forbidden path. Create valid outcome-aware candidate receipt, commit and run python3 scripts/check.py. Do not merge/push/cleanup/change eval fixtures. Then return.` |

## Grading Method

The grader inspected final repository state rather than response prose:

- `python3 skills/engineering/solve-records/scripts/solve-records.py dashboard --repo <fixture> --json`
- `python3 <candidate-worktree>/scripts/check.py`
- Ticket body, external Digest path, receipt frontmatter/body, live Git refs, candidate worktree cleanliness, and `git diff --check` where applicable.

The committed fixture constructor and grader are
`scripts/prepare-fixture.py` and `scripts/grade-run.py` beside this record;
both are included at treatment `95ca1ab`. The constructor is invoked with the
named treatment ref. The first-deviation fixture added an approved local
compatibility deviation before the session began; all changes were committed to
that fixture's `eval-base` before the model ran.

## Results

| Scenario | Ref | Final-state result | Grade |
| --- | --- | --- | --- |
| Direct simple execution and no Digest residue | `b5d8c4f` | Code check passed; Ticket completed with a path-only receipt backlink; no external Digest existed; helper classified a valid `outcome: candidate` receipt as `ready`. | Pass |
| Cross-module planning and Pre-Edit review | `b5d8c4f` | Digest held strategy, surfaces, risks, validation, and an incorporated review finding; Ticket stayed a Work Order; candidate receipt had valid live refs and passed helper gate. Capacity was unavailable for actual subagents, so the session used the documented serial two-lens fallback. | Pass with fallback |
| First compatibility deviation and handoff distillation | `b5d8c4f` | Session created an external Digest, distilled the decision into `## Notes`, and removed the non-resumable Digest. Ticket had no Digest section; candidate receipt passed the helper's live gate and the app check passed. Creation timing is supported by session evidence; final state intentionally retains no Digest. | Pass |
| Meaningful human-owned stop | `b5d8c4f` | Ticket became `ready-for-human` with `semantic_conflict`; no app files changed; a no-resource `outcome: ready-for-human` receipt with resume action was classified in `recovery`. | Pass |
| Stale Agent Brief hint (initial) | `b5d8c4f` | A fresh noninteractive session verified the deleted hint, changed the current receipt implementation, committed it, and the candidate worktree check passed. Terminal streaming interrupted before Ticket/receipt finalization, so no final-state candidate receipt was available to grade. | Historical incomplete — superseded by the final-head replay |
| Stale Agent Brief hint (final-head replay) | `95ca1ab` | A new fixture from the committed harness completed the Ticket and created a canonical candidate receipt. The committed grader passed all Ticket, receipt, dashboard, Git, deterministic-check, and forbidden-path assertions. | Pass — see [20260713-final-head-stale-hint.md](20260713-final-head-stale-hint.md) |

## Discovery And Correction

The first treatment (`f3eb12b`) completed the simple code change but created a legacy/hybrid receipt (`kind: candidate`) rather than the required `kind: solve_record` and `outcome: candidate` shape. That was a real adherence failure. It directly motivated `b5d8c4f`, which makes the runbook read the canonical receipt format immediately before either candidate or recovery finalization. The subsequent completed candidate and recovery sessions produced valid current-format receipts accepted by the helper.

## Interpretation

This run replaces the prior plan-only claim with actual model-session and
final-state evidence. The final-head replay closes the stale-hint scenario. It
does not prove true parallel fan-out or justify any cross-model claim; the
approved runbook permits the documented serial, capability-equivalent fallback
when subagent capacity is unavailable, so that fallback is not a remaining
candidate gate.
