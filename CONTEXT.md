# Jett Skills Maintainer Workflow

Jett Skills uses a local maintainer workflow for turning shaped work into agent-executed candidates and later landing or cleanup decisions.

## Language

**Maintainer Board**:
A repo-local, read-only view of issue readiness and solve-record state that helps a maintainer decide the next action. It does not execute workflow actions, aggregate multiple repositories, or change tracker, merge, or cleanup state.
_Avoid_: Workflow engine, action board, control panel, cross-repo dashboard

**Local Tool Trial**:
A repository tool used locally to test workflow usefulness before being promoted into catalog docs or skill surfaces.
_Avoid_: Promoted skill, plugin entry

**Board Snapshot**:
A deterministic JSON or static, build-free HTML rendering of the maintainer board at one point in time. Its HTML form is a dense maintainer report, not a long-running app.
_Avoid_: Long-running service, live agent session

**Lightweight Git Check**:
A read-only Git lookup used by the maintainer board to detect obvious drift, such as missing refs, mismatched SHAs, or registered worktree state. It is not a validation run.
_Avoid_: Test run, build run, installer discovery

**Issue**:
A unit of work whose explicit metadata describes whether it needs triage, is ready for an agent, needs a human, or is completed.
_Avoid_: Task

**Issue Metadata**:
The explicit machine-readable lines or frontmatter on an issue file, such as status, category, flags, solve branch, solve worktree, created date, blockers, parent, and solve-record links. The maintainer board treats both header-line metadata and YAML frontmatter as issue fact sources and does not infer state from natural-language prose.
_Avoid_: Implied status, prose-derived priority

**Completed Issue**:
An issue whose acceptance criteria have a finished, verified candidate. It does not mean the candidate has landed on its final branch or that all deployment gates have passed.
_Avoid_: Merged work, deployed work

**Solve Record**:
A receipt for a finished, checkable merge candidate after agent work. It is separate from issue completion and merge completion.
_Avoid_: PR, run log, issue replacement

**Merge Candidate**:
A finished candidate branch or worktree state that is ready for review or a landing decision, but is not necessarily merged.
_Avoid_: In-progress attempt, merged work

**Candidate Branch**:
The branch whose current head represents the finished work recorded by a solve record. It may be an isolated solve branch, an adopted development branch, a PR branch, or a stack branch.
_Avoid_: Landing branch, base branch

**Landing Branch**:
The branch that a candidate branch is meant to enter after review, validation, deployment, or another project-specific landing gate. It may be `main`, a development branch, an environment branch, or a previous stack branch.
_Avoid_: Candidate branch, execution branch

**Protected Baseline Branch**:
A branch that should not receive direct `/ultra solve` implementation edits, such as `main`, `master`, or a project-defined protected release branch. Solve work may branch from it, but should not adopt it as the candidate branch.
_Avoid_: Adopted candidate branch, scratch branch

**Adopted Worktree**:
A worktree that already exists before `/ultra solve` starts and is chosen as the solve execution or integration location after Agent judgment or user selection.
_Avoid_: Nested solve worktree, implicit merge target

**Adopted Integration Branch**:
The branch attached to an adopted worktree when `/ultra solve` uses it as the final place to assemble, validate, and record a finished candidate before that candidate lands elsewhere.
_Avoid_: Group branch, already-merged mainline

**Solve-Owned Resource**:
A branch or worktree created by `/ultra solve` for execution, integration, landing construction, or cleanup-safe temporary work. Adopted worktrees and adopted candidate branches are not solve-owned resources.
_Avoid_: User-owned branch, adopted worktree

**Attention Bucket**:
A maintainer-board grouping that answers what kind of human attention an issue or solve record needs next. It is derived only from explicit metadata and lightweight Git checks.
_Avoid_: Raw status list, priority ranking
