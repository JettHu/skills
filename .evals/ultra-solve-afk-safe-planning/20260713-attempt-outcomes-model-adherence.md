# Ultra Solve Attempt-Outcome Model-Adherence Run

Date: 2026-07-13

## Scope And Evidence Boundary

- Treatment ref: `4bf8d66` (`feat(ultra-solve): finalize outcome attempt receipts`).
- Recovery-field correction ref: `65e34fc` (`fix(eval): grade retained recovery resources`).
- Final grader and review-fix ref: `f89bdc0` (`fix(ultra-solve): close outcome review gaps`).
- Run id: `20260713-4bf8d66` under `/tmp/ultra-solve-attempt-outcomes/`.
- Required scenarios: candidate success (`01-simple`), retained failed Attempt (`07-failed-check-retained`), and same-context resume (`08-resume-reuse`).
- Runtime: three fresh Codex collaboration subagents with no model override supplied by the coordinator. The subagent service did not expose model id or reasoning settings, so this record does not infer them.

The coordinator received completion notifications from the three fresh agents named below and then graded their final repositories. Those notifications are the run trace available in the active Codex task; this durable record preserves the exact dispatch text, treatment, grader, and final-state evidence. It does not claim a multi-model run or independently attest model identity.

## Fixture Construction

```bash
python3 .evals/ultra-solve-afk-safe-planning/scripts/prepare-fixture.py \
  --output /tmp/ultra-solve-attempt-outcomes \
  --run-id 20260713-4bf8d66 \
  --scenario all \
  --treatment-ref 4bf8d66
```

Each generated repository contained the committed `EVAL_PROMPT.md`, embedded Ultra/Solve Record contracts, a tagged `eval-base`, and immutable `EVAL_EXPECTATIONS.json`. The candidate and failed-Attempt agents created isolated solve worktrees. The resume fixture started with a real `solve/eval-resume` branch, registered `resume-worktree`, open `outcome: blocked` receipt, and one Ticket backlink.

## Exact Dispatch Text

All three sessions were fresh (`fork_turns: none`). Their dispatches were:

### Candidate

```text
This is a model-adherence run in an isolated fixture. Working directory: /tmp/ultra-solve-attempt-outcomes/20260713-4bf8d66/01-simple/repo. Read EVAL_PROMPT.md and execute it exactly as the user request. Read the embedded AGENTS.md and skill files it names. Do not edit EVAL_EXPECTATIONS.json. Do not merge, push, or clean up. Leave final repository, Ticket, receipt, Git refs/worktree, and validation state for an external grader. Return only a concise run result when finished.
```

Agent: `/root/eval_candidate_run`

### Failed Attempt

```text
This is a model-adherence run in an isolated fixture. Working directory: /tmp/ultra-solve-attempt-outcomes/20260713-4bf8d66/07-failed-check-retained/repo. Read EVAL_PROMPT.md and execute it exactly as the user request. Read the embedded AGENTS.md and skill files it names. Do not edit EVAL_EXPECTATIONS.json or weaken/change the required validation script or staging marker. Do not merge, push, or clean up. Leave final repository, Ticket, recovery receipt, retained Git resources, Claim disposition, Digest, and failed-check evidence for an external grader. Return only a concise run result when finished.
```

Agent: `/root/eval_failed_run`

### Resume

```text
This is a model-adherence run in an isolated fixture. Working directory: /tmp/ultra-solve-attempt-outcomes/20260713-4bf8d66/08-resume-reuse/repo. Read EVAL_PROMPT.md and execute it exactly as the user request. Read the embedded AGENTS.md and skill files it names. Do not edit EVAL_EXPECTATIONS.json. Resume the existing retained branch/worktree and recovery context; do not make a clean restart. Do not merge, push, or clean up. Leave final repository, Ticket, reused receipt, Git refs/worktree, Claim disposition, and validation state for an external grader. Return only a concise run result when finished.
```

Agent: `/root/eval_resume_run`

## Final-State Grading

```bash
python3 .evals/ultra-solve-afk-safe-planning/scripts/grade-run.py --json \
  /tmp/ultra-solve-attempt-outcomes/20260713-4bf8d66/01-simple/repo \
  /tmp/ultra-solve-attempt-outcomes/20260713-4bf8d66/07-failed-check-retained/repo \
  /tmp/ultra-solve-attempt-outcomes/20260713-4bf8d66/08-resume-reuse/repo
```

| Scenario | Graded final state | Result |
| --- | --- | --- |
| Candidate success | Ticket `completed`; Claim released; exactly one Ticket backlink; canonical `outcome: candidate` receipt; live candidate fields; ready candidate dashboard route; retained clean worktree; `scripts/check.py` passed; no Digest residue. | Pass |
| Retained failed Attempt | Ticket `ready-for-human`; Claim released; exactly one backlink and `outcome: blocked` receipt; Digest retained; solve branch/worktree/commit retained and named; no candidate-gate fields; recovery dashboard route; required staging check still failed with the recorded marker error. | Pass |
| Same-context resume | Base receipt was `outcome: blocked`; Ticket reclaimed and completed; Claim released; receipt id/path `08-resume-reuse` reused in place; exactly one receipt and backlink; same `solve/eval-resume` branch and `resume-worktree`; canonical candidate route; `scripts/check.py` passed; no Digest residue. | Pass |

Every grader result had an empty `failed` list.

## Grader Correction

The first failed-Attempt grade reported one false failure because the earlier grader treated any recovery `worktree` field as candidate-only. The canonical format explicitly permits optional recovery `branch`, `worktree`, and `commit` references. Ref `65e34fc` narrowed the negative assertion to candidate comparability fields (`base`, `base_sha`, `head`, `head_sha`). Post-Execution Review then found that retained-commit linkage was still asserted only in prose; ref `f89bdc0` added branch-head, worktree-head, Ticket-link, and receipt-link checks plus the deterministic recovery-resource fixture. The same untouched model-run repository passed both corrections while remaining excluded from candidate gates.

## Interpretation

These runs support adherence for the three required finalization paths on one Codex runtime: successful candidate creation after review, meaningful failed-check recovery with retained resources, and idempotent same-context resume into the original receipt. They do not establish cross-model behavior, and the local final-state grader proves repository/receipt/Git outcomes rather than model identity.
