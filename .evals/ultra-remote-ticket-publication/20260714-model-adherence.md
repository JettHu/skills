# Remote Ticket publication model adherence

Date: 2026-07-14

## Evidence type

One fresh-context Agent run and a deterministic final-state grader. The Agent
read only the prepared scenario prompts, did not read the expectations or
grader, and was graded from retained remote-state and escalation files rather
than response prose.

## Durable harness

- Constructor: `scripts/prepare-fixture.py`
- Grader: `scripts/grade-run.py`
- Deterministic harness: `tests/ultra-remote-ticket-publication-eval.sh`
- Fresh run root: `/tmp/ultra-remote-ticket-publication-model-eval-20260714-fix-rerun`
- Fresh Agent: Codex subagent `/root/remote_eval_rerun`
- Model and reasoning settings: unavailable from the subagent runtime; this
  record makes no stronger model or configuration claim.

The fresh run was graded with:

```sh
python3 .evals/ultra-remote-ticket-publication/scripts/grade-run.py \
  /tmp/ultra-remote-ticket-publication-model-eval-20260714-fix-rerun
```

It returned `{"passed": true, "failures": []}`.

## Scenarios and final-state grade

| Scenario | Required final state | Result |
| --- | --- | --- |
| GitHub remote review-fix | A verify-phase failure leaves provisional state; a reviewer body repair resumes and promotes the exact set. | pass |
| GitLab remote review-fix | A verify-phase failure leaves provisional state; a reviewer body repair resumes and promotes the exact set. | pass |
| GitHub local staging recovery | A wire-phase failure retains a manifest snapshot; resume verifies, promotes, and removes staging. | pass |
| GitLab local staging recovery | A wire-phase failure retains a manifest snapshot; resume verifies, promotes, and removes staging. | pass |
| GitLab human-owned choice | An escalation remains and no remote Ticket is created. | pass |

## Deterministic coverage

`tests/ultra-remote-ticket-publication.sh` exercises GitHub and GitLab for
both publication strategies, with injected failures after create, wire,
verify, and promote. It verifies durable recovery, idempotent resume,
provider-native and textual-fallback relationship representations,
complete-set ready promotion, reviewer-body retention, and staging cleanup
only after final verification. The eval harness separately proves the
constructor and grader agree on five model-adherence scenario outcomes,
including remote review repair and partial staging recovery.

## Provenance boundary

The final-state grader proves that retained files satisfy the scenario
contract. The named subagent is in-session evidence that an Agent produced the
fresh run. Neither the files nor the grader cryptographically proves a model
identity, hidden reasoning settings, or cross-model coverage.
