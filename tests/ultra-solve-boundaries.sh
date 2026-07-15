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
frontier = (repo / "skills/engineering/ultra/scripts/local_ticket_frontier.py").read_text(
    encoding="utf-8"
)
brief = (repo / "skills/engineering/ultra-to-tickets/references/agent-brief.md").read_text(
    encoding="utf-8"
)
wrapper = (repo / "skills/engineering/ultra-to-tickets/SKILL.md").read_text(encoding="utf-8")
record_format = (repo / "skills/engineering/solve-records/references/record-format.md").read_text(
    encoding="utf-8"
)
eval_plan = (repo / ".evals/ultra-solve-afk-safe-planning/20260708-model-adherence-eval-plan.md").read_text(
    encoding="utf-8"
)

approved_storage_literals = {
    ".scratch/<feature>/issues/",
    ".scratch/<feature>/issue.md",
    ".scratch/<feature>/issues/*.md",
    ".scratch/<feature>/issues/<ticket-file>.md",
    ".scratch/*/issues/*.md",
    ".scratch/*/issue.md",
}
approved_compatibility_identifiers = {
    "read_issue(issue_id)",
    "claim_issue(issue_id, branch, worktree)",
    "set_state(issue_id, state)",
    "add_flag(issue_id, flag)",
    "remove_flag(issue_id, flag)",
    "record_blocker(issue_id, reason, evidence_link_or_summary)",
    "link_change(issue_id, branch_or_worktree_or_commit_or_pr)",
    "link_validation(issue_id, command_or_check_run, status)",
    "close_completed(issue_id)",
}
approved_provider_native_names = {"GitHub Issue", "GitLab Issue"}
approved_legacy_spans = []
compatibility_heading = solve.index("## Tracker Adapter Compatibility")
for code_span in re.finditer(r"`([^`\n]+)`", solve):
    literal = code_span.group(1)
    if literal in approved_storage_literals:
        approved_legacy_spans.append(code_span.span(1))
        continue
    if literal not in approved_compatibility_identifiers:
        continue
    line_start = solve.rfind("\n", 0, code_span.start()) + 1
    line_end = solve.find("\n", code_span.end())
    line_end = len(solve) if line_end < 0 else line_end
    line_text = solve[line_start:line_end]
    documented_example = (
        "compatibility identifiers" in line_text and "Ticket" in line_text
    )
    adapter_signature = (
        code_span.start() > compatibility_heading
        and line_text.strip() == f"- `{literal}`"
    )
    if documented_example or adapter_signature:
        approved_legacy_spans.append(code_span.span(1))
for provider_name in approved_provider_native_names:
    approved_legacy_spans.extend(match.span() for match in re.finditer(re.escape(provider_name), solve))

unapproved_legacy_terms = []
identifier_token = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
legacy_piece = re.compile(r"issues?", flags=re.IGNORECASE)


def legacy_term_spans(text):
    for token_match in identifier_token.finditer(text):
        token = token_match.group()
        for piece in legacy_piece.finditer(token):
            raw = piece.group()
            before = token[piece.start() - 1] if piece.start() else ""
            after = token[piece.end()] if piece.end() < len(token) else ""
            left_boundary = (
                not before
                or before in "_-"
                or (raw[0].isupper() and (before.islower() or before.isdigit()))
                or (raw in {"Issue", "Issues"} and before.isupper())
            )
            right_boundary = not after or after in "_-" or after.isupper()
            if left_boundary and right_boundary:
                start = token_match.start() + piece.start()
                yield start, start + len(raw)


for legacy_identifier in (
    "issue",
    "issues",
    "issue_id",
    "issue-id",
    "issueId",
    "IssueTracker",
    "issuesPath",
    "legacyIssueId",
    "readIssue",
):
    assert list(legacy_term_spans(legacy_identifier)), (
        f"legacy Ticket identifier escaped structural detection: {legacy_identifier}"
    )
for unrelated_word in ("issuer", "issued", "tissue", "issuerId", "TissueTracker"):
    assert not list(legacy_term_spans(unrelated_word)), (
        f"unrelated word triggered legacy Ticket detection: {unrelated_word}"
    )
for match_start, match_end in legacy_term_spans(solve):
    if any(start <= match_start and match_end <= end for start, end in approved_legacy_spans):
        continue
    line = solve.count("\n", 0, match_start) + 1
    excerpt = solve.splitlines()[line - 1].strip()
    unapproved_legacy_terms.append(f"line {line}: {excerpt}")
assert not unapproved_legacy_terms, (
    "Ultra Solve contains unapproved legacy Ticket terminology:\n"
    + "\n".join(unapproved_legacy_terms)
)
assert (
    "compatibility API identifiers retain their established spellings while operating on Tickets"
    in solve
), "compatibility identifiers must identify their surrounding domain objects as Tickets"

assert "Context:" not in brief
for field in ("Constraints:", "Validation:", "Hints:"):
    assert field in brief, f"Agent Brief field missing: {field}"
assert "Omit each empty field and omit the entire section when every field is empty" in brief
assert "Agent Brief content never participates in parsing, eligibility, state transitions, or merge gates." in brief
assert "non-duplicative execution delta" in brief

link = re.search(r"\[Agent Brief contract\]\(([^)]+)\)", wrapper)
assert link, "wrapper must disclose the Agent Brief reference"
assert (repo / "skills/engineering/ultra-to-tickets" / link.group(1)).is_file(), (
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

for predicate in (
    "For a contract declaring `Frontier adapter: bundled-local-markdown-v1`",
    "Explicit Ticket IDs bound the selection universe",
    "#### `--all` Frontier Loop",
    "Treat one discovery result as one frontier generation",
    "Distinguish a valid empty frontier from an adapter failure",
):
    assert predicate in solve, f"claimable-frontier contract missing: {predicate}"
for predicate in (
    "stale dependency state: frontier snapshot changed before Claim",
    "missing-blocker-target:",
    "dependency-cycle",
    "publication-invalid:",
    "Claim post-write verification failed",
):
    assert predicate in frontier, f"claimable-frontier adapter missing: {predicate}"

assert "distill each durable Digest decision or deviation" in solve
assert "distill each durable decision or deviation" in record_format
assert "distill durable decisions and deviations" in record_format
assert "Do not create a **candidate** solve record" in solve
assert "a transient Attempt that is fully cleaned up stays recordless" in solve
assert "Read the [Solve Record format]" in solve
record_link = re.search(r"\[Solve Record format\]\(([^)]+)\)", solve)
assert record_link, "solve must name the receipt format before finalization"
assert (repo / "skills/engineering/ultra" / record_link.group(1)).is_file(), (
    "Solve Record format reference must resolve"
)

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
assert "A real model-adherence run was started" in eval_plan
assert "Ticket, Digest, and Solve Record state" in eval_plan
assert (repo / ".evals/ultra-solve-afk-safe-planning/20260713-model-adherence-eval.md").is_file()

print("ultra solve boundary fixture passed")
PY
