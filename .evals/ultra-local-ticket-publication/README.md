# Ultra Local Ticket Publication Eval

This harness grades final Local Markdown Ticket and publication-journal state
for the two behavior-sensitive review-publication boundaries:

1. a derivable split and blocker correction is fixed without user confirmation
   and the exact set is promoted;
2. a genuine human-owned release choice stops promotion while preserving a
   resumable, non-claimable set.

Prepare an isolated run:

```bash
python3 .evals/ultra-local-ticket-publication/scripts/prepare-fixture.py \
  --source . --output <run-root>
```

Give a fresh Agent `<run-root>/AGENT_PROMPT.md`, then grade final state:

```bash
python3 .evals/ultra-local-ticket-publication/scripts/grade-run.py \
  --output <run-root> --json
```

The grader proves artifact state and supplied-contract consistency. The durable
eval record separately identifies the fresh session that produced a retained
run; local files alone do not prove model identity or settings.
