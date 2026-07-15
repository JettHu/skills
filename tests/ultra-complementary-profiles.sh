#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$REPO_ROOT" <<'PY'
from pathlib import Path
import importlib.util
import sys

repo = Path(sys.argv[1])
core = (repo / "skills/engineering/ultra/SKILL.md").read_text(encoding="utf-8")
profiles = (repo / "skills/engineering/ultra/PROFILES.md").read_text(encoding="utf-8")
prepare_path = repo / "tests/evals/ultra-complementary-profiles/prepare-fixture.py"
spec = importlib.util.spec_from_file_location("complementary_prepare", prepare_path)
prepare = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(prepare)
assert set(prepare.SCENARIOS) == {
    "architecture-native-ownership", "diagnosis-feedback-loop-first",
    "spec-independent-code-trigger", "tickets-review-publication",
    "short-evidence-complete", "long-stale-context", "triage-native-exploration",
}

for target in (
    "improve-codebase-architecture", "to-spec", "diagnosing-bugs", "to-tickets",
    "triage", "tdd", "prototype", "grill-me", "grill-with-docs", "handoff",
):
    assert f"| {target} |" in profiles, f"missing ownership profile: {target}"

for text in (
    "A goal may have only one owner and must run at most once",
    "This sufficiency check never suppresses an unconditional target-native stage",
    "Missing evidence in conversation context is not, by itself, a trigger",
    "Target-native delegation is outside this cap and remains intact",
    "invoke the target first so it can build and run its red-capable feedback loop",
):
    assert text in core, f"missing complementary routing rule: {text}"

for text in (
    "No Ultra pre-exploration",
    "Always review the complete Ticket set once",
    "publication/promotion",
    "Proportional review after actual code changes",
    "A short current artifact names affected modules and contracts",
    "A long prior discussion covers architecture but predates a changed contract",
):
    assert text in profiles, f"missing profile contract: {text}"

for proxy in ("20+ messages", "completely unfamiliar area", "already traced the code path"):
    assert proxy not in core + profiles, f"proxy heuristic returned: {proxy}"
PY

python3 - "$TMP/fake-qoder" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text("#!/usr/bin/env python3\nimport sys\nraise SystemExit(9)\n", encoding="utf-8")
path.chmod(0o755)
PY

runner=(python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/run-eval.py"
  --output "$TMP/runner" --run-id failure-record --scenario architecture-native-ownership
  --treatment-ref working-tree --ablation-ref HEAD --model fake --context-window 1000000
  --timeout 5 --qoder-bin "$TMP/fake-qoder" --variant treatment)
if "${runner[@]}" >/dev/null 2>&1; then
  echo "runner unexpectedly passed a failed model run" >&2
  exit 1
fi
if "${runner[@]}" >/dev/null 2>&1; then
  echo "runner unexpectedly passed a failed rerun" >&2
  exit 1
fi
test -f "$TMP/runner/failure-record/architecture-native-ownership/treatment/attempt-001/result.json"
test -f "$TMP/runner/failure-record/architecture-native-ownership/treatment/attempt-002/result.json"

python3 - "$TMP/sleep-qoder" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n", encoding="utf-8")
path.chmod(0o755)
PY
if python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/run-eval.py" \
  --output "$TMP/runner" --run-id timeout-record --scenario architecture-native-ownership \
  --treatment-ref working-tree --ablation-ref HEAD --model fake --context-window 1000000 \
  --timeout 1 --qoder-bin "$TMP/sleep-qoder" --variant ablation >/dev/null 2>&1; then
  echo "runner unexpectedly passed a timed-out model run" >&2
  exit 1
fi
python3 - "$TMP/runner/timeout-record/architecture-native-ownership/ablation/attempt-001/result.json" <<'PY'
import json
from pathlib import Path
import sys
result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["timed_out"] is True and result["run_exit_code"] == 124
PY

python3 "$REPO_ROOT/tests/evals/ultra-complementary-profiles/prepare-fixture.py" \
  --output "$TMP" --run-id fixture --scenario architecture-native-ownership \
  --treatment-ref working-tree --ablation-ref HEAD >/dev/null

python3 - "$REPO_ROOT" "$TMP" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv[1])
tmp = Path(sys.argv[2])
base = tmp / "fixture/architecture-native-ownership"
treatment = base / "treatment/attempt-001/repo"
ablation = base / "ablation/attempt-001/repo"
grader = repo / "tests/evals/ultra-complementary-profiles/grade-run.py"

t_manifest = json.loads((treatment.parent / "fixture-manifest.json").read_text())
a_manifest = json.loads((ablation.parent / "fixture-manifest.json").read_text())
assert t_manifest["common_hashes"] == a_manifest["common_hashes"], "pair fixtures are not equivalent"
assert subprocess.run([sys.executable, str(grader), str(treatment)], capture_output=True).returncode != 0

artifact = treatment / "artifacts/architecture-report.md"
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text("Order Router route_order ADR-0001\nvalidation: python3 scripts/check.py\n")
events = [
    {"name": "target-native-explore", "owner": "target", "goal": "discover-candidates", "evidence": "app/router.py"},
    {"name": "target-artifact", "owner": "target", "goal": "produce-report", "evidence": "artifacts/architecture-report.md"},
    {"name": "ultra-post-review", "owner": "ultra", "goal": "risk-and-adr-review", "evidence": "docs/adr/ADR-0001.md"},
    {"name": "validation", "owner": "root", "goal": "validate-repository", "evidence": "python3 scripts/check.py"},
]
(treatment / "artifacts/stage-evidence.json").write_text(json.dumps({"events": events}, indent=2) + "\n")
assert subprocess.run([sys.executable, str(grader), str(treatment)], capture_output=True).returncode == 0

artifact = ablation / "artifacts/architecture-report.md"
artifact.parent.mkdir(parents=True, exist_ok=True)
artifact.write_text("Order Router route_order ADR-0001\nvalidation: python3 scripts/check.py\n")
events.insert(0, {"name": "ultra-code-explore", "owner": "ultra", "goal": "duplicate-discovery", "evidence": "app/router.py"})
(ablation / "artifacts/stage-evidence.json").write_text(json.dumps({"events": events}, indent=2) + "\n")
assert subprocess.run([sys.executable, str(grader), str(ablation)], capture_output=True).returncode != 0
PY

echo "ultra complementary profiles fixture passed"
