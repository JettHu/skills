#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
solve = (root / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")

required = (
    "Build a compact **Design Context** index",
    "- `L0`:",
    "- `L1`:",
    "- `L2`:",
    "- `L3`:",
    "Adoption Routing selects the branch/worktree route",
    "the Checkpoint selects enabled preparation",
    "the Digest preserves only resumable or material decisions",
    "Pre-Execute Gate verifies live branch/worktree/Claim facts",
    "The default is `Digest: none`",
    "Final Validate proves executable validation facts",
    "Post-Execution Review consumes the Group Review and Final Validate results",
)
for text in required:
    assert text in solve, f"missing preparation contract: {text}"

assert "exploration, implementation, analysis, verification, and independent-review dispositions;" not in solve
assert "Unselected heavy stages are not recreated as empty checklist entries." in solve


def tier(*, local=True, multi_file=False, cross_module=False, public_contract=False,
         data=False, production=False, external=False, obscure_validation=False,
         governance=False):
    if governance:
        return "L3"
    if cross_module or public_contract or data or production or external or obscure_validation:
        return "L2"
    if multi_file:
        return "L1"
    assert local
    return "L0"


assert tier() == "L0"
assert tier(multi_file=True) == "L1"
assert tier(cross_module=True) == "L2"
assert tier(public_contract=True) == "L2"
assert tier(governance=True) == "L3"


def digest_needed(*, multi_module=False, delegated=False, resumable=False,
                  interrupted=False, obscure_validation=False, external=False,
                  material_decision=False):
    return any((multi_module, delegated, resumable, interrupted,
                obscure_validation, external, material_decision))


assert digest_needed() is False
assert digest_needed(multi_module=True) is True
assert digest_needed(material_decision=True) is True
assert digest_needed(obscure_validation=True) is True

print("ultra solve preparation fixture passed")
PY
