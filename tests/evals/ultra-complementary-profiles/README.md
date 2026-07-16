# Ultra Complementary Profiles Eval Harness

This harness compares revised profile contracts with an ablation ref in equivalent,
isolated Git repositories. It grades final repository, artifact, live validation,
tracker, supplied-contract, and structured stage state. For delegation-sensitive
scenarios it also grades the runtime JSONL trace, so a model-authored stage ledger
cannot substitute for an actual target-native subagent call. Model response prose is
not a scoring input.

Every mechanically exact task outcome is repeated in the shared `EVAL_PROMPT.md`: the
artifact path and literal coverage terms, exact tracker status, validation command and
success condition, plus the `stage-evidence.json` schema and scenario-specific stable
stage vocabulary. A scenario vocabulary contains required stages, published aliases,
and any explicitly recordable ablation stage; it is not a global union and does not
automatically expose historical forbidden-stage names.
The prompt is byte-identical for treatment and ablation. It does not publish a
treatment-owned stage sequence, ownership decision, or duplicate-stage conclusion.
The ledger records completed stages in their actual runtime order; raw runtime trace,
not a model-authored ledger, is authoritative for duplicate exploration. Validation is
proved by a successful runtime command plus a fresh external rerun; the primary
artifact does not need a hidden validation literal.

The attempt-local `control.json`, outside the model repository, is the authoritative
expectation record and pins the initial fixture commit. The repository's
`EVAL_EXPECTATIONS.json` contains only public fixture metadata and has its own hash in
that control record; hidden required stages, owners, trace rules, and write sets exist
only in the external authority. The grader requires each hidden scenario stage exactly
once and preserves its contract-relative order, so
removing a required candidate, review, publication, or feedback-loop stage still fails
even when repository, artifact, tracker, and validation state are correct. Extra
recorded stages do not themselves prove duplicate exploration; only completed runtime
trace calls can produce the attributable `extra_exploration_call` delta.

The grader never executes model-writable Python. Its immutable scenario validator
checks final behavior and structurally parses diagnosis code without importing it,
then compares the whole repository to the pinned initial commit and rejects paths
outside the scenario write set. Missing or malformed
workspace expectations, artifacts, tracker state, result files, or receipts become
stable failure codes rather than grader exceptions. Scenario-specific Markdown
section and source-reference checks prevent token-only artifacts from passing.

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
The runner resolves both requested refs before preparing a fixture and prepares
directly from those immutable SHAs, so recorded provenance cannot race a moving ref.
`working-tree` remains available only to `prepare-fixture.py` for deterministic
constructor/grader tests because uncommitted contents cannot be truthfully named by
a commit SHA.

The generated prompt is contract-only: it does not contain a slash invocation and
forbids the runtime `Skill` tool and installed/global skill contracts. The runner also
uses an ephemeral user configuration root. Qoder is started with only the project
setting source and with built-in skills disabled; Primary receives an isolated
`HOME`/`CODEX_HOME` containing only an auth link. The temporary configuration root is removed
after execution. Runtime traces independently fail any observed `Skill` invocation, so
the supplied treatment/ablation contracts are the only admissible workflow inputs.

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
  --canary-gate \
  --timeout 1800
```

Use `--canary-gate` only for the fail-fast treatment/ablation sentinel. It writes a
pair-specific durable verdict such as
`canary-verdict-treatment-001-ablation-001.json` and passes the gate only when treatment is fully correct,
ablation has valid repository/artifact/validation/tracker evidence, and the ablation
fails solely on the scenario's declared ownership delta. If both variants pass, the
verdict is `no-observed-attributable-difference`; that is an honest negative result
and stops the matrix rather than claiming incremental value. Invalid tracker or
validation state on either side also stops the matrix and cannot be counted as an
ablation difference. For the architecture canary, a ledger-only ownership claim is
insufficient: the raw trace must produce the dedicated `extra_exploration_call`
failure for a completed delegated stage marked `[eval-stage:ultra-code-explore]`.
Every completed Agent call must carry exactly one known neutral stage-intent marker;
role names and free text are never classifiers. Marker counts are reconciled with the
stage ledger in both directions, so a ledger-only claim or an unrecorded trace call
produces non-attributable `stage_trace_mismatch`. Re-running the same run id
preserves every pair verdict under its treatment/ablation attempt numbers.

Omit `--reasoning-effort` to preserve a model's default. Each rerun creates a new
numbered attempt and never overwrites prior evidence. Every attempt preserves the
exact argument vector, shell rendering, raw stdout/stderr, timeout or exit state,
literal grader output, runtime version, resolved treatment/ablation SHAs, observed
delegation calls/models, and a recovery command description.

Delegation-sensitive `TARGET_SKILL.md` native contracts carry neutral markers such as
`[eval-stage:target-native-explore]`; the shared prompt publishes only the generic
`[eval-stage:<stage-name>]` annotation rule and scenario vocabulary, not the hidden
required sequence. The trace grader accepts only calls whose outer runtime status and
every reported child Agent terminal state are completed. It parses shell command
segments, so an exact validation followed by a composite second invocation counts as
two executions. Every behavior-sensitive scenario has external evidence through
stage markers, red/green command order, immutable file changes, publication adapter
receipt, or a no-delegation cap. The grader also
records primary-runtime delegated model identity as `unknown/unavailable` when the
Codex JSONL protocol does not expose it.

This harness supports the later four-model matrix, but one smoke pair is not that
matrix and must not be described as a complete model-adherence eval.
