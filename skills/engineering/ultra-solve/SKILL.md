---
name: ultra-solve
description: Completion-friendly wrapper for /ultra solve.
disable-model-invocation: true
---

# Ultra Solve

Delegate to the `ultra` skill with subcommand `solve`.

Treat the user's request as if they had written:

```text
/ultra solve <user arguments>
```

Forward all arguments and context unchanged. Do not implement separate issue-execution logic here; follow the core `ultra` workflow, which dispatches `solve` to `solve.md`.
