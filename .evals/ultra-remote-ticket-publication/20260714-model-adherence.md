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
- Fresh run root: `/tmp/ultra-remote-publication-model-eval`
- Fresh Agent: Codex subagent `/root/remote_publication_model_eval`
- Model and reasoning settings: unavailable from the subagent runtime; this
  record makes no stronger model or configuration claim.

The fresh run was graded with:

```sh
python3 .evals/ultra-remote-ticket-publication/scripts/grade-run.py \
  /tmp/ultra-remote-publication-model-eval
```

It returned `{"passed": true, "failures": []}`.

## Scenarios and final-state grade

| Scenario | Required final state | Result |
| --- | --- | --- |
| GitHub remote review-pending | Exact run members are re-read and promoted only as a complete ready set. | pass |
| GitLab human-owned choice | An escalation remains and no remote Ticket is created. | pass |
| GitHub local staging | Reviewed members publish, verify, promote, then remove staging. | pass |
| GitLab local staging | Reviewed members publish, verify, promote, then remove staging. | pass |

## Deterministic coverage

`tests/ultra-remote-ticket-publication.sh` exercises GitHub and GitLab for
both publication strategies, with injected failures after create, wire,
verify, and promote. It verifies durable recovery, idempotent resume,
provider-native and textual-fallback relationship representations,
complete-set ready promotion, and staging cleanup only after final
verification. The eval harness separately proves the constructor and grader
agree on the four model-adherence scenario outcomes.

## Provenance boundary

The final-state grader proves that retained files satisfy the scenario
contract. The named subagent is in-session evidence that an Agent produced the
fresh run. Neither the files nor the grader cryptographically proves a model
identity, hidden reasoning settings, or cross-model coverage.
