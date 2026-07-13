---
name: ultra-solve
description: Completion-friendly wrapper for outcome-aware /ultra solve.
disable-model-invocation: true
---

# Ultra Solve

Delegate to the `ultra` skill with subcommand `solve`.

Treat the user's request as if they had written:

```text
/ultra solve <user arguments>
```

Forward all arguments and context unchanged through the core `ultra` workflow, which dispatches `solve` to `solve.md`.
