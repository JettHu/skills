# Ultra Complementary Profiles Eval Harness

This harness compares revised profile contracts with an ablation ref in equivalent,
isolated Git repositories. It grades final repository, artifact, live validation,
tracker, supplied-contract, and structured stage state; model response prose is not
a scoring input.

Prepare all reusable scenarios without a model run:

```bash
python3 tests/evals/ultra-complementary-profiles/prepare-fixture.py \
  --output /tmp/ultra-complementary \
  --run-id local-check \
  --scenario all \
  --treatment-ref working-tree \
  --ablation-ref <baseline-sha>
```

Run a treatment/ablation pair through Qoder:

```bash
python3 tests/evals/ultra-complementary-profiles/run-eval.py \
  --output .evals/ultra-complementary-profiles/runs \
  --run-id <run-id> \
  --scenario architecture-native-ownership \
  --treatment-ref <implementation-sha> \
  --ablation-ref <baseline-sha> \
  --model Qwen3.7-Max-DogFooding \
  --context-window 1000000 \
  --timeout 1800
```

Omit `--reasoning-effort` to preserve a model's default. Each rerun creates a new
numbered attempt and never overwrites prior evidence. Every attempt preserves the
exact argument vector, shell rendering, raw stdout/stderr, timeout or exit state,
literal grader output, and a recovery command description.

This harness supports the later four-model matrix, but one smoke pair is not that
matrix and must not be described as a complete model-adherence eval.
