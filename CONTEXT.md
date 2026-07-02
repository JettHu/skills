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

**Solve Record**:
A receipt for a finished, checkable merge candidate after agent work. It is separate from issue completion and merge completion.
_Avoid_: PR, run log, issue replacement

**Merge Candidate**:
A finished candidate branch or worktree state that is ready for review or a landing decision, but is not necessarily merged.
_Avoid_: In-progress attempt, merged work

**Attention Bucket**:
A maintainer-board grouping that answers what kind of human attention an issue or solve record needs next. It is derived only from explicit metadata and lightweight Git checks.
_Avoid_: Raw status list, priority ranking
