---
name: ultra-to-issues
description: Completion-friendly wrapper for /ultra to-issues.
disable-model-invocation: true
---

# Ultra To Issues

Delegate to the `ultra` skill with target skill `to-issues`.

Treat the user's request as if they had written:

```text
/ultra to-issues <user arguments>
```

Forward all arguments and context unchanged through the core `ultra` workflow, then invoke `to-issues` through it.

When the delegated flow publishes `ready-for-agent` issues, disclose the local [Agent Brief contract](references/agent-brief.md) as the preferred brief shape.
