---
name: ultra-to-spec
description: Completion-friendly wrapper for /ultra to-spec.
disable-model-invocation: true
---

# Ultra To Spec

Delegate to the `ultra` skill with target skill `to-spec`.

Treat the user's request as if they had written:

```text
/ultra to-spec <user arguments>
```

Forward all arguments and context unchanged through the core `ultra` workflow, then invoke `to-spec` through it.
