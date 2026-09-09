#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PHASE="${1:---contract}"

if [[ "$PHASE" != "--expand" && "$PHASE" != "--contract" ]]; then
  echo "usage: $0 [--expand|--contract]" >&2
  exit 2
fi

python3 - "$REPO_ROOT" "$PHASE" <<'PY'
from pathlib import Path
import sys

repo = Path(sys.argv[1])
phase = sys.argv[2]
core = (repo / "skills/engineering/ultra/SKILL.md").read_text(encoding="utf-8")
profiles = (repo / "skills/engineering/ultra/PROFILES.md").read_text(encoding="utf-8")

for text in (
    "Dispatch solve only when the user requests Ticket execution through Ultra",
    "take the disposition directly from the profile: `target-native`, `ultra-additive`, or `unavailable`",
    "affected surfaces and governing contracts",
    "Long discussion, message count, broad familiarity",
    "For canonical shaping targets `to-spec` and `to-tickets`, review the exact generated artifact",
    "The main Agent fixes every derivable finding in those same artifacts",
    "The fresh-context reviewer checks Spec coverage, canonical terminology",
    "re-registers the repaired set, and re-runs affected review",
    "Ask only for unresolved human-owned scope, product/API/data/security/architecture/significant-UX",
):
    assert text in core, f"core routing/review-fix contract missing: {text}"

for text in (
    "| to-spec | Repository exploration is conditional `target-native`",
    "| to-tickets | Context gathering and repository exploration are conditional `target-native`",
    "Add research only for an unresolved source-verifiable external fact that directly determines the Spec",
    "Spec is large, ambiguous, cross-system, or high-risk",
    "Research only when a source-verifiable external fact directly determines acceptance or a blocker",
    "complete normative target conditions",
):
    assert text in profiles, f"canonical profile condition missing: {text}"

assert "20+ messages" not in profiles, "message-count proxy is still present"

bridge_rows = (
    "| to-prd | to-spec | Temporary internal bridge",
    "| to-issues | to-tickets | Temporary internal bridge",
)
if phase == "--expand":
    for row in bridge_rows:
        assert row in profiles, f"expand-phase bridge missing: {row}"
    assert "Ticket 15 removes it during catalog contraction." in profiles, (
        "temporary bridge must name its contraction owner"
    )
else:
    for row in bridge_rows:
        assert row not in profiles, f"contracted catalog retained bridge: {row}"

for path in (
    repo / "tests/evals/ultra-canonical-routing/prepare-fixture.py",
    repo / "tests/evals/ultra-canonical-routing/grade-run.py",
):
    assert path.is_file(), f"model-adherence fixture surface missing: {path.relative_to(repo)}"

print(f"ultra canonical routing fixture passed ({phase[2:]} phase)")
PY

fixture_root="$(mktemp -d)"
trap 'rm -rf "$fixture_root"' EXIT
phase_name="${PHASE#--}"
python3 "$REPO_ROOT/tests/evals/ultra-canonical-routing/prepare-fixture.py" \
  --source "$REPO_ROOT" --output "$fixture_root" --phase "$phase_name" >/dev/null
python3 - "$REPO_ROOT" "$fixture_root" "$phase_name" <<'PY'
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv[1])
fixture = Path(sys.argv[2])
phase = sys.argv[3]
grader_path = repo / "tests/evals/ultra-canonical-routing/grade-run.py"
spec = importlib.util.spec_from_file_location("canonical_routing_grader", grader_path)
grader = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(grader)

manifest = json.loads((fixture / "contract-manifest.json").read_text(encoding="utf-8"))
expected_by_id = dict(grader.COMMON_EXPECTED)
if phase == "expand":
    expected_by_id["07-legacy-bridge"] = grader.LEGACY_BRIDGE_EXPECTED
for scenario_id, expected in expected_by_id.items():
    decision = {key: value for key, value in expected.items() if key != "evidence"}
    decision["contract_sha256"] = manifest["contract_sha256"]
    decision["evidence"] = [expected["evidence"]]
    path = fixture / "scenarios" / scenario_id / "routing-decision.json"
    path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")

review_artifact = fixture / "scenarios/05-review-fix/artifact.md"
review_artifact.write_text(
    """# Generated Tickets

## Ticket: rename endpoint

POST /v2/accounts/rename requires auth.required: true.

Validation: pnpm test -- endpoint-rename
""",
    encoding="utf-8",
)
(fixture / "scenarios/06-human-owned-choice/escalation.json").write_text(
    json.dumps({"choice": "release owner"}) + "\n", encoding="utf-8"
)

command = [sys.executable, str(grader_path), "--output", str(fixture), "--json"]
quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
assert subprocess.run(command, check=False, **quiet).returncode == 0, "valid routing traces must grade"

scenarios_path = fixture / "scenarios.json"
original_scenarios = scenarios_path.read_text(encoding="utf-8")
scenarios = json.loads(original_scenarios)
removed_scenario = "07-legacy-bridge" if phase == "expand" else "06-human-owned-choice"
scenarios_path.write_text(
    json.dumps([scenario for scenario in scenarios if scenario["id"] != removed_scenario], indent=2)
    + "\n",
    encoding="utf-8",
)
assert subprocess.run(command, check=False, **quiet).returncode != 0, (
    "grader must reject a run missing an expected scenario"
)
scenarios_path.write_text(original_scenarios, encoding="utf-8")

path = fixture / "scenarios/01-to-spec-bounded/routing-decision.json"
decision = json.loads(path.read_text(encoding="utf-8"))
decision["contract_sha256"] = "not-the-supplied-contract"
path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
assert subprocess.run(command, check=False, **quiet).returncode != 0, (
    "grader must reject a routing trace not tied to the supplied contract"
)

decision["contract_sha256"] = manifest["contract_sha256"]
path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
profiles = fixture / "skill-input/skills/engineering/ultra/PROFILES.md"
profiles.write_text(profiles.read_text(encoding="utf-8") + "\ntrace mutation\n", encoding="utf-8")
assert subprocess.run(command, check=False, **quiet).returncode != 0, (
    "grader must reject a trace whose supplied contract content changed"
)
PY
