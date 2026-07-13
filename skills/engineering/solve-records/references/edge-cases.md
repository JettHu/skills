# Solve Record Edge Cases

Read this for explicit record closure, recovery handling, resource cleanup, or
external PR/MR links.

## Candidate record closure

Use record-only closure only when the user explicitly says a candidate is
abandoned, replaced, obsolete, or should be closed. Ordinary open candidates
use the promoted merge, manual-review, or cleanup next actions.

Before changing a candidate record:

1. Re-read it and verify `outcome: candidate`.
2. Live-verify the selected record and candidate resources when the action
   depends on them.
3. Set `state: closed` and `closed_at`.
4. Write the reason in the body.
5. Keep linked Ticket state unchanged.
6. Leave branches and worktrees in place unless the user also requested
   candidate cleanup and every cleanup safety check passes.

If the linked Ticket itself should be rejected or abandoned, use the tracker or
triage workflow instead of candidate-record closure.

## Recovery resume, close, supersede, and cleanup

Recovery receipts (`blocked`, `needs-info`, `ready-for-human`, `abandoned`,
and `superseded`) are not candidate operations. Never run acceptance review,
merge, ship, land, or candidate cleanup on them.

For a resume request:

1. Re-read the receipt, linked Ticket, `## Confirmed Findings`, and `## Resume
   Or Cleanup`.
2. Verify each recorded retained resource only when it is needed for the
   proposed resume. Missing candidate `base`, `head`, SHA, or worktree fields
   are not a defect in a recovery receipt that does not own them.
3. Treat the linked Ticket, exact retained-resource set, unresolved blocker or
   requested information, and next action as the recovery identity. When all
   still match, reclaim the Ticket through its tracker contract and reuse the
   receipt. At the next meaningful handoff, atomically replace its prior
   outcome-specific fields and sections with the current canonical candidate
   or recovery outcome. Repeated resumes keep one receipt and one Ticket
   backlink.
4. When that identity changed materially or a clean restart is safer, close or
   supersede the old receipt, preserve its Ticket backlink, record the old
   resources' disposition, and release the old Claim before the new Claim.
   The new Attempt creates its own receipt only when it later reaches a
   meaningful handoff.

For an explicit close or supersede request, set the lifecycle state and reason
on the selected receipt only. Do not silently change the linked Ticket state or
delete a retained resource.

For an explicit recovery resource-cleanup request, use the ownership and
safety evidence in `## Outcome`, `## Resources`, and the linked Ticket:

- Leave every user-owned resource in place.
- For a solve-owned worktree or branch, verify registration, Git common dir,
  clean status, identity, and the recorded cleanup rationale before removal.
- For a mixed record, remove only the individually proven solve-owned resource
  and leave the remainder discoverable in the receipt.
- If ownership or safety evidence is missing, report the smallest blocker and
  retain the resource.

This guidance is deliberately separate from candidate cleanup: a recovery
receipt does not become mergeable or eligible for candidate cleanup because it
contains a branch or worktree.

## Remote PR/MR boundary

Local solve records are local Markdown artifacts by default. Commit them only
when the repo convention or user explicitly says to.

If a native GitHub PR or GitLab MR exists, treat that remote artifact as the
primary merge artifact. A local receipt may store `external_provider` and
`external_url` as a backlink/cache; the remote PR/MR remains the merge source
of truth.
