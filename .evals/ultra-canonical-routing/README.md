# Ultra canonical-routing adherence fixture

This fixture exercises the v1.1 canonical shaping profiles without altering a
project tracker. It prepares seven isolated artifact directories, asks one fresh
Agent session to apply the installed `ultra` routing contract, and grades final
artifacts plus routing-decision traces tied to the supplied contract rather
than response prose or an untraceable self-report.

```bash
python3 .evals/ultra-canonical-routing/scripts/prepare-fixture.py \
  --source . --output /tmp/ultra-canonical-routing
# Run a fresh Agent session with /tmp/ultra-canonical-routing/AGENT_PROMPT.md.
python3 .evals/ultra-canonical-routing/scripts/grade-run.py --output /tmp/ultra-canonical-routing
```

The committed fresh-session run is
`runs/20260713-trace-fresh/`; grade it with the same command using that
directory as `--output`.

The grader proves only final-state artifact and trace consistency with the
supplied contract. The run record identifies the fresh session separately;
neither the fixture nor its routing-decision JSON proves a model session or
cryptographic execution provenance on its own.
