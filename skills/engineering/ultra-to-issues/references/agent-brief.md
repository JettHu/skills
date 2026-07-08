# Agent Brief Contract

Use this contract when `/ultra to-issues` publishes issues intended for `/ultra solve`.

The Agent Brief is preferred approved input for solve-time planning. It is not a schema gate: `/ultra solve` may proceed without it when the issue, repository, and conversation provide enough approved context.

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

- Keep acceptance criteria authoritative. The brief should make execution safer while staying subordinate to the issue.
- Include hints only when they materially reduce search or recovery cost.
- Treat hints as stale until re-checked against current code and repo conventions.
- Put unapproved product, API, data, security, architecture, or significant UX choices in the issue as human review needs instead of solve instructions.
- If the brief is missing or incomplete, `/ultra solve` infers what it can; missing core requirements become `needs-info`, and human-owned decisions become `ready-for-human`.
