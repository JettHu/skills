# Canonical Ultra routing model-adherence run

Date: 2026-07-13

## Evidence Type

One fresh-session model-adherence run plus a deterministic final-state grader.
The session executed each requested `/ultra <target>` route using the candidate
core runbook and installed shaping targets. The grader checks routing decisions
and generated artifacts, not response prose.

## Fixture And Runtime

- Candidate checkout: `/Users/lingjie/workspace/jett-skills-worktree-solve-20260713-canonical-ultra-v1-1-routing`
- Final fixture root: `/tmp/ultra-canonical-routing-20260713-isolated`
- Constructor: `scripts/prepare-fixture.py --source <candidate>`
- Grader: `scripts/grade-run.py`
- Fresh session: Codex Desktop child session `/root/canonical_routing_eval_isolated`
- Model and reasoning settings: unavailable from the child-session runtime; no stronger configuration claim is made.

The constructor copied only the candidate `ultra` runbook and profile contract
into the isolated fixture's `skill-input/` directory. The child session read
that supplied input, executed the requested routes against isolated artifacts,
and had no fixture grader or expected-result map in its supplied input.

## Scenarios And Final-State Grade

| Scenario | Final-state assertion | Result |
| --- | --- | --- |
| `01-to-spec-bounded` | `to-spec` selected code exploration only; fresh review skipped | pass |
| `02-to-spec-high-risk` | `to-spec` selected code exploration and fresh review; research stayed off because local approved context settled external facts | pass |
| `03-to-tickets-local` | `to-tickets` selected code exploration and fresh review; generic decomposition research stayed off | pass |
| `04-to-tickets-external-fact` | `to-tickets` enabled research only for the unresolved official fact that directly determined an acceptance criterion | pass |
| `05-review-fix` | main Agent repaired the exact Ticket artifact from approved context, replaced `Issue` with `Ticket`, added the source-derived route/auth/validation facts, and re-reviewed it | pass |
| `06-human-owned-choice` | unresolved release ownership produced an escalation rather than an invented Ticket or blocker edge | pass |
| `07-legacy-bridge` | the still-promoted `to-prd` route resolved through the temporary `to-spec` bridge without becoming a canonical example | pass |

The final command was:

```bash
python3 .evals/ultra-canonical-routing/scripts/grade-run.py \
  --output /tmp/ultra-canonical-routing-20260713-isolated --json
```

It returned `{"passed": true, "failures": []}`.

## Corrections During Evaluation

An initial fixture exposed its expected routing map to the child and merely
asked for a self-reported JSON result. That attempt is not used as adherence
evidence. The fixture was corrected so the child receives only realistic route
prompts, approved artifact context, and a copied runbook/profile input; the
grader and expected decisions are excluded from the supplied fixture input. A
later real run found that the review-fix wording did not explicitly
repair old `Issue` terminology. Core Ultra was updated to require canonical
`Ticket` terminology, and the corrected fresh-session run above passed.

## Provenance Boundary

The final-state grade proves the isolated artifacts satisfy the routing and
review-fix assertions. The retained child-session reference is the in-session
evidence that an Agent produced those artifacts. Neither local files nor the
grader output cryptographically proves model identity or provides cross-model
coverage.
