# Ultra Solve Expand-Contract Eval

This targeted model-adherence eval grades a realistic shared-integration payload migration from final repository state, not response prose. The fixture has the declared graph `EXPAND -> {BATCH-A, BATCH-B} -> CONTRACT -> INTEGRATE-VERIFY`: either batch alone is intentionally not green, while the named shared integration branch becomes green only after both migrations and contract removal.

The grader checks exact Ticket blockers and released Claims, scoped versus final validation ownership, the clean committed shared branch, an unchanged target branch, the final integration check, and the candidate receipt owned by `INTEGRATE-VERIFY`.

Prepare and grade:

```text
python3 .evals/ultra-solve-expand-contract/scripts/prepare-fixture.py \
  --output /tmp/ultra-expand-contract-eval --treatment-ref HEAD
python3 .evals/ultra-solve-expand-contract/scripts/grade-run.py \
  /tmp/ultra-expand-contract-eval/repo
```

Fresh-session model evidence is recorded in the dated Markdown file beside this README. The deterministic graph fixture is `tests/ultra-solve-expand-contract.sh`.
