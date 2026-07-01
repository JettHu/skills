# Solve Record Edge Cases

Read this only for explicit record closure or records with external PR/MR links.

## Record-Only Closure

Use only when the user explicitly says a candidate is abandoned, replaced, obsolete, or should be closed. Do not suggest closure as the default next action for ordinary open candidates.

Steps:

1. Re-read the selected record and live-verify that it is the intended candidate.
2. Set `state: closed`.
3. Set `closed_at`.
4. Write the reason in the body.
5. Do not change linked issue state.
6. Do not delete branches or worktrees unless the user also requested cleanup and cleanup safety passes.

If the linked issue itself should be rejected or abandoned, use the tracker or triage workflow instead of solve-record closure.

## Remote PR/MR Boundary

Local solve records are local markdown artifacts by default. Do not commit them unless the repo convention or user explicitly says to.

If a native GitHub PR or GitLab MR exists, treat that remote artifact as the primary merge artifact. A local solve record may store `external_provider` and `external_url` as a backlink/cache, but do not maintain two equal sources of truth.
