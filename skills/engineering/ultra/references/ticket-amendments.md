# Approved Ticket Amendments

Read this when an approved decision changes a published Ticket's scope,
acceptance criteria, source context, or dependencies, or when a Ticket has
`Contract Amendment` metadata. V1 is a Local Markdown publication operation;
remote adapters must declare an equivalent capability before mutation.

## Produce a revision

Read the canonical Ticket through `ultra_tracker.py snapshot --ticket-id <id>`.
Use its verified `publication.current_digest` as the compare-and-set input.
Keep the approval basis explicit (a decision link or a durable quotation with
its approving authority); the adapter checks its presence, not the authority
of the person named. Existing user authorization remains valid for its scope.

Write a JSON request with exactly these fields:

```json
{
  "id": "DELETE-A1",
  "ticket": "DELETE-01",
  "status": "approved",
  "approval": "Approved decision: prohibit deletion even without references",
  "predecessor": null,
  "replaces": {
    "Acceptance criteria": "- [ ] All deletion is rejected.",
    "Blocked by": "- POLICY-02"
  }
}
```

`replaces` names whole sections: `What to build`, `Acceptance criteria`,
`Parent`, or the configured blocker heading. Each section body is the complete
replacement for that clause range; section-level identity makes overlap
unambiguous. An empty blocker body explicitly removes dependencies. Other
empty sections and embedded level-one/two headings are refused. Source metadata,
Ticket identity, title, arbitrary prose and coordination fields are outside this
V1 edit surface. For a different kind of scope change, publish a successor Ticket.

`predecessor` is null for the first revision, otherwise the exact current
amendment ID. An explicit successor may replace the same section again. IDs
are unique within a publication run. A stale predecessor, reused ID with changed
input, fork, cycle or missing approved file is a conflict; file names, timestamps
and conversation order never resolve competing contracts.

```bash
python3 /path/to/ultra/scripts/ultra_tracker.py publication amend \
  --repo /canonical/repository --location .scratch/policy/issues \
  --run-id policy-review --ticket-id DELETE-01 \
  --expected-digest <verified-current-sha256> --amendment /path/to/request.json
```

The adapter stores an immutable independent JSON amendment under the surface's
`.ultra-publications/amendments/<run-id>/<id>.json`. It contains approval,
predecessor, replaced section ranges, original and effective Ticket text, both
digests, previous status, and execution ownership. It updates the Ticket's
managed `Contract Amendment` link and materializes the effective sections in
the canonical body. The file itself is never a discoverable execution Ticket.
The publication journal preserves its original digest snapshot and appends an
ordered, digest-bound audit alongside existing integrity repair history.

Draft requests may stay outside the managed directory. To expose a draft in
snapshot, store it at that same independent file location with `status: draft`;
it is not approved by its location. An unlinked draft is visible and does not
change claimability. Approval uses the explicit operation above. A draft in an
approved chain, or a pending approved file without its completed publication
audit, blocks the affected publication set.

## Retry and execution ownership

The operation holds the frontier lock before the publication lock. An active
Claim must finish or hand off through its existing outcome workflow before an
amendment can apply. The operation resets acceptance checkboxes, clears inactive
branch/worktree assignments, and returns the Ticket to the configured ready
state. Blocker gates still decide whether it can actually be claimed.

A previously completed Ticket retains its historical completion in the amendment
and its existing receipts. The same canonical Ticket owns the new unfinished
work; it must enter a new Claim/Attempt. Existing candidate resources and
receipts remain unchanged. A candidate made under the new contract records the
adapter-derived `contract_revisions` in its immutable handoff binding. Old or
legacy candidate evidence cannot satisfy the new contract. Candidate refresh
and late gate enrichment cannot silently rebind that evidence.

On interruption, retry the **same request, ID, predecessor and expected old
digest**. The stored intent lets the adapter converge after either the amendment
or Ticket write. Until journal verification succeeds, reads block Claim and
acceptance. After success, an identical retry returns `unchanged`. Another
request, altered pending bytes or stale input is a conflict: inspect and resolve
the named inconsistency rather than editing the digest or journal manually.

Terminal Repair retains its enumerated integrity-only scope. It cannot change
business clauses or substitute for `publication amend`. Identity repair of a
publication with amendment history is refused before writes; publish a new
Ticket rather than rewrite historical amendment identity.

## Consume the effective contract

Executors, independent reviewers and acceptance reviewers start from the same
canonical Ticket and `snapshot` result. Read `contract.effective_text`,
`contract.amendment.chain`, the linked amendment paths and approval basis, plus
the current blocker/readiness facts. The chain distinguishes effective head,
superseded history and unapproved drafts. Source documents remain context; an
approved replacement explicitly supersedes its named Ticket section.

A failed publication check returns no effective text and makes
`contract.completed` false. It is an unresolved contract, even if raw metadata
still says completed. Re-read after repair; never select a convenient draft or
old receipt as current truth. Snapshot fingerprints include amendment files.
Candidate acceptance also uses the current `merge-gate`; a digest/chain conflict
or revision mismatch blocks readiness and requires current-contract work.
