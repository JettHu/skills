# Ultra Solve Adoption Model-Run Follow-Up

Date: 2026-07-06

## Scope

Existing model-run reports reviewed:

- `.evals/ultra-solve-current-branch/model-runs/20260703-103802-MiniMax-M3-default-uzqjr/REPORT.md`
- `.evals/ultra-solve-current-branch/model-runs/20260703-183617-Qwen3.7-Plus-high-k4m9/REPORT.md`
- `.evals/ultra-solve-current-branch/model-runs/20260703-143000-Qwen3.7-Max-DogFooding-high-a7k2m/REPORT.md`
- `.evals/ultra-solve-current-branch/model-runs/20260703-183556-DeepSeek-V4-Flash-max-a7b3/REPORT.md`

Changed surface:

- `skills/engineering/ultra/solve.md`

## Evidence Type

Model adherence eval review plus deterministic repository validation. No new model run was executed in this pass; this record summarizes the follow-up from the four existing reports.

## Findings

- All four reports chose the documented top-level routes for the five scenarios: prepared dev branch adoption, protected-baseline isolation, dirty-overlap isolation, merge into the landing branch, and no cleanup of user-owned adopted resources.
- The repeated ambiguity was positive identification of a "safely indicated prepared development branch"; models inferred this from branch names, commits, issue paths, clean status, and missing claim conflicts.
- The strongest behavioral variance was isolated worktree creation from a protected baseline when another apparently related feature branch exists. The previous wording allowed models to treat a merely visible branch as a "better base" too easily.
- One report also conflated the isolated worktree creation starting point with the solve record `base` field. This risk comes from using "base" for both the `git worktree add` starting ref and the solve record landing branch.

## Follow-Up Change

- Replaced worktree-creation "base ref" wording in `/ultra solve` with `branch-from ref`, keeping solve record `base` reserved for the landing branch.
- Added a positive but non-mechanical description of prepared development branch signals, including the boundary that name similarity alone is not enough.
- Clarified protected-baseline fallback: default the branch-from ref to the current baseline or HEAD unless user, tracker, Codex App setup, or stack topology clearly identifies another integration branch.
- Stated that branch-from ref is only the `git worktree add` starting point and is not necessarily the solve record `base`.
- Added compact adoption declaration shape and a short `adopted-integration` parallel-group example.

## Commands

- `git diff --check -- skills/engineering/ultra/solve.md` - passed
- `git diff --check` - passed
- `scripts/validate-skills.sh` - passed
