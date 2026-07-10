#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$REPO_ROOT" <<'PY'
import hashlib
import re
import sys
import tempfile
from pathlib import Path


repo = Path(sys.argv[1])
solve = (repo / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")
brief = (repo / "skills/engineering/ultra-to-issues/references/agent-brief.md").read_text(
    encoding="utf-8"
)
wrapper = (repo / "skills/engineering/ultra-to-issues/SKILL.md").read_text(encoding="utf-8")
record_format = (repo / "skills/engineering/solve-records/references/record-format.md").read_text(
    encoding="utf-8"
)
eval_plan = (repo / ".evals/ultra-solve-afk-safe-planning/20260708-model-adherence-eval-plan.md").read_text(
    encoding="utf-8"
)

assert "Context:" not in brief
for field in ("Constraints:", "Validation:", "Hints:"):
    assert field in brief, f"Agent Brief field missing: {field}"
assert "Omit each empty field and omit the entire section when every field is empty" in brief
assert "Agent Brief content never participates in parsing, eligibility, state transitions, or merge gates." in brief
assert "non-duplicative execution delta" in brief

link = re.search(r"\[Agent Brief contract\]\(([^)]+)\)", wrapper)
assert link, "wrapper must disclose the Agent Brief reference"
assert (repo / "skills/engineering/ultra-to-issues" / link.group(1)).is_file(), (
    "Agent Brief reference must resolve"
)

for parser_or_gate in list(repo.glob("skills/**/*.py")) + list(repo.glob("scripts/**/*.py")):
    assert "agent brief" not in parser_or_gate.read_text(encoding="utf-8").lower(), (
        f"Agent Brief must not enter a parser or gate: {parser_or_gate.relative_to(repo)}"
    )

assert "### Execution Digest: Conditional Working Memory" in solve
assert "never a Ticket-body section, tracker state, schema gate, or second requirement source" in solve
assert ".scratch/<feature>/execution-digests/<digest-key>.md" in solve
assert "never a broad `.scratch/**/*.md` glob" in solve
assert "first material decision or deviation" in solve
assert "reduced interruption-recovery guarantee" in solve
assert "`## Review` or `## Notes`" in solve
assert "`## Attempt Summary` or `## Confirmed Findings`" in solve
assert "\n## Execution Digest\n" not in solve
assert "agent-decision" not in solve
assert "Agent Decision Log" not in solve

for predicate in (
    "simple, familiar, local, low-risk, fully specified, and obviously verifiable",
    "adaptive read-only subagent fan-out",
    "relevant modules, constraints, risks, validation paths, and unresolved questions",
    "source-verifiable external API, framework, standard, platform, compatibility, or security fact",
    "Complex, delegated, resumable, or digest-worthy Attempts receive a Pre-Edit Plan Review",
):
    assert predicate in solve, f"Pre-Implementation Checkpoint contract missing: {predicate}"

assert "distill each durable Digest decision or deviation" in solve
assert "distill each durable decision or deviation" in record_format
assert "distill durable decisions and deviations" in record_format

safe_key = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def digest_key(ticket_identity, ticket_id, local_stem):
    if ticket_id and safe_key.fullmatch(ticket_id):
        return ticket_id
    if safe_key.fullmatch(local_stem):
        return local_stem
    return hashlib.sha256(ticket_identity.encode("utf-8")).hexdigest()


def digest_path(ticket_path, ticket_identity, ticket_id=None):
    parts = ticket_path.parts
    if len(parts) >= 4 and parts[-2] == "issues":
        feature_root = ticket_path.parents[1]
    elif len(parts) >= 3 and ticket_path.name == "issue.md":
        feature_root = ticket_path.parent
    else:
        raise AssertionError(f"unsupported local Ticket path: {ticket_path}")
    return feature_root / "execution-digests" / f"{digest_key(ticket_identity, ticket_id, ticket_path.stem)}.md"


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    issue_ticket = root / ".scratch/feature/issues/04-boundaries.md"
    single_ticket = root / ".scratch/standalone/issue.md"
    for ticket in (issue_ticket, single_ticket):
        ticket.parent.mkdir(parents=True, exist_ok=True)
        ticket.write_text("Status: ready-for-agent\n\n# Simple Ticket\n", encoding="utf-8")
        assert "Execution Digest" not in ticket.read_text(encoding="utf-8")

    issue_digest = digest_path(issue_ticket, ".scratch/feature/issues/04-boundaries.md")
    single_digest = digest_path(single_ticket, ".scratch/standalone/issue.md")
    assert issue_digest == root / ".scratch/feature/execution-digests/04-boundaries.md"
    assert single_digest == root / ".scratch/standalone/execution-digests/issue.md"
    assert not issue_digest.exists(), "simple fixture must leave no Digest residue"

    discovered = sorted(root.glob(".scratch/*/issues/*.md")) + sorted(root.glob(".scratch/*/issue.md"))
    assert discovered == [issue_ticket, single_ticket]

    issue_digest.parent.mkdir(parents=True)
    issue_digest.write_text("# Execution Digest: 04-boundaries\n\nStrategy: retained\n", encoding="utf-8")
    resumed = digest_path(issue_ticket, ".scratch/feature/issues/04-boundaries.md")
    assert resumed == issue_digest and resumed.read_text(encoding="utf-8").endswith("retained\n")
    assert discovered == sorted(root.glob(".scratch/*/issues/*.md")) + sorted(root.glob(".scratch/*/issue.md"))

    candidate_record = root / ".scratch/feature/solve-records/04-boundaries.md"
    candidate_record.parent.mkdir(parents=True)
    candidate_record.write_text("## Review\n- Digest decision distilled\n", encoding="utf-8")
    issue_digest.unlink()
    assert not issue_digest.exists(), "distilled, non-resumable Digest must be removable"

    assert digest_key("ticket://feature/unsafe key", "TICKET-4", "unsafe key") == "TICKET-4"
    unsafe = digest_key("ticket://feature/unsafe key", None, "unsafe key")
    assert unsafe == hashlib.sha256(b"ticket://feature/unsafe key").hexdigest()
    assert "/" not in unsafe

for scenario in (
    "Simple direct execution",
    "Non-trivial adaptive fan-out",
    "Pre-Edit Plan Review",
    "First-deviation Digest creation",
    "Stale Agent Brief hint",
    "Handoff distillation",
    "No unnecessary Digest residue",
):
    assert scenario in eval_plan, f"model-adherence scenario missing: {scenario}"
assert "No model adherence run was executed" in eval_plan
assert "Ticket, Digest, and Solve Record state" in eval_plan

print("ultra solve boundary fixture passed")
PY
