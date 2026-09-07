# Ultra Solve Context-Routing Eval

This is a bounded model-adherence harness for the Context-pointer producer and
Bootstrap consumer contract. It creates isolated repositories with current
skill files, a live Claim snapshot, and a formal Ticket. A model reads
`EVAL_PROMPT.md` and writes only `BOOTSTRAP_RESULT.json`; the grader checks the
declared disposition, pointer diagnostics, source ref/path pairs, native-pass
suppression, and immutable inputs.

The authoritative-missing scenario deliberately advances current `HEAD` with a
same-path document that is absent from `eval-base`. Only a consumer that reads
the declared document/ref pair can produce the expected missing-authoritative
diagnostic.

Prepare and prove untouched fixtures fail:

```bash
eval_root="$(mktemp -d)"
python3 tests/evals/ultra-solve-context-routing/prepare-fixture.py --output "$eval_root"
python3 tests/evals/ultra-solve-context-routing/grade-run.py "$eval_root"/*/repo
```

Run a model separately in every `repo` directory with `EVAL_PROMPT.md`, then
run the same grader. Historical model outputs belong under the ignored
`.evals/ultra-solve-context-routing/` directory and never gate CI.
