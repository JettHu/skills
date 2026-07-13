# Jett Skills Maintainer Workflow

Jett Skills uses a local maintainer workflow for turning shaped work into agent-executed candidates and later landing or cleanup decisions.

## Language

**Maintainer Board**:
A repo-local, read-only view of ticket readiness and solve-record state that helps a maintainer decide the next action. It does not execute workflow actions, aggregate multiple repositories, or change tracker, merge, or cleanup state.
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

**Ticket**:
The canonical work item: what to build, acceptance criteria, blocking edges, source spec, state, claim metadata, comments/notes, retained-resource links, and solve-record backlinks. A ticket may be stored as a GitHub issue, a GitLab issue, a Linear issue, a local markdown issue file, or a section in a local `tickets.md`. Shaping skills produce tickets; `/ultra solve` claims and mutates tickets through the configured tracker backend.
_Avoid_: Solve record, attempt, run log

**Tracker Backend / Storage Representation**:
The concrete storage for a ticket, such as a GitHub issue, GitLab issue, Linear issue, local markdown issue file, or local `tickets.md` section. Use backend-specific names only when discussing adapter mechanics or storage shape.
_Avoid_: Canonical work item, solve record

**Ticket Metadata**:
The explicit machine-readable lines, frontmatter, labels, fields, or tracker-native metadata on a ticket, such as status, category, flags, solve branch, solve worktree, created date, blockers, parent, retained-resource links, and solve-record links. The maintainer board treats configured metadata surfaces as ticket fact sources and does not infer state from natural-language prose.
_Avoid_: Implied status, prose-derived priority

**Ticket Discovery**:
The pre-claim `/ultra solve` step that selects eligible ready-for-agent tickets and filters out wrong-state, already-claimed, stale, or review-pending work. It is a lightweight tracker scan, not code exploration.
_Avoid_: Pre-execute exploration, implementation planning

**Attempt**:
An in-progress try at a ticket. It may be represented by claim metadata, `solve-in-progress`, a branch, a worktree, a ticket comment/note, or current session context. It is not a default durable entity; failed validation, missing requirements, and unclear human decisions should remain ticket blockers unless a finished candidate exists.
_Avoid_: Solve record, delivery receipt, run log

**Agent Brief**:
Stable, approved execution context on a ticket, usually produced while shaping tickets for AFK work. It helps an agent understand context, constraints, and validation expectations, with optional hints only when useful; solve must treat it as preferred input rather than a required schema field.
_Avoid_: Execution Digest, implementation transcript, unresolved question list

**Pre-Implementation Checkpoint**:
A mandatory post-claim, pre-edit checkpoint inside an agent-ready solve run that reads the approved ticket context, decides whether extra read-only exploration is needed, synthesizes execution and validation plans, and routes non-executable work before code edits.
_Avoid_: Human approval loop, PRD review, speculative redesign

**Adaptive Subagent Fan-Out**:
A solve-planning policy where read-only subagents are available by default but are spawned only when ticket complexity, unfamiliar code, coupling, validation risk, or main-agent context pressure justifies parallel exploration. Subagents isolate read-heavy exploration and return compressed findings; the main agent keeps final responsibility for synthesis, implementation, validation, and solve-record finalization.
_Avoid_: Mandatory subagents, fixed agent count, always-on exploration, delegated ownership

**Pre-Edit Plan Review**:
A pre-edit review of the Pre-Implementation Checkpoint plan for omitted steps, unhandled risks, missing validation, and unsafe assumptions. For complex or digest-worthy tickets, solve should use a read-only planning reviewer subagent by default when available, then fold compressed findings back into the plan or Execution Digest.
_Avoid_: Plan approval, durable review report, implementation review

**Execution Digest**:
A compressed, state-relevant ticket note from a substantial Pre-Implementation Checkpoint that preserves execution strategy, touched surfaces, key risks, validation plan, and agent decisions without storing raw exploration notes. Tracker adapters choose the concrete comment or note format.
_Avoid_: Plan approval, full transcript, subagent log, PRD replacement

**Agent Decision Log**:
A tracker note that records a low-risk choice an agent made while completing an AFK-ready ticket, including the problem, options, decision, reason, and risk. It is separate from an Execution Digest, though the two notes may appear together.
_Avoid_: Execution plan, human approval, hidden assumption

**Post-Execution Review**:
A multi-perspective agent self-check of the integrated candidate after final validation and before solve-record finalization. It checks the final candidate against tickets, acceptance criteria, execution digests, agent decisions, side effects, regressions, and validation gaps; fixable findings are fixed before handoff.
_Avoid_: Group review, merge gate, acceptance review, solve record

**Completed Ticket**:
A ticket whose acceptance criteria have a finished, verified candidate. It does not mean the candidate has landed on its final branch or that all deployment gates have passed.
_Avoid_: Merged work, deployed work

**Solve Record**:
A short, maintainer-facing delivery receipt for a finished, checkable merge candidate after agent work. It summarizes linked ticket, changed behavior, verification evidence, review notes, candidate refs, and manual gates. It may record that manual review, acceptance, or merge is still required; when no finished candidate exists, the blocker stays on the ticket instead of becoming a solve record.
_Avoid_: PR, run log, ticket replacement, implementation transcript

**Human Acceptance**:
The human review step after a candidate is delivered: accept it, reject it, or request changes. Human acceptance may happen through a ticket, solve record review, PR/MR review, or another project-specific gate; it is separate from the agent's Post-Execution Review.
_Avoid_: Agent self-check, automated validation, solve-record creation

**Merge Candidate**:
A finished candidate branch or worktree state that is ready for review or a landing decision, but is not necessarily merged.
_Avoid_: In-progress attempt, merged work

**Review Submission**:
The surface used to hand a candidate to human or mainline review. In remote workflows this is usually a PR or MR; in local workflows it may be a candidate branch, commit, worktree, and solve record without a remote pull request.
_Avoid_: Solve record, merged work, attempt

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
A maintainer-board grouping that answers what kind of human attention a ticket or solve record needs next. It is derived only from explicit metadata and lightweight Git checks.
_Avoid_: Raw status list, priority ranking
