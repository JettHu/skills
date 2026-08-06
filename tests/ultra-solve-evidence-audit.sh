#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$ROOT" <<'PY'
from dataclasses import dataclass
from pathlib import Path
import sys


root = Path(sys.argv[1])
solve = (root / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")
skill = (root / "skills/engineering/solve-records/SKILL.md").read_text(encoding="utf-8")
record_format = (root / "skills/engineering/solve-records/references/record-format.md").read_text(encoding="utf-8")
candidate_gates = (root / "skills/engineering/solve-records/references/candidate-gates.md").read_text(encoding="utf-8")

for predicate in (
    "full **requirement-to-evidence audit**",
    "every explicit requirement, acceptance criterion, named artifact, validation gate, invariant, and required deliverable",
    "scope-matched proof",
    "contradictory evidence",
    "incomplete, weak, or indirect evidence",
    "stale delegated evidence",
    "narrower-than-required evidence",
    "plan, Execution Digest, delegated summary, manifest, search result, green narrow check, or absence of errors",
    "The audit passes only when every enumerated item has scope-matched proof",
    "context boundary, or execution limit",
    "remains non-candidate",
    "full requirement-to-evidence audit passed, validated, and Post-Execution Review passed",
):
    assert predicate in solve, f"evidence-complete finalization contract missing: {predicate}"

assert "Requirement-to-evidence audit: passed" in record_format
assert "concise conclusion and evidence summary" in record_format
assert "per-requirement checklist" in record_format
assert "full-boundary requirement-to-evidence audit" in skill
assert "live head still matches the audited head" in candidate_gates


@dataclass(frozen=True)
class Evidence:
    requirement: str
    classification: str
    current_head: bool = True


PASS = "scope-matched"
NON_PASS = {"contradictory", "incomplete", "weak", "indirect", "stale", "narrow"}


def audit(requirements, evidence):
    by_requirement = {item.requirement: item for item in evidence}
    for requirement in requirements:
        item = by_requirement.get(requirement)
        if item is None or item.classification != PASS or not item.current_head:
            return False
    return not any(item.classification in NON_PASS for item in evidence)


def finalize(*, requirements, evidence, final_validate, post_execution_review,
             interrupted=False, meaningful=True, cleaned=False):
    if interrupted:
        return "recovery" if meaningful and not cleaned else "recordless"
    if not audit(requirements, evidence) or not final_validate or not post_execution_review:
        return "recovery" if meaningful else "recordless"
    return "candidate"


requirements = {"narrow unit behavior", "broad cross-module invariant"}

# Partial work can be green without proving the full boundary.
assert finalize(
    requirements=requirements,
    evidence=[Evidence("narrow unit behavior", PASS)],
    final_validate=True,
    post_execution_review=True,
) == "recovery"

# A narrow check cannot prove a broad criterion.
assert finalize(
    requirements=requirements,
    evidence=[Evidence("narrow unit behavior", PASS), Evidence("broad cross-module invariant", "narrow")],
    final_validate=True,
    post_execution_review=True,
) == "recovery"

# Delegated evidence pinned to an old head is stale even if its conclusion said pass.
assert finalize(
    requirements=requirements,
    evidence=[Evidence(name, PASS, current_head=(name != "broad cross-module invariant")) for name in requirements],
    final_validate=True,
    post_execution_review=True,
) == "recovery"

# Contradictory current evidence blocks completion.
assert finalize(
    requirements=requirements,
    evidence=[Evidence("narrow unit behavior", PASS), Evidence("broad cross-module invariant", "contradictory")],
    final_validate=True,
    post_execution_review=True,
) == "recovery"

matched = [Evidence(name, PASS) for name in requirements]
assert finalize(
    requirements=requirements,
    evidence=matched,
    final_validate=True,
    post_execution_review=True,
) == "candidate"

# Candidate ordering requires the audit, Final Validate, and PER all to pass.
assert finalize(requirements=requirements, evidence=matched, final_validate=False, post_execution_review=True) != "candidate"
assert finalize(requirements=requirements, evidence=matched, final_validate=True, post_execution_review=False) != "candidate"

# Interruptions preserve the boundary and use existing meaningful/recovery semantics.
assert finalize(requirements=requirements, evidence=matched[:1], final_validate=False, post_execution_review=False, interrupted=True) == "recovery"
assert finalize(requirements=requirements, evidence=[], final_validate=False, post_execution_review=False, interrupted=True, meaningful=False, cleaned=True) == "recordless"

print("ultra solve evidence audit fixture passed")
PY
