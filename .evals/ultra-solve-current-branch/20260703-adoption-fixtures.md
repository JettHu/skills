# Ultra Solve Adoption Fixtures Validation

Date: 2026-07-03

## Scope

Issue:

- `.scratch/ultra-solve-current-branch/issues/04-add-adoption-fixtures-and-board-display.md`

Changed surfaces:

- `skills/engineering/solve-records/scripts/solve-records.py`
- `skills/in-progress/maintainer-board/scripts/maintainer-board.py`
- `tests/solve-records.sh`
- `tests/maintainer-board.sh`

## Evidence Type

Deterministic fixture and repository validation.

No model adherence eval was run. This slice adds deterministic Git/record fixtures and board display calibration for the adoption model; it does not change the `/ultra solve` model-facing runbook beyond the already-recorded adoption semantics slice.

## Commands

- `tests/solve-records.sh` - passed
- `bash tests/maintainer-board.sh` - passed
- `scripts/validate-skills.sh` - passed
- `python3 -m py_compile skills/engineering/solve-records/scripts/solve-records.py skills/in-progress/maintainer-board/scripts/maintainer-board.py` - passed
- `git diff --check` - passed

## Fixture Coverage

- Default isolated solve record still uses a `solve/` candidate branch.
- Adopted current branch record uses the prepared development branch as `head` without creating a nested issue-named candidate branch.
- Protected baseline fallback uses an isolated `solve/` candidate branch.
- Temporary group branches are merged into an adopted integration branch used as the candidate.
- Adopted cleanup records with user-owned resources are reported as done, not cleanup targets.
- Development-validation-pending records remain manual-required while linked issues are completed.
- Maintainer board JSON and HTML show landing branch, candidate branch, and cleanup ownership for adoption records.
