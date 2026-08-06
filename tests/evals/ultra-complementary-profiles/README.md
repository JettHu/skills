# Ultra Complementary Profiles Eval Harness

## Current portable acceptance boundary

Ticket 20 now accepts the portable profile contract through deterministic validation.
Model-adherence runs are optional, separately reported evidence: an absent or failed
model run does not block acceptance of the portable catalog contract. Historical
attempts, raw traces, grader output, policies, and `NOT ACCEPTED` verdicts remain
immutable evidence and are not reinterpreted by this scope change.

The prospective policies below document the historical model-evaluation program and
the gates that applied within that program. They do not define the current portable
contract gate. A future model-evaluation Ticket may reuse them only under its own
explicit authorization and immutable-evidence rules.

## Prospective acceptance policy

Ticket 20's required model-adherence gate is frozen in
[`acceptance-policy-v1.json`](acceptance-policy-v1.json). Version 1 is prospective
only: attempts that began before the Git commit containing that byte-identical policy
are diagnostic evidence and cannot satisfy its gate. Any policy change requires a new
version and new run IDs; results do not migrate between policy versions.

Before the first model call, write a durable pre-run manifest that pins the accepted
policy commit and file hash, the independently reviewed treatment ref, the policy's
fixed ablation ref, all run IDs, models, settings, scenarios, and timeout. The manifest
does not amend the policy. A behavioral attempt is never retried after its model has
started. A failure before model start may be retried only under a new attempt ID while
preserving the failed attempt.

The reference model must pass every declared treatment. The three heterogeneous
sentinels exercise the highest-risk ownership and context-sufficiency scenarios; two
of three must pass each scenario in addition to the reference pass. This prospective
quorum tolerates one model-specific limitation while requiring a majority across all
preselected sentinels. Every sentinel still runs and remains evidence. The phase order
and stop rule prevent later cells from being used to rescue an earlier failed gate.

The policy's Codex CLI classification is an exclusion caused by an unavailable
delegation capability, not a passing result. Version 1 supports Qoder adherence claims
only and cannot be cited as evidence for Codex CLI delegation behavior.

## Prospective acceptance policy v2

[`acceptance-policy-v2.json`](acceptance-policy-v2.json) supersedes v1 for all future
gating. It keeps the same Qoder reference/sentinel model matrix, reasoning settings,
1,000,000-token context window, architecture attribution rule, and per-scenario 2/3
quorum. Policy v1, its manifests, attempts, receipts, and verdict gaps remain
diagnostic-only and are permanently non-gating.

Use [`run-policy.py`](run-policy.py) as the only policy entrypoint. Its
`--create-manifest` mode atomically creates exactly one `canonical-manifest.json` with
the policy commit/hash, reviewed treatment and ablation refs, all 15 fixed run IDs,
every model/settings/scenario cell, phase order, and timeout; an existing or incomplete
manifest fails closed. `--execute` accepts no loose model, ref, scenario, phase, or
timeout arguments and runs only those cells. It writes append-only state receipts,
durable architecture pair evidence, and one durable verdict per phase. A failed phase
prevents the next phase from starting.

`runtime_invoked` is recorded before the runtime CLI is called. `model_started` becomes
true only when the raw runtime trace contains an assistant model event. A pre-runtime
failure may create a new attempt directory; after runtime invocation, including a trace
without a model event, the reserved policy cell cannot be retried under another run ID.

## Prospective acceptance policy v4

[`acceptance-policy-v4.json`](acceptance-policy-v4.json) supersedes v3 for all future
gating. Policies v1, v2, and v3 and all of their evidence remain permanently
non-gating. Version 2 Phase 1 permanently failed (`passed=false`); its evidence,
verdicts, and run IDs must not be re-run, re-graded, retried, or retrospectively
accepted.

Policy v4 keeps the same Qoder reference/sentinel model matrix, reasoning settings,
1,000,000-token context window, architecture attribution rule, per-scenario 2/3 quorum,
phase order, stop rule, and timeout as v2. All 15 run IDs are fresh `ticket-20-v4-*`
identifiers relative to all prior policies. The only substantive changes from v2/v3
are the Workflow evidence transport/normalization and policy version/run IDs. Any
future policy change requires Policy v5 and another completely fresh run-ID set.

### Workflow as a capability-equivalent delegation surface

Qoder Workflow is a supported capability-equivalent delegation surface. When the model
uses a Workflow to orchestrate multiple `agent()` calls, the evaluator treats those
child agents as equivalent to direct Agent calls for grading purposes, provided the
Workflow supplies authoritative runtime evidence.

**Authoritative runtime artifacts** (trust as runtime-owned evidence):
- `.qoder/sessions/<session-id>/workflows/runs/<run-id>/manifest.json`
- `.qoder/sessions/<session-id>/workflows/runs/<run-id>/journal.jsonl`
- `.qoder/sessions/<session-id>/workflows/runs/<run-id>/output.json`

The manifest and journal prove child identity and lifecycle. The raw runtime trace,
including the strictly parsed runtime-owned child transcript captured under
`runtime-evidence/config-projects/`, proves invocation/session binding, stage markers,
delegated model starts, and observed ordering. Child transcript paths must agree
between manifest and journal. A top-level Workflow completion or model-written script
is never sufficient.

**Non-authoritative model declarations** (never used as sole evidence):
- Model-written workflow JavaScript/TypeScript scripts.
- Model-authored stage ledger entries.
- Model response prose claiming delegation occurred.

**Fail-closed conditions** (never guess or infer from prose):
- Missing, corrupt, unparseable, or symlinked manifest, journal, output, or raw trace.
- Child agent without a terminal event in the journal (Workflow overall completed
  alone cannot substitute).
- Runtime unavailable, trace incomplete, or parser unknown.

**Normalized stage model**: both direct Agent and Workflow use the same normalized
stage model. Stage markers, roles, execution order, command calls, and reconciliation
with the stage ledger are graded identically regardless of delegation surface.

**Write-set isolation**: Workflow metadata is snapshotted, with symlinks preserved, to
the attempt-owned `runtime-evidence/` directory before cleanup. It is then removed
from the fixture repository before repository/write-set grading. The grader never
globally ignores `.qoder/**`.

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
copied. One shared argument set gives the model invocation and every token-free probe
the same config root, opaque fixture cwd, project-only setting source, disabled built-in
Skills mode, and isolated runtime `HOME`. `qodercli status --output json` must report
`logged_in` exactly `true`. `qodercli agents list` must match the Qoder 1.0.48 protocol:
an exact `<count> active agents` header, one blank line, `Built-in:`, then exactly that
many `<name> · <mode>` entries; additional well-formed built-in Agents are allowed, but
both `Explore` and `general-purpose` are required. Unknown lines, mixed formats, count
mismatches, and empty output fail closed. `qodercli skills list` is clean only when its
sole non-empty output is `No skills discovered.`; a well-formed `Discovered Agent Skills:`
listing is a Skill leak, while mixed, empty, or unknown output is an unrecognized protocol.

Agent failures use `qoder_agent_probe_failed`, `qoder_agent_protocol_unrecognized`, or
`qoder_required_agent_missing`. Skill failures use `qoder_skill_probe_failed`,
`qoder_skill_protocol_unrecognized`, or `qoder_skill_isolation_failed`. Every failure
stops before model execution. Invocation evidence records only authentication and
protocol classifications, required Agent names, and probe exit codes; it never records
account identity, authentication contents, or raw Agent/Skill output. Binary lookup,
version, preflight, execution, and timeout failures all produce attempt-local
invocation/result/error evidence, and temporary runtime directories are removed on every
path.

Primary uses the same isolated temporary `HOME`/`CODEX_HOME`, but intentionally keeps
Codex session persistence enabled inside that disposable store. Codex collaboration
resolves the parent through the thread store; `codex exec --ephemeral` suppresses that
rollout and made the saved Primary attempts fail with `no thread` and `no rollout
found`. The temporary store is deleted after the attempt. Deterministic runner tests
prove this launch shape, not live Agent spawning; fresh Primary model evidence must
still verify collaboration end to end.

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
once and preserves only contract-backed precedence, so
removing a required candidate, review, publication, or feedback-loop stage still fails
even when repository, artifact, tracker, and validation state are correct. Extra
recorded stages do not themselves prove duplicate exploration; only completed runtime
trace calls can produce the attributable `extra_exploration_call` delta.

For Spec scenarios the evaluator follows the portable coordinator order: an eligible
Ultra independent-code pre-pass, target-native exploration, target artifact, fresh
review, then validation. Ticket publication and validation must each execute exactly
once after complete-set review, but their relative order is not a hidden requirement.

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
`never`; it does not bypass the sandbox or disable its temporary thread store. Model
eval runs require committed refs.
The runner resolves both requested refs before preparing a fixture and prepares
directly from those immutable SHAs, so recorded provenance cannot race a moving ref.
`working-tree` remains available only to `prepare-fixture.py` for deterministic
constructor/grader tests because uncommitted contents cannot be truthfully named by
a commit SHA.

The generated prompt is contract-only: it does not contain a slash invocation and
forbids the runtime `Skill` tool and installed/global skill contracts. The runner also
uses an ephemeral user configuration root and isolated `HOME`. Qoder starts with only
the ambient `.qoder/.auth` bridge, project-only settings, and disabled built-in
skills; it does not copy settings, skills, or plugins. The strictly parsed token-free
Qoder preflight independently proves that required built-in Agents remain available
while no Skill is discoverable, under the same shared isolation arguments as the model
call. Primary receives an isolated `HOME`/`CODEX_HOME` containing only an auth
link. Temporary runtime state is removed after every outcome. Runtime traces independently
fail any observed `Skill` invocation, so the supplied treatment/ablation contracts are the
only admissible workflow inputs.

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

For an ordinary matrix comparison, add `--pair-verdict` instead of
`--canary-gate`. The runner assigns one evaluator-owned `pair_id` to both attempts and
writes a `pair-verdict-*.json` after both complete. Its identity includes runtime and
version, model, context/reasoning/timeout settings, scenario, and both immutable
treatment/ablation refs. The generator rejects mismatched arms rather than discovering
or guessing a partner across concurrent attempts. Verdict files include the pair
identity and attempt numbers and are created exclusively, so retries cannot overwrite
an older verdict. Repository, validation, write-set, tracker, or artifact failure keeps
the ablation evidence invalid and can never yield an attributable difference.

Existing attempts may be classified without a model run by copying their
`invocation.json`, `result.json`, `grader-control.json`, `fixture-manifest.json`, and
literal or temporary regraded `grader-stdout.json` to a temporary matching
run/scenario tree, then running:

```bash
python3 tests/evals/ultra-complementary-profiles/pair_verdict.py \
  --treatment-attempt /tmp/<run>/<scenario>/treatment/attempt-001 \
  --ablation-attempt /tmp/<run>/<scenario>/ablation/attempt-001 \
  --output /tmp/<run>/<scenario>
```

Legacy attempts without a shared `pair_id` must be supplied explicitly. The generator
still requires matching runtime/model/settings/scenario/refs and one shared copied
run/scenario root; it never auto-pairs attempt numbers.

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
events, including validation launched through ordinary `sh -c`, `bash -lc`,
command-substitution wrappers, absolute paths under the declared command cwd, and
file-descriptor redirects such as `2>&1`, so repeated executions cannot hide behind
those forms. Qoder background Agent launches become completed calls only after the
later task event reports a terminal `completed` state; failed, stopped, duplicated, or
never-completed tasks remain failures. Every behavior-sensitive scenario has external
evidence through stage markers, red/green command order, immutable file changes,
publication adapter receipt, or a no-delegation cap. The grader also
records primary-runtime delegated model identity as `unknown/unavailable` when the
Codex JSONL protocol does not expose it.

This harness supports the later four-model matrix, but one smoke pair is not that
matrix and must not be described as a complete model-adherence eval.
