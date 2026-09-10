# Obsidian Tracker Workspace contract

Run `python3 <skill-dir>/scripts/obsidian-workspace.py --config /absolute/path/workspace.json`.
Resolve `<skill-dir>` to this installed skill, independent of the current project.
Python 3.10+ and compatible `ultra` and `solve-records` skills are required.
The renderer supports Tracker Snapshot schema v1 / semantics v2; it checks the
query and receipt-helper capabilities before writing output. Keep the three skills
from a compatible catalog revision together. In a flat skill installation they
are siblings; in this repository the dependencies live under `skills/engineering/`.
For a separate installation, set `JETT_ULTRA_SKILL_DIR` to the absolute Ultra skill
directory; its sibling `solve-records` is the corresponding receipt dependency.
An explicit missing/incompatible dependency fails without trying another checkout.
Include that environment assignment in the delivered refresh command when used.

The repository's `scripts/obsidian-workspace.py` remains a compatibility CLI.
This skill is in-progress, not promoted. The existing Maintainer Board remains available.

```json
{
  "vault": "/absolute/path/to/selected-vault",
  "generated": "tracker-generated/asc09",
  "projects": [
    {"id": "project-one", "repository": "/canonical/checkout/one"},
    {"id": "project-two", "repository": "/canonical/checkout/two", "selection": ["ABC-01"]}
  ]
}
```

Select exactly one existing vault. Each binding names its canonical tracker
checkout explicitly; no worktree fallback or repository discovery occurs. Keep
project IDs stable, unique, and lowercase (`a-z`, digits, `_`, `-`). Omitted
selection means all Tickets; `[]` means none. Selection is delegated to the
Snapshot owner after full-source validation. No cross-vault navigation or
aggregation is provided. Keep this machine-specific configuration outside Git.

Open `<generated>/Home.md` in Obsidian after each explicit refresh. Home groups
Work, Delivery and Attention links by project, showing separate source
fingerprints, render signatures, selections and refresh results. A binding changed
to a different repository never inherits the old repository's last-success state.
Kanban v2 renders the Markdown boards; without the plugin they remain readable
headings and lists. Tasks is not needed. Plugin configuration is never modified.

## Setup ownership and recovery

`setup-workspace.py` provides `inspect`, `configure` and `verify`; use each command's
`--help` for arguments. Inspect reads only the explicit/default config, platform
Obsidian registry and selected paths. It never searches the home directory or
uses the open-window flag to choose a Vault. An existing workspace at a custom
output needs its explicit config or generated path; discovery does not crawl it.

Setup selects an installed Python 3.10+ without downloading a runtime. Set
`JETT_WORKSPACE_PYTHON` to an absolute interpreter path when needed. The result
contains the resolved interpreter and renderer command, including a dependency
override when applicable.

The generated root's `.workspace-config.json` is a locator for the single machine
config, not another source of tracker state. `.setup.lock` serializes setup of that
output; ordinary refresh still uses the renderer. Existing output without a
locator can be adopted only with its existing config and matching project sources.
Unknown output requires an empty dedicated directory. Setup keeps prior config
bytes in a sibling `.backup-*` file when changing it. A refresh failure can occur
after the config is saved: retain the config, inspect the reported error and retry.

`verify` summarizes the last refresh and checks its project bindings/selection
against config. It does not certify fresh source contents or real UI navigation.
Use the supplied refresh command to observe current sources. Its `ui_verification`
remains pending until the Agent supplies actual UI evidence.

## Authority and navigation

The renderer consumes `tracker_snapshot.snapshot(repository, selection)` and does
not parse Ticket state, publication, blockers or receipts. Cards preserve exact
canonical entity locators and project/repository namespaces. SHA-named Vault-local
file symlinks point to canonical source files; filenames never depend on a title
or basename lookup. The Ticket body is not copied. An unavailable source is shown
as unavailable text, never linked to another same-name note. Source Specs and
Parent links are preserved when they resolve exactly inside the configured
repository; explicit HTTP(S) context links are retained. Out-of-repository local
context is displayed as unavailable. Section Tickets open their full canonical
container and retain the exact section locator on the card; section scrolling is
not inferred from Ticket IDs.

Symlink notes are the actual canonical files: editing them in Obsidian edits the
canonical source. This tool performs no writeback. Only generated board cards,
lanes and checkboxes are disposable presentation. Canonical owners still own all
publication, Claim, acceptance, landing and cleanup operations and recheck gates
at mutation time.

## Refresh publication and failures

Home is the only publication point. New project pages and symlink aliases are
staged in fresh `generations/<token>/<project>/` directories, files are flushed,
then one atomic replacement publishes Home, its embedded state and links together.
There is no authoritative sidecar. A project observation/render failure retains
its previous successful generation while other projects may publish new results.
Home explicitly reports `partial failure` / `failed`, attempted selection, last
successful selection and observation, and unknown currentness. Boards link back
to Home for the latest result and always identify themselves as last-success
observations. Static pages never assert perpetual freshness.

No change to source fingerprint, schema/semantic/renderer version, selection,
options, or generated content leaves the published files untouched. Successful
refresh repairs edited cards/aliases by publishing a new generation. An already
open old board remains a historical page; return through Home to open the result
of a refresh. Retained content found edited during a failed refresh is explicitly
marked damaged; its old fingerprint no longer certifies those bytes.

The cache lock serializes refreshes for one output directory. A competing refresh
returns nonzero without overwriting the running refresh. A write/replace failure
returns `ok: false, persisted: false` and preserves the previous Home; it cannot
promise an on-disk failure notice when the disk refuses that write. Callers must
inspect exit status (`0` success, `2` failure) and the JSON result. Configuration
errors likewise return nonzero without guessing another output location.

The guarantee covers normal process interruption and filesystem call failures
around the Home commit point. It is not a power-loss transaction, a transaction
across projects' canonical writers, or protection against arbitrary concurrent
manual file edits. A partially staged generation is never linked from Home.

Keep personal notes outside the dedicated generated directory. Old generations
are deliberately retained so open pages keep their provenance and source links.
The entire dedicated cache may be discarded and regenerated when no old pages
are needed; no automatic cleanup, watcher, source/metadata migration or plugin
installation is performed. Never delete symlink *targets* when discarding cache.

## Maintained-use parity

Evidence: `python3 tests/obsidian-workspace.py`, shared query coverage in
`tests/tracker-snapshot.py` and `tests/tracker-selection-refresh.py`, plus the local
ASC-09 acceptance record under `.evals/asc-integration-20260910/` in the canonical checkout.

| Maintained use case | Projection / evidence | Remaining difference |
| --- | --- | --- |
| Claimable versus ready, provisional and blocked | Work uses owner eligibility; real publication/dependency fixture | No interactive field filters; configure exact selection |
| Claim and human-needed work | Work lanes plus Claim branch/worktree facts | Native note search, not HTML search controls |
| Completed with/without receipts | Completed Tickets plus explicit receipt relations/navigation | Completion is separate from delivery, never acceptance |
| Publication and malformed entities | Attention with owner reason/effect/source diagnostics | No mutation affordance |
| Candidate ready/manual | Delivery candidate lane; exact owner merge observations | Readiness stays a separate dimension rather than a lane |
| Recovery / retained resources / successor | Delivery and Attention, recovery action, ownership and successor navigation | No resume/cleanup action buttons |
| Landing / cleanup / historical receipts | Landing and cleanup evidence, operation observations, closed/history lane | Full returned history; no HTML recent-ten truncation |
| Missing refs, SHA mismatch, worktree drift | Owner ref/reason, handoff consistency and source degradation in Attention | Observational checks, not operation approval |
| Source/Ticket/receipt navigation | Exact file aliases; two same-ID projects and special-character fixtures | No inferred section anchor or cross-vault link |
| Refresh and generated edits | Atomic Home barrier, partial failure, no-op/version/selection, overwrite fixtures | Old open pages require navigating through Home |

Retirement of Maintainer Board, general Tasks queries, drag-to-mutate, frontmatter
migration, automatic backlink enrichment and broader vault layout portability
remain separate decisions. The approved ASC-08 vault/path/plugin combination is
the real-UI baseline; other layouts require their own UI validation.
