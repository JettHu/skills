# Candidate finalization

Read before authorized landing or cleanup, and when recovering after Git
succeeded but the receipt update was interrupted. Both `/ultra solve` and
`$solve-records` use these Tracker Facade operations. They write evidence to the
selected canonical receipt and never merge, delete resources, change Tickets,
or grant authorization. Follow [candidate-gates.md](candidate-gates.md) for
acceptance, live landing, WIP, and cleanup safeguards.

## Prepare the complete scope

After constructing and validating the landing commit, and before advancing any
selected target or deleting a resource, collect one JSON input with the complete
selected repository set. Include the canonical receipt repository exactly once;
each Git common directory may occur once. Example single-repository input:

```json
{
  "authorization": "Existing user request authorizes landing and cleanup of this selected candidate.",
  "scope_evidence": "Linked Ticket requires only this repository.",
  "repositories": [{
    "repo": "/absolute/project",
    "base": "main",
    "base_sha": "FULL_VERIFIED_BASE_SHA",
    "head": "solve/candidate",
    "head_sha": "FULL_VERIFIED_HEAD_SHA",
    "worktree": "/absolute/candidate-worktree",
    "landing_sha": "FULL_VALIDATED_LANDING_SHA",
    "ownership": {"branch": "solve-owned", "worktree": "solve-owned"},
    "ownership_evidence": "Creation/Claim evidence identifying this exact branch and worktree, and its owner.",
    "gate_evidence": {
      "checks": "passed", "review": "passed", "merge": "ready",
      "rollout_config": "none", "activation": "none",
      "audit": "passed", "dependencies": "satisfied"
    }
  }]
}
```

For disposable landing branches/worktrees or other applicable resources in the
same repository, include `additional_resources` on that repository member. Each
entry names `kind` (`branch` or `worktree`), `identity` (branch name or canonical
absolute path), full `head_sha`, `owner`, and `ownership_evidence`. Worktrees
also name `branch` (empty for detached HEAD). Declare both resources when a
worktree has a temporary branch; a detached worktree needs only its own entry.
Every extra commit must be included in the validated landing. These resources
participate in the same cleanup completion condition as the candidate resources.
The Agent verifies that the inventory covers all applicable resources; the
writer cannot discover ownership of undeclared unrelated worktrees.

The Agent verifies authorization, complete Ticket scope, ownership provenance,
requirement audit, dependencies and substantive check/review results. These are
explicit evidence assertions, not facts the script can infer from Git or a
branch name. Name concrete session, Claim or existing receipt evidence in the
text fields. Adopted branches/worktrees use `user-owned`; retain them. Never
upgrade unknown ownership into solve-owned. The primary repository must match
its existing candidate-gate evidence; other selected repositories supply their
own gate assertions. Preserve the original input for retries.

```sh
python3 <ultra>/scripts/ultra_tracker.py solve-record finalization-record \
  --repo /absolute/project --record .scratch/feature/solve-records/candidate.md \
  --phase prepare --evidence /absolute/finalization-input.json
```

Preparation verifies exact local refs, landing ancestry, acceptance gates,
registered clean worktrees, repository identity and the current landing write
surface. It freezes the complete scope, original ownership and resource
identities in `## Finalization` on the same receipt. It leaves state open.
Identical preparation retries reuse the binding; changed scope/identity is a
conflict. Preparation freezes candidate refresh and gate rewriting for this
landing operation. A drifted candidate requires investigation; never discard
partial landing evidence to restart a candidate loop.

## Reconcile actual results

Recheck live landing gates immediately before each authorized Git operation.
Use `landing-plan --repo <canonical-repo> --record <receipt>
--target-repo <exact-prepared-repo>` for each pending member (target-repo defaults
to the canonical repository). It reruns the original landing gates and current
write-surface checks against the bound landing SHA. Already landed members
refuse a repeated landing plan and proceed directly to reconciliation/cleanup.
A prepared snapshot is evidence, not permission to bypass later WIP or ref
changes. Advance each target through the existing fast-forward landing rule.
After each successful landing, and again after safe cleanup, run:

```sh
python3 <ultra>/scripts/ultra_tracker.py solve-record finalization-record \
  --repo /absolute/project --record .scratch/feature/solve-records/candidate.md \
  --phase reconcile
```

The operation verifies prepared landing commits in their exact target branches
and records per-repository landing facts and resource dispositions. A successful
write can still report `pending` or `cleanup-pending`; inspect `state`,
`cleanup_done`, and every repository's blockers. Retry reconciliation after
fixing a blocker. Never repeat a merge already proven landed.

Only all-repository landing completion sets `state: merged`. `merged_sha` is
the primary repository's actual prepared landing commit; each repository stores
its own `landing_sha`. `merged_at` is the first verified completion observation,
not the candidate commit date or a guessed external event time. Partial landing
keeps state open and appears in Manual with its per-repository recovery facts.
Cleanup failure preserves verified landing and leaves `cleanup_done: false`.
Only verified removal of all solve-owned resources and verified retention of
user-owned resources completes cleanup. No external actor or deletion timestamp
is inferred.

External deletion is confirmable only against the previously verified resource
inventory, a verified landing, an absent original path, an absent registration,
and the exact branch state. A missing path with a registration, replaced path,
moved/stale branch, dirty worktree, or missing user-owned resource is a blocker.
Historical receipts without sufficient preparation remain pending verification;
read them without migration and report the missing evidence. This operation
never automatically repairs historical records. Remote-primary receipts require
the remote provider's merge evidence and are outside this local writer.

`finalization-plan`, dashboard, and other query/plan operations are read-only.
Use `finalization-plan --repo ... --record ...` to inspect current facts without
writing. The JSON block is gate-owned evidence within the existing lifecycle,
not another receipt or lifecycle. Preserve Summary, Ticket associations, original
handoff identity and historical gate evidence. After interruption, reuse the
same receipt and prepared scope; the write is atomic and retryable.
