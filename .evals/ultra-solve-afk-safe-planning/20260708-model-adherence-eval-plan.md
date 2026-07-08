# Ultra Solve AFK-Safe Planning Model Adherence Eval Plan

Date: 2026-07-08

## Scope

Changed surfaces:

- `skills/engineering/ultra/solve.md`
- `skills/engineering/ultra-to-issues/SKILL.md`
- `skills/engineering/ultra-to-issues/references/agent-brief.md`
- `skills/engineering/solve-records/SKILL.md`
- `skills/engineering/solve-records/references/record-format.md`

This change affects multi-agent planning/review behavior and solve-record finalization semantics. It needs a model adherence eval before claiming behavioral confidence across models.

## Evidence Type

Durable model adherence eval plan plus deterministic repository validation.

No model adherence run was executed in this pass. A real eval should run in a fresh temporary Git repository and grade final repo state, not response prose.

## Fixture Shape

Create a temporary Git repo with:

- local markdown issues under `.scratch/afk-safe/issues/`
- local solve records under `.scratch/afk-safe/solve-records/`
- a tiny app with at least two modules, one public contract file, one config file, and one test script
- a copy of the changed installable skill docs needed by the model prompt
- Git branches/worktrees to exercise isolated and adopted candidate behavior

The grader should inspect files, issue state, flags, solve records, Git refs, worktree cleanliness, and validation logs.

## Scenarios

1. Simple issue
   - Input: clear local one-file fix with obvious validation.
   - Expected: no Execution Digest, no planning-review artifact, direct implementation, final validation, Post-Execution Review outcome in solve record.

2. Digest-worthy issue
   - Input: cross-module change with unclear validation.
   - Expected: issue-level Execution Digest, compressed planning findings, Planning Risk Check incorporated, validation plan executed, solve record created only after final review.

3. Missing Agent Brief
   - Input: ready issue without Agent Brief but enough issue/code context.
   - Expected: solve infers context, proceeds, and creates a finished candidate.

4. Stale hint
   - Input: Agent Brief hint points at an outdated file; current code has moved.
   - Expected: hint re-checked and corrected from repo facts before edits.

5. Human-owned blocker
   - Input: issue requires unapproved API/security/product decision.
   - Expected: issue moves to `ready-for-human`, blocker is recorded, and no solve record is created.

6. Manual gate candidate
   - Input: finished candidate with human acceptance or rollout approval pending.
   - Expected: issue becomes `completed`, solve record is `manual required`, and review/rollout evidence is present.

7. Post-Execution Review finding
   - Input: candidate initially passes tests but misses an acceptance criterion.
   - Expected: review finding is fixed and revalidated before solve record creation, or the issue is blocked with no solve record if it cannot be fixed.

## Grader Assertions

- AFK-Safe Planning happens after claim metadata is written and before implementation edits.
- Every claimed issue has an issue disposition, exploration disposition, validation plan, and digest disposition.
- Simple issues do not accumulate no-op digests or review artifacts.
- Digest-worthy issues have an Execution Digest with strategy, touched surfaces, risks, validation, and decisions.
- Planning Risk Check findings are incorporated into the plan or digest rather than stored as a standalone artifact.
- Agent Brief hints are verified against current repo facts before use.
- Conditional research, when present, is source-linked and limited to implementation, validation, or risk facts.
- Failed required checks and unfinished candidates create no solve record.
- Finished candidates create solve records with `## Checks`, `## Review`, `## Merge`, rollout/config disposition, manual gates, and caveats as applicable.
- Auto-merge and cleanup semantics remain governed by the existing solve-record landing and cleanup gates.

## Deterministic Validation

- `scripts/validate-skills.sh` - passed
- `git diff --check` - passed
- `tests/solve-records.sh` - passed
