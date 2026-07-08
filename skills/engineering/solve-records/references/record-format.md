# Solve Record Format

Read this only when creating or repairing solve records.

Use ids aligned with the head branch slug:

```text
20260701-1432-caption-fix
solve/20260701-1432-caption-fix
```

A solve record points to one finished candidate branch. `head` is the candidate branch. `base` is the landing branch. Derive the commit set from Git with `base_sha..head_sha`.

The candidate may be an isolated solve branch, an adopted development branch, a PR branch, or a stack branch. The landing branch is where the candidate should enter after review, validation, deployment, or another project-specific gate.

Required frontmatter:

```yaml
id: 20260701-1432-caption-fix
kind: solve_record
state: open
base: master
base_sha: abc1234
head: solve/20260701-1432-caption-fix
head_sha: def5678
issues:
  - .scratch/caption/issues/01.md
worktree: ../.agent-worktrees/project/project-solve-caption-fix
created_at: 2026-07-01T14:32:00+08:00
cleanup_done: false
```

Optional frontmatter:

```yaml
merged_at:
merged_sha:
closed_at:
updated_at:
external_provider:
external_url:
```

Body template:

```md
# Solve Record: <title>

## Summary
Status: open | merged | closed
Next action: merge | manual review | cleanup | none

<short summary>

## Issues
- `<issue path>` - completed

## Changes
- <implementation summary>

## Checks
Status: passed | unavailable | stale
- `<command or check>` - passed | unavailable | stale

## Review
Post-Execution Review: passed | manual gate | blocked
- <integrated-candidate review outcome, unresolved manual gate, or blocking finding>

## Merge
Status: ready | auto-merged | manual required
Gate:
- [ ] Required checks passed
- [ ] Worktree clean
- [ ] Base/head match recorded SHAs or record was revalidated
- [ ] Landing SHA constructed before base mutation
- [ ] Landing validation passed
- [ ] Final landing write surface reviewed
- [ ] Base dirty and untracked paths reviewed as non-overlapping
- [ ] Mandatory hard-stop patterns reviewed
- [ ] No manual-review trigger detected
- [ ] Low-risk agent decisions recorded or none
- [ ] Dependencies merged or not required
- [ ] Conflict resolution not needed or completed safely
Reason:
- <why merge is allowed, performed, or blocked>
- Rollout/config disposition: <none | pre-merge action required | post-merge activation required>; <short rationale>
- Activation: <post-merge action or none>
- Smoke: <validation check or none>
- Rollback: <disable or rollback path or none>
- Landing: <fast-forward | merge-commit | resolved-merge-commit | blocked>, `<landing_sha or none>`

## Resources
Base: `<base>`
Base SHA: `<base_sha>`
Head: `<head>`
Head SHA: `<head_sha>`
Worktree: `<repo-relative worktree path>`
Cleanup: pending | done | blocked

## Notes
- <agent decisions, conflict notes, caveats, or empty>
```

Use `Cleanup: done` when no solve-owned resources remain, including adoption records where the adopted worktree and candidate branch are user-owned and stay outside `$solve-records cleanup`.

Merge status examples:

```md
## Merge
Status: manual required
Reason:
- Manual required: human acceptance is pending after the candidate checks passed.
- Rollout/config disposition: none; no rollout/config/operator action is needed.
- Landing: blocked, `none`
```

```md
## Merge
Status: ready
Reason:
- Acceptance review passed: issue criteria, checks, refs, and manual-review triggers were reverified.
- Rollout/config disposition: post-merge activation required; code merge is safe because the default remains disabled.
- Activation: enable `FEATURE_DIRECT_MODE=true` after merge.
- Smoke: run the documented direct-mode request check in staging.
- Rollback: disable `FEATURE_DIRECT_MODE`.
- Landing: fast-forward, `<head_sha>`
```

```md
---
state: merged
merged_at: 2026-07-03T18:30:00+08:00
merged_sha: abcdef0
---

## Summary
Status: merged
Next action: cleanup

## Merge
Status: auto-merged
Reason:
- Landed after the merge gate passed.
- Rollout/config disposition: none; no rollout/config/operator action was needed.
- Landing: fast-forward, `abcdef0`
```

Adopted development branch example:

```md
---
id: 20260703-1700-feature-current-branch
kind: solve_record
state: open
base: main
base_sha: abc1234
head: feature/current-branch
head_sha: def5678
issues:
  - .scratch/current-branch/issues/02.md
worktree: .
created_at: 2026-07-03T17:00:00+08:00
cleanup_done: true
---

# Solve Record: Adopted current branch

## Summary
Status: open
Next action: manual review

Finished candidate on the adopted development branch.

## Issues
- `.scratch/current-branch/issues/02.md` - completed

## Changes
- Updated the candidate on the adopted branch.

## Checks
Status: passed
- `scripts/validate-skills.sh` - passed

## Review
Post-Execution Review: passed
- Integrated candidate matched the linked issue and no fixable review findings remained.

## Merge
Status: manual required
Gate:
- [x] Required checks passed
- [x] Worktree clean
- [x] Base/head match recorded SHAs or record was revalidated
- [ ] Landing SHA constructed before base mutation
- [ ] Landing validation passed
- [ ] Final landing write surface reviewed
- [ ] Base dirty and untracked paths reviewed as non-overlapping
- [ ] Mandatory hard-stop patterns reviewed
- [ ] No manual-review trigger detected
- [x] Low-risk agent decisions recorded or none
- [x] Dependencies merged or not required
- [x] Conflict resolution not needed or completed safely
Reason:
- Manual required: development environment validation pending before landing into `main`.
- Rollout/config disposition: none; no rollout/config/operator action is needed.
- Landing: blocked, `none`

## Resources
Base: `main`
Base SHA: `abc1234`
Head: `feature/current-branch`
Head SHA: `def5678`
Worktree: `.`
Cleanup: done; adopted worktree and candidate branch are user-owned

## Notes
- `head` is the adopted candidate branch. `base` is the landing branch; this record does not imply a merge back into `feature/current-branch`.
```

Issue backlink:

```md
## Comments

### Solve Record

- `../solve-records/20260701-1432-caption-fix.md`
```

If an issue has multiple records, use `### Solve Records` with one path-only bullet per record. Keep checks, merge rationale, resource details, summaries, and record state in the solve record.
