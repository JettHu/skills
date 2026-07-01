# Jett Skills Agent Guidance

This repository is a skill catalog. Keep skill directories lean, keep reusable validation evidence durable, and avoid turning heavy model evals into default CI.

## Source Of Truth

- Installable skills live under `skills/<category>/<skill-name>/`.
- Repository checks live under `scripts/` and `tests/`.
- `.scratch/` is local issue and design working state; it is not committed by default.
- `.evals/` stores durable validation and eval records that should survive beyond a single chat session.

## Validation Policy

Run deterministic tests for ordinary skill edits:

- `scripts/validate-skills.sh` for skill metadata, references, and bundled shell scripts.
- Skill-specific fixtures under `tests/` for behavior that can be checked with local files and Git state.
- Installer discovery, such as `npx --yes skills@latest add . --list --full-depth`, when trigger wording or manifests change.

Model evals are heavier adherence checks, not default CI. Run them only when explicitly requested by the user or when a change materially affects model behavior, such as core `ultra` routing, enhancement profiles, multi-agent orchestration, merge safety policy, or solve-record finalization semantics.

For small wrapper wording, README, manifest, deterministic fixture, or eval-record documentation changes, prefer local tests and skip model evals unless the user asks.

## Eval Records

When validation work is substantial, write a short durable record under `.evals/<skill-or-feature>/`.

Distinguish these evidence types clearly:

- Deterministic fixture: local shell/Python/Git checks with reproducible assertions.
- Model adherence eval: one or more real model runs through realistic prompts, graded by final repo state rather than response prose.
- Ablation: a comparison showing which guard or instruction is load-bearing.

An eval should be executable by one Agent session end to end: create isolated temporary repos or worktrees, run the skill through realistic prompts, and grade final files, issue state, Git refs, solve records, and cleanup effects. Do not claim a multi-model or multi-thinking eval was run unless there is an accompanying `.evals/` record with the tested models, settings, prompts, and grader results.

## Ultra And Solve Records

The `ultra-*` skills are thin wrapper entrypoints. Keep them explicit and delegation-only; put orchestration behavior in `skills/engineering/ultra/`.

`/ultra solve` creates solve records only after finished, reviewable candidates exist. Failed required checks do not create initial solve records. `$solve-records` owns listing, explaining, merge/ship/land gates, record-only closure, and safe cleanup semantics.
