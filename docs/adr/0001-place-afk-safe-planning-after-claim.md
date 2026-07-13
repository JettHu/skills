# Place Pre-Implementation Checkpoint After Claim

`/ultra solve` runs its Pre-Implementation Checkpoint after a tracker claim succeeds and before any implementation edits. This preserves the concurrency protection of claiming `ready-for-agent` tickets early, while still giving the agent a read-only planning window to inspect code, risks, validation paths, and low-risk agent decisions before touching files.
