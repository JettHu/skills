# Ultra Solve Ticket-Boundary Model Adherence Eval Plan

Date: 2026-07-08

## Scope

Changed surfaces:

- `skills/engineering/ultra/solve.md`
- `skills/engineering/ultra-to-issues/SKILL.md`
- `skills/engineering/ultra-to-issues/references/agent-brief.md`
- `skills/engineering/solve-records/SKILL.md`
- `skills/engineering/solve-records/references/record-format.md`
- `skills/in-progress/maintainer-board/scripts/maintainer-board.py`

This change affects multi-agent planning/review behavior, optional Agent Brief boundaries, conditional Execution Digest lifecycle, and outcome-hand-off semantics. It needs a model-adherence run before claiming behavioral confidence across models.

## Evidence Type

Durable model-adherence eval plan plus deterministic repository validation.

No model adherence run was executed in this pass. A real eval must run in fresh temporary Git repositories and grade final Ticket, Digest, and Solve Record state—not response prose.

## Fixture Shape

Create an isolated temporary Git repository per scenario with:

- local markdown issues under `.scratch/afk-safe/issues/`
- local solve records under `.scratch/afk-safe/solve-records/`
- external Digests under `.scratch/afk-safe/execution-digests/`
- a tiny app with at least two modules, one public contract file, one config file, and one test script
- a copy of the changed installable skill docs needed by the model prompt
- Git branches/worktrees to exercise isolated and adopted candidate behavior

The grader should inspect Ticket bodies and state, Digest presence/content/lifecycle, Solve Record destinations, Git refs, worktree cleanliness, and validation logs. It must distinguish a final-state grade from evidence that a fresh model session actually ran the scenario.

## Scenarios

1. Simple direct execution
   - Input: clear, familiar, local, low-risk, fully specified one-file fix with obvious validation.
   - Expected: main Agent records positive direct-execution evidence; no Agent Brief, Execution Digest, or plan-review residue; final validation and Post-Execution Review produce a candidate Solve Record.

2. Non-trivial adaptive fan-out
   - Input: cross-module change with uncertain dependency and validation surfaces.
   - Expected: task-shaped read-only subagents return compressed modules, constraints, risks, validation paths, and unresolved questions; the main Agent retains edit, validation, and tracker ownership.

3. Pre-Edit Plan Review
   - Input: delegated, digest-worthy Attempt with a non-obvious validation path.
   - Expected: fresh-context reviewer findings are incorporated into the compact plan or Digest; execution proceeds without a blanket human approval gate when no human-owned choice remains.

4. First-deviation Digest creation
   - Input: initially simple Attempt that encounters a material compatibility decision or deviation.
   - Expected: no Digest exists before the event; the first event creates the stable external Digest path without changing the Ticket body.

5. Stale Agent Brief hint
   - Input: optional Hint points at an outdated file while current code has moved.
   - Expected: the Hint is re-checked and corrected from repository facts; Brief content remains out of parsers, eligibility, state, and merge gates.

6. Handoff distillation
   - Input: Digest-worthy candidate and recovery Attempts with durable decisions or deviations.
   - Expected: candidate material reaches `## Review` or `## Notes`; recovery material reaches `## Attempt Summary` or `## Confirmed Findings`; the Ticket remains a Work Order.

7. No unnecessary Digest residue
   - Input: simple completed Attempt and a handed-off Attempt whose Digest has no remaining resume value.
   - Expected: the simple fixture creates no Digest; the handed-off Digest is deleted after durable distillation unless retained resources or repo policy require it.

## Grader Assertions

- The Pre-Implementation Checkpoint follows Claim metadata and precedes implementation edits.
- Every claimed Ticket has an issue disposition, exploration disposition, validation plan, and Digest disposition.
- Direct execution has explicit positive evidence for all six simple-ticket predicates.
- Simple Attempts do not accumulate no-op Digests or review artifacts.
- Digest-worthy Attempts use the external safe path and contain only strategy, touched surfaces, risks, validation, and record-worthy decisions or deviations.
- Pre-Edit Plan Review findings are incorporated into the plan or Digest rather than stored as a standalone artifact.
- Empty Agent Briefs are omitted; a present Brief has only non-duplicative Constraints, Validation, and optional Hints.
- Agent Brief hints are verified against current repository facts before use and Brief content changes no parser or gate outcome.
- Conditional research is source-linked, source-verifiable, and limited to implementation, validation, compatibility, or security facts.
- Candidate handoff distills durable Digest material into `## Review` or `## Notes`; recovery handoff uses `## Attempt Summary` or `## Confirmed Findings`.
- Ticket bodies contain no Digest section or progress log, and normal Ticket discovery excludes `execution-digests/`.
- Finished candidates create Solve Records with `## Checks`, `## Review`, `## Merge`, rollout/config disposition, manual gates, and caveats as applicable.
- Auto-merge and cleanup semantics remain governed by the existing solve-record landing and cleanup gates.

## Deterministic Validation

- `bash tests/ultra-solve-boundaries.sh` - passed on 2026-07-10
- `bash tests/maintainer-board.sh` - passed on 2026-07-10
- `bash tests/ultra-lenses.sh` - passed on 2026-07-10
- `bash tests/solve-records.sh` - passed on 2026-07-10
- `scripts/validate-skills.sh` - passed on 2026-07-10
- `git diff --check` - passed on 2026-07-10

These deterministic results validate the installable-skill contract and final-state fixture logic. They are not evidence that a fresh model session executed the seven scenarios; retain that distinction until a real run records its model, settings, prompts, refs, and grader results.
