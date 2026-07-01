# Solve Record Format

Read this only when creating or repairing solve records.

Use ids aligned with the head branch slug:

```text
20260701-1432-caption-fix
solve/20260701-1432-caption-fix
```

A solve record points to one finished candidate branch. Do not list commits in the record; derive the commit set from Git with `base_sha..head_sha`.

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

## Merge
Status: ready | auto-merged | manual required
Gate:
- [ ] Required checks passed
- [ ] Worktree clean
- [ ] Base/head match recorded SHAs or record was revalidated
- [ ] Head merges cleanly into base
- [ ] No manual-review trigger detected
- [ ] Low-risk agent decisions recorded or none
- [ ] Dependencies merged or not required
- [ ] Conflict resolution not needed or completed safely
Reason:
- <why merge is allowed, performed, or blocked>

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

Issue backlink:

```md
## Comments

### Solve Record

- `../solve-records/20260701-1432-caption-fix.md`
```

If an issue has multiple records, use `### Solve Records` with one path-only bullet per record. Do not copy checks, merge rationale, resource details, summaries, or record state into the issue.
