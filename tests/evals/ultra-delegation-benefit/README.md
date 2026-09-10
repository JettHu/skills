# Fixed-model delegation benefit experiment (ASC-04)

This bounded experiment reuses the stage-ownership harness's isolated Git fixtures,
real tasks, retained candidate and canonical receipt grading pattern. It deliberately
replaces that older harness's forced-route prompts and model-authored event oracle.
The original diagnosis case is a simple repair smoke; `diagnosis-v2` adds symptom-driven replay across event identity, revisions, projection and report-cache interactions. Run its separate pair for diagnosis evidence. Production skill files are never edited. No result authorizes changing defaults.

Prepare each of `local`, `cross-module`, `diagnosis`, `permission`, and
`worker-failure` once with each policy:

```sh
python3 tests/evals/ultra-delegation-benefit/fixture.py prepare /absolute/eval/local-current --case local --policy current
python3 tests/evals/ultra-delegation-benefit/fixture.py prepare /absolute/eval/local-benefit --case local --policy benefit
python3 tests/evals/ultra-delegation-benefit/test_fixture.py
```

Use a fresh output path. The complete tracked skill catalog and bundled tracker
context are copied into each fixture. The tracker context is a durable copy of
canonical catalog documents, so ignored historical `.scratch` state is not a
prerequisite. Actual publication register/promote/frontier run at prepare time;
the deterministic test additionally proves actual Claim, native worktree creation,
canonical handoff and parsing. No mock lifecycle facade is substituted.

The treatment changes only the copied `ultra/solve.md`: Stage Ownership's narrow
six-predicate direct branch and objective fallback wording, the Checkpoint
six-predicate reminder, and implementation step 2's docs/config reminder. It uses
parallel progress, context isolation and independent judgment benefits versus cost.
Both copies retain one writer, root synthesis/integration, required risk review,
canonical Claim/outcome gates, and no landing authority. File-hash comparison in
the deterministic test proves only this policy file differs for paired fixtures.

Run from the fixture repository with the same actual CLI, model, effort, tools,
permissions and wall-time limit for every pair. The tested host has Astra support
in `/Applications/ChatGPT.app/Contents/Resources/codex` (0.153.4); the older PATH
CLI is not equivalent. The bounded runner records the exact invocation, hashes, wall time and exit status:

```sh
python3 tests/evals/ultra-delegation-benefit/run.py /absolute/eval/local-current
```

Equivalent raw CLI invocation (redirect the prompt using the shell):

```sh
/Applications/ChatGPT.app/Contents/Resources/codex exec --ignore-user-config --enable multi_agent -m gpt-6-astra -c 'model_reasoning_effort="high"' -c 'approval_policy="never"' -s danger-full-access --json -C /absolute/eval/local-current/repo - < /absolute/eval/local-current/prompt.md > /absolute/eval/local-current/root.jsonl 2> /absolute/eval/local-current/stderr.log
```

Use an external timeout of 600 seconds per run; preserve its exit status, timestamps,
CLI version, exact invocation and prompt hash. Stop remaining child work before
inspecting a timeout. Do not use `--ephemeral`: native child rollouts are required.
Git metadata must be writable identically in both variants. These fixtures contain
no production data or services. Runtime transport failures are unavailable evidence,
not model quality failures. Do not change settings halfway through a pair.

```sh
python3 tests/evals/ultra-delegation-benefit/collect-traces.py /absolute/eval/local-current --sessions "$HOME/.codex/sessions/2026/09/09"
python3 tests/evals/ultra-delegation-benefit/fixture.py grade /absolute/eval/local-current
```

`oracle.json` stays outside the model worktree, read-only, and pins initial main,
protected content hashes, application allowlist and behavioral oracle. Archive its
hash before model execution, and verify the hash afterward; read-only file mode is
not an OS security boundary under unrestricted permissions. The grader uses the
external checks and repository's trusted parser, never edited candidate tests or
model event assertions. It checks preserved main, real registered candidate
worktree/common Git directory, ancestry, clean state, exact compact receipt head,
Ticket release, scope and protected files. A forged passing checker is rejected.

Artifact grading is only one evidence layer. A root reviewer must inspect native
root and child calls and outputs, actual diffs, refs and checks. Establish writer
assignment/start/stop intervals and root re-read/integration; audit all shell and
patch writes, not only `apply_patch`. Independent review must actually inspect the
candidate against the Ticket and applicable checks. Diagnose explanation quality
from its reproducer and causal account: the length check proves presence only.
`collect-traces.py` copies only root and metadata-linked descendants and preserves
native usage objects. Missing child logs or token totals remain unavailable, never
zero or inferred from root-only usage. Native tool logs may be incomplete; report
an unresolved evidence boundary instead of an ownership pass.

The worker-failure case injects one preflight tool failure via a marker in the
fixture's Git common directory. It ends the assigned writer stage. Evidence counts
as **worker-stage tool failure with coordinator recovery** only when a real worker
hits it, relinquishes writing, and root confirms stop before resuming once. A root
preflight failure, same-worker auto-retry, or model-authored failure story does not
establish that case. This does not simulate a lost process/network worker. If
routing never selects a worker, record the recovery comparison as unexercised;
never alter the prompt to force a preferred route after seeing results.

Assess scope/authority and ownership violations first, correctness and necessary
evidence second, then measured cost/latency. One run per cell is descriptive
case evidence, not statistical superiority. Retaining the current default is a
valid conclusion. Historical run output belongs only under `.evals/asc-04/`, not
in this harness or default CI.
