# Ultra Solve Ticket-Boundary Eval Harness

This committed harness creates disposable, isolated Git fixtures and grades
their final state with the committed canonical receipt helper. Generated runs
stay ignored; the constructor, grader, prompts, and expectations are durable.

## Prepare

Always pin the treatment to the exact committed candidate under review:

```bash
python3 .evals/ultra-solve-afk-safe-planning/scripts/prepare-fixture.py \
  --output /tmp/ultra-solve-evals \
  --run-id 20260713-ticket-boundaries \
  --scenario 04-stale-hint \
  --treatment-ref <commit-sha>
```

Use `--scenario all` for the six current-contract fixtures: simple direct
execution, fan-out/Pre-Edit planning, first-deviation distillation, stale hint,
meaningful recovery handoff, and no Digest residue.

Each generated `repo/EVAL_PROMPT.md` is the exact model prompt. Start a fresh
model session in that fixture, send that prompt unchanged, and do not merge,
push, clean up, or edit `EVAL_EXPECTATIONS.json`.

## Grade

```bash
python3 .evals/ultra-solve-afk-safe-planning/scripts/grade-run.py \
  /tmp/ultra-solve-evals/20260713-ticket-boundaries/04-stale-hint/repo
```

The grader reads Ticket state, external Digest lifecycle, current receipt
shape/outcome/dashboard route through the embedded canonical helper, candidate
Git evidence, stale-hint forbidden paths, and scenario checks. A base fixture
must fail: passing requires a model session to leave a completed final state.

After a real run, commit a dated report with the exact treatment SHA, run ID,
prompt path, model/settings, grader command/output, and final-state result.
