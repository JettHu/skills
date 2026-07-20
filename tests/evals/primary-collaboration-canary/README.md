# Primary collaboration runtime canary

This evaluator answers one narrow question: can the Primary Codex CLI launch and
complete one real child Agent through the same isolated runtime path used by the
Ticket 20 Primary profile evaluator?

It is not a treatment/ablation or portable-Ultra canary, and
`run-eval.py --canary-gate` cannot substitute for it. The canary imports the shared
`PrimaryRuntimeAdapter` from the complementary-profile evaluator. That adapter owns
the temporary `HOME`, temporary `CODEX_HOME`, auth.json-only bridge, opaque Git cwd,
Codex command construction, model/reasoning/timeout settings, raw output capture,
timeout handling, workspace restoration, and temporary thread-store cleanup. It
intentionally does not pass `--ephemeral`.

## Deterministic validation

Run the fake-runtime fixture, which consumes no model tokens:

```bash
bash tests/primary-collaboration-canary.sh
```

The fixture covers feature-protocol failures, missing or malformed collaboration
lifecycle evidence, failed or unfinished children, duplicate spawns/children,
runtime failures and timeouts, every repository write-set class, evidence
sanitization, append-only attempts, cleanup, and shared-adapter ownership. Existing
Primary/Qoder profile fixtures remain covered by
`bash tests/ultra-complementary-profiles.sh`.

## Evidence and authority

Each invocation creates a new
`<output>/<run-id>/attempt-NNN/` directory. It never overwrites an earlier attempt.
The directory contains invocation and runtime version evidence, sanitized feature
preflight evidence and raw feature output, raw model JSONL and stderr, evaluator-owned
grader control, grader output, result/verdict, and the restored Git fixture plus its
write-set evidence. Authentication contents and the disposable runtime/thread store
are never copied into the attempt.

PASS requires all of the following external evidence:

- `codex features list` succeeds in the exact model environment and reports
  `multi_agent ... true` in the recognized protocol;
- raw Codex JSONL has exactly one terminal `spawn_agent` collaboration call carrying
  `[eval-stage:primary-collaboration-canary]`;
- the outer call and its single real child identity are completed, with no failed,
  cancelled, timed-out, or running child;
- runtime exit is zero, tracked/committed/untracked/symlink write sets are empty, and
  all disposable runtime paths are removed.

Root prose and model-authored ledgers are ignored. Full child response text is not a
required trace field.

## Gated real invocation

The implementation based on `7bfd2dc9e54995f711e88144372f3f8c837bee5e`
must receive independent acceptance before a real canary is allowed. After that
acceptance, the only permitted real invocation is:

```bash
python3 tests/evals/primary-collaboration-canary/run-canary.py \
  --output .evals/primary-collaboration-canary \
  --run-id 20260720-primary-collaboration-runtime-canary \
  --model gpt-5.6-sol \
  --reasoning-effort medium \
  --timeout 600
```

Do not run it during implementation or independent implementation review. Preserve
the first attempt literally; no retry, profile pair, Qoder, or DeepSeek run is
authorized by this interface.
