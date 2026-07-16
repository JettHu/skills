# Ultra Complementary Profiles Eval Harness

This harness compares revised profile contracts with an ablation ref in equivalent,
isolated Git repositories. It grades final repository, artifact, live validation,
tracker, supplied-contract, and structured stage state. For delegation-sensitive
scenarios it also grades the runtime JSONL trace, so a model-authored stage ledger
cannot substitute for an actual target-native subagent call. Model response prose is
not a scoring input.

Prepare all reusable scenarios without a model run:

```bash
python3 tests/evals/ultra-complementary-profiles/prepare-fixture.py \
  --output /tmp/ultra-complementary \
  --run-id local-check \
  --scenario all \
  --treatment-ref working-tree \
  --ablation-ref <baseline-sha>
```

Run a fresh-context treatment/ablation pair through the primary Codex runtime:

```bash
python3 tests/evals/ultra-complementary-profiles/run-eval.py \
  --output .evals/ultra-complementary-profiles/runs \
  --run-id <run-id> \
  --scenario architecture-native-ownership \
  --treatment-ref <implementation-sha> \
  --ablation-ref <baseline-sha> \
  --runtime primary \
  --model <primary-model> \
  --timeout 1800
```

The primary entrypoint uses `workspace-write` sandboxing with approval policy
`never`; it does not bypass the sandbox. Model eval runs require committed refs.
`working-tree` remains available only to `prepare-fixture.py` for deterministic
constructor/grader tests because uncommitted contents cannot be truthfully named by
a commit SHA.

Run a treatment/ablation pair through Qoder:

```bash
python3 tests/evals/ultra-complementary-profiles/run-eval.py \
  --output .evals/ultra-complementary-profiles/runs \
  --run-id <run-id> \
  --scenario architecture-native-ownership \
  --treatment-ref <implementation-sha> \
  --ablation-ref <baseline-sha> \
  --runtime qoder \
  --model Qwen3.7-Max-DogFooding \
  --context-window 1000000 \
  --timeout 1800
```

Omit `--reasoning-effort` to preserve a model's default. Each rerun creates a new
numbered attempt and never overwrites prior evidence. Every attempt preserves the
exact argument vector, shell rendering, raw stdout/stderr, timeout or exit state,
literal grader output, runtime version, resolved treatment/ablation SHAs, observed
delegation calls/models, and a recovery command description.

Delegation-sensitive prompts carry a stable target-owned marker (for example,
`[target-native:architecture-candidate-discovery]`). The trace grader accepts only
successfully completed calls with that marker, rejects missing/extra calls, and
records primary-runtime delegated model identity as `unknown/unavailable` when the
Codex JSONL protocol does not expose it.

This harness supports the later four-model matrix, but one smoke pair is not that
matrix and must not be described as a complete model-adherence eval.
