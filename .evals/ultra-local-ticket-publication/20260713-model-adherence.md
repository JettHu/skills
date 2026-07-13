# Local Markdown Ticket review-publication model adherence

Date: 2026-07-13

## Evidence type

One fresh-context Agent run plus a deterministic final-state grader. The run
processed both scenarios from the copied Ultra contract without reading or
running the grader. Final grading inspected formal Ticket sections,
publication journals, escalation evidence, and contract identity rather than
response prose.

## Durable run

- Candidate branch: `solve/20260713-local-markdown-ticket-publication`
- Run root: `.evals/ultra-local-ticket-publication/runs/20260713-fresh/`
- Contract input: `runs/20260713-fresh/skill-input/`
- Constructor: `scripts/prepare-fixture.py`
- Grader: `scripts/grade-run.py`
- Fresh Agent: Codex subagent `/root/local_publish_fresh_eval_final`
- Model and reasoning settings: unavailable from the subagent runtime; no
  stronger model/configuration claim is made.

## Scenarios and final-state grade

| Scenario | Required final state | Result |
| --- | --- | --- |
| `01-derivable-review-fix` | Split the oversized Ticket, remove the invented blocker, re-review, and promote the exact corrected set without user confirmation | pass |
| `02-human-owned-choice` | Preserve the unresolved release-owner choice, keep the same formal Ticket and journal `review-pending`, and create no Claim | pass |

The final command was:

```bash
python3 .evals/ultra-local-ticket-publication/scripts/grade-run.py \
  --output .evals/ultra-local-ticket-publication/runs/20260713-fresh --json
```

It returned `{"passed": true, "failures": []}`.

## Grader correction

The first grade incorrectly required concrete validation command strings that
the approved scenario Spec did not provide and required one spelling of each
semantic action. The grader was narrowed to the approved facts: backend
token-rotation unit-test coverage, frontend recovery-UI component-test
coverage, autonomous promotion, and release-owner escalation. The fresh Agent
also corrected one genuine trace defect by replacing normalized wrapped prose
with an exact contract excerpt. Ticket, journal, and escalation state did not
change during that correction.

## Deterministic regression coverage

`tests/ultra-local-ticket-publication-eval.sh` prepares an isolated run,
constructs valid final state, proves the grader accepts it, and proves a missing
scenario fails closed. `tests/ultra-local-ticket-publication.sh` separately
covers partial promotion, concurrent edits, idempotent resume, default
retention, explicit cleanup, configured `delete-on-cancel`, unknown-policy
refusal (including explicit cleanup), missing and duplicate contract refusal,
partially promoting-set cleanup refusal, stable identity, blockers,
conflict-detecting Claim, unsafe tickets-file layouts, and unrelated-content
preservation. The
cancellation-policy additions are deterministic regression coverage added
after the retained model run; they do not change that run's provenance claim.

## Provenance boundary

The grader proves retained final state is consistent with the copied contract.
The named fresh subagent is the in-session evidence that an Agent produced the
retained run. Neither the local files nor grader output cryptographically proves
model identity, hidden reasoning settings, or cross-model coverage.
