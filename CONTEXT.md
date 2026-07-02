# Jett Skills Maintainer Workflow

Jett Skills uses a local maintainer workflow for turning shaped work into agent-executed candidates and later landing or cleanup decisions.

## Language

**Maintainer Board**:
A repo-local, read-only view of issue readiness and solve-record state that helps a maintainer decide the next action. It does not execute workflow actions, aggregate multiple repositories, or change tracker, merge, or cleanup state.
_Avoid_: Workflow engine, action board, control panel, cross-repo dashboard

**Issue**:
A unit of work whose state describes whether it needs triage, is ready for an agent, needs a human, or is completed.
_Avoid_: Task

**Solve Record**:
A receipt for a finished, checkable merge candidate after agent work. It is separate from issue completion and merge completion.
_Avoid_: PR, run log, issue replacement

**Merge Candidate**:
A finished candidate branch or worktree state that is ready for review or a landing decision, but is not necessarily merged.
_Avoid_: In-progress attempt, merged work
