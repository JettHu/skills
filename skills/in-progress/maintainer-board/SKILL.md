---
name: maintainer-board
description: Generate a read-only local HTML dashboard for a repository's .scratch issues and solve records.
disable-model-invocation: true
---

# Maintainer Board

Generate the board and report the generated HTML path.

Run the bundled script from the target repository shell:

```bash
python /path/to/maintainer-board/scripts/maintainer-board.py
```

No arguments means:

- target repo: the current working directory's Git root
- HTML output: `<repo>/.scratch/maintainer-board/index.html`

The board consumes the shared full Tracker Snapshot owned by `ultra`. It reads
only the configured Local Markdown surface and reuses canonical Frontier,
publication and Solve Record helpers. Before diagnosing query failures or
integrating another View, read Ultra's `references/tracker-snapshot.md` for the
versioned facts, bounded read-consistency boundary and fatal/incomplete behavior.
Run-tagged readiness requires the same verified complete-set publication gate
used by `/ultra solve`.

Issue classification follows explicit Ticket state after those safety gates:
Tickets whose publication journal cannot be verified go to Publication
attention even when their explicit state is `completed`, so integrity failures
cannot be hidden by a terminal state; `needs-triage` has its own lane;
`solve-in-progress` enters Claimed only when publication verification is valid.
Completed lanes scan and count every other completed Ticket, while the
HTML view shows the most recently completed items first and keeps the rest
behind Show more.

Completed cards display the lifecycle boundary explicitly: `completed` means
the Candidate gate is complete; it does not prove merge, deployment, or online
smoke. The board preserves the canonical Ticket state and adds this as a
derived display fact rather than creating another lifecycle state.

Closed recovery receipts are terminal when their explicit disposition is
complete: `state: closed` with `outcome: superseded` or `abandoned` goes to the
historical recent lane after `cleanup_done: true`, and to Cleanup pending while
cleanup remains false. The outcome is preserved as historical disposition.

Recovery validation is state-aware: open recovery records need an explicit next
action, while closed `abandoned` or `superseded` records may omit synthetic
`Blocker Or Requested Information` and `Resume Or Cleanup` sections when their
outcome, ownership, and cleanup disposition are clear.

`rejected` is a terminal outcome for an evidence-backed candidate explicitly
declined for landing or rollout. It is not a recovery route; closed rejected
records appear with terminal results.

Closed `abandoned` or `superseded` records with completed cleanup are historical
terminal evidence. Only open recovery records belong in the Recovery lane;
closed recovery records with pending cleanup belong in Cleanup.

If the user gives another checkout, pass it explicitly:

```bash
python /path/to/maintainer-board/scripts/maintainer-board.py --repo /path/to/repo
```

The default HTML output still belongs to that target repo.

For a raw machine snapshot instead of HTML, use:

```bash
python /path/to/maintainer-board/scripts/maintainer-board.py --json
```

Treat the helper as read-only except for writing the HTML path. It does not run tests, builds, installer discovery, merges, cleanup, Agents, or models. It derives issue state from explicit metadata/frontmatter, not natural-language prose. Use `$solve-records` for advancing, merging, closing, or cleaning solve records.

Install `maintainer-board`, `ultra`, and `solve-records` together. The board applies
view grouping to the shared Snapshot; canonical parsing, eligibility, handoff
consistency and readiness remain behind that query. HTML displays the source
fingerprint and any incomplete-observation diagnostics.

Normal Candidate and Recovery lanes require the compact receipt, every linked
Ticket, Claim disposition, retained-resource declaration, and any reciprocal
successor relation to agree. A missing backlink, partial grouped transition,
Claim/resource mismatch, or one-sided `supersedes` / `superseded_by` relation
enters handoff attention instead of a normal lane. Retry the same handoff key
through the Tracker Facade when its result is retryable; the board remains
read-only and never completes, repairs, accepts, lands, deploys, or cleans an
outcome handoff.
