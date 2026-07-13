# Ultra canonical-routing adherence fixture

This fixture exercises the v1.1 canonical shaping profiles without altering a
project tracker. It prepares seven isolated artifact directories, asks one fresh
Agent session to apply the installed `ultra` routing contract, and grades final
artifact and routing-decision state rather than response prose.

```bash
python3 .evals/ultra-canonical-routing/scripts/prepare-fixture.py \
  --source . --output /tmp/ultra-canonical-routing
# Run a fresh Agent session with /tmp/ultra-canonical-routing/AGENT_PROMPT.md.
python3 .evals/ultra-canonical-routing/scripts/grade-run.py --output /tmp/ultra-canonical-routing
```

The grader proves only final-state conformance. The run record identifies the
fresh session separately; neither the fixture nor a local JSON result proves a
model session on its own.
