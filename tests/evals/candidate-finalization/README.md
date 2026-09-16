# Candidate finalization continuation

This harness copies the production policy and facade into an isolated two-repo
fixture. One target is already landed and its worktree deleted; the original
receipt write was interrupted. A real model must verify partial facts, complete
the second landing and remaining cleanup, and reconcile the original receipt.

```sh
python3 tests/evals/candidate-finalization/fixture.py prepare /tmp/finalization-eval
codex exec --ephemeral --ignore-user-config -s danger-full-access -C /tmp/finalization-eval/one --json - < /tmp/finalization-eval/PROMPT.md
python3 tests/evals/candidate-finalization/fixture.py grade /tmp/finalization-eval
```

Retain CLI version, effective model/settings, prompt, copied sources, JSON output,
exit status and grader result under `.evals/candidate-finalization/`. No model run
is part of deterministic CI. The grader checks refs, resource removal, the
original receipt and query projection; inspect the transcript to establish use
of the supported writer. This is a bounded continuation, with fixture-provided
acceptance evidence; it does not validate real business authorization, remote
provider merges, or deployment. A passing run is adherence evidence, not an
ablation or a multi-model comparison.
