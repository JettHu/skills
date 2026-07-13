#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$REPO_ROOT" <<'PY'
import importlib.util
import tempfile
from pathlib import Path
import sys


root = Path(sys.argv[1])
solve = (root / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")
record_format = (root / "skills/engineering/solve-records/references/record-format.md").read_text(encoding="utf-8")
agents = (root / "AGENTS.md").read_text(encoding="utf-8")
readme = (root / "README.md").read_text(encoding="utf-8")
ultra_meta = (root / "skills/engineering/ultra/agents/openai.yaml").read_text(encoding="utf-8")
wrapper = (root / "skills/engineering/ultra-solve/SKILL.md").read_text(encoding="utf-8")
wrapper_meta = (root / "skills/engineering/ultra-solve/agents/openai.yaml").read_text(encoding="utf-8")

assert "### 8.5 Outcome Finalization" in solve
assert "Every Attempt that stops or hands off routes through this decision once." in solve
assert "Claim remains the temporary concurrency lock; it never creates a receipt." in solve
assert "Immediate Claim release, transient failure, or fully cleaned work with no useful finding" in solve
assert "source Specs, approved decisions" in solve
assert "recovery edge cases" in solve
assert "exact retained-resource set" in solve
assert "Repeated resumes update that receipt in place" in solve
assert "The new Attempt creates its own receipt only when it later reaches a meaningful handoff." in solve
assert "Apply this section only after the Outcome gate re-reads `outcome: candidate`." in solve
assert "record the pending evidence in `## Verification` or `## Merge`" in solve
assert "record the pending evidence in `## Checks`" not in solve

format_link = "../solve-records/references/record-format.md"
edge_link = "../solve-records/references/edge-cases.md"
for link in (format_link, edge_link):
    assert (root / "skills/engineering/ultra" / link).resolve().is_file(), link
assert "outcome: candidate" in record_format
edge_cases = (root / "skills/engineering/solve-records/references/edge-cases.md").read_text(encoding="utf-8")
assert "Repeated resumes keep one receipt and one Ticket backlink." in edge_cases
for outcome in ("blocked", "needs-info", "ready-for-human", "abandoned", "superseded"):
    assert outcome in solve
    assert outcome in record_format

for text in (agents, readme, ultra_meta, wrapper, wrapper_meta):
    assert "outcome" in text.lower()
assert "Claim itself creates no receipt" in agents
assert "Claim itself creates no receipt" in wrapper_meta

tool_path = root / "skills/engineering/solve-records/scripts/solve-records.py"
spec = importlib.util.spec_from_file_location("ultra_outcome_fixture", tool_path)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ticket(status: str, record, claim: bool, retained: str = "") -> str:
    lines = [f"Status: {status}"]
    if claim:
        lines.append("Flags: solve-in-progress")
    if retained:
        lines.extend((f"Solve branch: {retained}", "Solve worktree: ../attempt-wt"))
    lines.extend(("", "# Fixture Ticket"))
    if record:
        lines.extend(("", "## Comments", "", "### Solve Record", "", f"- `../solve-records/{record}.md`"))
    return "\n".join(lines) + "\n"


def recovery_record(record_id: str, outcome: str, issue_path: str, retained: str, action: str, finding: str) -> str:
    ownership = "solve-owned; resume owns cleanup" if retained != "none" else "no retained resources; no cleanup needed"
    state = "closed" if outcome in {"abandoned", "superseded"} else "open"
    return f"""---
id: {record_id}
kind: solve_record
state: {state}
outcome: {outcome}
issues:
  - {issue_path}
created_at: 2026-07-13T12:00:00+08:00
cleanup_done: false
---

# Solve Record: {outcome}

## Ticket
Linked Ticket: `{issue_path}`

## Outcome
Result: {outcome}
Branch/worktree/commit/PR: {retained}
Resource ownership: {ownership}

## Attempt Summary
- Attempt reached a meaningful recovery handoff.

## Confirmed Findings
- {finding}

## Blocker Or Requested Information
- {finding}

## Resume Or Cleanup
Next action: {action}
- Follow the recorded recovery context.

## Resources
Cleanup: pending
- {retained}; {ownership}
"""


def candidate_record(record_id: str, issue_path: str) -> str:
    return f"""---
id: {record_id}
kind: solve_record
state: open
outcome: candidate
base: main
base_sha: 1111111111111111111111111111111111111111
head: solve/fixture
head_sha: 2222222222222222222222222222222222222222
issues:
  - {issue_path}
worktree: ../attempt-wt
created_at: 2026-07-13T12:00:00+08:00
cleanup_done: false
---

# Solve Record: candidate

## Ticket
Linked Ticket: `{issue_path}`

## Outcome
Result: candidate
Branch/worktree/commit/PR: solve/fixture, ../attempt-wt, 2222222
Resource ownership: solve-owned; candidate cleanup owns the temporary resources

## What Changed
- Finished the fixture.

## Verification
Status: passed
- fixture check - passed

## Review
Post-Execution Review: passed
- Ticket, source Spec, decisions, validation, and Digest agree.

## Merge
Status: ready
Reason:
- Rollout/config disposition: none; fixture only

## Resources
Cleanup: pending
- solve-owned candidate resources retained for review

## Notes
- none
"""


with tempfile.TemporaryDirectory() as temp:
    repo = Path(temp)
    issues = repo / ".scratch/outcomes/issues"
    records = repo / ".scratch/outcomes/solve-records"
    issue_path = ".scratch/outcomes/issues/05.md"
    issue_file = repo / issue_path

    # Claim and immediate no-value release are both recordless.
    write(issue_file, ticket("ready-for-agent", None, True))
    assert not list(records.glob("*.md"))
    write(issue_file, ticket("ready-for-agent", None, False))
    assert "solve-in-progress" not in issue_file.read_text(encoding="utf-8")
    assert not list(records.glob("*.md"))

    expected_states = {
        "blocked": "ready-for-human",
        "needs-info": "needs-info",
        "ready-for-human": "ready-for-human",
        "abandoned": "ready-for-agent",
        "superseded": "ready-for-agent",
    }
    actions = {
        "blocked": "resume",
        "needs-info": "provide information",
        "ready-for-human": "human decision",
        "abandoned": "close",
        "superseded": "supersede",
    }

    for outcome, status in expected_states.items():
        record_id = f"fixture-{outcome}"
        retained = "solve/fixture, ../attempt-wt, 3333333" if outcome in {"blocked", "abandoned", "superseded"} else "none"
        write(records / f"{record_id}.md", recovery_record(record_id, outcome, issue_path, retained, actions[outcome], f"{outcome} finding"))
        keep_claim = outcome == "blocked"
        write(issue_file, ticket(status, record_id, keep_claim, "solve/fixture" if retained != "none" else ""))
        parsed = helper.parse_record(repo, records / f"{record_id}.md")
        assert not parsed.get("malformed"), parsed
        assert parsed["outcome"] == outcome
        assert helper.candidate_operation_refusal(parsed) == f"outcome is {outcome}; candidate-only operations are unavailable"
        issue_text = issue_file.read_text(encoding="utf-8")
        assert f"Status: {status}" in issue_text
        assert issue_text.count(f"../solve-records/{record_id}.md") == 1
        assert ("solve-in-progress" in issue_text) == keep_claim
        if retained != "none":
            assert "Solve branch: solve/fixture" in issue_text
            assert parsed["retained_resources"] == retained
            assert parsed["resource_ownership"]

    # Failed required validation is a retained blocked handoff, never a candidate.
    failed_id = "fixture-failed-check"
    write(records / f"{failed_id}.md", recovery_record(failed_id, "blocked", issue_path, "solve/fixture, ../attempt-wt, 4444444", "resume", "required validation failed"))
    failed = helper.parse_record(repo, records / f"{failed_id}.md")
    assert failed["outcome"] == "blocked"
    assert "required validation failed" in failed["text"]
    assert helper.candidate_operation_refusal(failed)

    # Same Ticket, retained resources, blocker, and action reuse one receipt idempotently.
    resume_id = "fixture-resume"
    resume_path = records / f"{resume_id}.md"
    write(resume_path, recovery_record(resume_id, "blocked", issue_path, "solve/fixture, ../attempt-wt, 5555555", "resume", "dependency unavailable"))
    write(issue_file, ticket("ready-for-human", resume_id, True, "solve/fixture"))
    before = sorted(path.name for path in records.glob("fixture-resume*.md"))
    resume_text = resume_path.read_text(encoding="utf-8").replace(
        "- Attempt reached a meaningful recovery handoff.",
        "- Attempt reached a meaningful recovery handoff.\n- Resume revalidated the same retained context.",
    )
    write(resume_path, resume_text)
    write(resume_path, resume_path.read_text(encoding="utf-8"))
    after = sorted(path.name for path in records.glob("fixture-resume*.md"))
    assert before == after == [f"{resume_id}.md"]
    assert issue_file.read_text(encoding="utf-8").count(f"../solve-records/{resume_id}.md") == 1

    # A clean restart supersedes the old receipt before a later candidate handoff.
    superseded = resume_path.read_text(encoding="utf-8")
    superseded = superseded.replace("state: open", "state: closed", 1).replace("outcome: blocked", "outcome: superseded", 1)
    superseded = superseded.replace("Result: blocked", "Result: superseded", 1).replace("Next action: resume", "Next action: supersede", 1)
    write(resume_path, superseded)
    write(issue_file, ticket("ready-for-agent", resume_id, True))
    old = helper.parse_record(repo, resume_path)
    assert old["outcome"] == "superseded" and old["state"] == "closed"
    assert len(list(records.glob("fixture-resume*.md"))) == 1

    candidate_id = "fixture-restart-candidate"
    write(records / f"{candidate_id}.md", candidate_record(candidate_id, issue_path))
    write(issue_file, ticket("completed", candidate_id, False, "solve/fixture"))
    candidate = helper.parse_record(repo, records / f"{candidate_id}.md")
    assert not candidate.get("malformed"), candidate
    assert candidate["outcome"] == "candidate"
    assert not helper.candidate_operation_refusal(candidate)
    assert sorted(path.name for path in records.glob("fixture-*.md")).count(f"{candidate_id}.md") == 1

print("ultra solve attempt outcome fixture passed")
PY
