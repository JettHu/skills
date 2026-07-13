# Historical Design Note: Ultra Solve AFK-Safe Planning

## Status

Superseded by the approved [ticket-boundary reference](../../.scratch/matt-v1.1-skill-upgrade/reference.md). This file preserves the earlier design discussion only; it is not a runtime runbook or an additional source of requirements.

## Current Contract

Use these sources when implementing or reviewing `/ultra solve`:

- `skills/engineering/ultra/solve.md` for the coordinator runbook.
- `skills/engineering/ultra-to-issues/references/agent-brief.md` for the optional Agent Brief delta.
- `skills/engineering/solve-records/references/record-format.md` for outcome receipts.
- `.scratch/matt-v1.1-skill-upgrade/reference.md` for the approved boundary model and ticket acceptance.

The approved model is:

- A Ticket is a stable Work Order: task contract, acceptance, blockers, claim/backlink metadata, and retained-resource links. It is never a progress journal.
- An Agent Brief is optional and may contain only non-duplicative `Constraints`, `Validation`, and optional `Hints`. It has no `Context` field and cannot affect parsing, eligibility, state, or merge gates.
- An Execution Digest is conditional, external working memory at `.scratch/<feature>/execution-digests/<digest-key>.md`. It records only strategy, touched surfaces, risks, validation, and durable decisions or deviations; it is not a Ticket section.
- Outcome finalization creates a candidate receipt only for a finished reviewable candidate. A meaningful stopped Attempt creates an outcome-aware recovery receipt; a fully cleaned transient Attempt remains recordless.

## Retired Ideas

The previous draft’s Agent Brief `Context` field, Ticket-native Agent Decision Log, `agent-decision` Ticket flag, candidate-only receipt rule, and default pre-edit Digest are retired. Do not restore them from this historical note.

## Why This File Remains

The old draft is retained only to make the design transition explicit for readers who encounter legacy links. It intentionally does not restate workflow details, gates, or evaluation requirements: duplicating those rules here would create a competing source of truth.
