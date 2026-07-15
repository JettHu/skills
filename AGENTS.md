# Jett Skills Agent Guidance

This repository is a skill catalog. Keep skill directories lean, keep reusable validation evidence durable, and avoid turning heavy model evals into default CI.

## Source Of Truth

- Installable skills live under `skills/<category>/<skill-name>/`.
- Repository checks live under `scripts/` and `tests/`; reusable model-eval harnesses live under `tests/evals/`.
- `.scratch/` is local issue and design working state; it is not committed by default.
- `.evals/` stores local model-run evidence that should survive beyond a single chat session without becoming catalog content or a CI dependency.

## Catalog Buckets And Promotion

- `skills/engineering/` is the promoted bucket for stable, broadly reusable engineering skills.
- `skills/personal/` is for local setup or personal workflow skills. It may be exposed through the personal marketplace plugin, but it is not part of the promoted engineering set.
- `skills/in-progress/` is for drafts. Do not add in-progress skills to the promoted plugin entry, top-level stable README table, or future human docs until they are promoted.
- A skill is stable enough to promote only when its invocation mode is explicit, trigger wording is settled, the workflow is repeatable, the resource layout is lean, side-effecting behavior has deterministic validation or a durable eval record, and installer discovery has been checked when manifests or trigger wording changed.
- Promoting a skill into `engineering/` requires syncing the top-level `README.md`, `skills/engineering/README.md`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and the skill's `agents/openai.yaml`.

## Invocation Policy

- Every skill should intentionally be either user-invoked or model-invoked.
- User-invoked skills set `disable-model-invocation: true` in `SKILL.md` and `policy.allow_implicit_invocation: false` in `agents/openai.yaml`.
- Model-invoked skills omit `disable-model-invocation` and set `policy.allow_implicit_invocation: true` in `agents/openai.yaml` when autonomous use is useful.
- The `ultra-*` skills are user-invoked completion-friendly entrypoints. Keep them explicit and delegation-only.
- `ultra` is the core orchestration dependency that wrappers and the model may invoke.
- `solve-records` is user-invoked. Users call `$solve-records` explicitly for listing, acceptance review, merge/land, and cleanup; `/ultra solve` finalization follows the same record semantics from its own runbook.

## Agent Communication

- DO NOT send optional commentary. Keep status and final reports focused on requested work, evidence, blockers, and actionable next steps.

## Validation Policy

Run deterministic tests for ordinary skill edits:

- `scripts/validate-skills.sh` for skill metadata, references, and bundled shell scripts.
- Skill-specific fixtures under `tests/` for behavior that can be checked with local files and Git state.
- Installer discovery, such as `npx --yes skills@latest add . --list --full-depth`, when trigger wording or manifests change.

Model evals are heavier adherence checks, not default CI. Run them only when explicitly requested by the user or when a change materially affects model behavior, such as core `ultra` routing, enhancement profiles, multi-agent orchestration, merge safety policy, or solve-record finalization semantics.

For small wrapper wording, README, manifest, deterministic fixture, eval-harness, or local eval-record documentation changes, prefer local tests and skip model evals unless the user asks.

## Eval Records

When validation work is substantial, write a short local record under `.evals/<skill-or-feature>/`. Keep executable prepare/grade logic under `tests/evals/<skill-or-feature>/` so a fresh clone can validate the harness without historical run output.

Distinguish these evidence types clearly:

- Deterministic fixture: local shell/Python/Git checks with reproducible assertions.
- Model adherence eval: one or more real model runs through realistic prompts, graded by final repo state rather than response prose.
- Ablation: a comparison showing which guard or instruction is load-bearing.

An eval should be executable by one Agent session end to end: create isolated temporary repos or worktrees, run the skill through realistic prompts, and grade final files, issue state, Git refs, solve records, and cleanup effects. CI and deterministic tests must not depend on historical `.evals/` output. Do not claim a multi-model or multi-thinking eval was run unless there is an accompanying local `.evals/` record with the tested models, settings, prompts, and grader results.

## Ultra And Solve Records

The `ultra-*` skills are thin wrapper entrypoints. Keep them explicit and delegation-only; put orchestration behavior in `skills/engineering/ultra/`.

`/ultra solve` creates outcome Solve Records only when an Attempt reaches a meaningful handoff; Claim itself creates no receipt. Finished candidates become `candidate` receipts only after validation and Post-Execution Review, while substantive failed checks or stopped Attempts become recovery receipts and fully cleaned no-value Attempts remain recordless. `$solve-records` owns listing, explaining, candidate merge/ship/land gates, record-only closure, and safe outcome-specific cleanup semantics.

Do not split `skills/engineering/ultra/solve.md` just because it is large. Before extracting reference-only material, evaluate the candidate split with concrete evidence:

- The extracted reference has one clear owning concept, a named read condition, and either multiple consumers or a large conditional section that ordinary runs can skip.
- `solve.md` remains the coordinator runbook; extracted files do not create a second state machine or alternate merge policy.
- `$solve-records` and `/ultra solve` still agree on record creation, live verification, merge gates, unavailable-check handling, and cleanup safety.
- Deterministic fixtures and `scripts/validate-skills.sh` pass after the split. If the split changes model behavior around orchestration, merge policy, or solve-record finalization, add or update a local `.evals/` record.
