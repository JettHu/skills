# Agent Brief Contract

Use this contract when `/ultra to-tickets` publishes Tickets intended for `/ultra solve`.

The Agent Brief is an optional, non-duplicative execution delta within a Ticket. The Ticket, its acceptance criteria, and its source Spec remain authoritative. It is not a schema gate: `/ultra solve` may proceed without it when the approved Ticket, repository, and conversation provide enough context.

Use only fields that add approved information not already expressed by the Ticket or source Spec. Omit each empty field and omit the entire section when every field is empty:

```markdown
## Agent Brief

Constraints:
Validation:
Hints:
```

## Fields

- `Constraints`: approved execution boundaries that do not fit naturally in acceptance criteria, such as compatibility requirements, state-machine rules, or rollout limits.
- `Validation`: non-obvious commands, environments, fixtures, manual evidence, or check runs.
- `Hints`: optional orientation such as likely files, patterns, prior Attempts, or commands; include it only when it materially reduces orientation cost.

## Rules

- Do not repeat the problem, behavior, domain terms, acceptance criteria, or source-Spec content in the Brief.
- Treat hints as stale until re-checked against current code and repo conventions.
- Put unapproved product, API, data, security, architecture, or significant UX choices in the Ticket as human review needs instead of solve instructions.
- If the Brief is missing or incomplete, `/ultra solve` infers what it can; missing core requirements become `needs-info`, and human-owned decisions become `ready-for-human`.
- Agent Brief content never participates in parsing, eligibility, state transitions, or merge gates.
