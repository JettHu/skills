# Candidate Gates

Read this only after the Outcome gate selected outcome: candidate and the user
requested acceptance review, merge, ship, land, close, or candidate cleanup.
The record contract itself lives in [record-format.md](record-format.md);
recovery actions live in [edge-cases.md](edge-cases.md).

## 1. Live verification

Re-read the exact receipt and linked Ticket. Verify the live facts required by
the requested operation:

- Candidate record parses and remains outcome: candidate.
- Base and head refs exist and match base_sha and head_sha, or the narrow
  base-only revalidation rule applies.
- Candidate worktree is registered and clean whenever merge or cleanup uses it.
- Checks are passed, or the complete low-risk unavailable-check evidence is
  present.
- Post-Execution Review is passed, dependencies are satisfied, and the
  rollout/config disposition is explicit.
- A remote-primary PR/MR record remains a remote merge artifact.

A changed head SHA requires fresh validation. A changed base SHA can be
revalidated only when recorded base is an ancestor of live base, head still
matches, a preflight merge is clean, and checks are rerun or the documented
low-risk exception is restated.

Completion: the requested operation has a current, comparable candidate and
every relevant live fact above is recorded as pass or its smallest actionable
manual reason.

## 2. Acceptance review

Acceptance review changes readiness, not lifecycle state. Keep state: open.
When every live gate passes, update Merge from manual required to ready and
record the acceptance evidence. When any gate remains, retain manual required
and record the smallest actionable reason.

Completion: exactly one readiness result is visible in Merge, and it follows
from current refs, checks, worktree, review, dependencies, and rollout/config
evidence.

## 3. Merge, ship, or land

Treat merge, ship, and land as the same explicit candidate operation. Process
an approved bounded set one candidate at a time in dependency order.

Use merge-gate for a fact index, then independently live-verify. Construct a
landing SHA before touching the user base worktree:

- Fast-forward: live base is an ancestor of head, so landing SHA is head SHA.
- Non-fast-forward clean merge: create and validate a disposable landing
  commit from live base.
- Mechanical conflict: resolve only in that disposable environment, validate,
  and record the result.
- Semantic conflict: retain the candidate as manual required.

Use landing-plan, then verify the base checkout, ancestry, final write surface,
dirty and untracked paths, and hard-stop paths. Advance base only with:

    git merge --ff-only <landing_sha>

Completion: the recorded landing SHA is validated, the base fast-forward
succeeds, and the receipt records merged state, merged timestamp, merged SHA,
and landing rationale. A blocked candidate remains open with its actionable
reason and resources intact.

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

Completion: every solve-owned resource is either safely removed and marked
done, or remains listed with its exact safety blocker; user-owned resources
remain present and discoverable.
