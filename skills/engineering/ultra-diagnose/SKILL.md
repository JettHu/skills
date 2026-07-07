---
name: ultra-diagnose
description: Completion-friendly wrapper for /ultra diagnose.
disable-model-invocation: true
---

# Ultra Diagnose

Delegate to the `ultra` skill with target skill `diagnose`.

Treat the user's request as if they had written:

```text
/ultra diagnose <user arguments>
```

Forward all arguments and context unchanged through the core `ultra` workflow, which resolves the `diagnose` alias to the `diagnosing-bugs` profile before invoking the target skill.
