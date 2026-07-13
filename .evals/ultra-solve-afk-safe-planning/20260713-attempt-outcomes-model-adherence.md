# Ultra Solve Attempt-Outcome Model-Adherence Run

Date: 2026-07-13

## Scope And Evidence Boundary

- Treatment ref: `cd717cbbe77aab699e784116096e0bdc99bc9edc` (`fix(eval): make outcome runs auditable`).
- Run id: `20260713-cd717cb` under `/tmp/ultra-solve-attempt-outcomes/`.
- Required scenarios: candidate success (`01-simple`), retained failed Attempt (`07-failed-check-retained`), and same-context resume (`08-resume-reuse`).
- Superseded evidence: the earlier `20260713-4bf8d66` sessions exercised a pre-review treatment and are not acceptance evidence for this final treatment.

The coordinator received completion notifications from all three fresh agents and then graded their final repositories. This record preserves the exact treatment, fixture commands, dispatch text, available runtime settings, literal grader output, and final-state result. It does not claim a multi-model run or independently attest model identity.

## Runtime And Settings

| Field | Recorded value |
| --- | --- |
| Runtime | Codex collaboration subagent service |
| Session isolation | Three fresh sessions with `fork_turns: none` |
| Model override | None supplied by the coordinator |
| Model id | `unavailable` — the subagent service did not expose it |
| Reasoning setting | `unavailable` — the subagent service did not expose it |
| Candidate agent | `/root/eval_candidate_cd717cb` |
| Failed-Attempt agent | `/root/eval_failed_cd717cb` |
| Resume agent | `/root/eval_resume_cd717cb` |

Unavailable fields are recorded explicitly rather than inferred. Reproduction pins the committed treatment, fixture constructor, exact prompt text, session-isolation setting, and grader below; exact model identity cannot be reproduced from the runtime metadata exposed to the coordinator.

## Fixture Construction

```bash
python3 .evals/ultra-solve-afk-safe-planning/scripts/prepare-fixture.py \
  --output /tmp/ultra-solve-attempt-outcomes \
  --run-id 20260713-cd717cb \
  --scenario 01-simple \
  --treatment-ref cd717cbbe77aab699e784116096e0bdc99bc9edc
python3 .evals/ultra-solve-afk-safe-planning/scripts/prepare-fixture.py \
  --output /tmp/ultra-solve-attempt-outcomes \
  --run-id 20260713-cd717cb \
  --scenario 07-failed-check-retained \
  --treatment-ref cd717cbbe77aab699e784116096e0bdc99bc9edc
python3 .evals/ultra-solve-afk-safe-planning/scripts/prepare-fixture.py \
  --output /tmp/ultra-solve-attempt-outcomes \
  --run-id 20260713-cd717cb \
  --scenario 08-resume-reuse \
  --treatment-ref cd717cbbe77aab699e784116096e0bdc99bc9edc
```

Each generated repository contained the committed `EVAL_PROMPT.md`, embedded Ultra and Solve Record contracts including `references/edge-cases.md`, a tagged `eval-base`, and immutable `EVAL_EXPECTATIONS.json`. The candidate and failed-Attempt agents created isolated solve worktrees. The resume fixture started with a real `solve/eval-resume` branch, registered `resume-worktree`, open `outcome: blocked` receipt, and one Ticket backlink.

## Exact Dispatch Text

### Candidate

```text
This is a model-adherence run in an isolated fixture. Working directory: /tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/01-simple/repo. Read EVAL_PROMPT.md and execute it exactly as the user request. Read the embedded AGENTS.md and skill files it names. Do not edit EVAL_EXPECTATIONS.json. Do not merge, push, or clean up. Leave final repository, Ticket, receipt, Git refs/worktree, and validation state for an external grader. Return only a concise run result when finished.
```

### Failed Attempt

```text
This is a model-adherence run in an isolated fixture. Working directory: /tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/07-failed-check-retained/repo. Read EVAL_PROMPT.md and execute it exactly as the user request. Read the embedded AGENTS.md and skill files it names. Do not edit EVAL_EXPECTATIONS.json or weaken/change the required validation script or staging marker. Do not merge, push, or clean up. Leave final repository, Ticket, recovery receipt, retained Git resources, Claim disposition, Digest, and failed-check evidence for an external grader. Return only a concise run result when finished.
```

### Resume

```text
This is a model-adherence run in an isolated fixture. Working directory: /tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/08-resume-reuse/repo. Read EVAL_PROMPT.md and execute it exactly as the user request. Read the embedded AGENTS.md and skill files it names. Do not edit EVAL_EXPECTATIONS.json. Resume the existing retained branch/worktree and recovery context; do not make a clean restart. Do not merge, push, or clean up. Leave final repository, Ticket, reused receipt, Git refs/worktree, Claim disposition, and validation state for an external grader. Return only a concise run result when finished.
```

## Final-State Grading

Command:

```bash
python3 .evals/ultra-solve-afk-safe-planning/scripts/grade-run.py --json \
  /tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/01-simple/repo \
  /tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/07-failed-check-retained/repo \
  /tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/08-resume-reuse/repo
```

Exit code: `0`

| Scenario | Final-state result |
| --- | --- |
| Candidate success | Pass |
| Retained failed Attempt | Pass |
| Same-context resume | Pass |

Literal output:

```json
[
  {
    "scenario": "01-simple",
    "repo": "/tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/01-simple/repo",
    "passed": [
      "Ticket exists",
      "Ticket status is completed",
      "Ticket has no inline Digest",
      "linked receipt exists",
      "receipt passes canonical parser",
      "receipt outcome is candidate",
      "Ticket links the selected receipt exactly once",
      "receipt is classified by canonical dashboard",
      "no unnecessary external Digest",
      "candidate handoff released the Claim",
      "candidate has live Git fields",
      "candidate uses a candidate dashboard route",
      "candidate check passes"
    ],
    "failed": []
  },
  {
    "scenario": "07-failed-check-retained",
    "repo": "/tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/07-failed-check-retained/repo",
    "passed": [
      "Ticket exists",
      "Ticket status is ready-for-human",
      "Ticket has no inline Digest",
      "linked receipt count is 1",
      "linked receipt exists",
      "receipt passes canonical parser",
      "receipt outcome is blocked",
      "Ticket links the selected receipt exactly once",
      "Claim is released",
      "Ticket backlink count is 1",
      "receipt is classified by canonical dashboard",
      "external Digest exists",
      "Digest contains Strategy:",
      "Digest contains Validation plan:",
      "recovery receipt has no candidate-gate fields",
      "recovery receipt uses recovery dashboard route",
      "retained resources contain solve/",
      "retained resources contain worktree",
      "retained solve worktree is registered",
      "receipt names the retained registered branch and worktree",
      "receipt stores retained branch, worktree, and commit fields",
      "retained commit equals branch head",
      "retained commit equals worktree head",
      "Ticket resource surface links the retained branch, worktree, and commit",
      "receipt outcome names the retained branch, worktree, and commit",
      "required staging validation still fails on the retained Attempt",
      "receipt preserves failed-check evidence"
    ],
    "failed": []
  },
  {
    "scenario": "08-resume-reuse",
    "repo": "/tmp/ultra-solve-attempt-outcomes/20260713-cd717cb/08-resume-reuse/repo",
    "passed": [
      "Ticket exists",
      "Ticket status is completed",
      "Ticket has no inline Digest",
      "linked receipt count is 1",
      "linked receipt exists",
      "receipt passes canonical parser",
      "receipt outcome is candidate",
      "Ticket links the selected receipt exactly once",
      "receipt id remains 08-resume-reuse",
      "Claim is released",
      "Ticket backlink count is 1",
      "base receipt outcome is blocked",
      "resume reused the original receipt path",
      "receipt is classified by canonical dashboard",
      "no unnecessary external Digest",
      "candidate handoff released the Claim",
      "candidate has live Git fields",
      "candidate uses a candidate dashboard route",
      "candidate head remains solve/eval-resume",
      "candidate worktree remains resume-worktree",
      "candidate check passes"
    ],
    "failed": []
  }
]
```

## Interpretation

All three required final-treatment sessions passed the committed final-state grader with empty `failed` lists. The evidence supports candidate creation after review, retained failed-check recovery with live Git-resource linkage, and idempotent same-context resume into the original receipt on the recorded Codex runtime. It does not establish cross-model behavior, and final-state grading proves repository, Ticket, receipt, Claim, and Git-resource outcomes rather than model identity.
