---
name: solve-records
description: Manage local Attempt Receipts for candidate delivery and recovery handoffs.
disable-model-invocation: true
---

# Solve Records

An Attempt Receipt is the durable local handoff for one meaningful solve
outcome. It complements a Ticket and Claim; it is not either of them.

Use outcome as the result and state as the receipt lifecycle. The outcome gate
keeps candidate delivery and recovery work on separate, predictable routes.

## Outcome gate

- candidate is the only delivery route. It may enter acceptance review, merge,
  ship, land, and candidate cleanup after its live gates pass.
- blocked, needs-info, ready-for-human, abandoned, and superseded are recovery
  routes. They enter Needs Attention or Resume with their ownership and next
  action.
- malformed receipts enter repair; repair the contract before routing work.

Read [record-format.md](references/record-format.md) when creating or
repairing any receipt. It is the source of truth for the machine-readable
contract, legacy mapping, common header, and outcome-specific sections.

New Attempt outcomes enter this workflow only through the configured Tracker
Facade outcome-handoff adapter. It is the one canonical writer for the compact
receipt, Ticket backlink and state, Claim disposition, and recovery successor
relation. Always create and retain the opaque handoff key before submission;
do not prewrite a receipt, choose its path, or mutate lifecycle surfaces by
hand. Retryable results use the same handoff key and identical immutable input.

## 1. Discover

With no prompt, run the read-only dashboard:

    python /path/to/solve-records/scripts/solve-records.py dashboard --repo . --json

Discover feature-local and root-level receipt paths if the helper is
unavailable. Present Ready to merge, Manual merge required, Cleanup pending,
Recently merged, Needs attention or resume, and Stale or malformed as distinct
views. Each discovered file belongs to exactly one view.

Completion: every discovered receipt is classified once, with malformed
receipts named alongside their repair reason.

## 2. Select and gate

For an exact receipt path, read that file directly. Otherwise use select only
for discovery or disambiguation:

    python /path/to/solve-records/scripts/solve-records.py select --repo . --query <query> --json

Show multiple matches for a read-only request. For a state-changing request,
obtain one selected receipt or one explicit bounded set before mutation. Re-read
the selected receipt, apply the Outcome gate, and keep each selected receipt on
its own route.

Completion: the user intent, selected receipt set, outcome route, and next
operation are all unambiguous.

## 3. Candidate route

Candidate Readiness belongs to `/ultra solve`: a finished candidate must pass
verification, the root's full-boundary requirement-to-evidence audit, and
Post-Execution Review before the outcome handoff. The adapter derives candidate
identity and writes the compact candidate receipt with its concise Summary.
Candidate Readiness is not Candidate Acceptance Review, merge, landing,
deployment, release, smoke, or cleanup authority.

Before every candidate acceptance review, merge, ship, land, close, or
cleanup request, read [candidate-gates.md](references/candidate-gates.md). It
owns the live verification, landing, closure, and cleanup steps.

Completion: the candidate is either advanced through the applicable candidate
gate with current evidence, or remains an open receipt with its smallest
actionable manual reason.

## 4. Recovery route

For a recovery receipt, report its confirmed facts, linked Ticket, retained
resources, ownership, and recorded next action. Read
[edge-cases.md](references/edge-cases.md) before a resume, close, supersede,
recovery resource-cleanup, or remote PR/MR action.

A recovery receipt is created by the outcome-handoff adapter at a meaningful
handoff: substantive assessment or work leaves evidence, a retained resource,
a blocker, or a next action. Open resume handoffs retain ownership only for the
complete verified solve-owned resource set; all other cases follow the recovery
ownership matrix and either release the Claim or fail closed.
Transient tool failures, immediate no-value Claim releases, and fully cleaned
work without recovery value leave no receipt.

Completion: the recovery route leaves a resumable, closed, superseded, or
ownership-safe resource state visible without entering a candidate operation.

## 5. Preserve the remote boundary

A native GitHub PR or GitLab MR remains the primary merge artifact when the
receipt records external_provider or external_url. The local receipt is its
backlink/cache and retains its outcome and ownership context.

Completion: the selected merge authority and the local receipt role agree.
