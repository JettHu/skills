---
name: ultra-to-prd
description: Explicit completion-friendly wrapper for /ultra to-prd. Use only when the user invokes ultra-to-prd, asks for the ultra-enhanced to-prd flow, or writes /ultra to-prd.
---

# Ultra To PRD

Delegate to the `ultra` skill with target skill `to-prd`.

Treat the user's request as if they had written:

```text
/ultra to-prd <user arguments>
```

Forward all arguments and context unchanged. Do not implement separate PRD-writing logic here; follow the core `ultra` workflow, then invoke `to-prd` through it.
