---
name: solve-records
description: Manage local solve records for finished /ultra solve candidates, including readiness review, merge/land, and cleanup.
disable-model-invocation: true
---

# Solve Records

Use solve records as local markdown receipts for finished, checkable merge candidates. They are not PRs, MRs, run logs, or replacements for the issue tracker.

## Quick Reference

| Intent | Default result |
| --- | --- |
| no prompt | read-only dashboard |
| ambiguous state-changing prompt | show candidates and stop |
| acceptance review / can this merge? | live-verify, update `## Merge` to `ready` or keep `manual required`, keep `state: open` |
| merge / ship / land | live-verify, construct `landing_sha`, then fast-forward base |
| unavailable checks | manual required unless the low-risk exception is explicit |
| cleanup | delete only registered, clean, merged solve-owned worktrees/branches |
| abandoned / replaced | close the record only; do not change issue state |

Mechanics are flexible; gates are not. Adapt commands, helper skills, preflight shape, and reporting detail to the runtime and repo evidence, but never skip live verification, manual-review triggers, required-check handling, or cleanup safety checks.

Resolve `scripts/solve-records.py` relative to this skill directory, not relative to the target repo. When running from a repo shell, execute the bundled script by absolute path if needed, and pass the target checkout with `--repo`.

Prefer one `dashboard` or `list` helper call per user request and reuse its JSON as a fact index until a later live-verification or mutation gate needs fresh target-specific evidence. When the user provides an exact solve-record path, read that file directly; use `select` only for discovery or disambiguation. Run `merge-gate` or `landing-plan` when preparing a readiness transition or merge gate, not repeatedly to restate already-read body prose.

## 1. Dashboard

With no prompt, use read-only dashboard/list mode for records.

Run the bundled read-only helper first when available:

```bash
python /path/to/solve-records/scripts/solve-records.py dashboard --repo . --json
```

Use the helper output as a fact index for the read-only dashboard. If the helper is unavailable or fails, fall back to manual discovery in both locations:

- Feature-local: `.scratch/<feature>/solve-records/*.md`
- Root-level: `.scratch/solve-records/*.md`

Bucket every discovered file:

- `Ready to merge`: `state: open`, no manual blocker, live refs match the record, checks either passed or are unavailable with an explicit low-risk exception, and the body records an explicit rollout/config disposition that permits merge.
- `Manual merge required`: open records with a manual-review trigger, missing or blocking rollout/config disposition, unavailable checks without a low-risk rationale, blocked dependencies, or stale live state.
- `Cleanup pending`: `state: merged` or `state: closed` with `cleanup_done: false`.
- `Recently merged`: the 10 most recent `state: merged` records.
- `Stale or malformed`: missing refs, SHA mismatch, unreadable frontmatter, missing required fields, or body/frontmatter conflicts.

Show malformed records alongside valid records. Completion criterion: every discovered file is either listed in exactly one bucket or reported as malformed with its path and repair reason.

## 2. Select

With a prompt, infer the intent semantically instead of requiring strict subcommands.

If the prompt contains an exact solve-record path, read the record directly and use it as the selected candidate. Use `select` only when discovery or disambiguation is needed.

Use the helper for candidate lookup when available:

```bash
python /path/to/solve-records/scripts/solve-records.py select --repo . --query "<user wording>" --json
```

Treat helper matches as candidates. You still decide whether the user's latest wording selects one record, a bounded set, or an ambiguous set.

Supported intents:

- list or filter records
- explain a record
- acceptance review, such as `验收下`, `review this`, `can this merge?`, or `is this ready?`
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

An explicit bounded set is allowed when the user clearly says `all` or names a scoped set, such as `all ready records`, `all low-risk ones`, or `clean up merged records`. For explicit sets, enumerate the matched records first, then process exactly that approved set one by one through the full gate. Skip and report records whose individual gate fails; do not broaden the set to dependencies, stale records, manual-required records, or malformed records unless the user explicitly approves that wider operation.

If one record or one explicit bounded set matches unambiguously, continue to live verification.

## 3. Acceptance Review

Acceptance review is a readiness transition separate from merge intent. Use it when the user asks whether a finished candidate is accepted, ready, or mergeable without explicitly saying `merge`, `ship`, or `land`.

For an acceptance review:

- re-read the exact record and linked issue evidence
- verify refs match or are narrowly revalidated, the candidate worktree is clean, checks passed or have the documented low-risk unavailable-check exception, dependencies are satisfied, and no conflict remains
- verify rollout/config/operator-action signals were considered and dispositioned in the record body
- preserve `state: open`; records become `merged` only after an actual landing succeeds
- if no manual-review trigger remains, update only `## Merge` from `Status: manual required` to `Status: ready` and record the acceptance evidence
- if a trigger remains, keep `Status: manual required` and record the smallest actionable reason

Keep `manual required` while acceptance evidence is still pending; rollout/config disposition is missing or says `pre-merge action required`; product/API/security/data/architecture review is required; checks are unavailable without the low-risk exception; refs are stale; the candidate worktree is dirty; dependencies are unmerged; or conflict resolution needs human judgment.

`post-merge activation required` can still be ready when the record explains why code merge is safe, which action activates the feature, how to smoke-check or validate it, and how to roll back or disable it.

## 4. Live Verify

Before any acceptance-review readiness update, merge, ship, land, close, cleanup, or record update, re-read the record and verify current Git state. Do not trust stored SHAs, body prose, or earlier chat context.

Verify at least:

- the record still parses and contains required frontmatter
- `base` and `head` refs exist when the action depends on them
- live `base` and `head` still match `base_sha` and `head_sha`, or the record is explicitly revalidated before proceeding
- the relevant worktree is clean before merge or cleanup
- required checks are still passed for the recorded or revalidated candidate
- the record has no human-required decision, unresolved dependency, or manual-review trigger
- the rollout/config disposition is present and permits readiness or merge before any `ready` transition or merge
- the selected action still matches the user's latest wording

If verification fails, fail closed: preserve the record's existing state, keep open merge candidates open, write or report the smallest manual reason, and do not delete resources. For cleanup failure on a merged record, keep `state: merged` and `cleanup_done: false`.

Revalidation is narrow. A changed `head_sha` means the candidate changed; stop and require a fresh validation/update before merge. A changed `base_sha` may be revalidated only when the recorded base is an ancestor of the live base, the recorded `head_sha` still matches the live head, a merge/preflight against the live base is clean, and required checks are rerun or the unavailable-check low-risk exception is restated against the live base. If any part is uncertain, treat the record as stale/manual-required.

## 5. Create Or Repair A Record

Read [record-format.md](references/record-format.md) before creating or repairing a record. Use that file as the single source of truth for frontmatter, body sections, and backlink shape.

Create a solve record only after `/ultra solve` has a finished, reviewable candidate:

- implementation commits exist on `head`
- the candidate worktree is clean
- required checks passed, or checks are unavailable with the reason written in the record
- no unresolved conflict or known blocker remains
- linked issues are ready to be marked `completed`

In frontmatter, `head` is the candidate branch whose current head contains finished work. `base` is the landing branch the candidate is meant to enter when merge, ship, or land intent is approved. In adoption mode, `head` may be a user-owned development branch; `base` remains the landing branch and must not be interpreted as "merge back into the current adopted branch."

Never create an initial solve record for claim-time state, in-progress attempts, failed required checks, missing requirements, or a human-required decision that prevents the candidate from being finished. If the candidate is finished and merely requires human review before merge, create an open record with `## Merge` set to `manual required`.

Before creating an auto-mergeable or ready record, explicitly consider rollout/config/operator-action signals. Use existing context when it is sufficient; otherwise scan changed files and nearby docs for generic signals such as config files, environment variables, feature flags, migrations, deployment docs, and runbooks. Record the conclusion as body prose in `## Merge` or `## Notes`.

The v1 record source of truth is markdown frontmatter and body from [record-format.md](references/record-format.md). Supported frontmatter stays limited to the documented fields; JSON registries and v1-style fields such as `phase`, `merge_mode`, `merge_status`, `review_status`, `checks_status`, `attempt_id`, `candidate_state`, `human_state`, or `cleanup_state` stay outside the v1 schema.

When creating a record from `/ultra solve`, mark linked issues `completed` in the same finalize step and append only a backlink to the record. Checks, merge rationale, cleanup state, development-environment deployment, and human acceptance evidence live in the solve record, especially `## Checks` and `## Merge`. If that evidence is pending, keep the issue completed when its acceptance criteria are verified and set the record merge gate to `manual required`.

## 6. Checks And Decisions

Treat checks as merge-safety evidence rather than a full test log.

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

Rollout/config disposition is required before a record is treated as ready:

- `none`: no rollout/config/operator action is needed.
- `pre-merge action required`: human/operator action is needed before merge; keep `## Merge` as `manual required`.
- `post-merge activation required`: code may be mergeable only when the record names why code merge is safe, the activation action, a smoke or validation check, and a rollback or disable path.

This disposition lives in body prose, preferably under `## Merge` `Reason:` or `## Notes`, separate from issue state, solve-record state, and frontmatter enums.

## 7. Merge, Ship, Or Land

Treat `merge`, `ship`, and `land` as the same intent: advance the selected record through the merge gate.

Process records one by one, in dependency order. Do not merge unmerged dependencies unless the user explicitly approves the wider operation.

For explicit set operations, eligible records may merge while ineligible records are skipped with reasons. Never let one eligible member of a set make another member eligible.

Before mutating the base branch, construct a verified `landing_sha`. The base branch is the record's landing branch. If the candidate branch was adopted from the user's current worktree, merge/ship/land still targets the landing branch, not the adopted branch itself.

Gate the record first:

- live-verify the record
- use `merge-gate` from the helper when available, then independently apply the full gate
- verify the candidate worktree is clean
- verify no manual-review trigger remains
- verify required checks passed, or the unavailable-check low-risk exception is recorded
- verify rollout/config disposition is explicit; `pre-merge action required` blocks merge, while `post-merge activation required` needs safety, activation, smoke/validation, and rollback notes

Construct `landing_sha`:

- Fast-forward candidate: if live base is an ancestor of head, set `landing_sha=<head_sha>`.
- Non-fast-forward clean merge: create a disposable worktree or equivalent throwaway merge environment from live base, merge head there, run required validation there, and set `landing_sha=<merge_commit_sha>`.
- Mechanical conflict: resolve only in the disposable environment. Use `resolving-merge-conflicts` when available; otherwise apply the inline contract below. Run required validation there and set `landing_sha=<resolved_merge_commit_sha>` only after the merge result is clean and committed.

Inline conflict contract when the skill is unavailable:

- inspect the merge state and conflicting files
- read both sides' commits, linked issues, docs, or other primary sources to understand intent
- preserve both intents where possible
- choose one side only when it matches the merge goal and record the tradeoff
- do not invent new behavior
- stop as `manual required` when resolution requires product, API, security, data, architecture, rollout, or other human judgment

After `landing_sha` exists, run the dirty-base landing gate. Use `landing-plan` from the helper when available, then verify the reported facts:

```bash
python /path/to/solve-records/scripts/solve-records.py landing-plan --repo . --record <id> --landing-sha <landing_sha> --json
```

Required proof:

- the base worktree is on the expected base ref
- live base is an ancestor of `landing_sha`
- `landing_sha` contains head
- final landing write surface is `git diff --name-only <live_base>..<landing_sha>`
- dirty and untracked base paths are listed
- dirty and untracked base paths are disjoint from the final landing write surface
- mandatory hard-stop patterns were reviewed

Mandatory hard-stop pattern hits require `manual required` unless the user explicitly approved proceeding and the record captures why. Review generic signal classes: lockfiles and dependency manifests, config files, environment variables, feature flags, migrations or schemas, deployment docs and runbooks, CI/build/rollout config, and skill or Agent invocation metadata such as `SKILL.md`, `agents/openai.yaml`, `.claude-plugin/**`, `AGENTS.md`, or `CLAUDE.md`.

The helper reports these as `hard_stop_paths` and blocks by default; explicit user approval is a human decision, not a helper override.

If the dirty-base gate passes, land with:

```bash
git merge --ff-only <landing_sha>
```

The user's base worktree must never be used for conflict resolution. A dirty-base exception only preserves unrelated local files; it does not relax cleanup safety or semantic-review gates.

After a successful merge:

- update `state: merged`, `merged_at`, and `merged_sha` to the landed `landing_sha`
- write the merge rationale in `## Merge`, including any dirty-base preservation evidence
- attempt safe cleanup
- if cleanup fails, keep the merge, keep `state: merged`, keep `cleanup_done: false`, and report blockers

If landing construction or the dirty-base gate fails before merge, abort any in-progress disposable merge when possible, keep `state: open`, write `manual required` with the smallest actionable reason, and do not clean up the candidate branch or worktree.

## 8. Close

The promoted v1 dashboard next actions are merge, manual review, and cleanup. If the user explicitly says a candidate is abandoned, replaced, or should be closed, read [edge-cases.md](references/edge-cases.md) and perform record-only closure.

Closing a solve record never changes linked issue state. If the linked issue itself should be abandoned, use the tracker or triage workflow.

## 9. Cleanup

Cleanup deletes only local temporary Git resources created for solve. It never deletes issues, PRDs, product files, the solve record itself, adopted worktrees, or adopted candidate branches.

For adoption records, mark `cleanup_done: true` when no solve-owned temporary resources remain, even though the user-owned adopted branch/worktree still exists. In `## Resources`, write that cleanup is done because the remaining resources are user-owned. Do not put adopted resources in the cleanup queue.

Cleanup must pass all safety checks before removing anything:

- resolve the worktree path relative to the repo root
- verify the path is registered in `git worktree list --porcelain`
- verify the path is not the repo root or current invocation checkout
- verify the worktree belongs to the same Git common dir as the repo root
- verify the current branch equals record `head`
- verify the worktree is clean
- verify `head` is merged into `base` before deleting the branch

Use `cleanup-plan` from the bundled solve-records helper when available, then verify the reported facts before deleting anything.

Then remove the worktree, run `git worktree prune`, and delete the branch with `git branch -d`. Solve resource cleanup uses raw Git checks and native Git cleanup commands; `agent-worktree` remains hook/config scaffolding.

If any safety check fails, do not delete anything. Update or report `Cleanup: blocked` with the exact remaining resource and reason.

## 10. Remote Boundary

Keep local solve records local by default. If `external_provider` or `external_url` is present, read [edge-cases.md](references/edge-cases.md): native GitHub PRs and GitLab MRs are primary merge artifacts, and the local record is only a backlink/cache.
