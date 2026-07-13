---
name: setup-ultra-skills
description: Configure the Ultra extension for an existing Matt tracker setup.
disable-model-invocation: true
---

# Setup Ultra Skills

Configure the small tracker extension that Ultra needs after
`setup-matt-pocock-skills` has established the base tracker contract. The base
contract remains authoritative for ordinary tracker and triage behavior; this
extension owns review publication, Claim, frontier, resource-link, and Solve
Record operations.

## 1. Read the base

Read `docs/agents/issue-tracker.md`, the existing `## Agent skills` block, and
any current `docs/agents/ultra-tracker.md`. Select the instruction file the
base setup uses: prefer the file already containing `## Agent skills`; otherwise
use its existing `CLAUDE.md` or `AGENTS.md` selection. If the base tracker
contract is absent, stop with the base-setup prerequisite.

Completion: the tracker preset, instruction file, and any prior extension are
known without changing project files.

## 2. Choose the extension policy

Use the base contract as evidence for one preset:

- `local-markdown` uses `local-review-pending`. Select the base contract's
  configured `file-per-ticket` or safely delimited `tickets-file`
  representation and path. Formal Tickets start in `review-pending`, carry a
  stable Ticket ID and publication-run identity, become `ready-for-agent` only
  after complete-set review and promotion, and use one executable cancellation
  policy: `retain-until-explicit-cleanup` or `delete-on-cancel`. The adapter
  reads that exact machine-readable policy from the managed contract; unknown
  values fail closed. A tickets-file without exact section
  markers, stable IDs, safe state mutation, blocker lookup, and
  conflict-detecting Claim semantics is unsupported.
- `github` or `gitlab` choose `remote-review-pending` when provisional remote
  Tickets are acceptable, or `local-staging` when the remote must contain only
  reviewed Tickets.
- `other` records labeled custom policy. Provide one line for each review,
  promotion, recovery, Claim, state, frontier, resource-link, Solve Record,
  and unsupported-operation field; the helper rejects incomplete policy.
  The required labels are `Draft or review-pending representation`, `Review
  update operation`, `Publish or promote operation`, `Partial-publish
  recovery`, `Claim and release`, `State mapping`, `Blocker and frontier
  lookup`, `Branch/worktree/PR links`, `Solve Record backlinks`, and
  `Unsupported operations`.

For a remote review policy, confirm the non-claimable marker and the durable
publication-set identity. For local staging, keep the default ignored root
`.scratch/.ultra-staging/` unless the project chooses another safe root.

Completion: one tested preset and one publication strategy are explicit, with
all backend-specific policy needed for idempotent resumption.

## 3. Review the generated extension

Render a draft with the bundled helper before any write. Replace
`<skill-dir>` with this installed skill's directory:

```text
python3 <skill-dir>/scripts/configure.py \
  --repo . --preset <preset> --publication-strategy <strategy> \
  --instructions <AGENTS.md-or-CLAUDE.md> \
  [--local-ticket-representation <file-per-ticket|tickets-file>] \
  [--local-ticket-path <configured-path>] [--custom-prose "..."]
```

Show the generated `docs/agents/ultra-tracker.md`, the short managed pointer,
and any staging ignore entry. Let the user revise the policy before applying.

Completion: the user has reviewed the exact managed contract and the change
preserves unrelated instruction text.

## 4. Apply and verify

Re-run the same command with `--apply`. The helper replaces its complete
generated contract and only its marked instruction block, so reconfiguration
keeps one contract and one pointer.

Verify that the contract points to the base file, includes Ticket Review
Publication and Solve Coordination, and that the instruction file has exactly
one `setup-ultra-skills` marker pair. When `local-staging` is selected, verify
the staging root is ignored and excluded from Ticket discovery.

Completion: the managed extension, pointer, and chosen backend policy are
present exactly once; the base tracker contract and unrelated project guidance
are preserved.
