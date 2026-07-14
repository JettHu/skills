# Ultra Solve Claimable-Frontier Eval

This eval grades the discovery and Claim phase of `/ultra solve` from final
tracker state rather than response prose.

The committed constructor creates three independent repositories:

- `01-explicit`: an explicit set containing one frontier Ticket, one blocked
  Ticket, and one provisional Ticket. Only the initial frontier may be claimed.
- `02-all`: a branching DAG that must advance by frontier generation.
- `03-unsafe`: a contract without safe Claim configuration. Discovery must fail
  closed without Ticket mutation.

`scripts/tracker.py` inside each generated fixture wraps the bundled adapter and
records successful Claim/completion transitions in an eval-only audit file. It
does not replace the production graph or Claim implementation.

Prepare and grade:

```text
python3 .evals/ultra-solve-claimable-frontier/scripts/prepare-fixture.py \
  --output /tmp/ultra-frontier-eval --treatment-ref HEAD
python3 .evals/ultra-solve-claimable-frontier/scripts/grade-run.py \
  /tmp/ultra-frontier-eval/<scenario>/repo
```

Heavy fresh-session model runs are recorded in dated Markdown files here and
are intentionally outside default CI. Deterministic adapter behavior remains
covered by `tests/ultra-solve-claimable-frontier.sh`.
