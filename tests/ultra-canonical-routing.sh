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
