---
name: ultra-solve
description: Explicit completion-friendly wrapper for /ultra solve. Use only when the user invokes ultra-solve, asks for the ultra solve flow, or writes /ultra solve.
---

# Ultra Solve

Delegate to the `ultra` skill with subcommand `solve`.

Treat the user's request as if they had written:

```text
/ultra solve <user arguments>
```

Forward all arguments and context unchanged. Do not implement separate issue-execution logic here; follow the core `ultra` workflow, which dispatches `solve` to `solve.md`.
