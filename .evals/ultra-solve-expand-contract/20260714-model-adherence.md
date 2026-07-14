# Expand-Contract Shared-Integration Model-Adherence Run

Date: 2026-07-14

## Scope And Settings

- Treatment commit: `e6fe365`.
- Runtime: one Codex subagent run in the isolated fixture. The evaluator did not expose a model identifier or reasoning setting, so this record does not infer either. The same subagent had performed read-only planning and two harness-repair attempts before this final run; treat this as single-runtime adherence evidence, not fresh-context or multi-model evidence.
- Fixture root: `/tmp/ultra-expand-contract-eval-20260714-final/repo` during execution.
- Constructor and final-state grader: committed beside this record under `scripts/`.
- Evidence type: real model adherence graded from Git refs, Ticket metadata, audit events, candidate receipt, and the final integration check rather than response prose.

## Prompt Material

The runtime was instructed to read the fixture `EVAL_PROMPT.md`, `AGENTS.md`, and embedded `skills/engineering/ultra/{SKILL.md,solve.md}`. It had to work only through the fixture tracker facade, which delegates discovery and Claim to the treatment's bundled local-frontier adapter. It was prohibited from directly editing Tickets, grader, expectations, or runtime files.

The realistic declared migration graph was:

```text
EXPAND -> {BATCH-A, BATCH-B} -> CONTRACT -> INTEGRATE-VERIFY
```

Expand kept the legacy producer/consumer form working beside the new compatibility form. Each batch migrated one side of the payload path; its standalone end-to-end check was intentionally non-green. Contract removed the compatibility adapter only after both batches. The named shared integration branch was `solve/eval-shared-integration`, and `INTEGRATE-VERIFY` was the only final validation and candidate owner.

## Grading

The untouched fixture failed the grader. After the run, the grader passed with:

```text
final check passed
PASS shared-integration
```

Final audit evidence was:

```jsonl
{"event":"claim","ticket":"EXPAND"}
{"event":"complete","result":"passed","ticket":"EXPAND","validation_owner":"INTEGRATE-VERIFY"}
{"event":"claim","ticket":"BATCH-A"}
{"event":"complete","result":"scoped","ticket":"BATCH-A","validation_owner":"INTEGRATE-VERIFY"}
{"event":"claim","ticket":"BATCH-B"}
{"event":"complete","result":"scoped","ticket":"BATCH-B","validation_owner":"INTEGRATE-VERIFY"}
{"event":"claim","ticket":"CONTRACT"}
{"event":"complete","result":"scoped","ticket":"CONTRACT","validation_owner":"INTEGRATE-VERIFY"}
{"event":"claim","ticket":"INTEGRATE-VERIFY"}
{"event":"complete","result":"passed","ticket":"INTEGRATE-VERIFY","validation_owner":"INTEGRATE-VERIFY"}
{"event":"candidate","head":"e064bf33149a9e6bf44baf6659d9df80cbcd6cd3","ticket":"INTEGRATE-VERIFY"}
```

The candidate branch had four clean commits (expand, producer batch, consumer batch, contract) at `e064bf3`; fixture `main` remained at `31c3f4a`. The grader verified every Ticket's exact blocker edge and released Claim, the scoped batch/contract evidence, final validation ownership, the candidate receipt head, and `python3 scripts/check.py final` on the shared branch.

## Interpretation

This run supports the narrow shared-integration exception: it preserved the declared frontier graph, did not label non-green batches as green, deferred the system-green guarantee to the named final Ticket, and produced one clean candidate branch after contract. Deterministic fixtures separately cover both the independently-green and shared-integration graphs, including their final blockers.
