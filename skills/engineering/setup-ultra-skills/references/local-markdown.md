# Local Markdown setup reference

Read this reference only when selecting or reconfiguring the `local-markdown`
preset in `setup-ultra-skills`.

The base tracker chooses either `file-per-ticket` or a safely delimited
`tickets-file` representation. The configured path is shared with the runtime:
only a complete single-segment `<feature>` placeholder is optional, while
`file-per-ticket` requires exactly one final `<ticket-file>.md` component.
Unknown, embedded, repeated, or missing placeholders fail closed.

Contract-bounded normalization accepts declared key aliases and state
presentation variants. Identity values and section markers remain exact.
Duplicate, unknown, undeclared, ambiguous, and conflicting variants fail
closed.

For Local Markdown, the `## Blocked by` body section is the canonical blocker
source. `Blocked By` and `Blockers` metadata are legacy fallback only. Omit the
section when there are no blockers; when both forms exist, use the body without
merging. Blocker entries use repository-relative Ticket paths in new Tickets;
legacy IDs remain readable.

Publication exposes `register`, `inspect`, `promote`, and `cleanup`. These are
publication transactions and do not have a manual fallback. Frontier owns
whole-tracker discovery, blockers, snapshots, Claim, and execution
branch/worktree assignment. An interrupted or failed publication operation is
resumed through its named adapter operation after the reported artifact or
contract issue is repaired.
