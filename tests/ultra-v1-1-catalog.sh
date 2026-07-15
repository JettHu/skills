#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$REPO_ROOT" <<'PY'
import json
import re
import sys
from pathlib import Path


repo = Path(sys.argv[1])
engineering = repo / "skills/engineering"
expected_promoted = [
    "solve-records",
    "setup-ultra-skills",
    "ultra",
    "ultra-diagnose",
    "ultra-solve",
    "ultra-to-spec",
    "ultra-to-tickets",
]

for name, target in (("ultra-to-spec", "to-spec"), ("ultra-to-tickets", "to-tickets")):
    root = engineering / name
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    metadata = (root / "agents/openai.yaml").read_text(encoding="utf-8")
    assert f"name: {name}" in skill
    assert "disable-model-invocation: true" in skill
    assert f"Delegate to the `ultra` skill with target skill `{target}`." in skill
    assert f"/ultra {target} <user arguments>" in skill
    assert "Forward all arguments and context unchanged through the core `ultra` workflow" in skill
    assert "allow_implicit_invocation: false" in metadata
    assert f"${name}" in metadata

brief = (engineering / "ultra-to-tickets/references/agent-brief.md").read_text(
    encoding="utf-8"
)
ticket_wrapper = (engineering / "ultra-to-tickets/SKILL.md").read_text(encoding="utf-8")
assert "[Agent Brief contract](references/agent-brief.md)" in ticket_wrapper
assert "only when its optional, non-duplicative fields would add approved execution context" in ticket_wrapper
assert "Context:" not in brief
for field in ("Constraints:", "Validation:", "Hints:"):
    assert field in brief
assert "Omit each empty field and omit the entire section when every field is empty" in brief
assert "never participates in parsing, eligibility, state transitions, or merge gates" in brief

for retired in ("ultra-to-prd", "ultra-to-issues"):
    assert not (engineering / retired / "SKILL.md").exists(), f"retired wrapper remains: {retired}"
assert not (engineering / "wayfinder/SKILL.md").exists(), "Wayfinder remains upstream-owned"

plugin = json.loads((repo / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
marketplace = json.loads((repo / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
plugin_names = [Path(value).name for value in plugin["skills"]]
stable = next(item for item in marketplace["plugins"] if item["name"] == "jett-skills")
marketplace_names = [Path(value).name for value in stable["skills"]]
assert plugin_names == expected_promoted
assert marketplace_names == expected_promoted
assert len(plugin_names) == len(set(plugin_names))
assert len(marketplace_names) == len(set(marketplace_names))
assert not any("in-progress" in value for value in plugin["skills"] + stable["skills"])

readme = (repo / "README.md").read_text(encoding="utf-8")
engineering_readme = (engineering / "README.md").read_text(encoding="utf-8")
profiles = (engineering / "ultra/PROFILES.md").read_text(encoding="utf-8")
core = (engineering / "ultra/SKILL.md").read_text(encoding="utf-8")
publication = (engineering / "ultra/references/ticket-review-publication.md").read_text(
    encoding="utf-8"
)
for name in expected_promoted:
    assert plugin_names.count(name) == 1
for name in ("setup-ultra-skills", "ultra-to-spec", "ultra-to-tickets"):
    assert name in readme
for term in ("Spec", "Tickets", "Claim", "Attempt", "Solve Record"):
    assert term in readme or term in engineering_readme

live_promoted = "\n".join(
    [
        readme,
        engineering_readme,
        profiles,
        core,
        (repo / ".claude-plugin/plugin.json").read_text(encoding="utf-8"),
        (repo / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"),
    ]
    + [path.read_text(encoding="utf-8") for path in engineering.glob("*/SKILL.md")]
    + [path.read_text(encoding="utf-8") for path in engineering.glob("*/agents/openai.yaml")]
)
for retired in ("ultra-to-prd", "ultra-to-issues", "/ultra to-prd", "/ultra to-issues"):
    assert retired not in live_promoted, f"live promoted surface retains retired route: {retired}"
assert "| to-prd | to-spec |" not in profiles
assert "| to-issues | to-tickets |" not in profiles

# Wrapper smoke: both exact routes resolve to canonical profile rows. The target-specific
# behavior stays owned by core Ultra, not duplicated into the thin wrappers.
assert re.search(r"^\| to-spec \| yes \| cond \| cond \|", profiles, re.MULTILINE)
assert "The Spec is large, ambiguous, cross-system, or high-risk" in profiles
assert re.search(r"^\| to-tickets \| yes \| cond \| yes \|", profiles, re.MULTILINE)
assert "For `to-tickets`, first read and follow [Ticket Review Publication]" in core
assert "The main Agent fixes every derivable finding in those same artifacts" in core
assert "only verified promotion yields `ready-for-agent`" in core
assert "review-pending" in publication and "publication-run identity" in publication
assert "Manual fallback is prohibited for every operation" in publication
assert "Publication has no public" in publication

print("ultra v1.1 catalog and wrapper smoke fixture passed")
PY
