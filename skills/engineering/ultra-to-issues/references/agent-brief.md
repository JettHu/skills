# Agent Brief Contract

Use this contract when `/ultra to-tickets` publishes tickets intended for `/ultra solve`. A ticket may be stored as a GitHub issue, GitLab issue, Linear issue, local markdown issue file, local tickets-file section, or another configured tracker backend representation.

The Agent Brief is preferred approved input for solve-time planning. It lives on the ticket. It is not a schema gate: `/ultra solve` may proceed without it when the ticket, repository, and conversation provide enough approved context.

Minimum shape:

```markdown
## Agent Brief

Context:
Constraints:
Validation:
Hints: optional
```

## Fields

- `Context`: the approved problem, behavior, domain terms, and relevant local surfaces.
- `Constraints`: scope boundaries, compatibility requirements, state-machine rules, rollout limits, or other fixed decisions.
- `Validation`: expected commands, manual evidence, check runs, fixtures, or proof needed for acceptance.
- `Hints`: optional orientation such as likely files, patterns, prior attempts, or commands.

## Rules

- Keep acceptance criteria authoritative. The brief should make execution safer while staying subordinate to the ticket.
- Include hints only when they materially reduce search or recovery cost.
- Treat hints as stale until re-checked against current code and repo conventions.
- Put unapproved product, API, data, security, architecture, or significant UX choices on the ticket as human review needs instead of solve instructions.
- If the brief is missing or incomplete, `/ultra solve` infers what it can; missing core requirements become `needs-info`, and human-owned decisions become `ready-for-human`.
