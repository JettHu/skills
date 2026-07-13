#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PHASE="${1:---expand}"

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
eval_record = (repo / ".evals/ultra-canonical-routing/20260713-model-adherence.md").read_text(
    encoding="utf-8"
)

for text in (
    "Examples — /ultra to-spec, /ultra diagnosing-bugs, /ultra to-tickets, /ultra solve --all.",
    "the `to-spec` profile defaults to code-only for well-bounded Specs",
    "For canonical shaping targets `to-spec` and `to-tickets`, review the exact generated artifact",
    "The main Agent fixes every finding derivable from approved context and current code",
    "canonical Spec/Ticket terminology (use `Ticket`, not `Issue`)",
    "Re-run the affected review after each repair",
    "Ask the user only for an unresolved scope, product-semantic, ownership, release-policy",
):
    assert text in core, f"core routing/review-fix contract missing: {text}"

for text in (
    "| to-spec | yes | cond | cond | — |",
    "| to-tickets | yes | cond | yes | — |",
    "### to-spec overrides",
    "### to-tickets overrides",
    "An unfamiliar external API, standard, or security requirement affects the Spec and approved local context cannot settle it",
    "The user explicitly requests external research and approved local context is insufficient",
    "The Spec is large, ambiguous, cross-system, or high-risk",
    "A source-verifiable external fact directly determines an acceptance criterion or blocker edge",
    "Approved local context cannot settle that fact",
    "do not use research for generic decomposition frameworks or unrelated open-source examples",
):
    assert text in profiles, f"canonical profile condition missing: {text}"

assert "| to-prd | yes |" not in profiles, "legacy to-prd is still a profile row"
assert "| to-issues | yes |" not in profiles, "legacy to-issues is still a profile row"

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
    repo / ".evals/ultra-canonical-routing/scripts/prepare-fixture.py",
    repo / ".evals/ultra-canonical-routing/scripts/grade-run.py",
):
    assert path.is_file(), f"model-adherence fixture surface missing: {path.relative_to(repo)}"

for scenario in (
    "01-to-spec-bounded",
    "02-to-spec-high-risk",
    "03-to-tickets-local",
    "04-to-tickets-external-fact",
    "05-review-fix",
    "06-human-owned-choice",
    "07-legacy-bridge",
):
    assert scenario in eval_record, f"model-adherence record missing scenario: {scenario}"
assert "final-state grader" in eval_record, "eval record must name final-state grading"

print(f"ultra canonical routing fixture passed ({phase[2:]} phase)")
PY

fixture_root="$(mktemp -d)"
trap 'rm -rf "$fixture_root"' EXIT
python3 "$REPO_ROOT/.evals/ultra-canonical-routing/scripts/prepare-fixture.py" \
  --source "$REPO_ROOT" --output "$fixture_root" >/dev/null
python3 - "$REPO_ROOT" "$fixture_root" <<'PY'
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv[1])
fixture = Path(sys.argv[2])
grader_path = repo / ".evals/ultra-canonical-routing/scripts/grade-run.py"
spec = importlib.util.spec_from_file_location("canonical_routing_grader", grader_path)
grader = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(grader)

manifest = json.loads((fixture / "contract-manifest.json").read_text(encoding="utf-8"))
for scenario_id, expected in grader.EXPECTED.items():
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
