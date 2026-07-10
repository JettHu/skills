#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$REPO_ROOT" <<'PY'
from pathlib import Path
import sys

repo = Path(sys.argv[1])
core = (repo / "skills/engineering/ultra/SKILL.md").read_text(encoding="utf-8")
profiles = (repo / "skills/engineering/ultra/PROFILES.md").read_text(encoding="utf-8")

core_lenses = {
    "Architecture agent": "**Architecture agent** (parallel codebase exploration):",
    "Risk agent": "**Risk agent** (parallel codebase exploration):",
    "Industry agent": "**Industry agent** (with web search):",
    "Completeness reviewer": "**Completeness reviewer**:",
    "Consistency reviewer": "**Consistency reviewer**:",
}
profile_template_headings = (
    "## Suggested agent briefs",
    "### Architecture agent (code)",
    "### Risk agent (code)",
    "### Industry agent (research)",
    "### Completeness reviewer (review)",
    "### Consistency reviewer (review)",
)

for lens, definition in core_lenses.items():
    count = core.count(definition)
    assert count == 1, f"{lens} must have exactly one compact core definition, found {count}"

for heading in profile_template_headings:
    assert heading not in profiles, f"profile prompt template returned: {heading}"

assert not any(line.startswith(">") for line in profiles.splitlines()), (
    "profiles must retain flags, overrides, and rationale rather than prompt templates"
)

for heading in (
    "# Enhancement Profiles",
    "## Skill aliases",
    "## When to skip or narrow pre-exploration",
    "### to-prd overrides",
):
    assert heading in profiles, f"profile guidance lost its required section: {heading}"

print("ultra lens ownership fixture passed")
PY
