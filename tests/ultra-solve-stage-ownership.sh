#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$ROOT" <<'PY'
from dataclasses import dataclass
from pathlib import Path
import sys


root = Path(sys.argv[1])
solve = (root / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")
stage_grader = (root / "tests/evals/ultra-solve-stage-ownership/grade-run.py").read_text(encoding="utf-8")
for path in (
    "tests/evals/ultra-solve-stage-ownership/prepare-fixture.py",
    "tests/evals/ultra-solve-stage-ownership/grade-run.py",
    "tests/evals/ultra-solve-stage-ownership/README.md",
):
    assert (root / path).is_file(), f"stage-ownership eval surface missing: {path}"

for predicate in (
    "Ticket Claim is released",
    "Ticket links the receipt exactly once",
    "candidate base SHA matches live unchanged main",
    "candidate head SHA matches live branch",
    "candidate worktree branch matches receipt",
    "candidate worktree HEAD matches receipt",
    "candidate records an explicit merge disposition",
    "invocation repository has no unexpected dirty implementation or evidence paths",
):
    assert predicate in stage_grader, f"stage-ownership final-state grader missing: {predicate}"

for predicate in (
    "## Stage Ownership",
    "single owner of each stage disposition and its current evidence",
    "simple, familiar, local, low-risk, fully specified, and obviously verifiable",
    "use exactly one bounded implementation subagent for an assigned worktree",
    "Independent groups may still run in parallel in different assigned worktrees",
    "dependent stages and shared-worktree stages remain serialized",
    "implementation delegation is unavailable",
    "the assigned subagent worktree cannot be verified",
    "another active writer already owns that worktree",
    "concurrent mutation of non-namespaced shared state outside the worktree",
    "current context already supplies its required evidence",
    "the stage is trivial and local",
    "delegation overhead would exceed the work",
    "no suitable runtime capability is available",
    "Inherited history is advisory",
    "root re-read the integrated candidate",
    "Severity labels P0-P3 rank impact only",
    "Repairability",
    "Decision Ownership",
    "unresolved acceptance-affecting finding blocks candidate handoff",
    "grants no merge or landing authority",
):
    assert predicate in solve, f"stage-ownership contract missing: {predicate}"

assert "The main Agent retains synthesis, implementation edits" not in solve
assert "docs/config-only Ticket: edit directly" not in solve

DIRECT_FACTS = {
    "simple",
    "familiar",
    "local",
    "low-risk",
    "fully-specified",
    "obviously-verifiable",
}
FALLBACKS = {
    "delegation-unavailable",
    "worktree-unverifiable",
    "active-writer",
    "shared-state-mutation",
}


def implementation_route(facts, *, delegation=True, verified=True, active_writer=False, shared_state=False):
    if facts == DIRECT_FACTS:
        return "direct"
    if not delegation:
        return "root-fallback", "delegation-unavailable"
    if not verified:
        return "root-fallback", "worktree-unverifiable"
    if active_writer:
        return "root-fallback", "active-writer"
    if shared_state:
        return "root-fallback", "shared-state-mutation"
    return "delegated", "one-bounded-writer"


assert implementation_route(DIRECT_FACTS) == "direct"
for missing in DIRECT_FACTS:
    assert implementation_route(DIRECT_FACTS - {missing}) == ("delegated", "one-bounded-writer")
assert implementation_route(set(), delegation=False) == ("root-fallback", "delegation-unavailable")
assert implementation_route(set(), verified=False) == ("root-fallback", "worktree-unverifiable")
assert implementation_route(set(), active_writer=True) == ("root-fallback", "active-writer")
assert implementation_route(set(), shared_state=True) == ("root-fallback", "shared-state-mutation")
assert FALLBACKS == {
    implementation_route(set(), delegation=False)[1],
    implementation_route(set(), verified=False)[1],
    implementation_route(set(), active_writer=True)[1],
    implementation_route(set(), shared_state=True)[1],
}


def read_only_route(*, capability=True, context=False, trivial=False, overhead=False):
    if not capability:
        return "root", "capability-unavailable"
    if context:
        return "root", "sufficient-context"
    if trivial:
        return "root", "trivial-local"
    if overhead:
        return "root", "disproportionate-overhead"
    return "subagent", "preferred"


assert read_only_route() == ("subagent", "preferred")
assert read_only_route(context=True) == ("root", "sufficient-context")
assert read_only_route(trivial=True) == ("root", "trivial-local")
assert read_only_route(overhead=True) == ("root", "disproportionate-overhead")
assert read_only_route(capability=False) == ("root", "capability-unavailable")


class Writers:
    def __init__(self):
        self.active = {}

    def acquire(self, worktree, owner):
        assert worktree not in self.active, f"concurrent writer in {worktree}"
        self.active[worktree] = owner

    def handoff(self, worktree, owner):
        assert self.active.pop(worktree) == owner


writers = Writers()
writers.acquire("group-a", "implementation-a")
writers.acquire("group-b", "implementation-b")  # independent groups may overlap
try:
    writers.acquire("group-a", "root")
except AssertionError:
    pass
else:
    raise AssertionError("same-worktree concurrent writer was accepted")
writers.handoff("group-a", "implementation-a")
writers.acquire("group-a", "root")
writers.handoff("group-a", "root")
writers.handoff("group-b", "implementation-b")

events = []
for stage in ("explore", "pre-edit-review", "implement", "verify", "independent-review", "handoff", "integrate"):
    events.append(stage)
assert events.index("pre-edit-review") < events.index("implement")
assert events.index("implement") < events.index("verify") < events.index("independent-review")
assert events.index("handoff") < events.index("integrate")


@dataclass(frozen=True)
class Finding:
    severity: str
    derivable: bool
    human_owned: bool = False
    in_scope: bool = True
    affects_acceptance: bool = True


def review_action(finding):
    assert finding.severity in {"P0", "P1", "P2", "P3"}
    if finding.in_scope and finding.derivable:
        return "repair-revalidate-rereview"
    if finding.human_owned:
        return "human-recovery"
    if not finding.in_scope and not finding.affects_acceptance:
        return "follow-up"
    if finding.affects_acceptance:
        return "blocked-recovery"
    return "closed"


for severity in ("P0", "P1", "P2", "P3"):
    assert review_action(Finding(severity, True)) == "repair-revalidate-rereview"
assert review_action(Finding("P3", False, human_owned=True)) == "human-recovery"
assert review_action(Finding("P0", False, in_scope=False, affects_acceptance=False)) == "follow-up"
assert review_action(Finding("P3", False)) == "blocked-recovery"


def landing(candidate_ready, intent, base_sha):
    if candidate_ready and intent in {"auto-merge", "merge", "ship", "land", "repository-policy"}:
        return "advance-through-existing-gate"
    return base_sha


original_base = "base-before-autonomous-review"
assert landing(True, None, original_base) == original_base
assert landing(True, "auto-merge", original_base) == "advance-through-existing-gate"

print("ultra solve stage ownership fixture passed")
PY
