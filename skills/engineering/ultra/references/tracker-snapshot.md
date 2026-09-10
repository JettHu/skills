# Read-only Tracker Snapshot

For full tracker diagnostics or a View integration, call `snapshot(repository, selection=None)`
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
observations, including worktree cleanliness and full receipt membership. It includes the query semantic version and omits
wall-clock time. Selection does not change this full-source fingerprint. A consumer must display incomplete diagnostics and treat a failed
refresh as failure to observe current state. Selection applies after the full graph, publication checks and fatal validation.
`None` returns all entities; an explicit empty list returns none. Exact keys are
normalized by sorting and deduplicating, without fuzzy matching. Stable IDs on
malformed sources resolve to their retained diagnostic placeholders. Unknown keys
appear in `selection.missing`. Blockers and receipt/Ticket/successor relationships
retain resolved keys, `resolution` (`resolved`, `invalid-source`, `source-missing`)
and a `returned` flag. A filtered-out entity is therefore distinct from an absent
source. Global errors, global diagnostics and the full-source summary remain visible for
every selection. Returned entities retain their full-graph-derived diagnostics.

The facade accepts repeated `--ticket-id` arguments. The envelope retains full
summary counts; `selection` separately reports returned entity counts and exact
key resolution. `semantic_version` identifies query meaning independently of the
structural `schema_version`.

Maintainer Board consumes this complete query and applies its HTML grouping and
recent-card limits afterward. Install `ultra`, `solve-records`, and
`maintainer-board` together, either as catalog directories or installed sibling
skills. No Board retirement, Obsidian dependency, or storage migration is implied.


## HTML refresh evidence

The existing Board CLI accepts the same exact `--ticket-id` selection and an
optional `--visible-items` count. Its render signature covers the renderer version,
normalized selection and effective options. A renderer upgrade can require a new
artifact without claiming the authoritative source changed.

HTML is one self-contained atomic artifact. Its embedded state binds the last-good
body hash, source fingerprint and render signature to a generation; the latest
refresh result names that same generation. Read or render failure retains that
body and labels the latest refresh failed. A pre-existing unversioned HTML document
can be retained with explicitly unknown observation provenance. A status-write or
replacement failure leaves the prior file intact and returns a structured nonzero
CLI result. Consumers must heed that result: an unsuccessful persistence cannot
promise the on-disk notice was updated.

Identical source, render signature and content do not rewrite the file. A successful
retry clears a prior failure even when the body and generation are unchanged.
The static page always describes the last successful observation; only another
query can assess freshness. Atomic replacement prevents mixed body/status
generations, not concurrent-writer ordering or a transaction across arbitrary
source edits. There is no authoritative status sidecar.
