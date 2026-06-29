---
name: ultra-diagnose
description: Explicit completion-friendly wrapper for /ultra diagnose and /ultra diagnosing-bugs. Use only when the user invokes ultra-diagnose, asks for the ultra-enhanced diagnose flow, or writes /ultra diagnose.
---

# Ultra Diagnose

Delegate to the `ultra` skill with target skill `diagnose`.

Treat the user's request as if they had written:

```text
/ultra diagnose <user arguments>
```

Forward all arguments and context unchanged. Do not implement separate debugging logic here; follow the core `ultra` workflow, which resolves the `diagnose` alias to the `diagnosing-bugs` profile before invoking the target skill.
