---
name: solve-records
description: Use when the user invokes $solve-records, asks to list, explain, merge, ship, land, close, or clean up finished /ultra solve candidates, needs stale or malformed solve-record triage, or when /ultra solve finalization must create or advance local solve records.
---

# Solve Records

Use solve records as local markdown receipts for finished, checkable merge candidates. They are not PRs, MRs, run logs, or replacements for the issue tracker.

## Quick Reference

| Intent | Default result |
| --- | --- |
| no prompt | read-only dashboard |
| ambiguous state-changing prompt | show candidates and stop |
| merge / ship / land | live-verify, then merge one eligible record |
| unavailable checks | manual required unless the low-risk exception is explicit |
| cleanup | delete only registered, clean, merged solve worktrees/branches |
| abandoned / replaced | close the record only; do not change issue state |

Mechanics are flexible; gates are not. Adapt commands, helper skills, preflight shape, and reporting detail to the runtime and repo evidence, but never skip live verification, manual-review triggers, required-check handling, or cleanup safety checks.

Resolve `scripts/solve-records.py` relative to this skill directory, not relative to the target repo. When running from a repo shell, execute the bundled script by absolute path if needed, and pass the target checkout with `--repo`.

Prefer one `dashboard` or `list` helper call per user request and reuse its JSON as a fact index. Avoid invoking the helper once per record unless a later live-verification or mutation gate specifically needs fresh target-specific evidence.

## 1. Dashboard

With no prompt, list records only. Do not mutate Git, issues, branches, worktrees, or records.

Run the bundled read-only helper first when available:

```bash
python /path/to/solve-records/scripts/solve-records.py dashboard --repo . --json
```

Use the helper output as a fact index, not as permission to mutate. If the helper is unavailable or fails, fall back to manual discovery in both locations:

- Feature-local: `.scratch/<feature>/solve-records/*.md`
- Root-level: `.scratch/solve-records/*.md`

Bucket every discovered file:

- `Ready to merge`: `state: open`, no manual blocker, live refs match the record, and checks either passed or are unavailable with an explicit low-risk exception.
- `Manual merge required`: open records with a manual-review trigger, unavailable checks without a low-risk rationale, blocked dependencies, or stale live state.
- `Cleanup pending`: `state: merged` or `state: closed` with `cleanup_done: false`.
- `Recently merged`: the 10 most recent `state: merged` records.
- `Stale or malformed`: missing refs, SHA mismatch, unreadable frontmatter, missing required fields, or body/frontmatter conflicts.

Show malformed records without hiding valid records. Completion criterion: every discovered file is either listed in exactly one bucket or reported as malformed with its path and repair reason.

## 2. Select

With a prompt, infer the intent semantically instead of requiring strict subcommands.

Use the helper for candidate lookup when available:

```bash
python /path/to/solve-records/scripts/solve-records.py select --repo . --query "<user wording>" --json
```

Treat helper matches as candidates. You still decide whether the user's latest wording selects one record, a bounded set, or an ambiguous set.

Supported intents:

- list or filter records
- explain a record
- merge, ship, or land records through the same merge gate
- clean up records
- explicitly mark a solve record closed when the user says the candidate is abandoned, replaced, or no longer wanted

Supported selectors:

- record id
- record file path
- linked issue path
- branch name
- title fragment
- natural-language description, such as `the caption one`

If a read-only prompt matches multiple records, show the candidates. If a state-changing prompt matches multiple records, stop before mutation and ask which record or wider set the user wants.

An explicit bounded set is allowed when the user clearly says `all` or names a scoped set, such as `all ready records`, `all low-risk ones`, or `clean up merged records`. For explicit sets, enumerate the matched records first, then process them one by one through the full gate. Skip and report records whose individual gate fails; do not broaden the set to dependencies, stale records, manual-required records, or malformed records unless the user explicitly approves that wider operation.

If one record or one explicit bounded set matches unambiguously, continue to live verification.

## 3. Live Verify

Before any merge, ship, land, close, cleanup, or record update, re-read the record and verify current Git state. Do not trust stored SHAs, body prose, or earlier chat context.

Verify at least:

- the record still parses and contains required frontmatter
- `base` and `head` refs exist when the action depends on them
- live `base` and `head` still match `base_sha` and `head_sha`, or the record is explicitly revalidated before proceeding
- the relevant worktree is clean before merge or cleanup
- required checks are still passed for the recorded or revalidated candidate
- the record has no human-required decision, unresolved dependency, or manual-review trigger
- the selected action still matches the user's latest wording

If verification fails, fail closed: preserve the record's existing state, keep open merge candidates open, write or report the smallest manual reason, and do not delete resources. For cleanup failure on a merged record, keep `state: merged` and `cleanup_done: false`.

Revalidation is narrow. A changed `head_sha` means the candidate changed; stop and require a fresh validation/update before merge. A changed `base_sha` may be revalidated only when the recorded base is an ancestor of the live base, the recorded `head_sha` still matches the live head, a merge/preflight against the live base is clean, and required checks are rerun or the unavailable-check low-risk exception is restated against the live base. If any part is uncertain, treat the record as stale/manual-required.

## 4. Create Or Repair A Record

Read [record-format.md](references/record-format.md) before creating or repairing a record. Use that file as the single source of truth for frontmatter, body sections, and backlink shape.

Create a solve record only after `/ultra solve` has a finished, reviewable candidate:

- implementation commits exist on `head`
- the candidate worktree is clean
- required checks passed, or checks are unavailable with the reason written in the record
- no unresolved conflict or known blocker remains
- linked issues are ready to be marked `completed`

Never create an initial solve record for claim-time state, in-progress attempts, failed required checks, missing requirements, or a human-required decision that prevents the candidate from being finished. If the candidate is finished and merely requires human review before merge, create an open record with `## Merge` set to `manual required`.

Do not add JSON as a source of truth or v1 fields such as `phase`, `merge_mode`, `merge_status`, `review_status`, `checks_status`, `attempt_id`, `candidate_state`, `human_state`, or `cleanup_state`.

When creating a record from `/ultra solve`, mark linked issues `completed` in the same finalize step and append only a backlink to the record. Do not copy checks, merge rationale, or cleanup state into the issue.

## 5. Checks And Decisions

Treat checks as merge-safety evidence, not a full test log.

- `passed`: relevant checks passed for the recorded `base_sha` and `head_sha`.
- `unavailable`: no meaningful automated check exists or the environment cannot run it. This blocks auto-merge unless the change is trivial and low-risk, with the record explicitly saying why no meaningful check exists, why no manual-review trigger applies, and what evidence still supports the change.
- `stale`: live refs no longer match recorded evidence, or the candidate changed and must be revalidated.

Agents may make low-risk implementation or conflict-resolution decisions when they can defend the choice. Record the decision with:

- chosen direction
- rationale
- alternatives considered when useful
- risk
- validation evidence or why no meaningful validation exists

Require human review for product semantics, public API or data contracts, database schema or data changes, auth/security/privacy, production rollout risk, feature-flag defaults, broad architecture direction, billing/compliance, or any conflict where both intents cannot be preserved.

## 6. Merge, Ship, Or Land

Treat `merge`, `ship`, and `land` as the same intent: advance the selected record through the merge gate.

Process records one by one, in dependency order. Do not merge unmerged dependencies unless the user explicitly approves the wider operation.

For explicit set operations, eligible records may merge while ineligible records are skipped with reasons. Never let one eligible member of a set make another member eligible.

Before mutating the base branch:

- live-verify the record
- use `merge-gate` from the helper when available, then independently apply the full gate
- verify the base worktree is clean
- dry-run or preflight the merge using a disposable worktree when practical
- verify no manual-review trigger remains
- verify required checks passed, or the unavailable-check low-risk exception is recorded

If a mechanical conflict appears, resolve it on the candidate/head side or a disposable copy, then rerun checks and retry. Do not resolve conflicts in the user's base worktree. If resolving safely requires product, API, security, data, architecture, or rollout judgment, keep the record open and mark manual required.

After a successful merge:

- update `state: merged`, `merged_at`, and `merged_sha`
- write the merge rationale in `## Merge`
- attempt safe cleanup
- if cleanup fails, keep the merge, keep `state: merged`, keep `cleanup_done: false`, and report blockers

If merge fails before completion, abort any in-progress merge when possible, keep `state: open`, write `manual required`, and do not clean up the candidate branch or worktree.

## 7. Close

There is no promoted `close` next action in v1 dashboards; do not suggest closure for ordinary open candidates. If the user explicitly says a candidate is abandoned, replaced, or should be closed, read [edge-cases.md](references/edge-cases.md) and perform record-only closure.

Closing a solve record never changes linked issue state. If the linked issue itself should be abandoned, use the tracker or triage workflow.

## 8. Cleanup

Cleanup deletes only local temporary Git resources created for solve. It never deletes issues, PRDs, product files, or the solve record itself.

Cleanup must pass all safety checks before removing anything:

- resolve the worktree path relative to the repo root
- verify the path is registered in `git worktree list --porcelain`
- verify the path is not the repo root or current invocation checkout
- verify the worktree belongs to the same Git common dir as the repo root
- verify the current branch equals record `head`
- verify the worktree is clean
- verify `head` is merged into `base` before deleting the branch

Use `cleanup-plan` from the helper when available, then verify the reported facts before deleting anything.

Then remove the worktree, run `git worktree prune`, and delete the branch with `git branch -d`. Use raw Git checks; `agent-worktree` may help when available but is not required.

If any safety check fails, do not delete anything. Update or report `Cleanup: blocked` with the exact remaining resource and reason.

## 9. Remote Boundary

Keep local solve records local by default. If `external_provider` or `external_url` is present, read [edge-cases.md](references/edge-cases.md): native GitHub PRs and GitLab MRs are primary merge artifacts, and the local record is only a backlink/cache.
