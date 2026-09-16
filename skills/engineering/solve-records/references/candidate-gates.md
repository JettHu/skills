# Candidate Gates

Read this only after the Outcome gate selected outcome: candidate and the user
requested acceptance review, merge, ship, land, close, or candidate cleanup.
Before integration writes, also read the WIP protection subsection below; that
subsection applies before a candidate receipt exists.
The record contract itself lives in [record-format.md](record-format.md);
recovery actions live in [edge-cases.md](edge-cases.md).

## 1. Live verification

Re-read the exact receipt and linked Ticket. Verify the live facts required by
the requested operation:

- Candidate record parses and remains outcome: candidate.
- A compact candidate receipt with `head` and `head_sha` is valid at handoff;
  missing later gate facts are pending evidence, not a malformed receipt.
- Base and head refs exist and match base_sha and head_sha, or the narrow
  base-only revalidation rule applies.
- Candidate worktree is registered and clean whenever merge or cleanup uses it.
- Checks are passed, or the complete low-risk unavailable-check evidence is
  present.
- The receipt records a passed full-boundary requirement-to-evidence audit and
  concise evidence summary, and the live head still matches the audited head.
- Post-Execution Review is passed, dependencies are satisfied, and the
  rollout/config disposition is explicit.
- A remote-primary PR/MR record remains a remote merge artifact.

A changed head SHA must first pass the explicit `ticket refresh-candidate`
operation with the full SHA observed in the retained solve-owned worktree. The
operation keeps the same open receipt and invalidates the previous snapshot's
code-specific gate evidence; rerun affected-scope validation and acceptance
review before recording new gate evidence. Do not create a replacement receipt
or Claim for a bounded in-scope fix. A changed base SHA can be
revalidated only when recorded base is an ancestor of live base, head still
matches, a preflight merge is clean, and checks are rerun or the documented
low-risk exception is restated.

Completion: the requested operation has a current, comparable candidate and
every relevant live fact above is recorded as pass or its smallest actionable
manual reason.

The candidate-gate operation is the narrow writer for these late facts. It
must re-read the live head, derive the registered candidate worktree and base
identity, verify the worktree boundary, and atomically enrich the receipt.
`merge-gate` and `landing-plan` remain read-only indexes; they do not repair a
receipt or mutate Git state.

## 2. Acceptance review

Acceptance review changes readiness, not lifecycle state. Keep state: open.
When every live gate passes, update Merge from manual required to ready and
record the acceptance evidence. When any gate remains, retain manual required
and record the smallest actionable reason.

Completion: exactly one readiness result is visible in Merge, and it follows
from current refs, checks, worktree, review, dependencies, and rollout/config
evidence. A post-merge activation requirement needs one explicit activation
action; release smoke and rollback are later-boundary evidence.

## 3. Merge, ship, or land

Resolve authorization and the target under [the solve landing authorization rule](../../ultra/solve.md#9-auto-merge-solve-records-if-requested). Process
an approved bounded set one candidate at a time in dependency order.

Use merge-gate for a fact index, then independently live-verify. Construct a
landing SHA before touching the user base worktree:

- Fast-forward: live base is an ancestor of head, so landing SHA is head SHA.
- Non-fast-forward clean merge: create and validate a disposable landing
  commit from live base.
- Mechanical conflict: resolve only in that disposable environment, validate,
  and record the result.
- Semantic conflict: retain the candidate as manual required.

Before advancing any target, read [finalization.md](finalization.md) and prepare
the complete selected repository/resource scope through the Tracker Facade.
Use landing-plan, then verify the base checkout, ancestry, final write surface,
dirty and untracked paths, and hard-stop paths. Advance base only with:

    git merge --ff-only <landing_sha>

Completion: the recorded landing SHA is validated, the base fast-forward
succeeds, and Tracker Facade `finalization-record --phase reconcile` records the verified
landing facts on the original receipt. Cross-repository partial success remains
open until every selected target is verified landed. A blocked candidate remains open with its actionable
reason and resources intact.

### WIP protection and delegated landing

This gate binds the root and every delegated executor before changing a target
worktree, index, or Git ref. A landing plan is read-only evidence, not a write
permit. Keep one active writer per target through the final check and operation.
Immediate rechecks and writer coordination are Agent obligations; the helper
does not provide an atomic merge lock against concurrent external changes.

For both stages, classify the exact registered worktree first: user base
(including adopted worktrees), solve-owned execution, or disposable integration/landing. User bases
protect all existing tracked and untracked WIP. For execution and disposable
worktrees, verify resource ownership, writer handoff and provenance of existing
changes; unknown changes block mutation even in a disposable worktree. Conflicts
between known committed candidates follow the existing integration rules; they
are not user WIP and do not authorize discarding unknown changes.

**Before integration writes:** check the planned integration write scope against existing tracked and untracked changes
before writing. This stage needs neither a candidate receipt nor a final landing
SHA; do not run landing-plan as a prerequisite to constructing the candidate.

**Before final landing:** once the candidate receipt and validated landing SHA
exist, rerun landing-plan immediately before changing the target base worktree,
index or ref, using that final landing SHA and exact target. Compare the live
base/head, registered checkout,
final write surface (including rename sources, destinations and directory/file
collisions), staged/unstaged paths and untracked paths with the handoff evidence.
Revalidate any drift, including new WIP after planning or a changed landing
commit; a prior ready result cannot authorize the new state. If another writer
can still change the target, stop until exclusive ownership is established.

An overlap without applicable disposition authorization blocks that target:
leave its contents, index and ref unchanged, report exact paths and the needed
path-specific decision. Do not automatically stash, overwrite, partially restore,
or declare user changes obsolete. General merge/cleanup permission is not WIP
disposition permission. Reuse an existing explicit authorization only for its
named paths, disposition method and still-valid conditions; do not ask again
when those match. Perform only that authorized disposition, then rerun the live
gate before landing. Authorization does not turn a blocked plan into ready.
Disjoint WIP stays intact while otherwise eligible landing proceeds.

A delegated landing assignment must be self-contained and carry:

- exact repository/common-dir, registered target worktree, role, branch and SHAs;
- validated landing SHA and allowed final write surface;
- protected tracked/untracked paths and observed overlap, with live-check evidence;
- existing merge and path/method-specific WIP authorizations, or their absence;
- exclusive writer, handoff boundary, required immediate recheck and stop rule.

The executor returns actual before/after refs, check evidence, preserved paths,
and landed/blocked disposition per target. The root verifies those facts before
reconciliation; a delegated summary cannot waive this gate. For multiple repos,
retain completed targets and blocked targets separately on the original receipt
through finalization reconciliation. Report partial success as partial; never
roll back a successful target or claim overall completion to hide a WIP blocker.

## 4. Candidate close and cleanup

For explicit candidate closure, follow the candidate closure instructions in
[edge-cases.md](edge-cases.md). Closure does not change the linked Ticket.

Candidate cleanup applies only to local solve-owned resources. Before removal,
verify every applicable safeguard:

- The worktree is registered, outside the repo root and invocation checkout,
  and belongs to the same Git common dir.
- The registered branch equals recorded head and the worktree is clean.
- Head is merged into base.
- Resource ownership is solve-owned rather than adopted or user-owned.

Use cleanup-plan as a fact index, verify its result, remove the worktree,
prune registrations, and delete the branch with git branch -d.

Reconcile through [finalization.md](finalization.md) after each cleanup attempt,
including when earlier Git success outlived an interrupted receipt write.

Completion: every solve-owned resource is either safely removed and marked
done, or remains listed with its exact safety blocker; user-owned resources
remain present and discoverable.
