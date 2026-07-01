---
name: ultra-to-prd
description: Completion-friendly wrapper for /ultra to-prd.
disable-model-invocation: true
---

# Ultra To PRD

Delegate to the `ultra` skill with target skill `to-prd`.

Treat the user's request as if they had written:

```text
/ultra to-prd <user arguments>
```

Forward all arguments and context unchanged. Do not implement separate PRD-writing logic here; follow the core `ultra` workflow, then invoke `to-prd` through it.
