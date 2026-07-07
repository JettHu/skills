# Solve Records Readiness Gates Validation

Date: 2026-07-07

## Scope

- `.scratch/solve-records-v1/issues/03-require-rollout-config-gate-before-merge.md`
- `.scratch/solve-records-v1/issues/04-clarify-acceptance-review-ready-transition.md`

## Evidence Type

Deterministic fixture.

## What Changed

- `$solve-records` merge readiness now requires body-prose rollout/config disposition before a record is treated as ready.
- `/ultra solve` finalization now records rollout/config/operator-action disposition before creating an auto-mergeable record.
- `$solve-records` documents acceptance review as a readiness transition distinct from merge/ship/land.
- Exact-path acceptance review guidance avoids redundant selector helper calls and keeps `state: open`.

## Fixture Coverage

- Config/rollout signal with missing disposition stays manual.
- `pre-merge action required` stays manual.
- `post-merge activation required` remains mergeable only with code-safety, activation, smoke/validation, and rollback notes.
- Exact-path acceptance review updates only `## Merge` to `Status: ready`, keeps frontmatter `state: open`, and does not trigger cleanup.
- Acceptance review keeps `manual required` when a real rollout/config pre-merge trigger remains.
- Landing fixtures include the required rollout/config disposition and still pass existing dirty-base and hard-stop checks.

## Commands

- `tests/solve-records.sh` - passed
- `scripts/validate-skills.sh` - passed
- `git diff --check` - passed

## Model Eval

No model adherence eval was run in this pass. There is no repo-local model-eval harness in this checkout; the change is backed by deterministic helper behavior and temp-repo fixtures that grade final record, gate, and Git state.
