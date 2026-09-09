# Read-only Tracker Snapshot

For full tracker diagnostics or a View integration, call `snapshot(repository)`
in the bundled `scripts/tracker_snapshot.py`, or use the same query through:

```bash
python3 /path/to/ultra/scripts/ultra_tracker.py snapshot --repo /canonical/repository
```

The facade returns `data.schema_version: tracker-snapshot/v1`, repository context,
all normalized Tickets and receipts, adapter-derived eligibility, publication and
Claim facts, associations, readiness observations, structured diagnostics, counts,
and a deterministic `source_fingerprint`. The core contains no lanes, card limits,
or mutation commands. Readiness observes existing evidence and grants no authority.

Pass the canonical tracker checkout explicitly when working from a linked worktree
whose configuration or `.scratch` points outside that worktree. Source symlinks
must remain inside the explicit repository; the query fails instead of selecting
another checkout. Only configured Ticket surfaces are discovered. Solve Record
locations and compatibility remain owned by the canonical Solve Record helper.

The query reuses existing frontier and per-surface publication locks with bounded
read waits. It opens existing locks read-only and creates no coordination files.
For a missing lock, it verifies that the lock remained absent; a concurrent writer
creating that lock invalidates the observation and causes a bounded retry. Sources,
lock identities and Git observations are checked again before returning. These
locks coordinate the existing adapters; two observations cannot guarantee an atomic
transaction against arbitrary editors or external Git writers. Persistent source
churn fails after two attempts. Interrupted handoff artifacts remain incomplete
attention evidence rather than being repaired by the query.

Configuration, source escape and global identity ambiguity are fatal structured
errors. Individual malformed artifacts remain exact-source diagnostics excluded
from actionable collections. Missing optional Git observations mark the result
incomplete. Frontmatter block lists are readable compatibility facts; their
unsupported mutation syntax is excluded from Claim eligibility. Mutation callers
retain their existing strict parser and operation contracts.

The fingerprint includes contributing source contents and relevant Git/worktree
observations, including worktree cleanliness and full receipt membership. It omits
wall-clock time. A consumer must display incomplete diagnostics and treat a failed
refresh as failure to observe current state. Exact selection and atomic refresh
behavior are separate follow-up work.

Maintainer Board consumes this complete query and applies its HTML grouping and
recent-card limits afterward. Install `ultra`, `solve-records`, and
`maintainer-board` together, either as catalog directories or installed sibling
skills. No Board retirement, Obsidian dependency, or storage migration is implied.
