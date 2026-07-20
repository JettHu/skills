# Ultra Complementary Profiles Eval Harness

## Practical threat model and authority boundary

This harness evaluates a cooperative-but-fallible Agent. The Agent may inspect files
visible from its working directory, invoke ordinary shell wrappers, and produce
malformed output or an inaccurate stage ledger. The evaluator therefore does not use
model prose or the ledger alone to prove delegation, execution order, validation, or
final state. Those claims require evaluator-owned repository checks and runtime trace
evidence.

This is not an adversarial-isolation or security-sandbox claim. Deliberate Git
metadata attacks such as `git replace` or `skip-worktree`, guessing evaluator-owned
absolute host paths, and intentional reads outside the supplied workspace are
out-of-scope defense-in-depth. The canary remains blocked on the practical boundary
described here, not on hardening against an actively hostile Agent.

Public task mechanics belong in the byte-identical treatment/ablation prompt and
public metadata. Hidden grading policy belongs only to evaluator authority. Before a
model starts, the runner snapshots `control.json` in memory and removes it from disk;
only after the runtime exits does it materialize `grader-control.json`. The model runs
from a neutral opaque directory name, while variant/ref mappings remain in external
invocation evidence. `EVAL_EXPECTATIONS.json` intentionally omits arm identity and
contract refs. Only the supplied skill/profile content differs between arms.

The practical runtime boundary is preflighted without a model request. Qoder receives
an isolated `HOME` and a temporary config root containing only a bridge to
`~/.qoder/.auth`; settings, skills, plugins, and other ambient Qoder state are not
copied. A real `qodercli status --output json` check runs in that isolation before
execution. The runner parses the JSON protocol and requires `logged_in` to be exactly
`true`; exit zero alone, a missing/false field, or malformed JSON fails closed before
any model request. Evidence records only whether authentication was available, never
account identity or authentication contents. Binary lookup, version, preflight, execution,
and timeout failures all produce attempt-local invocation/result/error evidence, and
temporary runtime directories are removed on every path.

## Public contract and external observability

This harness compares revised profile contracts with an ablation ref in equivalent,
isolated Git repositories. It grades final repository, artifact, live validation,
tracker, supplied-contract, and structured stage state. For delegation-sensitive
scenarios it also grades the runtime JSONL trace, so a model-authored stage ledger
cannot substitute for an actual target-native subagent call. Model response prose is
not a scoring input.

Every mechanically exact task outcome is repeated in the shared `EVAL_PROMPT.md`: the
artifact path and literal coverage terms, exact tracker status, validation command and
success condition, plus the `stage-evidence.json` schema and scenario-specific stable
stage vocabulary. A new scenario vocabulary contains one canonical name per stage and
any explicitly recordable ablation stage; it is not a global union and does not
automatically expose historical forbidden-stage names. Schema-v2/v3 controls retain
their recorded alias normalization for historical regrading, but new fixtures never
publish a canonical stage beside its semantic alias.
The prompt is byte-identical for treatment and ablation. It does not publish a
treatment-owned stage sequence, ownership decision, or duplicate-stage conclusion.
The ledger records completed stages in their actual runtime order; raw runtime trace,
not a model-authored ledger, is authoritative for duplicate exploration. Validation is
proved by a successful runtime command plus a fresh external rerun; the primary
artifact does not need a hidden validation literal.

New fixtures use schema version 4. Ledger events contain only `name` and `evidence`;
the evaluator does not ask the model to guess an owner label. The supplied contracts
declare semantic ownership, while evaluator-owned required-stage identities, runtime
stage markers, and command evidence establish execution. The evaluator maps canonical
stage names to evaluator-owned evidence-goal identities, so a second exploration maps
to the same candidate-discovery goal instead of passing merely because the Agent chose
different prose. This mapping stays out of the shared prompt; attributable ablation
still requires the matching real trace call. Historical schema-v3 ledgers keep their
recorded `owner` and alias checks when regraded under their preserved control record.

The prepare-only attempt-local `control.json`, outside the model repository, is the
authoritative expectation record and pins the initial fixture commit. The runner
snapshots and removes it before model execution, then recreates its contents only as
`grader-control.json` after runtime exit. The repository's
`EVAL_EXPECTATIONS.json` contains only public fixture metadata and has its own hash in
that control record; hidden required stages, trace rules, and write sets exist only in
the external authority. The grader requires each hidden scenario stage exactly
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
uses an ephemeral user configuration root and isolated `HOME`. Qoder starts with only
the ambient `.qoder/.auth` bridge, project-only settings, and disabled built-in
skills; it does not copy settings, skills, or plugins. Primary receives an isolated
`HOME`/`CODEX_HOME` containing only an auth link. Temporary runtime state is removed
after every outcome. Runtime traces independently fail any observed `Skill` invocation, so
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
  --model Qwen3.8-Max-Preview \
  --context-window 1000000 \
  --canary-gate \
  --timeout 1800
```

Use `--canary-gate` only for the fail-fast treatment/ablation sentinel. It writes a
pair-specific durable verdict such as
`canary-verdict-treatment-001-ablation-001.json` and passes the gate only when
treatment is fully correct, ablation has valid repository/artifact/validation/tracker
evidence, and the ablation fails solely on the scenario's declared
duplicate-exploration profile delta. If both variants pass, the
verdict is `no-observed-attributable-difference`; that is an honest negative result
and stops the matrix rather than claiming incremental value. Invalid tracker or
validation state on either side also stops the matrix and cannot be counted as an
ablation difference. For the architecture canary, a ledger-only duplicate-stage claim
is insufficient: the raw trace must produce the dedicated `extra_exploration_call`
failure for a completed delegated stage marked `[eval-stage:ultra-code-explore]`.
The same recorded stage may also produce `duplicate_evidence_goal` through the hidden
stable goal mapping; that code is allowable but never substitutes for the required
external trace delta.
Every completed Agent call must carry exactly one known neutral stage-intent marker;
an explicit `subagent_type` or `agent_type` constrains Explore intent when exposed,
while `task_name` remains task identity and free text is never a role classifier.
Marker identities and their real
trace order are reconciled with the stage ledger in both directions, so a ledger-only
claim, an unrecorded trace call, or false ledger ordering produces non-attributable
`stage_trace_mismatch`. Architecture treatment additionally requires one real
target-native Explore call followed by a distinct delegated Ultra post-review; a
ledger-only post-review cannot pass. Re-running the same run id
preserves every pair verdict under its treatment/ablation attempt numbers.

Agent and command events also retain one unified runtime index. The architecture
contract requires completed target-native Explore, then completed Ultra post-review,
then successful validation; keeping validation last only in the model-authored ledger
cannot conceal a validation-first runtime trace.

Omit `--reasoning-effort` to preserve a model's default. Each rerun creates a new
numbered attempt and never overwrites prior evidence. Every attempt preserves the
exact argument vector, shell rendering, raw stdout/stderr, timeout or exit state,
literal grader output, runtime version, resolved treatment/ablation SHAs, observed
delegation calls/models, and a recovery command description.

Delegation-sensitive `TARGET_SKILL.md` native contracts carry neutral markers such as
`[eval-stage:target-native-explore]`; the shared prompt publishes only the generic
`[eval-stage:<stage-name>]` annotation rule and scenario vocabulary, not the hidden
required sequence. The trace grader accepts only calls whose outer runtime status and
every reported child Agent terminal state are completed. It observes shell command
events, including validation launched through ordinary `sh -c`, `bash -lc`, and
command-substitution wrappers, so repeated executions cannot hide behind those common
forms. Every behavior-sensitive scenario has external evidence through
stage markers, red/green command order, immutable file changes, publication adapter
receipt, or a no-delegation cap. The grader also
records primary-runtime delegated model identity as `unknown/unavailable` when the
Codex JSONL protocol does not expose it.

This harness supports the later four-model matrix, but one smoke pair is not that
matrix and must not be described as a complete model-adherence eval.
