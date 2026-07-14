---
name: ultra-to-tickets
description: Completion-friendly wrapper for /ultra to-tickets.
disable-model-invocation: true
---

# Ultra To Tickets

Delegate to the `ultra` skill with target skill `to-tickets`.

Treat the user's request as if they had written:

```text
/ultra to-tickets <user arguments>
```

Forward all arguments and context unchanged through the core `ultra` workflow, then invoke `to-tickets` through it.

When the delegated flow publishes `ready-for-agent` Tickets, disclose the local [Agent Brief contract](references/agent-brief.md) only when its optional, non-duplicative fields would add approved execution context.
