#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 - "$TMP/fake-codex" <<'PY'
from pathlib import Path
import json
import sys

path = Path(sys.argv[1])
path.write_text(
    "#!/usr/bin/env python3\n"
    "import json, sys\n"
    "if '--version' in sys.argv:\n"
    "    print('codex-cli 0.fake')\n"
    "elif sys.argv[1:3] == ['features', 'list']:\n"
    "    print('multi_agent       stable             true')\n"
    "    print('multi_agent_mode  removed            false')\n"
    "    print('multi_agent_v2    under development  false')\n"
    "else:\n"
    "    marker = '[eval-stage:primary-collaboration-canary]'\n"
    "    started = {'type': 'item.started', 'item': {'id': 'spawn-1', 'type': 'collab_tool_call', 'tool': 'spawn_agent', 'prompt': marker, 'agents_states': {}, 'status': 'in_progress'}}\n"
    "    completed = {'type': 'item.completed', 'item': {'id': 'spawn-1', 'type': 'collab_tool_call', 'tool': 'spawn_agent', 'prompt': marker, 'receiver_thread_ids': ['child-1'], 'agents_states': {'child-1': {'status': 'completed'}}, 'status': 'completed'}}\n"
    "    print(json.dumps(started)); print(json.dumps(completed))\n",
    encoding="utf-8",
)
path.chmod(0o755)
PY

python3 "$REPO_ROOT/tests/evals/primary-collaboration-canary/run-canary.py" \
  --output "$TMP/evidence" \
  --run-id deterministic-happy \
  --model fake-primary \
  --reasoning-effort medium \
  --timeout 5 \
  --primary-bin "$TMP/fake-codex" >/dev/null

ATTEMPT="$TMP/evidence/deterministic-happy/attempt-001"
python3 - "$ATTEMPT" <<'PY'
from pathlib import Path
import json
import sys

attempt = Path(sys.argv[1])
result = json.loads((attempt / "result.json").read_text(encoding="utf-8"))
grade = json.loads((attempt / "grader-output.json").read_text(encoding="utf-8"))
assert result["verdict"] == "PASS"
assert grade["passed"] is True
assert grade["spawn_count"] == 1
assert grade["child_identities"] == ["child-1"]
for name in (
    "invocation.json", "runtime-version.txt", "feature-preflight.json",
    "raw-stdout.jsonl", "stderr.log", "grader-control.json",
    "grader-output.json", "result.json", "repository-evidence.json",
):
    assert (attempt / name).is_file(), name
PY

python3 "$REPO_ROOT/tests/evals/primary-collaboration-canary/deterministic-fixture.py"
