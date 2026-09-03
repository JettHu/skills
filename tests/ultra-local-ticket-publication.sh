#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ADAPTER="$REPO_ROOT/skills/engineering/ultra/scripts/local_ticket_publication.py"
FRONTIER="$REPO_ROOT/skills/engineering/ultra/scripts/local_ticket_frontier.py"
TMPDIR_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ultra-local-publication.XXXXXX")"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

FILE_REPO="$TMPDIR_ROOT/file-per"
SECTION_REPO="$TMPDIR_ROOT/tickets-file"
mkdir -p "$FILE_REPO/.scratch/feature/issues" "$SECTION_REPO/.scratch/feature"

write_contract() {
  local repo="$1" policy="$2"
  local representation="${3:-file-per-ticket}"
  local location="${4:-.scratch/<feature>/issues/<ticket-file>.md}"
  mkdir -p "$repo/docs/agents"
  printf 'Publication strategy: local-review-pending\nLocal Ticket representation: %s\nLocal Ticket path: %s\nCancellation policy: %s\nFrontier adapter: bundled-local-markdown-v1\nTicket ID field aliases: Ticket ID, ID\nPublication Run field aliases: Publication Run\nSource field aliases: Source Spec, Parent\nTicket state fields: Status, State\nTicket state values: review-pending, ready-for-agent, completed, ready-for-human, needs-info\nReady state: ready-for-agent\nCompleted state: completed\nHuman-blocked states: ready-for-human, needs-info\nBlocker metadata fields: Blocked By, Blockers\nBlocker body heading: Blocked by\nClaim field: Flags\nClaim field aliases: Flags, Labels\nClaim value: solve-in-progress\nSolve branch field: Solve Branch\nSolve branch field aliases: Solve Branch, Branch\nSolve worktree field: Solve Worktree\nSolve worktree field aliases: Solve Worktree, Worktree\n' "$representation" "$location" "$policy" >"$repo/docs/agents/ultra-tracker.md"
}

write_contract "$FILE_REPO" retain-until-explicit-cleanup
write_contract "$SECTION_REPO" retain-until-explicit-cleanup tickets-file .scratch/feature/tickets.md

write_file_ticket() {
  local path="$1" id="$2" run="$3" status="$4" blockers="$5" title="$6"
  python3 - "$path" "$id" "$run" "$status" "$blockers" "$title" <<'PY'
from pathlib import Path
import sys

path, ticket_id, run_id, status, blockers, title = sys.argv[1:]
Path(path).write_text(
    f"Status: {status}\n"
    f"Ticket ID: {ticket_id}\n"
    f"Publication Run: {run_id}\n"
    "Source Spec: docs/spec.md\n"
    f"Blocked By: {blockers}\n"
    "Flags:\n\n"
    f"# {title}\n\n"
    "## Acceptance criteria\n\n- [ ] independently verifiable\n",
    encoding="utf-8",
)
PY
}

adapter() {
  local repo="$1" representation="$2" location="$3" run="$4" action="$5"
  shift 5
  python3 "$ADAPTER" "$action" \
    --repo "$repo" --representation "$representation" \
    --location "$location" --run-id "$run" "$@"
}

# Acceptance completion is operational evidence added after a solve. Checking
# an unchanged criterion must not invalidate the reviewed Ticket body, while
# changing the criterion text must still fail closed.
CHECKBOX_REPO="$TMPDIR_ROOT/acceptance-checkbox"
mkdir -p "$CHECKBOX_REPO/.scratch/feature/issues"
write_contract "$CHECKBOX_REPO" retain-until-explicit-cleanup
write_file_ticket "$CHECKBOX_REPO/.scratch/feature/issues/CHECKBOX-1.md" CHECKBOX-1 checkbox-run review-pending "" "Acceptance checkbox normalization"
adapter "$CHECKBOX_REPO" file-per-ticket .scratch/feature/issues checkbox-run register >/dev/null
python3 - "$CHECKBOX_REPO/.scratch/feature/issues/CHECKBOX-1.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(
    path.read_text(encoding="utf-8").replace(
        "- [ ] independently verifiable", "- [x] independently verifiable", 1
    ),
    encoding="utf-8",
)
PY
adapter "$CHECKBOX_REPO" file-per-ticket .scratch/feature/issues checkbox-run promote >/dev/null
python3 - "$CHECKBOX_REPO/.scratch/feature/issues/CHECKBOX-1.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(
    path.read_text(encoding="utf-8").replace(
        "independently verifiable", "semantically changed", 1
    ),
    encoding="utf-8",
)
PY
if adapter "$CHECKBOX_REPO" file-per-ticket .scratch/feature/issues checkbox-run promote >"$TMPDIR_ROOT/checkbox-semantic-change.out" 2>&1; then
  echo "publication accepted changed acceptance text" >&2
  exit 1
fi
grep -Fq 'Ticket content changed after review registration' "$TMPDIR_ROOT/checkbox-semantic-change.out"

python3 - "$ADAPTER" <<'PY'
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

sys.path.insert(0, str(Path(sys.argv[1]).parent))
spec = spec_from_file_location("local_ticket_publication", sys.argv[1])
module = module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

kwargs = {
    "state_fields": ("status",),
    "claim_fields": ("flags",),
    "branch_fields": ("solve_branch",),
    "worktree_fields": ("solve_worktree",),
}
before = "Status: review-pending\n\n# Ticket\n\nBody\n"
terminal = before.rstrip() + "\n\n## Solve Records\n\n- `../solve-records/abc.md`\n"
assert module.normalize_operational_fields(before, **kwargs) == module.normalize_operational_fields(terminal, **kwargs)

before_with_heading = (
    "Status: review-pending\n\n# Ticket\n\nBody\n\n"
    "## Solve Records\n\n## Acceptance\n\n- [ ] check\n"
)
nonterminal = before_with_heading.replace(
    "## Solve Records\n\n## Acceptance",
    "## Solve Records\n\n- `../solve-records/abc.md`\n\n## Acceptance",
)
assert module.normalize_operational_fields(before_with_heading, **kwargs) == module.normalize_operational_fields(nonterminal, **kwargs)

for invalid in (
    "- `../solve-records/abc.md semantic waiver`\n",
    "- `notes/solve-records/abc.md`\n",
    "- `../solve-records/abc.txt`\n",
):
    changed = before.rstrip() + "\n\n## Solve Records\n\n" + invalid
    assert module.normalize_operational_fields(before, **kwargs) != module.normalize_operational_fields(changed, **kwargs)
PY

# Publication digests cover reviewed semantics, not adapter-owned lifecycle
# evidence. A complete run must remain valid while one member is claimed and
# finalized, while a real body edit must still invalidate the run.
LIFECYCLE_REPO="$TMPDIR_ROOT/publication-lifecycle"
mkdir -p "$LIFECYCLE_REPO/.scratch/feature/issues"
git -C "$LIFECYCLE_REPO" init -q
write_contract "$LIFECYCLE_REPO" retain-until-explicit-cleanup
for ticket_id in LIFE-1 LIFE-2; do
  write_file_ticket "$LIFECYCLE_REPO/.scratch/feature/issues/$ticket_id.md" \
    "$ticket_id" lifecycle-run review-pending "" "Lifecycle $ticket_id"
  python3 - "$LIFECYCLE_REPO/.scratch/feature/issues/$ticket_id.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(
    path.read_text(encoding="utf-8").replace("Flags:\n\n", "\n", 1),
    encoding="utf-8",
)
PY
done
adapter "$LIFECYCLE_REPO" file-per-ticket .scratch/feature/issues lifecycle-run register >/dev/null
adapter "$LIFECYCLE_REPO" file-per-ticket .scratch/feature/issues lifecycle-run promote >/dev/null
python3 "$FRONTIER" frontier --repo "$LIFECYCLE_REPO" --ticket-id LIFE-1 >"$TMPDIR_ROOT/lifecycle-frontier.json"
lifecycle_snapshot="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["snapshot"])' "$TMPDIR_ROOT/lifecycle-frontier.json")"
python3 "$FRONTIER" claim --repo "$LIFECYCLE_REPO" --ticket-id LIFE-1 \
  --expected-snapshot "$lifecycle_snapshot" --branch solve/LIFE-1 \
  --worktree "$LIFECYCLE_REPO-worktree" >/dev/null
adapter "$LIFECYCLE_REPO" file-per-ticket .scratch/feature/issues lifecycle-run inspect >/dev/null

python3 - "$LIFECYCLE_REPO/.scratch/feature/issues/LIFE-1.md" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = re.sub(r"(?m)^Status:[ \t]*.*$", "Status: completed", text, count=1)
text = re.sub(r"(?m)^(?:Flags|Solve Branch|Solve Worktree):[ \t]*.*\n?", "", text)
metadata_end = text.index("\n\n")
text = text[:metadata_end] + "\ncompleted: 2026-08-21" + text[metadata_end:]
text = (
    text.rstrip()
    + "\n\n## Comments\n\n### Solve Record\n\n- `../solve-records/life-1-legacy.md`\n"
    + "\n## Solve Records\n\n- `../solve-records/life-1.md`\n"
)
path.write_text(text, encoding="utf-8")
PY
adapter "$LIFECYCLE_REPO" file-per-ticket .scratch/feature/issues lifecycle-run inspect >/dev/null
python3 "$FRONTIER" frontier --repo "$LIFECYCLE_REPO" --ticket-id LIFE-2 >"$TMPDIR_ROOT/lifecycle-sibling.json"
python3 - "$TMPDIR_ROOT/lifecycle-sibling.json" <<'PY'
import json
import sys

payload = json.load(open(sys.argv[1], encoding="utf-8"))
assert payload["claimable"] == ["LIFE-2"], payload
PY
python3 - "$LIFECYCLE_REPO/.scratch/feature/issues/LIFE-1.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(
    path.read_text(encoding="utf-8").replace(
        "independently verifiable", "semantically changed", 1
    ),
    encoding="utf-8",
)
PY
if adapter "$LIFECYCLE_REPO" file-per-ticket .scratch/feature/issues lifecycle-run inspect >"$TMPDIR_ROOT/lifecycle-semantic-change.out" 2>&1; then
  echo "publication accepted changed lifecycle Ticket body" >&2
  exit 1
fi
grep -Fq 'Ticket content changed after review registration' "$TMPDIR_ROOT/lifecycle-semantic-change.out"

# Every adapter operation is authorized by the one configured Local Markdown
# representation and durable surface, never by CLI coordinates alone.
surface_failures=0
SURFACE_REGISTER_REPO="$TMPDIR_ROOT/surface-register"
mkdir -p "$SURFACE_REGISTER_REPO/.scratch/outside/issues"
write_contract "$SURFACE_REGISTER_REPO" delete-on-cancel file-per-ticket '.scratch/configured/issues/<ticket-file>.md'
write_file_ticket "$SURFACE_REGISTER_REPO/.scratch/outside/issues/SURFACE-REGISTER.md" SURFACE-REGISTER surface-register-run review-pending "" "Outside configured surface"
if adapter "$SURFACE_REGISTER_REPO" file-per-ticket .scratch/outside/issues surface-register-run register >"$TMPDIR_ROOT/surface-register.out" 2>&1; then
  echo "register accepted a path outside the configured surface" >&2
  surface_failures=1
fi
grep -Fq 'configured Local Ticket path does not authorize requested surface' "$TMPDIR_ROOT/surface-register.out" || surface_failures=1
if test -e "$SURFACE_REGISTER_REPO/.scratch/outside/issues/.ultra-publications"; then
  echo "surface-mismatched register created coordination metadata" >&2
  surface_failures=1
fi

prepare_surface_run() {
  local repo="$1" run="$2" id="$3"
  mkdir -p "$repo/.scratch/outside/issues"
  write_contract "$repo" retain-until-explicit-cleanup file-per-ticket '.scratch/outside/issues/<ticket-file>.md'
  write_file_ticket "$repo/.scratch/outside/issues/$id.md" "$id" "$run" review-pending "" "Surface drift fixture"
  adapter "$repo" file-per-ticket .scratch/outside/issues "$run" register >/dev/null
  write_contract "$repo" delete-on-cancel file-per-ticket '.scratch/configured/issues/<ticket-file>.md'
}

SURFACE_PROMOTE_REPO="$TMPDIR_ROOT/surface-promote"
prepare_surface_run "$SURFACE_PROMOTE_REPO" surface-promote-run SURFACE-PROMOTE
if adapter "$SURFACE_PROMOTE_REPO" file-per-ticket .scratch/outside/issues surface-promote-run promote >"$TMPDIR_ROOT/surface-promote.out" 2>&1; then
  echo "promote accepted a path outside the configured surface" >&2
  surface_failures=1
fi
grep -Fq 'configured Local Ticket path does not authorize requested surface' "$TMPDIR_ROOT/surface-promote.out" || surface_failures=1
grep -Fq 'Status: review-pending' "$SURFACE_PROMOTE_REPO/.scratch/outside/issues/SURFACE-PROMOTE.md" || surface_failures=1

SURFACE_CLEANUP_REPO="$TMPDIR_ROOT/surface-cleanup"
prepare_surface_run "$SURFACE_CLEANUP_REPO" surface-cleanup-run SURFACE-CLEANUP
if adapter "$SURFACE_CLEANUP_REPO" file-per-ticket .scratch/outside/issues surface-cleanup-run cleanup >"$TMPDIR_ROOT/surface-cleanup.out" 2>&1; then
  echo "cleanup accepted a path outside the configured surface" >&2
  surface_failures=1
fi
grep -Fq 'configured Local Ticket path does not authorize requested surface' "$TMPDIR_ROOT/surface-cleanup.out" || surface_failures=1
test -e "$SURFACE_CLEANUP_REPO/.scratch/outside/issues/SURFACE-CLEANUP.md" || surface_failures=1

SURFACE_INSPECT_REPO="$TMPDIR_ROOT/surface-inspect"
prepare_surface_run "$SURFACE_INSPECT_REPO" surface-inspect-run SURFACE-INSPECT
if adapter "$SURFACE_INSPECT_REPO" file-per-ticket .scratch/outside/issues surface-inspect-run inspect >"$TMPDIR_ROOT/surface-inspect.out" 2>&1; then
  echo "inspect accepted a path outside the configured surface" >&2
  surface_failures=1
fi
grep -Fq 'configured Local Ticket path does not authorize requested surface' "$TMPDIR_ROOT/surface-inspect.out" || surface_failures=1

SURFACE_CLAIM_REPO="$TMPDIR_ROOT/surface-claim"
mkdir -p "$SURFACE_CLAIM_REPO/.scratch/outside/issues"
write_contract "$SURFACE_CLAIM_REPO" retain-until-explicit-cleanup file-per-ticket '.scratch/outside/issues/<ticket-file>.md'
write_file_ticket "$SURFACE_CLAIM_REPO/.scratch/outside/issues/SURFACE-CLAIM.md" SURFACE-CLAIM surface-claim-run review-pending "" "Surface claim fixture"
adapter "$SURFACE_CLAIM_REPO" file-per-ticket .scratch/outside/issues surface-claim-run register >/dev/null
adapter "$SURFACE_CLAIM_REPO" file-per-ticket .scratch/outside/issues surface-claim-run promote >/dev/null
write_contract "$SURFACE_CLAIM_REPO" delete-on-cancel file-per-ticket '.scratch/configured/issues/<ticket-file>.md'
if adapter "$SURFACE_CLAIM_REPO" file-per-ticket .scratch/outside/issues surface-claim-run claim --ticket-id SURFACE-CLAIM >"$TMPDIR_ROOT/surface-claim.out" 2>&1; then
  echo "claim accepted a path outside the configured surface" >&2
  surface_failures=1
fi
grep -Fq 'unsupported operation: claim' "$TMPDIR_ROOT/surface-claim.out" || surface_failures=1
if grep -Fq 'solve-in-progress' "$SURFACE_CLAIM_REPO/.scratch/outside/issues/SURFACE-CLAIM.md"; then
  echo "surface-mismatched claim mutated Claim metadata" >&2
  surface_failures=1
fi

REPRESENTATION_REPO="$TMPDIR_ROOT/surface-representation"
mkdir -p "$REPRESENTATION_REPO/.scratch/feature/issues"
write_contract "$REPRESENTATION_REPO" retain-until-explicit-cleanup tickets-file .scratch/feature/tickets.md
write_file_ticket "$REPRESENTATION_REPO/.scratch/feature/issues/REPRESENTATION-1.md" REPRESENTATION-1 representation-run review-pending "" "Representation mismatch"
if adapter "$REPRESENTATION_REPO" file-per-ticket .scratch/feature/issues representation-run register >"$TMPDIR_ROOT/surface-representation.out" 2>&1; then
  echo "register accepted a representation mismatch" >&2
  surface_failures=1
fi
grep -Fq 'configured Local Ticket representation does not match the requested adapter' "$TMPDIR_ROOT/surface-representation.out" || surface_failures=1
test "$surface_failures" -eq 0

# Setup and runtime enforce the same canonical placeholder grammar. A
# file-per-ticket contract has exactly one complete final <ticket-file>
# component; unknown, embedded, repeated, or missing forms fail closed before
# coordination metadata is created.
for invalid_pattern in \
  '.scratch/<feature>/issues/<ticket-file><ticket-file>' \
  '.scratch/<feature>/issues/prefix-<ticket-file>.md' \
  '.scratch/<unknown>/issues/<ticket-file>.md' \
  '.scratch/<feature>/issues'; do
  STRICT_REPO="$TMPDIR_ROOT/strict-$(printf '%s' "$invalid_pattern" | shasum | cut -c1-12)"
  mkdir -p "$STRICT_REPO/.scratch/feature/issues"
  write_contract "$STRICT_REPO" delete-on-cancel file-per-ticket "$invalid_pattern"
  write_file_ticket "$STRICT_REPO/.scratch/feature/issues/STRICT.md" STRICT strict-run review-pending "" "Strict placeholder grammar"
  if adapter "$STRICT_REPO" file-per-ticket .scratch/feature/issues strict-run register >"$TMPDIR_ROOT/strict-placeholder.out" 2>&1; then
    echo "adapter accepted non-canonical file-per-ticket path: $invalid_pattern" >&2
    exit 1
  fi
  test ! -e "$STRICT_REPO/.scratch/feature/issues/.ultra-publications"
done

# Deterministically inject a symlink target change after the pre-lock surface
# resolution. Each operation must retry against one stable resolved surface;
# it must never read or mutate B while using A's journal identity.
python3 - "$ADAPTER" "$TMPDIR_ROOT/surface-swap" <<'PY'
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys

adapter_path, root_arg = sys.argv[1:]
sys.path.insert(0, str(Path(adapter_path).resolve().parent))
spec = importlib.util.spec_from_file_location("local_ticket_publication", adapter_path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
root = Path(root_arg)
real_lock = module.mutation_lock


def write_contract(repo: Path) -> None:
    path = repo / "docs/agents/ultra-tracker.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Publication strategy: local-review-pending\n"
        "Local Ticket representation: file-per-ticket\n"
        "Local Ticket path: .scratch/<feature>/issues/<ticket-file>.md\n"
        "Cancellation policy: delete-on-cancel\n"
        "Ticket ID field aliases: Ticket ID, ID\n"
        "Publication Run field aliases: Publication Run\n"
        "Source field aliases: Source Spec, Parent\n"
        "Ticket state fields: Status, State\n"
        "Ticket state values: review-pending, ready-for-agent, completed, ready-for-human, needs-info\n"
        "Ready state: ready-for-agent\n"
        "Completed state: completed\n"
        "Human-blocked states: ready-for-human, needs-info\n"
        "Blocker metadata fields: Blocked By, Blockers\n"
        "Claim field aliases: Flags, Labels\n"
        "Solve branch field aliases: Solve Branch, Branch\n"
        "Solve worktree field aliases: Solve Worktree, Worktree\n",
        encoding="utf-8",
    )


def write_ticket(path: Path, ticket_id: str, run_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "Status: review-pending\n"
        f"Ticket ID: {ticket_id}\n"
        f"Publication Run: {run_id}\n"
        "Source Spec: docs/spec.md\n"
        "Blocked By:\n"
        "Flags:\n\n"
        f"# {ticket_id}\n",
        encoding="utf-8",
    )


def target(repo: Path, name: str) -> Path:
    return repo / ".scratch" / name / "issues"


def journal(repo: Path, name: str, run_id: str) -> Path:
    return target(repo, name) / ".ultra-publications" / f"{run_id}.json"


def point(link: Path, name: str) -> None:
    link.unlink(missing_ok=True)
    link.symlink_to(name, target_is_directory=True)


def install_one_shot_swap(repo: Path) -> None:
    link = repo / ".scratch" / "current"
    calls = {"count": 0}

    @contextmanager
    def swapping_lock(location, representation):
        calls["count"] += 1
        if calls["count"] == 1:
            point(link, "B")
        with real_lock(location, representation):
            yield

    module.mutation_lock = swapping_lock


def prepare(name: str, run_id: str, ticket_id: str, register_both: bool) -> Path:
    repo = (root / name).resolve()
    module.mutation_lock = real_lock
    write_contract(repo)
    for surface in ("A", "B"):
        write_ticket(target(repo, surface) / f"{ticket_id}.md", ticket_id, run_id)
    link = repo / ".scratch" / "current"
    point(link, "A")
    if register_both:
        module.register(repo, "file-per-ticket", ".scratch/A/issues", run_id, False)
        module.register(repo, "file-per-ticket", ".scratch/B/issues", run_id, False)
    install_one_shot_swap(repo)
    return repo


register_repo = prepare("register", "swap-register", "SWAP-REGISTER", False)
module.register(
    register_repo, "file-per-ticket", ".scratch/current/issues", "swap-register", False
)
assert not journal(register_repo, "A", "swap-register").exists()
assert journal(register_repo, "B", "swap-register").exists()
registered = json.loads(journal(register_repo, "B", "swap-register").read_text())
assert registered["location"] == ".scratch/B/issues"


flapping_repo = prepare("flapping", "swap-flapping", "SWAP-FLAPPING", False)
flapping_link = flapping_repo / ".scratch" / "current"

@contextmanager
def flapping_lock(location, representation):
    point(flapping_link, "B" if location == target(flapping_repo, "A") else "A")
    with real_lock(location, representation):
        yield

module.mutation_lock = flapping_lock
try:
    module.register(
        flapping_repo,
        "file-per-ticket",
        ".scratch/current/issues",
        "swap-flapping",
        False,
    )
except module.AdapterError as error:
    assert "changed while acquiring" in str(error)
else:
    raise AssertionError("continuously changing surface unexpectedly registered")
assert not journal(flapping_repo, "A", "swap-flapping").exists()
assert not journal(flapping_repo, "B", "swap-flapping").exists()
assert "Status: review-pending" in (target(flapping_repo, "A") / "SWAP-FLAPPING.md").read_text()
assert "Status: review-pending" in (target(flapping_repo, "B") / "SWAP-FLAPPING.md").read_text()


promote_repo = prepare("promote", "swap-promote", "SWAP-PROMOTE", True)
module.promote(
    promote_repo, "file-per-ticket", ".scratch/current/issues", "swap-promote"
)
assert json.loads(journal(promote_repo, "A", "swap-promote").read_text())["phase"] == "review-pending"
assert "Status: review-pending" in (target(promote_repo, "A") / "SWAP-PROMOTE.md").read_text()
assert json.loads(journal(promote_repo, "B", "swap-promote").read_text())["phase"] == "promoted"
assert "Status: ready-for-agent" in (target(promote_repo, "B") / "SWAP-PROMOTE.md").read_text()

cleanup_repo = prepare("cleanup", "swap-cleanup", "SWAP-CLEANUP", True)
module.cleanup(
    cleanup_repo, "file-per-ticket", ".scratch/current/issues", "swap-cleanup", True
)
assert journal(cleanup_repo, "A", "swap-cleanup").exists()
assert (target(cleanup_repo, "A") / "SWAP-CLEANUP.md").exists()
assert not journal(cleanup_repo, "B", "swap-cleanup").exists()
assert not (target(cleanup_repo, "B") / "SWAP-CLEANUP.md").exists()
PY

write_file_ticket "$FILE_REPO/.scratch/feature/issues/T-1.md" T-1 review-fix-run review-pending "" "Oversized draft"
write_file_ticket "$FILE_REPO/.scratch/feature/issues/T-2.md" T-2 review-fix-run review-pending T-1 "Dependent draft"
adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run register >/dev/null

# A read-only review can cause a derivable split/blocker repair. The main Agent
# changes the same formal set and must explicitly re-register membership.
write_file_ticket "$FILE_REPO/.scratch/feature/issues/T-3.md" T-3 review-fix-run review-pending T-1 "Reviewer-derived split"
write_file_ticket "$FILE_REPO/.scratch/feature/issues/T-2.md" T-2 review-fix-run review-pending T-3 "Corrected blocker"
if adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run register >"$TMPDIR_ROOT/membership.out" 2>&1; then
  echo "membership drift registered without explicit review-fix authorization" >&2
  exit 1
fi
adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run register --allow-membership-change >/dev/null

# Concurrent content changes fail before any promotion mutation.
printf '\nconcurrent mutation\n' >>"$FILE_REPO/.scratch/feature/issues/T-3.md"
before_concurrent="$(sha256sum "$FILE_REPO/.scratch/feature/issues/T-1.md" | cut -d' ' -f1)"
if adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run promote >"$TMPDIR_ROOT/concurrent.out" 2>&1; then
  echo "concurrent Ticket change unexpectedly promoted" >&2
  exit 1
fi
after_concurrent="$(sha256sum "$FILE_REPO/.scratch/feature/issues/T-1.md" | cut -d' ' -f1)"
test "$before_concurrent" = "$after_concurrent"
grep -Fq 'changed after review registration' "$TMPDIR_ROOT/concurrent.out"
python3 - "$FILE_REPO/.scratch/feature/issues/T-3.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
path.write_text(path.read_text(encoding="utf-8").replace("\nconcurrent mutation\n", ""), encoding="utf-8")
PY
adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run register >/dev/null

# Mid-promotion interruption leaves the journal in `promoting`; even a member
# already carrying ready state is not claimable. Resumption is idempotent.
if ULTRA_PUBLICATION_FAIL_AFTER=1 adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run promote >"$TMPDIR_ROOT/interrupted.out" 2>&1; then
  echo "injected interruption unexpectedly succeeded" >&2
  exit 1
fi
adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run inspect >"$TMPDIR_ROOT/interrupted.json"
python3 - "$TMPDIR_ROOT/interrupted.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["phase"] == "promoting"
assert set(data["statuses"].values()) == {"review-pending", "ready-for-agent"}
PY
if adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run claim-check --ticket-id T-1 >/dev/null 2>&1; then
  echo "partial set became claimable" >&2
  exit 1
fi
adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run promote >/dev/null
adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run promote >/dev/null
for removed in claim-check claim; do
  before="$(shasum -a 256 "$FILE_REPO/.scratch/feature/issues/T-1.md")"
  if adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run "$removed" --ticket-id T-1 >"$TMPDIR_ROOT/removed-$removed.out" 2>&1; then
    echo "removed publication operation unexpectedly succeeded: $removed" >&2
    exit 1
  fi
  grep -Fq "unsupported operation: $removed" "$TMPDIR_ROOT/removed-$removed.out"
  test "$before" = "$(shasum -a 256 "$FILE_REPO/.scratch/feature/issues/T-1.md")"
done

# Frontmatter State/Labels aliases preserve their configured field spelling for
# publication; Claim belongs only to frontier.
ALIAS_REPO="$TMPDIR_ROOT/alias-file-per"
mkdir -p "$ALIAS_REPO/.scratch/feature/issues"
write_contract "$ALIAS_REPO" retain-until-explicit-cleanup
python3 - "$ALIAS_REPO/.scratch/feature/issues/A-1.md" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text("""---
sTaTe: REVIEW_PENDING
ticket_id: A-1
publication_run: alias-run
source-spec: docs/spec.md
blocked-by: []
Labels: []
---

# Alias Ticket
""", encoding="utf-8")
PY
adapter "$ALIAS_REPO" file-per-ticket .scratch/feature/issues alias-run register >/dev/null
adapter "$ALIAS_REPO" file-per-ticket .scratch/feature/issues alias-run promote >/dev/null
grep -Fq 'sTaTe: ready-for-agent' "$ALIAS_REPO/.scratch/feature/issues/A-1.md"
grep -Fq 'Labels: []' "$ALIAS_REPO/.scratch/feature/issues/A-1.md"

# Digest normalization derives every operational field family from the
# configured contract, including non-default aliases. Status-only partial
# promotion and assignment/Claim metadata changes remain resumable.
CUSTOM_ALIAS_REPO="$TMPDIR_ROOT/custom-operational-aliases"
mkdir -p "$CUSTOM_ALIAS_REPO/.scratch/feature/issues"
write_contract "$CUSTOM_ALIAS_REPO" retain-until-explicit-cleanup
python3 - "$CUSTOM_ALIAS_REPO/docs/agents/ultra-tracker.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("Ticket state fields: Status, State", "Ticket state fields: Ticket Status")
text = text.replace("Claim field aliases: Flags, Labels", "Claim field aliases: Work Flags")
text = text.replace("Solve branch field aliases: Solve Branch, Branch", "Solve branch field aliases: Attempt Branch")
text = text.replace("Solve worktree field aliases: Solve Worktree, Worktree", "Solve worktree field aliases: Attempt Worktree")
path.write_text(text, encoding="utf-8")
PY
for id in CUSTOM-1 CUSTOM-2; do
  cat >"$CUSTOM_ALIAS_REPO/.scratch/feature/issues/$id.md" <<EOF
Ticket Status: REVIEW_PENDING
Ticket ID: $id
Publication Run: custom-alias-run
Source Spec: docs/spec.md
Blocked By:
Work Flags:
Attempt Branch:
Attempt Worktree:

# Custom operational aliases $id
EOF
done
adapter "$CUSTOM_ALIAS_REPO" file-per-ticket .scratch/feature/issues custom-alias-run register >/dev/null
python3 - "$CUSTOM_ALIAS_REPO/.scratch/feature/issues/CUSTOM-1.md" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
text = text.replace("Work Flags:", "Work Flags: solve-in-progress")
text = text.replace("Attempt Branch:", "Attempt Branch: solve/custom-1")
text = text.replace("Attempt Worktree:", "Attempt Worktree: /tmp/custom-1")
path.write_text(text, encoding="utf-8")
PY
if ULTRA_PUBLICATION_FAIL_AFTER=1 adapter "$CUSTOM_ALIAS_REPO" file-per-ticket .scratch/feature/issues custom-alias-run promote >"$TMPDIR_ROOT/custom-alias-interrupted.out" 2>&1; then
  echo 'custom operational alias promotion interruption unexpectedly succeeded' >&2
  exit 1
fi
grep -Fq 'injected mid-promotion interruption' "$TMPDIR_ROOT/custom-alias-interrupted.out"
adapter "$CUSTOM_ALIAS_REPO" file-per-ticket .scratch/feature/issues custom-alias-run promote >/dev/null
test "$(grep -Rh '^Ticket Status: ready-for-agent$' "$CUSTOM_ALIAS_REPO/.scratch/feature/issues" | wc -l | tr -d ' ')" -eq 2
grep -Fq 'Work Flags: solve-in-progress' "$CUSTOM_ALIAS_REPO/.scratch/feature/issues/CUSTOM-1.md"
grep -Fq 'Attempt Branch: solve/custom-1' "$CUSTOM_ALIAS_REPO/.scratch/feature/issues/CUSTOM-1.md"
grep -Fq 'Attempt Worktree: /tmp/custom-1' "$CUSTOM_ALIAS_REPO/.scratch/feature/issues/CUSTOM-1.md"

# Cancellation retains formal artifacts by default. Explicit cleanup is scoped
# to the named provisional run and cannot delete a promoted run.
write_file_ticket "$FILE_REPO/.scratch/feature/issues/C-1.md" C-1 cancel-run review-pending "" "Cancelled draft"
adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues cancel-run register >/dev/null
cancel_before="$(sha256sum "$FILE_REPO/.scratch/feature/issues/C-1.md" | cut -d' ' -f1)"
if adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues cancel-run cleanup >"$TMPDIR_ROOT/cancel.out" 2>&1; then
  echo "default cancellation unexpectedly deleted artifacts" >&2
  exit 1
fi
test -f "$FILE_REPO/.scratch/feature/issues/C-1.md"
test "$cancel_before" = "$(sha256sum "$FILE_REPO/.scratch/feature/issues/C-1.md" | cut -d' ' -f1)"
adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues cancel-run cleanup --explicit >/dev/null
test ! -e "$FILE_REPO/.scratch/feature/issues/C-1.md"
if adapter "$FILE_REPO" file-per-ticket .scratch/feature/issues review-fix-run cleanup --explicit >/dev/null 2>&1; then
  echo "promoted run unexpectedly cleaned" >&2
  exit 1
fi

# Explicit cleanup overrides the default retain choice, not the managed
# contract or promotion-state safety gates.
cancellation_safety_failures=0
MISSING_CONTRACT_REPO="$TMPDIR_ROOT/missing-contract"
mkdir -p "$MISSING_CONTRACT_REPO/.scratch/feature/issues"
write_contract "$MISSING_CONTRACT_REPO" retain-until-explicit-cleanup
write_file_ticket "$MISSING_CONTRACT_REPO/.scratch/feature/issues/MISSING-1.md" MISSING-1 missing-contract-run review-pending "" "Missing-contract draft"
adapter "$MISSING_CONTRACT_REPO" file-per-ticket .scratch/feature/issues missing-contract-run register >/dev/null
rm "$MISSING_CONTRACT_REPO/docs/agents/ultra-tracker.md"
if adapter "$MISSING_CONTRACT_REPO" file-per-ticket .scratch/feature/issues missing-contract-run cleanup --explicit >"$TMPDIR_ROOT/missing-contract.out" 2>&1; then
  echo "explicit cleanup bypassed a missing cancellation contract" >&2
  cancellation_safety_failures=1
fi
if ! test -e "$MISSING_CONTRACT_REPO/.scratch/feature/issues/MISSING-1.md"; then
  echo "missing-contract cleanup deleted its Ticket" >&2
  cancellation_safety_failures=1
fi
grep -Fq 'missing Local tracker contract' "$TMPDIR_ROOT/missing-contract.out"

PROMOTING_REPO="$TMPDIR_ROOT/promoting-cleanup"
mkdir -p "$PROMOTING_REPO/.scratch/feature/issues"
write_contract "$PROMOTING_REPO" retain-until-explicit-cleanup
write_file_ticket "$PROMOTING_REPO/.scratch/feature/issues/PROMOTING-1.md" PROMOTING-1 promoting-run review-pending "" "First promoting draft"
write_file_ticket "$PROMOTING_REPO/.scratch/feature/issues/PROMOTING-2.md" PROMOTING-2 promoting-run review-pending "" "Second promoting draft"
adapter "$PROMOTING_REPO" file-per-ticket .scratch/feature/issues promoting-run register >/dev/null
if ULTRA_PUBLICATION_FAIL_AFTER=1 adapter "$PROMOTING_REPO" file-per-ticket .scratch/feature/issues promoting-run promote >"$TMPDIR_ROOT/promoting.out" 2>&1; then
  echo "injected promoting interruption unexpectedly succeeded" >&2
  exit 1
fi
if adapter "$PROMOTING_REPO" file-per-ticket .scratch/feature/issues promoting-run cleanup --explicit >"$TMPDIR_ROOT/promoting-cleanup.out" 2>&1; then
  echo "explicit cleanup deleted a partially promoted set" >&2
  cancellation_safety_failures=1
fi
for ticket in PROMOTING-1 PROMOTING-2; do
  if ! test -e "$PROMOTING_REPO/.scratch/feature/issues/$ticket.md"; then
    echo "promoting cleanup deleted $ticket" >&2
    cancellation_safety_failures=1
  fi
done
grep -Fq 'cleanup requires journal phase review-pending, found promoting' "$TMPDIR_ROOT/promoting-cleanup.out"

MIXED_STATE_REPO="$TMPDIR_ROOT/mixed-state-cleanup"
mkdir -p "$MIXED_STATE_REPO/.scratch/feature/issues"
write_contract "$MIXED_STATE_REPO" retain-until-explicit-cleanup
write_file_ticket "$MIXED_STATE_REPO/.scratch/feature/issues/MIXED-1.md" MIXED-1 mixed-state-run review-pending "" "Mixed-state draft"
adapter "$MIXED_STATE_REPO" file-per-ticket .scratch/feature/issues mixed-state-run register >/dev/null
python3 - "$MIXED_STATE_REPO/.scratch/feature/issues/MIXED-1.md" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(
    path.read_text(encoding="utf-8").replace(
        "Status: review-pending", "Status: ready-for-agent", 1
    ),
    encoding="utf-8",
)
PY
if adapter "$MIXED_STATE_REPO" file-per-ticket .scratch/feature/issues mixed-state-run cleanup --explicit >"$TMPDIR_ROOT/mixed-state-cleanup.out" 2>&1; then
  echo "explicit cleanup deleted a non-review-pending member" >&2
  cancellation_safety_failures=1
fi
if ! test -e "$MIXED_STATE_REPO/.scratch/feature/issues/MIXED-1.md"; then
  echo "mixed-state cleanup deleted MIXED-1" >&2
  cancellation_safety_failures=1
fi
grep -Fq 'cleanup requires every run member to be review-pending' "$TMPDIR_ROOT/mixed-state-cleanup.out"
test "$cancellation_safety_failures" -eq 0

# A configured safe alternative is operational rather than descriptive: the
# adapter reads the managed contract and cleans only the validated named run.
AUTO_CLEAN_REPO="$TMPDIR_ROOT/auto-clean"
mkdir -p "$AUTO_CLEAN_REPO/.scratch/feature/issues"
write_contract "$AUTO_CLEAN_REPO" delete-on-cancel
write_file_ticket "$AUTO_CLEAN_REPO/.scratch/feature/issues/AUTO-1.md" AUTO-1 auto-clean-run review-pending "" "Auto-cleaned draft"
adapter "$AUTO_CLEAN_REPO" file-per-ticket .scratch/feature/issues auto-clean-run register >/dev/null
adapter "$AUTO_CLEAN_REPO" file-per-ticket .scratch/feature/issues auto-clean-run cleanup >/dev/null
test ! -e "$AUTO_CLEAN_REPO/.scratch/feature/issues/AUTO-1.md"

# Unknown policy text fails closed and cannot authorize deletion.
UNKNOWN_POLICY_REPO="$TMPDIR_ROOT/unknown-policy"
mkdir -p "$UNKNOWN_POLICY_REPO/.scratch/feature/issues"
write_contract "$UNKNOWN_POLICY_REPO" retain-until-explicit-cleanup
write_file_ticket "$UNKNOWN_POLICY_REPO/.scratch/feature/issues/UNKNOWN-1.md" UNKNOWN-1 unknown-run review-pending "" "Unknown-policy draft"
adapter "$UNKNOWN_POLICY_REPO" file-per-ticket .scratch/feature/issues unknown-run register >/dev/null
write_contract "$UNKNOWN_POLICY_REPO" delete-whatever-the-contract-says
if adapter "$UNKNOWN_POLICY_REPO" file-per-ticket .scratch/feature/issues unknown-run cleanup >"$TMPDIR_ROOT/unknown-policy.out" 2>&1; then
  echo "unknown cancellation policy unexpectedly authorized deletion" >&2
  exit 1
fi
grep -Fq 'unsupported cancellation policy' "$TMPDIR_ROOT/unknown-policy.out"
test -e "$UNKNOWN_POLICY_REPO/.scratch/feature/issues/UNKNOWN-1.md"
if adapter "$UNKNOWN_POLICY_REPO" file-per-ticket .scratch/feature/issues unknown-run cleanup --explicit >"$TMPDIR_ROOT/unknown-policy-explicit.out" 2>&1; then
  echo "explicit cleanup bypassed an unknown cancellation policy" >&2
  exit 1
fi
grep -Fq 'unsupported cancellation policy' "$TMPDIR_ROOT/unknown-policy-explicit.out"
test -e "$UNKNOWN_POLICY_REPO/.scratch/feature/issues/UNKNOWN-1.md"
printf 'Publication strategy: remote-review-pending\nLocal Ticket representation: file-per-ticket\nLocal Ticket path: .scratch/<feature>/issues/<ticket-file>.md\nCancellation policy: delete-on-cancel\n' >"$UNKNOWN_POLICY_REPO/docs/agents/ultra-tracker.md"
if adapter "$UNKNOWN_POLICY_REPO" file-per-ticket .scratch/feature/issues unknown-run cleanup >"$TMPDIR_ROOT/wrong-strategy.out" 2>&1; then
  echo "non-local publication strategy unexpectedly authorized deletion" >&2
  exit 1
fi
grep -Fq 'must select local-review-pending exactly once' "$TMPDIR_ROOT/wrong-strategy.out"
test -e "$UNKNOWN_POLICY_REPO/.scratch/feature/issues/UNKNOWN-1.md"
if adapter "$UNKNOWN_POLICY_REPO" file-per-ticket .scratch/feature/issues unknown-run cleanup --explicit >"$TMPDIR_ROOT/wrong-strategy-explicit.out" 2>&1; then
  echo "explicit cleanup bypassed a non-local publication strategy" >&2
  exit 1
fi
grep -Fq 'must select local-review-pending exactly once' "$TMPDIR_ROOT/wrong-strategy-explicit.out"
test -e "$UNKNOWN_POLICY_REPO/.scratch/feature/issues/UNKNOWN-1.md"
printf 'Publication strategy: local-review-pending\nLocal Ticket representation: file-per-ticket\nLocal Ticket path: .scratch/<feature>/issues/<ticket-file>.md\nCancellation policy: delete-on-cancel\nCancellation policy: retain-until-explicit-cleanup\n' >"$UNKNOWN_POLICY_REPO/docs/agents/ultra-tracker.md"
if adapter "$UNKNOWN_POLICY_REPO" file-per-ticket .scratch/feature/issues unknown-run cleanup --explicit >"$TMPDIR_ROOT/duplicate-policy-explicit.out" 2>&1; then
  echo "explicit cleanup bypassed duplicate cancellation policies" >&2
  exit 1
fi
grep -Fq 'must define exactly one Cancellation policy' "$TMPDIR_ROOT/duplicate-policy-explicit.out"
test -e "$UNKNOWN_POLICY_REPO/.scratch/feature/issues/UNKNOWN-1.md"

# One safely delimited tickets-file is mutated by exact section identity while
# unrelated content is preserved.
python3 - "$SECTION_REPO/.scratch/feature/tickets.md" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text("""# Project Tickets

Unrelated introduction stays byte-for-byte.

<!-- ultra-ticket:begin id=S-1 -->
Status: review-pending
Ticket ID: S-1
Publication Run: section-run
Source Spec: docs/spec.md
Blocked By:
Flags:

## Ticket S-1

Independent acceptance.
<!-- ultra-ticket:end -->

<!-- ultra-ticket:begin id=S-2 -->
Status: review-pending
Ticket ID: S-2
Publication Run: section-run
Source Spec: docs/spec.md
Blocked By: S-1
Flags:

## Ticket S-2

Dependent acceptance.
<!-- ultra-ticket:end -->

<!-- ultra-ticket:begin id=S-3 -->
State: review-pending
Ticket ID: S-3
Publication Run: second-section-run
Source Spec: docs/spec.md
Blocked By:
Labels:

## Ticket S-3

Independent second-run acceptance.
<!-- ultra-ticket:end -->

Unrelated footer stays byte-for-byte.
""", encoding="utf-8")
PY
mkdir -p "$SECTION_REPO/.scratch/feature/.ultra-publications"
touch "$SECTION_REPO/.scratch/feature/.ultra-publications/.adapter.lock"
adapter "$SECTION_REPO" tickets-file .scratch/feature/tickets.md section-run register >/dev/null
adapter "$SECTION_REPO" tickets-file .scratch/feature/tickets.md second-section-run register >/dev/null
adapter "$SECTION_REPO" tickets-file .scratch/feature/tickets.md section-run promote >"$TMPDIR_ROOT/section-promote.out" &
section_pid=$!
adapter "$SECTION_REPO" tickets-file .scratch/feature/tickets.md second-section-run promote >"$TMPDIR_ROOT/second-section-promote.out" &
second_section_pid=$!
wait "$section_pid"
wait "$second_section_pid"
grep -Fq 'Unrelated introduction stays byte-for-byte.' "$SECTION_REPO/.scratch/feature/tickets.md"
grep -Fq 'Unrelated footer stays byte-for-byte.' "$SECTION_REPO/.scratch/feature/tickets.md"
test "$(grep -Fc 'Status: ready-for-agent' "$SECTION_REPO/.scratch/feature/tickets.md")" -eq 2
grep -Fq 'State: ready-for-agent' "$SECTION_REPO/.scratch/feature/tickets.md"
if adapter "$SECTION_REPO" tickets-file .scratch/feature/tickets.md section-run claim-check --ticket-id S-1 >"$TMPDIR_ROOT/section-claim-check.out" 2>&1; then
  echo 'tickets-file publication exposed claim-check' >&2
  exit 1
fi
grep -Fq 'unsupported operation: claim-check' "$TMPDIR_ROOT/section-claim-check.out"

# Unsafe tickets-file adapters fail closed without changing any byte.
for kind in duplicate missing-status nested unresolved heading-only mixed-identity; do
  repo="$TMPDIR_ROOT/unsafe-$kind"
  mkdir -p "$repo/.scratch/feature"
  write_contract "$repo" retain-until-explicit-cleanup tickets-file .scratch/feature/tickets.md
  python3 - "$repo/.scratch/feature/tickets.md" "$kind" <<'PY'
from pathlib import Path
import sys
path, kind = Path(sys.argv[1]), sys.argv[2]
base = """# Tickets
<!-- ultra-ticket:begin id=U-1 -->
Status: review-pending
Ticket ID: U-1
Publication Run: unsafe-run
Source Spec: docs/spec.md
Blocked By:
Flags:

## Ticket U-1
<!-- ultra-ticket:end -->
"""
if kind == "duplicate":
    text = base + base.replace("# Tickets\n", "")
elif kind == "missing-status":
    text = base.replace("Status: review-pending\n", "")
elif kind == "nested":
    text = base.replace("Status: review-pending", "<!-- ultra-ticket:begin id=U-2 -->\nStatus: review-pending")
elif kind == "unresolved":
    text = base.replace("Blocked By:\n", "Blocked By: DOES-NOT-EXIST\n")
elif kind == "mixed-identity":
    text = base + "\n## Ticket unsafe title-only sibling\n\nStatus: review-pending\n"
else:
    text = "# Tickets\n\n## Ticket inferred only from title\n\nStatus: review-pending\n"
path.write_text(text, encoding="utf-8")
PY
  unsafe_before="$(sha256sum "$repo/.scratch/feature/tickets.md" | cut -d' ' -f1)"
  if adapter "$repo" tickets-file .scratch/feature/tickets.md unsafe-run register >"$TMPDIR_ROOT/unsafe-$kind.out" 2>&1; then
    echo "unsafe tickets-file fixture passed: $kind" >&2
    exit 1
  fi
  test "$unsafe_before" = "$(sha256sum "$repo/.scratch/feature/tickets.md" | cut -d' ' -f1)"
done

if adapter "$FILE_REPO" file-per-ticket ../outside review-fix-run inspect >"$TMPDIR_ROOT/escape.out" 2>&1; then
  echo "path escape unexpectedly accepted" >&2
  exit 1
fi

# Terminal repair is a typed CAS over a promoted publication. It preserves the
# registration snapshot, appends exactly one audit, resumes after the Ticket
# write boundary, and keeps malformed or semantic changes fail-closed.
REPAIR_REPO="$TMPDIR_ROOT/terminal-repair"
mkdir -p "$REPAIR_REPO/.scratch/feature/issues"
write_contract "$REPAIR_REPO" retain-until-explicit-cleanup
write_file_ticket "$REPAIR_REPO/.scratch/feature/issues/A.md" A repair-run review-pending B "Repair source"
write_file_ticket "$REPAIR_REPO/.scratch/feature/issues/B.md" B repair-run review-pending "" "Old blocker"
write_file_ticket "$REPAIR_REPO/.scratch/feature/issues/C.md" C repair-run review-pending "" "Correct blocker"
write_file_ticket "$REPAIR_REPO/.scratch/feature/issues/F.md" F repair-run review-pending C "First identity dependent"
write_file_ticket "$REPAIR_REPO/.scratch/feature/issues/G.md" G repair-run review-pending C "Second identity dependent"
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run register >/dev/null
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run promote >/dev/null
repair_digest="$(python3 - "$ADAPTER" "$REPAIR_REPO/.scratch/feature/issues/A.md" "$REPAIR_REPO" <<'PY'
import importlib.util, sys
from pathlib import Path
adapter, ticket, repo = map(Path, sys.argv[1:])
sys.path.insert(0, str(adapter.parent))
spec = importlib.util.spec_from_file_location("publication", adapter)
module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
contract = module.configured_local_contract(repo)
print(module.load_file_per(ticket.parent, contract)[0].body_digest)
PY
)"
if ULTRA_TERMINAL_REPAIR_FAIL_AFTER=ticket adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id A --expected-digest "$repair_digest" --repair-type blocker-target \
  --old-value B --new-value C --reason 'human confirmed blocker identity' >"$TMPDIR_ROOT/repair-interrupt.out" 2>&1; then
  echo "terminal repair interruption unexpectedly succeeded" >&2
  exit 1
fi
grep -Fq 'Blocked By: C' "$REPAIR_REPO/.scratch/feature/issues/A.md"
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id A --expected-digest "$repair_digest" --repair-type blocker-target \
  --old-value B --new-value C --reason 'human confirmed blocker identity' >"$TMPDIR_ROOT/repair-success.json"
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id A --expected-digest "$repair_digest" --repair-type blocker-target \
  --old-value B --new-value C --reason 'human confirmed blocker identity' >"$TMPDIR_ROOT/repair-retry.json"
python3 - "$REPAIR_REPO/.scratch/feature/issues/.ultra-publications/repair-run.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert len(data["terminal_repairs"]) == 1, data
assert data["body_digests"]["A"] == data["terminal_repairs"][0]["old_digest"]
assert data["terminal_repairs"][0]["reason"] == "human confirmed blocker identity"
PY
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run inspect >"$TMPDIR_ROOT/repair-inspect.json"
identity_digest="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["body_digests"]["B"])' "$TMPDIR_ROOT/repair-inspect.json")"
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id B --expected-digest "$identity_digest" --repair-type ticket-identity \
  --old-value B --new-value D --reason 'human confirmed stable Ticket identity' >/dev/null
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id B --expected-digest "$identity_digest" --repair-type ticket-identity \
  --old-value B --new-value D --reason 'human confirmed stable Ticket identity' >/dev/null
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run inspect >"$TMPDIR_ROOT/repair-identity-inspect.json"
python3 - "$TMPDIR_ROOT/repair-identity-inspect.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
assert data["members"] == ["A", "C", "D", "F", "G"], data
assert set(data["original_body_digests"]) == {"A", "B", "C", "F", "G"}, data
assert set(data["body_digests"]) == {"A", "C", "D", "F", "G"}, data
PY
referenced_digest="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["body_digests"]["C"])' "$TMPDIR_ROOT/repair-identity-inspect.json")"
if ULTRA_TERMINAL_REPAIR_FAIL_AFTER=ticket:2 adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id C --expected-digest "$referenced_digest" --repair-type ticket-identity \
  --old-value C --new-value E --reason 'human confirmed referenced Ticket identity' >"$TMPDIR_ROOT/repair-dependent-interrupt.out" 2>&1; then
  echo "terminal repair dependent interruption unexpectedly succeeded" >&2
  exit 1
fi
if ULTRA_TERMINAL_REPAIR_FAIL_AFTER=ticket:2 adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id C --expected-digest "$referenced_digest" --repair-type ticket-identity \
  --old-value C --new-value E --reason 'human confirmed referenced Ticket identity' >"$TMPDIR_ROOT/repair-dependent-repeat.out" 2>&1; then
  echo "terminal repair repeated dependent boundary unexpectedly succeeded" >&2
  exit 1
fi
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id C --expected-digest "$referenced_digest" --repair-type ticket-identity \
  --old-value C --new-value E --reason 'human confirmed referenced Ticket identity' >/dev/null
grep -Fq 'Blocked By: E' "$REPAIR_REPO/.scratch/feature/issues/A.md"
grep -Fq 'Blocked By: E' "$REPAIR_REPO/.scratch/feature/issues/F.md"
grep -Fq 'Blocked By: E' "$REPAIR_REPO/.scratch/feature/issues/G.md"
python3 - "$REPAIR_REPO/.scratch/feature/issues/.ultra-publications/repair-run.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
identity_audits = [item for item in data["terminal_repairs"] if item.get("ticket_id") == "C"]
assert len(identity_audits) == 1, data
assert len(identity_audits[0]["related_digests"]) == 3, data
PY
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run inspect >"$TMPDIR_ROOT/repair-before-journal-boundary.json"
metadata_digest="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["body_digests"]["A"])' "$TMPDIR_ROOT/repair-before-journal-boundary.json")"
if ULTRA_TERMINAL_REPAIR_FAIL_AFTER=journal adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id A --expected-digest "$metadata_digest" --repair-type publication-metadata \
  --old-value 'Source Spec' --new-value Parent --reason 'human confirmed metadata alias' >"$TMPDIR_ROOT/repair-journal-interrupt.out" 2>&1; then
  echo "terminal repair journal interruption unexpectedly succeeded" >&2
  exit 1
fi
adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id A --expected-digest "$metadata_digest" --repair-type publication-metadata \
  --old-value 'Source Spec' --new-value Parent --reason 'human confirmed metadata alias' >/dev/null
python3 "$FRONTIER" frontier --repo "$REPAIR_REPO" --ticket-id A >"$TMPDIR_ROOT/repair-frontier.json"
python3 - "$TMPDIR_ROOT/repair-frontier.json" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
projection = data["publication"]["A"]
assert projection["ready"] is True, data
assert projection["current_digest"] != projection["original_digest"], data
PY
if adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id A --expected-digest "$(printf x%.0s {1..64})" --repair-type blocker-target \
  --old-value C --new-value B --reason stale >"$TMPDIR_ROOT/repair-stale.out" 2>&1; then
  echo "terminal repair accepted a stale expected digest" >&2
  exit 1
fi
before_semantic="$(sha256sum "$REPAIR_REPO/.scratch/feature/issues/A.md" | cut -d' ' -f1)"
if adapter "$REPAIR_REPO" file-per-ticket .scratch/feature/issues repair-run terminal-repair \
  --ticket-id A --expected-digest "$repair_digest" --repair-type arbitrary-body \
  --old-value x --new-value y --reason semantic >"$TMPDIR_ROOT/repair-semantic.out" 2>&1; then
  echo "terminal repair accepted arbitrary semantic body replacement" >&2
  exit 1
fi
test "$before_semantic" = "$(sha256sum "$REPAIR_REPO/.scratch/feature/issues/A.md" | cut -d' ' -f1)"

EXTERNAL_REPO="$TMPDIR_ROOT/terminal-repair-external-reference"
mkdir -p "$EXTERNAL_REPO/.scratch/feature/issues"
write_contract "$EXTERNAL_REPO" retain-until-explicit-cleanup
write_file_ticket "$EXTERNAL_REPO/.scratch/feature/issues/A.md" A run-a review-pending "" "Run A identity"
write_file_ticket "$EXTERNAL_REPO/.scratch/feature/issues/X.md" X run-x review-pending A "Run X dependent"
adapter "$EXTERNAL_REPO" file-per-ticket .scratch/feature/issues run-a register >/dev/null
adapter "$EXTERNAL_REPO" file-per-ticket .scratch/feature/issues run-a promote >/dev/null
adapter "$EXTERNAL_REPO" file-per-ticket .scratch/feature/issues run-x register >/dev/null
adapter "$EXTERNAL_REPO" file-per-ticket .scratch/feature/issues run-x promote >/dev/null
adapter "$EXTERNAL_REPO" file-per-ticket .scratch/feature/issues run-a inspect >"$TMPDIR_ROOT/external-inspect.json"
external_digest="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["body_digests"]["A"])' "$TMPDIR_ROOT/external-inspect.json")"
external_before="$(sha256sum "$EXTERNAL_REPO/.scratch/feature/issues/A.md" | cut -d' ' -f1)"
if adapter "$EXTERNAL_REPO" file-per-ticket .scratch/feature/issues run-a terminal-repair \
  --ticket-id A --expected-digest "$external_digest" --repair-type ticket-identity \
  --old-value A --new-value A2 --reason 'cross-run reference must refuse' >"$TMPDIR_ROOT/external-refusal.out" 2>&1; then
  echo "terminal repair crossed publication-run ownership" >&2
  exit 1
fi
grep -Fq 'references outside publication run: X' "$TMPDIR_ROOT/external-refusal.out"
test "$external_before" = "$(sha256sum "$EXTERNAL_REPO/.scratch/feature/issues/A.md" | cut -d' ' -f1)"

for drift_kind in extra missing; do
  DRIFT_REPO="$TMPDIR_ROOT/partial-identity-$drift_kind"
  mkdir -p "$DRIFT_REPO/.scratch/feature/issues"
  write_contract "$DRIFT_REPO" retain-until-explicit-cleanup
  write_file_ticket "$DRIFT_REPO/.scratch/feature/issues/A.md" A drift-run review-pending "" "Partial identity target"
  write_file_ticket "$DRIFT_REPO/.scratch/feature/issues/B.md" B drift-run review-pending "" "Membership sibling"
  adapter "$DRIFT_REPO" file-per-ticket .scratch/feature/issues drift-run register >/dev/null
  adapter "$DRIFT_REPO" file-per-ticket .scratch/feature/issues drift-run promote >/dev/null
  adapter "$DRIFT_REPO" file-per-ticket .scratch/feature/issues drift-run inspect >"$TMPDIR_ROOT/drift-$drift_kind-inspect.json"
  drift_digest="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["body_digests"]["A"])' "$TMPDIR_ROOT/drift-$drift_kind-inspect.json")"
  if ULTRA_TERMINAL_REPAIR_FAIL_AFTER=ticket adapter "$DRIFT_REPO" file-per-ticket .scratch/feature/issues drift-run terminal-repair \
    --ticket-id A --expected-digest "$drift_digest" --repair-type ticket-identity \
    --old-value A --new-value A2 --reason 'partial identity drift fixture' >"$TMPDIR_ROOT/drift-$drift_kind-partial.out" 2>&1; then
    echo "partial identity setup unexpectedly succeeded" >&2
    exit 1
  fi
  if test "$drift_kind" = extra; then
    write_file_ticket "$DRIFT_REPO/.scratch/feature/issues/C.md" C drift-run ready-for-agent "" "Unexpected member"
  else
    rm "$DRIFT_REPO/.scratch/feature/issues/B.md"
  fi
  drift_before="$(find "$DRIFT_REPO/.scratch/feature/issues" -type f -print0 | sort -z | xargs -0 shasum | shasum)"
  if adapter "$DRIFT_REPO" file-per-ticket .scratch/feature/issues drift-run terminal-repair \
    --ticket-id A --expected-digest "$drift_digest" --repair-type ticket-identity \
    --old-value A --new-value A2 --reason 'partial identity drift fixture' >"$TMPDIR_ROOT/drift-$drift_kind-refusal.out" 2>&1; then
    echo "partial identity repair accepted $drift_kind membership drift" >&2
    exit 1
  fi
  grep -Fq 'publication membership drifted' "$TMPDIR_ROOT/drift-$drift_kind-refusal.out"
  test "$drift_before" = "$(find "$DRIFT_REPO/.scratch/feature/issues" -type f -print0 | sort -z | xargs -0 shasum | shasum)"
done

python3 - "$REPO_ROOT" <<'PY'
from pathlib import Path
import sys

repo = Path(sys.argv[1])
core = (repo / "skills/engineering/ultra/SKILL.md").read_text(encoding="utf-8")
reference = (repo / "skills/engineering/ultra/references/ticket-review-publication.md").read_text(encoding="utf-8")
solve = (repo / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")
setup = (repo / "skills/engineering/setup-ultra-skills/SKILL.md").read_text(encoding="utf-8")

for text in (
    "Route Local Markdown publication only through its declared operations",
    "route complete-set registration through the publication adapter",
    "independent acceptance, context-window sizing, validation, source pointers, and true blocker edges",
    "only verified promotion yields `ready-for-agent`",
):
    assert text in core, text
for text in (
    "The approved Spec or approved conversation already authorizes ordinary Ticket",
    "conversation-only review is not a successful tracker mutation",
    "Manual fallback is prohibited for every operation",
    "Publication has no public",
):
    assert text in reference, text
assert "It is never claimable" in solve
assert "never rebuild the graph or Claim with Markdown edits" in solve
assert "outcome-handoff adapter is the one canonical writer" in solve
assert "Never prewrite a canonical receipt" in solve
assert "adapter derives candidate Git identity" in solve
assert "linked through the tracker's resource surface" not in solve
assert "Manual transaction fallback is prohibited" in setup
assert "## GitHub and GitLab remote adapter contract" in reference
assert "## Local Markdown adapter contract" in reference
PY

python3 -m py_compile "$ADAPTER"
echo "ultra Local Markdown Ticket publication fixture passed"
