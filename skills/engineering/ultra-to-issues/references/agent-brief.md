# Agent Brief Contract

Use this contract when `/ultra to-issues` publishes issues intended for `/ultra solve`.

The Agent Brief is an optional, non-duplicative execution delta within an issue. The issue, its acceptance criteria, and its source Spec remain authoritative. It is not a schema gate: `/ultra solve` may proceed without it when the approved issue, repository, and conversation provide enough context.

Use only fields that add approved information not already expressed by the issue or source Spec. Omit each empty field and omit the entire section when every field is empty:

```markdown
## Agent Brief

Constraints:
Validation:
Hints:
```

## Fields

- `Constraints`: approved execution boundaries that do not fit naturally in acceptance criteria, such as compatibility requirements, state-machine rules, or rollout limits.
- `Validation`: non-obvious commands, environments, fixtures, manual evidence, or check runs.
- `Hints`: optional orientation such as likely files, patterns, prior attempts, or commands; include it only when it materially reduces orientation cost.

## Rules

- Do not repeat the problem, behavior, domain terms, acceptance criteria, or source-Spec content in the Brief.
- Treat hints as stale until re-checked against current code and repo conventions.
- Put unapproved product, API, data, security, architecture, or significant UX choices in the issue as human review needs instead of solve instructions.
- If the brief is missing or incomplete, `/ultra solve` infers what it can; missing core requirements become `needs-info`, and human-owned decisions become `ready-for-human`.
- Agent Brief content never participates in parsing, eligibility, state transitions, or merge gates.
