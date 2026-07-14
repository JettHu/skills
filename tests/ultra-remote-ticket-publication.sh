#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ADAPTER="$ROOT/skills/engineering/ultra/scripts/remote_ticket_publication.py"
TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

spec() {
  cat >"$1" <<'JSON'
{"tickets":[{"key":"A","title":"Parent","body":"Parent body","blocks":["B"]},{"key":"B","title":"Child","body":"Child body","parent":"A"}]}
JSON
}

run() {
  python3 "$ADAPTER" publish "$@"
}

for provider in github gitlab; do
  dir="$TMPROOT/$provider-review-gate"; mkdir -p "$dir"; spec "$dir/spec.json"
  run --provider "$provider" --strategy local-staging --run-id review-gate --spec "$dir/spec.json" --remote-state "$dir/remote.json" --staging-root "$dir/.scratch/.ultra-staging" >"$dir/result.json"
  test -f "$dir/.scratch/.ultra-staging/review-gate/tickets.md"
  test -f "$dir/.scratch/.ultra-staging/review-gate/manifest.json"
  test ! -e "$dir/remote.json"
  grep -Fq '"phase": "review-pending"' "$dir/result.json"
done

reviewed="$TMPROOT/reviewed-staging"; mkdir -p "$reviewed"; spec "$reviewed/spec.json"
run --provider github --strategy local-staging --run-id reviewed-draft --spec "$reviewed/spec.json" --remote-state "$reviewed/remote.json" --staging-root "$reviewed/.scratch/.ultra-staging" >/dev/null
python3 - "$reviewed/.scratch/.ultra-staging/reviewed-draft/tickets.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text(path.read_text(encoding="utf-8").replace("Parent body", "Reviewed parent body"), encoding="utf-8")
PY
run --provider github --strategy local-staging --run-id reviewed-draft --spec "$reviewed/spec.json" --remote-state "$reviewed/remote.json" --staging-root "$reviewed/.scratch/.ultra-staging" --reviewed >/dev/null
python3 - "$reviewed/remote.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1]))
assert "Reviewed parent body" in state["tickets"][0]["body"]
PY

for provider in github gitlab; do
  for phase in create wire verify promote; do
    dir="$TMPROOT/$provider-remote-$phase"; mkdir -p "$dir"; spec "$dir/spec.json"
    if run --provider "$provider" --strategy remote-review-pending --run-id remote-run --spec "$dir/spec.json" --remote-state "$dir/remote.json" --native-relationships --reviewed --fail-at "$phase"; then
      echo "remote $phase failure unexpectedly succeeded" >&2; exit 1
    fi
    run --provider "$provider" --strategy remote-review-pending --run-id remote-run --spec "$dir/spec.json" --remote-state "$dir/remote.json" --native-relationships --reviewed >"$dir/result.json"
  python3 - "$dir" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]); state = json.loads((root / "remote.json").read_text()); result = json.loads((root / "result.json").read_text())
assert result["phase"] == "promoted" and result["claimable"] == ["A", "B"]
assert len(state["tickets"]) == 2
for item in state["tickets"]:
    assert item["ready"] and "ready-for-agent" in item["labels"] and "review-pending" not in item["labels"]
assert state["tickets"][0]["relationships"] == {"blocks": ["B"]}
assert state["tickets"][1]["relationships"] == {"blocks": [], "parent": ["A"]}
PY
  done
done

for provider in github gitlab; do
  dir="$TMPROOT/$provider-remote-review-fix"; mkdir -p "$dir"; spec "$dir/spec.json"
  if run --provider "$provider" --strategy remote-review-pending --run-id review-fix --spec "$dir/spec.json" --remote-state "$dir/remote.json" --reviewed --fail-at verify; then
    echo "review-fix setup failure unexpectedly succeeded" >&2; exit 1
  fi
  python3 - "$dir/remote.json" <<'PY'
import json, sys
path = sys.argv[1]
state = json.load(open(path))
assert all(not ticket["ready"] for ticket in state["tickets"])
state["tickets"][0]["body"] = state["tickets"][0]["body"].replace("Parent body", "Reviewer-fixed parent body")
state["tickets"][0]["relationships"] = {"blocks": []}
json.dump(state, open(path, "w"))
PY
  run --provider "$provider" --strategy remote-review-pending --run-id review-fix --spec "$dir/spec.json" --remote-state "$dir/remote.json" --reviewed >"$dir/result.json"
  python3 - "$dir" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
state = json.loads((root / "remote.json").read_text())
assert "Reviewer-fixed parent body" in state["tickets"][0]["body"]
assert state["tickets"][0]["relationships"] == {"blocks": []}
assert all(ticket["ready"] and "ready-for-agent" in ticket["labels"] for ticket in state["tickets"])
assert json.loads((root / "result.json").read_text())["claimable"] == ["A", "B"]
PY
done

for provider in github gitlab; do
  for phase in create wire verify promote; do
    dir="$TMPROOT/$provider-staging-$phase"; mkdir -p "$dir"; spec "$dir/spec.json"
    if run --provider "$provider" --strategy local-staging --run-id staging-run --spec "$dir/spec.json" --remote-state "$dir/remote.json" --staging-root "$dir/.scratch/.ultra-staging" --reviewed --fail-at "$phase"; then
      echo "staging $phase failure unexpectedly succeeded" >&2; exit 1
    fi
    test -f "$dir/.scratch/.ultra-staging/staging-run/manifest.json"
    run --provider "$provider" --strategy local-staging --run-id staging-run --spec "$dir/spec.json" --remote-state "$dir/remote.json" --staging-root "$dir/.scratch/.ultra-staging" --reviewed >"$dir/result.json"
    test ! -e "$dir/.scratch/.ultra-staging/staging-run"
  python3 - "$dir" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]); state = json.loads((root / "remote.json").read_text())
assert len(state["tickets"]) == 2
assert all(item["ready"] for item in state["tickets"])
assert all(item["relationship_mode"] == "textual-fallback" for item in state["tickets"])
assert "ultra-relationships:begin" in state["tickets"][0]["body"]
PY
  done
done

membership="$TMPROOT/membership"; mkdir -p "$membership"
cat >"$membership/three.json" <<'JSON'
{"tickets":[{"key":"A","title":"Parent","body":"Parent body","blocks":["B"]},{"key":"B","title":"Child","body":"Child body","parent":"A"},{"key":"C","title":"Obsolete","body":"Obsolete"}]}
JSON
spec "$membership/two.json"
if run --provider github --strategy remote-review-pending --run-id membership --spec "$membership/three.json" --remote-state "$membership/remote.json" --reviewed --fail-at verify; then
  echo "membership setup failure unexpectedly succeeded" >&2; exit 1
fi
if run --provider github --strategy remote-review-pending --run-id membership --spec "$membership/two.json" --remote-state "$membership/remote.json" --reviewed; then
  echo "subset resume unexpectedly succeeded" >&2; exit 1
fi
run --provider github --strategy remote-review-pending --run-id membership --spec "$membership/two.json" --remote-state "$membership/remote.json" --reviewed --supersede >/dev/null
python3 - "$membership/remote.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1]))
obsolete = next(ticket for ticket in state["tickets"] if ticket["key"] == "C")
assert obsolete["superseded"] and not obsolete["ready"]
assert "ready-for-agent" not in obsolete["labels"]
state["tickets"][0]["labels"].append("review-pending")
json.dump(state, open(sys.argv[1], "w"))
PY
if run --provider github --strategy remote-review-pending --run-id membership --spec "$membership/two.json" --remote-state "$membership/remote.json" --reviewed --supersede; then
  echo "provisional-marker drift unexpectedly succeeded" >&2; exit 1
fi

promoting="$TMPROOT/promoting"; mkdir -p "$promoting"; spec "$promoting/spec.json"
if run --provider gitlab --strategy local-staging --run-id promoting --spec "$promoting/spec.json" --remote-state "$promoting/remote.json" --staging-root "$promoting/.scratch/.ultra-staging" --reviewed --fail-at promote; then
  echo "promoting setup failure unexpectedly succeeded" >&2; exit 1
fi
python3 - "$promoting/remote.json" <<'PY'
import json, sys
state = json.load(open(sys.argv[1]))
state["tickets"][0]["relationships"] = {"blocks": ["wrong"]}
json.dump(state, open(sys.argv[1], "w"))
PY
if run --provider gitlab --strategy local-staging --run-id promoting --spec "$promoting/spec.json" --remote-state "$promoting/remote.json" --staging-root "$promoting/.scratch/.ultra-staging" --reviewed; then
  echo "promoting relationship drift unexpectedly succeeded" >&2; exit 1
fi
test -f "$promoting/.scratch/.ultra-staging/promoting/manifest.json"

echo "ultra remote ticket publication fixture passed"
