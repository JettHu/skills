---
name: ultra-to-issues
description: Explicit completion-friendly wrapper for /ultra to-issues. Use only when the user invokes ultra-to-issues, asks for the ultra-enhanced to-issues flow, or writes /ultra to-issues.
---

# Ultra To Issues

Delegate to the `ultra` skill with target skill `to-issues`.

Treat the user's request as if they had written:

```text
/ultra to-issues <user arguments>
```

Forward all arguments and context unchanged. Do not implement separate issue-splitting logic here; follow the core `ultra` workflow, then invoke `to-issues` through it.
