# Ticket Tracker: Local Markdown

Tickets and their source Specs or design handoffs live under the ignored `.scratch/` tree. The repository commits this contract, but it does not commit ordinary Ticket bodies, working notes, Claims, or Solve Records stored below `.scratch/`.

## Storage

- One effort per directory: `.scratch/<feature>/`.
- Formal Tickets use one file per Ticket: `.scratch/<feature>/issues/<NN>-<slug>.md`.
- Source material may use `spec.md`, `reference.md`, or another path explicitly linked from the Ticket's `## Parent` section.
- Solve Records use `.scratch/<feature>/solve-records/<record-id>.md`.
- Execution Digests use `.scratch/<feature>/execution-digests/<digest-key>.md`.

Ticket discovery scans only `.scratch/*/issues/*.md` and `.scratch/*/issue.md`. It never treats other Markdown files below `.scratch/` as Tickets.

## Ticket Contract

The stable Ticket Contract is the title plus these body sections when applicable:

- `## Parent`
- `## What to build`
- `## Acceptance criteria`
- `## Blocked by`

Concrete Attempt branch, worktree, commit, PR/MR, validation-run, and cleanup identities are coordination metadata or Solve Record resources, not Ticket Contract requirements.

## Coordination Metadata

Local Ticket metadata uses labeled lines near the top of the file:

- `Status:` stores the primary Ticket state.
- `Flags:` stores temporary Claim or workflow flags.
- `Solve Branch:` stores the active Claim branch assignment.
- `Solve Worktree:` stores the active Claim worktree assignment.
- `Category:` and `Created:` remain descriptive metadata.

The primary states are `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, and `completed`. `solve-in-progress` is a temporary Claim value under `Flags`, not a primary state. A Ticket is claimable only when its state is `ready-for-agent`, its blockers are completed, and it has no active Claim.

## Blockers And Comments

- Blockers are path references listed under the exact `## Blocked by` heading. A Ticket with no blockers omits the section; legacy `None` entries remain readable as no blockers.
- A blocker is satisfied only when its referenced Ticket currently has `Status: completed`.
- Comments and concise lifecycle notes append under `## Comments`.
- A completed or recovery Attempt may add a path-only Solve Record backlink under `## Comments`; the Solve Record remains authoritative for handed-off resources and cleanup.

## Publishing And Fetching

When a skill publishes formal Tickets, it writes them under the configured effort directory and preserves the contract and metadata conventions above. When a skill fetches a Ticket, it reads the exact user-provided path or resolves the requested stable Ticket identity within the configured Ticket surface.
