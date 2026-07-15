# Ultra Solve Stage Ownership Eval Harness

This harness prepares seven isolated Git scenarios and grades final repository,
Ticket, validation, receipt, worktree, exclusive-writer, review-action, and
unchanged-landing-branch state rather than response prose.

```bash
python3 tests/evals/ultra-solve-stage-ownership/prepare-fixture.py \
  --output /tmp/ultra-stage-ownership \
  --run-id <run-id> \
  --scenario all \
  --treatment-ref <candidate-sha>

python3 tests/evals/ultra-solve-stage-ownership/grade-run.py \
  /tmp/ultra-stage-ownership/<run-id>
```

Run each generated `repo/EVAL_PROMPT.md` unchanged in a fresh model session
before grading. The scenarios cover direct implementation with all six positive
facts, delegation when one fact is unproven, preferred read-only delegation, a
bounded root read-only exception, serialized dependent stages, autonomous
derivable repair, and human-owned escalation.

`bash tests/ultra-solve-stage-ownership-eval.sh` validates only constructor and
grader behavior. Its untouched fixtures must fail. It is not model-adherence
evidence. Record a real run separately under `.evals/` with the exact treatment
SHA, runtime/model/settings, prompt paths, grader command, and literal output.
