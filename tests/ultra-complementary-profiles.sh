#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

python3 - "$REPO_ROOT" <<'PY'
from pathlib import Path
import sys


root = Path(sys.argv[1])
profiles_text = (root / "skills/engineering/ultra/PROFILES.md").read_text(encoding="utf-8")
skill_text = (root / "skills/engineering/ultra/SKILL.md").read_text(encoding="utf-8")


def table_rows(markdown: str) -> dict[str, list[str]]:
    rows = {}
    for line in markdown.splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 6 and cells[0] not in {"Skill", "Scenario"}:
            rows[cells[0]] = cells
    return rows


rows = table_rows(profiles_text)
expected_targets = {
    "improve-codebase-architecture",
    "to-spec",
    "diagnosing-bugs",
    "to-tickets",
    "triage",
    "tdd",
    "prototype",
    "grill-me",
    "grill-with-docs",
    "handoff",
}
assert expected_targets <= rows.keys()
assert profiles_text.count("complete normative target conditions") == 1
assert "durable ownership contract" in profiles_text
assert "does not rediscover target ownership at runtime" in profiles_text


def route(
    target: str,
    *,
    additive_condition: bool = False,
    additive_goal_distinct: bool = False,
    goal_evidence_complete: bool = False,
    delegation_available: bool = True,
):
    row = rows[target]
    native = row[1]
    additive = row[3]
    native_stage = None if "No delegation requirement" in row[2] else {
        "owner": "target-native",
        "executor": "delegated-agent" if delegation_available else "root-serial-fallback",
        "goal": "native-goal",
    }
    stages = [] if native_stage is None else [native_stage]

    eligible = "`ultra-additive`" in additive
    if eligible and additive_condition and additive_goal_distinct and not goal_evidence_complete:
        stages.append({
            "owner": "ultra-additive",
            "executor": "delegated-agent" if delegation_available else "root-serial-fallback",
            "goal": "distinct-additive-goal",
        })
    return native, stages


# Native-only routing: Ultra has no additive stage to schedule.
native, stages = route("triage", additive_condition=True, additive_goal_distinct=True)
assert "unconditional `target-native`" in native
assert [stage["owner"] for stage in stages] == ["target-native"]

# Conditional additive routing requires both the named task condition and a distinct goal.
_, stages = route("to-spec", additive_condition=True, additive_goal_distinct=True)
assert [stage["owner"] for stage in stages] == ["target-native", "ultra-additive"]
_, missing_condition = route("to-spec", additive_condition=False, additive_goal_distinct=True)
_, duplicate_goal = route("to-spec", additive_condition=True, additive_goal_distinct=False)
assert [stage["owner"] for stage in missing_condition] == ["target-native"]
assert [stage["owner"] for stage in duplicate_goal] == ["target-native"]

# Current complete evidence covers an eligible goal; stale or missing context alone
# cannot manufacture the profile condition.
_, covered = route(
    "to-spec",
    additive_condition=True,
    additive_goal_distinct=True,
    goal_evidence_complete=True,
)
_, stale_without_trigger = route(
    "to-spec",
    additive_condition=False,
    additive_goal_distinct=True,
    goal_evidence_complete=False,
)
assert [stage["owner"] for stage in covered] == ["target-native"]
assert [stage["owner"] for stage in stale_without_trigger] == ["target-native"]

# Delegation availability changes only the executor. Ownership and exact-once
# evidence remain native, so Ultra cannot duplicate the goal.
_, serial = route(
    "to-spec",
    additive_condition=True,
    additive_goal_distinct=False,
    delegation_available=False,
)
assert serial == [{
    "owner": "target-native",
    "executor": "root-serial-fallback",
    "goal": "native-goal",
}]

# The portable runbook binds routing to the parsed profile contract.
required_contract = (
    "take the disposition directly from the profile",
    "A goal may have only one owner and must run at most once",
    "suppress the Ultra stage",
    "Missing evidence in conversation context is not, by itself, a trigger",
    "current, traceable to an approved artifact or repository observation",
    "affected surfaces and governing contracts",
    "material risks, dependencies, or unresolved facts",
    "a credible validation path",
    "Target-native delegation is outside this cap and remains intact",
    "execute the capability-equivalent stage serially",
    "invoke the target first so it can build and run its red-capable feedback loop",
)
for phrase in required_contract:
    assert phrase in skill_text, phrase

# Existing distinct behavior remains on its original owner and trigger.
assert "large, ambiguous, cross-system, or high-risk" in rows["to-spec"][4]
assert "Always review the complete Ticket set once" in rows["to-tickets"][4]
assert "publish/promote through the configured adapter" in rows["to-tickets"][4]
assert "After actual code changes, review once" in rows["diagnosing-bugs"][4]
assert "Proportional review after actual code changes" in rows["tdd"][3]
assert "only if the skill produced code changes" in skill_text

print("ultra complementary profile contract fixture passed")
PY
