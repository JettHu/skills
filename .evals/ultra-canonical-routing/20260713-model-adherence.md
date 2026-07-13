# Canonical Ultra routing model-adherence run

Date: 2026-07-13

## Evidence Type

One fresh-session model-adherence run plus a deterministic final-state grader.
The fresh session wrote durable `routing-decision.json` artifacts for every
scenario. The grader recomputes the supplied runbook/profile contract identity,
checks each trace against it, and grades the generated artifact or escalation
where relevant.

## Durable Run

- Candidate checkout: `/Users/lingjie/workspace/jett-skills-worktree-solve-20260713-canonical-ultra-v1-1-routing`
- Run root: `.evals/ultra-canonical-routing/runs/20260713-trace-fresh/`
- Contract input: `runs/20260713-trace-fresh/skill-input/`
- Contract identity: `runs/20260713-trace-fresh/contract-manifest.json`
- Constructor: `scripts/prepare-fixture.py --source <candidate>`
- Grader: `scripts/grade-run.py`
- Fresh session: Codex Desktop child session `/root/trace_fresh_eval`
- Model and reasoning settings: unavailable from the child-session runtime; no stronger configuration claim is made.

The session was given the durable run's `AGENT_PROMPT.md`, `skill-input/`, and
scenario files. It did not run the grader. The stored scenario directories
retain its seven routing-decision traces, the repaired Ticket artifact, and the
human-owned escalation artifact.

## Scenarios And Final-State Grade

| Scenario | Final-state assertion | Result |
| --- | --- | --- |
| `01-to-spec-bounded` | `to-spec` code exploration; review skipped | pass |
| `02-to-spec-high-risk` | `to-spec` fresh review enabled; research stayed off | pass |
| `03-to-tickets-local` | `to-tickets` code and fresh review; research stayed off | pass |
| `04-to-tickets-external-fact` | `to-tickets` research enabled only for the qualifying external fact | pass |
| `05-review-fix` | exact Ticket artifact repaired from approved context and re-reviewed | pass |
| `06-human-owned-choice` | release ownership escalated without inventing a Ticket or blocker edge | pass |
| `07-legacy-bridge` | legacy `to-prd` resolved through the temporary `to-spec` bridge | pass |

The command was:

```bash
python3 .evals/ultra-canonical-routing/scripts/grade-run.py \
  --output .evals/ultra-canonical-routing/runs/20260713-trace-fresh --json
```

It returned `{"passed": true, "failures": []}`.

## Regression Coverage

`tests/ultra-canonical-routing.sh --expand` constructs a temporary trace run
and proves the grader passes valid traces but fails closed for both a mismatched
decision contract identity and post-trace mutation of the supplied profile
input.

## Historical Note

The earlier `/tmp/ultra-canonical-routing-20260713-isolated` run used the
superseded self-reported `result.json` format. It is not used as routing
decision evidence and its old grader command is intentionally not replayed.

## Provenance Boundary

The grader proves the durable artifacts and routing-decision traces are
consistent with the supplied contract. The child-session reference is the
in-session evidence that an Agent produced the retained run. Neither local
files nor grader output cryptographically proves model identity, actual target
execution, or cross-model coverage.
