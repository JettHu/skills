# Scope and landing adherence continuations

`fixture.py` prepares a temporary Git repository starting after one Ticket's Claim and branch assignment. It copies the actual selected revision's solve policy and direct consumers; it does not substitute policy text. The application is deliberately small so scope, conflicts and landing authority remain the experimental variables.

```sh
python3 tests/evals/ultra-scope-landing/fixture.py prepare /tmp/scope-candidate --case scope --ref WORKTREE
codex exec --ignore-user-config --ephemeral -s workspace-write -m gpt-6-astra -c model_reasoning_effort=high -C /tmp/scope-candidate --json - < /tmp/scope-candidate/EVAL_PROMPT.md
python3 tests/evals/ultra-scope-landing/fixture.py grade /tmp/scope-candidate
```

Use a new directory for each run and preserve the prompt, CLI version, model/effort, copied policy, stdout/stderr, process result and grader JSON under `.evals/`. For a paired baseline, pass its commit to `--ref`, holding the case, prompt, harness, model and effort fixed. The supported cases are `scope`, `integration`, `conflict`, `apply-fix`, `apply-patch`, `land`, `inferred-land`, `ambiguous`, `failed-gate`, and `auto-merge`.

The grader checks application files, candidate/target/remote refs, receipt outcome and lifecycle, Ticket state, and cleanliness. It does not grade response wording. `bash tests/ultra-scope-landing-eval.sh` exercises positive and negative grader states without invoking a model; these deterministic fixtures are not adherence evidence.

This is a bounded continuation eval, not a full publication/Claim adapter or multi-agent orchestration eval. The minimal fixture adapter writes real local receipt/state artifacts but is not the production Tracker Facade. Review/dependency/rollout inputs are fixture evidence. The CLI's unavailable delegation is explicit; no independent model review is claimed. Remote refs are local test refs and no production deployment service is configured. Inspect actual run output for attempted out-of-environment actions and report those limitations; ref checks alone cannot prove behavior against a live remote or deployment service. Host-level model instructions may already enforce the intended boundary, so a passing baseline is not evidence of a causal policy improvement.
