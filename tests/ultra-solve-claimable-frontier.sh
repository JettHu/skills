#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ADAPTER="$ROOT/skills/engineering/ultra/scripts/local_ticket_frontier.py"
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

init_repo() {
  local repo="$1"
  mkdir -p "$repo/docs/agents" "$repo/.scratch/feature/issues"
  git -C "$repo" init -q
  git -C "$repo" config user.name fixture
  git -C "$repo" config user.email fixture@example.com
  printf '# Base tracker\n' >"$repo/docs/agents/issue-tracker.md"
  write_contract "$repo" file-per-ticket '.scratch/<feature>/issues/<ticket-file>.md'
}

write_contract() {
  local repo="$1" representation="$2" location="$3"
  cat >"$repo/docs/agents/ultra-tracker.md" <<EOF
# Ultra Tracker Extension
Publication strategy: local-review-pending
Local Ticket representation: $representation
Local Ticket path: $location
Cancellation policy: retain-until-explicit-cleanup
Frontier adapter: bundled-local-markdown-v1
Ticket state fields: Status, State
Ready state: ready-for-agent
Completed state: completed
Human-blocked states: ready-for-human, needs-info
Blocker metadata fields: Blocked By, Blockers
Blocker body heading: Blocked by
Claim field: Flags
Claim field aliases: Flags, Labels
Claim value: solve-in-progress
Solve branch field: Solve Branch
Solve branch field aliases: Solve Branch, Branch
Solve worktree field: Solve Worktree
Solve worktree field aliases: Solve Worktree, Worktree
EOF
}

write_ticket() {
  local repo="$1" id="$2" status="$3" blockers="$4" flags="$5"
  cat >"$repo/.scratch/feature/issues/$id.md" <<EOF
Status: $status
Ticket ID: $id
Flags: $flags

# Ticket $id

## Blocked by

$blockers
EOF
}

frontier() {
  python3 "$ADAPTER" frontier --repo "$1" "${@:2}"
}

claim() {
  python3 "$ADAPTER" claim --repo "$1" --ticket-id "$2" \
    --expected-snapshot "$3" --branch "solve/$2" --worktree "/tmp/worktree-$2"
}

REPO="$TMPDIR_ROOT/file-per"
init_repo "$REPO"
write_ticket "$REPO" A ready-for-agent '' ''
write_ticket "$REPO" B ready-for-agent '- `A`' ''
write_ticket "$REPO" C ready-for-agent '- `A`' ''
write_ticket "$REPO" D ready-for-agent $'- `B`\n- `C`' ''
write_ticket "$REPO" PROVISIONAL review-pending '' ''
write_ticket "$REPO" CLAIMED ready-for-agent '' solve-in-progress
write_ticket "$REPO" HUMAN ready-for-human '' ''
write_ticket "$REPO" MISSING ready-for-agent '- `DOES-NOT-EXIST`' ''
write_ticket "$REPO" X ready-for-agent '- `Y`' ''
write_ticket "$REPO" Y ready-for-agent '- `X`' ''
cat >"$REPO/.scratch/feature/issues/NO-BLOCKER-FIELD.md" <<'EOF'
Status: ready-for-agent
Ticket ID: NO-BLOCKER-FIELD
Flags:

# Missing blocker metadata means unblocked
EOF

frontier "$REPO" >"$TMPDIR_ROOT/initial.json"
python3 - "$TMPDIR_ROOT/initial.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["safe_for_batch"] is True
assert data["claimable"] == ["A", "NO-BLOCKER-FIELD"]
reasons = data["non_frontier"]
assert "blocked-by:A:ready-for-agent" in reasons["B"]
assert "provisional-state:review-pending" in reasons["PROVISIONAL"]
assert "claim-conflict" in reasons["CLAIMED"]
assert "human-blocked-state:ready-for-human" in reasons["HUMAN"]
assert "missing-blocker-target:DOES-NOT-EXIST" in reasons["MISSING"]
assert "dependency-cycle" in reasons["X"] and "dependency-cycle" in reasons["Y"]
PY

# Explicit selection never expands to blockers or dependents.
frontier "$REPO" --ticket-id D >"$TMPDIR_ROOT/explicit.json"
python3 - "$TMPDIR_ROOT/explicit.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["claimable"] == []
assert list(data["non_frontier"]) == ["D"]
PY

snapshot="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot"])' "$TMPDIR_ROOT/initial.json")"
claim "$REPO" A "$snapshot" >"$TMPDIR_ROOT/claim-a.json"
grep -Fq 'Flags: solve-in-progress' "$REPO/.scratch/feature/issues/A.md"
grep -Fq 'Solve Branch: solve/A' "$REPO/.scratch/feature/issues/A.md"
grep -Fq 'Solve Worktree: /tmp/worktree-A' "$REPO/.scratch/feature/issues/A.md"
if claim "$REPO" A "$snapshot" >"$TMPDIR_ROOT/conflict.out" 2>&1; then
  echo 'conflicting or stale Claim unexpectedly succeeded' >&2
  exit 1
fi
grep -Fq 'stale dependency state' "$TMPDIR_ROOT/conflict.out"

# Finalizing A unlocks exactly B and C on the next graph read.
python3 - "$REPO/.scratch/feature/issues/A.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("Status: ready-for-agent", "Status: completed", 1)
text = text.replace("Flags: solve-in-progress", "Flags:", 1)
path.write_text(text, encoding="utf-8")
PY
frontier "$REPO" >"$TMPDIR_ROOT/second.json"
python3 - "$TMPDIR_ROOT/second.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["claimable"] == ["B", "C", "NO-BLOCKER-FIELD"]
assert "blocked-by:B:ready-for-agent" in data["non_frontier"]["D"]
PY

# Any dependency-state drift after discovery blocks Claim without mutation.
second_snapshot="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot"])' "$TMPDIR_ROOT/second.json")"
printf '\nchanged after discovery\n' >>"$REPO/.scratch/feature/issues/B.md"
if claim "$REPO" C "$second_snapshot" >"$TMPDIR_ROOT/stale.out" 2>&1; then
  echo 'stale frontier snapshot unexpectedly claimed a Ticket' >&2
  exit 1
fi
grep -Fq 'stale dependency state' "$TMPDIR_ROOT/stale.out"
if grep -Fq 'solve-in-progress' "$REPO/.scratch/feature/issues/C.md"; then
  echo 'stale Claim partially mutated the Ticket' >&2
  exit 1
fi

# Run-tagged Tickets retain the promoted-journal gate.
write_ticket "$REPO" UNPROMOTED ready-for-agent '' ''
python3 - "$REPO/.scratch/feature/issues/UNPROMOTED.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8").replace(
    "Ticket ID: UNPROMOTED\n", "Ticket ID: UNPROMOTED\nPublication Run: missing-run\nSource Spec: docs/spec.md\n", 1
)
path.write_text(text, encoding="utf-8")
PY
frontier "$REPO" --ticket-id UNPROMOTED >"$TMPDIR_ROOT/unpromoted.json"
python3 - "$TMPDIR_ROOT/unpromoted.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["claimable"] == []
assert any(reason.startswith("publication-invalid:") for reason in data["non_frontier"]["UNPROMOTED"])
PY

# Unsupported Claim configuration fails closed instead of returning an empty frontier.
sed '/^Claim value:/d' "$REPO/docs/agents/ultra-tracker.md" >"$TMPDIR_ROOT/unsafe-contract.md"
cp "$TMPDIR_ROOT/unsafe-contract.md" "$REPO/docs/agents/ultra-tracker.md"
if frontier "$REPO" >"$TMPDIR_ROOT/unsafe.out" 2>&1; then
  echo 'unsafe Claim contract unexpectedly produced a frontier' >&2
  exit 1
fi
grep -Fq 'must define exactly one Claim value' "$TMPDIR_ROOT/unsafe.out"

# The same graph and atomic Claim semantics work for safely delimited tickets-file.
SECTIONS="$TMPDIR_ROOT/sections"
mkdir -p "$SECTIONS/docs/agents" "$SECTIONS/.scratch/product"
git -C "$SECTIONS" init -q
write_contract "$SECTIONS" tickets-file '.scratch/<feature>/tickets.md'
cat >"$SECTIONS/.scratch/product/tickets.md" <<'EOF'
# Product Tickets

<!-- ultra-ticket:begin id=S-1 -->
Status: ready-for-agent
Ticket ID: S-1
Flags:

# Ticket S-1
<!-- ultra-ticket:end -->

<!-- ultra-ticket:begin id=S-2 -->
Status: ready-for-agent
Ticket ID: S-2
Labels:
Blockers: [S-1]

# Ticket S-2
<!-- ultra-ticket:end -->
EOF
frontier "$SECTIONS" >"$TMPDIR_ROOT/sections.json"
python3 - "$TMPDIR_ROOT/sections.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["claimable"] == ["S-1"]
assert "blocked-by:S-1:ready-for-agent" in data["non_frontier"]["S-2"]
PY
sections_snapshot="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot"])' "$TMPDIR_ROOT/sections.json")"
claim "$SECTIONS" S-1 "$sections_snapshot" >/dev/null
grep -Fq 'Flags: solve-in-progress' "$SECTIONS/.scratch/product/tickets.md"

python3 -m py_compile "$ADAPTER"
echo 'ultra solve claimable-frontier fixture passed'
