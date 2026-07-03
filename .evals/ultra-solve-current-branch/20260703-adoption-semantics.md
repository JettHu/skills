# Ultra Solve Adoption Semantics Validation

Date: 2026-07-03

## Scope

Issues:

- `.scratch/ultra-solve-current-branch/issues/02-add-ultra-solve-adoption-routing.md`
- `.scratch/ultra-solve-current-branch/issues/03-update-solve-record-candidate-landing-semantics.md`

Changed surfaces:

- `skills/engineering/ultra/solve.md`
- `skills/engineering/solve-records/SKILL.md`
- `skills/engineering/solve-records/references/record-format.md`

## Evidence Type

Deterministic fixture and repository validation.

No model adherence eval was run in this pass. The change affects model-facing runbook semantics, but there is no repo-local model-eval harness in this checkout. The follow-up fixture issue remains `.scratch/ultra-solve-current-branch/issues/04-add-adoption-fixtures-and-board-display.md`.

## Commands

- `scripts/validate-skills.sh` - passed
- `tests/solve-records.sh` - passed

## Notes

- The runbook now documents Agent-judged adoption routing, protected-baseline fallback, adoption declaration output, and adopted worktree entry gates.
- Solve-record wording now treats `head` as the candidate branch and `base` as the landing branch.
- Adoption record guidance marks user-owned adopted branches/worktrees as outside `$solve-records cleanup`.
