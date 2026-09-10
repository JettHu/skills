# Bounded exploration adherence eval

This experiment exercises the Pre-Implementation Checkpoint only. It is not a
full solve/Claim/receipt acceptance run or a latency benchmark.

Prepare fresh isolated fixtures:

```sh
python3 tests/evals/ultra-bounded-exploration/fixture.py prepare /tmp/exploration-run
```

For a realistic multi-module case, supply `--backend <alter-backend-checkout>` and
`--frontend <xhs_agent_frontend-checkout>`. The preparer copies only its explicit
source list; all model work happens in the copies. `baseline.json` records the
exact inputs. The default small synthetic case may reasonably use direct routing.

Run each directory's `EVAL_PROMPT.md` in an independent agent session with
collaboration available. Supply only that fixture and its scope, not the expected
route. Grade each directory with `fixture.py grade <directory>`.

The deterministic grader checks input preservation and checkpoint completeness.
Separately inspect actual tool/collaboration traces and the returned source
locations: was delegation useful for the unresolved questions, did the root avoid
repeating the worker's investigation, were constraints and validation preserved,
and did the run stop at an implementation-ready plan? The local scenario should
not acquire unnecessary orchestration. A result's self-reported route alone is
not delegation evidence. Keep model settings, exact fixture hashes, observed
behavior and limits under local `.evals/`; historical runs are not CI inputs.
