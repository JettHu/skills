# Ultra Solve Ticket-Boundary Model-Adherence Run

Date: 2026-07-13

## Scope And Model Settings

- Treatment refs: initial `f3eb12b`, then corrected `b5d8c4f`.
- Fixture roots: `/tmp/ultra-model-adherence-20260713*`; each scenario had an independent Git repository, base tag, and candidate worktree.
- Prompt: the fixture's `EVAL_PROMPT.md` requested `/ultra solve <ticket>`, then each fresh session was additionally told to read the embedded runbook and canonical receipt format, avoid merge/push/cleanup, and leave final state for grading.
- Successful fresh sessions: Codex Desktop GPT-5 default child sessions; no model override was supplied by the evaluator. The child-session service does not expose a model-id or reasoning setting, so this record does not infer one.
- One noninteractive retry: Codex CLI `0.144.1`, `gpt-5.6-terra`, `high` reasoning, approval `never`. It was resumed after terminal streaming interrupted its first pass and did not reach a complete receipt finalization.

This is real single-runtime model evidence, not a multi-model or multi-setting evaluation.

## Grading Method

The grader inspected final repository state rather than response prose:

- `python3 skills/engineering/solve-records/scripts/solve-records.py dashboard --repo <fixture> --json`
- `python3 <candidate-worktree>/scripts/check.py`
- Ticket body, external Digest path, receipt frontmatter/body, live Git refs, candidate worktree cleanliness, and `git diff --check` where applicable.

The fixture constructor was the local AFK-safe planning harness at
`/Users/lingjie/workspace/jett-skills/.evals/ultra-solve-afk-safe-planning/scripts/prepare-fixture.py`, invoked with the named treatment ref. The first-deviation fixture added an approved local compatibility deviation before the session began; all changes were committed to that fixture's `eval-base` before the model ran.

## Results

| Scenario | Ref | Final-state result | Grade |
| --- | --- | --- | --- |
| Direct simple execution and no Digest residue | `b5d8c4f` | Code check passed; Ticket completed with a path-only receipt backlink; no external Digest existed; helper classified a valid `outcome: candidate` receipt as `ready`. | Pass |
| Cross-module planning and Pre-Edit review | `b5d8c4f` | Digest held strategy, surfaces, risks, validation, and an incorporated review finding; Ticket stayed a Work Order; candidate receipt had valid live refs and passed helper gate. Capacity was unavailable for actual subagents, so the session used the documented serial two-lens fallback. | Pass with fallback |
| First compatibility deviation and handoff distillation | `b5d8c4f` | Session created an external Digest, distilled the decision into `## Notes`, and removed the non-resumable Digest. Ticket had no Digest section; candidate receipt passed the helper's live gate and the app check passed. Creation timing is supported by session evidence; final state intentionally retains no Digest. | Pass |
| Meaningful human-owned stop | `b5d8c4f` | Ticket became `ready-for-human` with `semantic_conflict`; no app files changed; a no-resource `outcome: ready-for-human` receipt with resume action was classified in `recovery`. | Pass |
| Stale Agent Brief hint | `b5d8c4f` | A fresh noninteractive session verified the deleted hint, changed the current receipt implementation, committed it, and the candidate worktree check passed. Terminal streaming interrupted before Ticket/receipt finalization, so no final-state candidate receipt was available to grade. | Incomplete — do not count as a pass |

## Discovery And Correction

The first treatment (`f3eb12b`) completed the simple code change but created a legacy/hybrid receipt (`kind: candidate`) rather than the required `kind: solve_record` and `outcome: candidate` shape. That was a real adherence failure. It directly motivated `b5d8c4f`, which makes the runbook read the canonical receipt format immediately before either candidate or recovery finalization. The subsequent completed candidate and recovery sessions produced valid current-format receipts accepted by the helper.

## Interpretation

This run replaces the prior plan-only claim with actual model-session and final-state evidence. It does **not** close the stale-hint scenario or prove true parallel fan-out, and it does not justify any cross-model claim. The originating candidate therefore remains `manual required` until a fresh stale-hint finalization run (and, if required for stronger assurance, an available-capacity fan-out run) is graded.
