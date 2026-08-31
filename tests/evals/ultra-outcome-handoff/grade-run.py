#!/usr/bin/env python3
"""Grade final state for the candidate-handoff model eval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys


def main() -> int:
    repo = Path(sys.argv[1]).resolve()
    expected = json.loads((repo / "EVAL_EXPECTATIONS.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    name = hashlib.sha256(expected["key"].encode()).hexdigest() + ".md"
    receipt = repo / ".scratch/outcome/solve-records" / name
    receipt_text = receipt.read_text(encoding="utf-8") if receipt.is_file() else ""
    for ticket_id in expected["tickets"]:
        ticket = repo / f".scratch/outcome/issues/{ticket_id}.md"
        ticket_text = ticket.read_text(encoding="utf-8")
        if "Status: completed" not in ticket_text or "solve-in-progress" in ticket_text:
            failures.append(f"Ticket {ticket_id} is not completed with its Claim released")
        if ticket_text.count(f"../solve-records/{name}") != 1:
            failures.append(f"Ticket {ticket_id} does not contain exactly one canonical backlink")
    for expected_text in ("outcome: candidate", "state: open", "head: solve/eval-A", f'handoff_key: "{expected["key"]}"'):
        if expected_text not in receipt_text:
            failures.append(f"receipt is missing {expected_text}")
    for legacy_field in ("\nid:", "\nkind:", "\nissues:", "\ncleanup_done:"):
        if legacy_field in receipt_text:
            failures.append(f"canonical writer emitted legacy field {legacy_field.strip()}")
    if "tickets:\n  - .scratch/outcome/issues/A.md\n  - .scratch/outcome/issues/B.md" not in receipt_text:
        if expected["tickets"] == ["A", "B"]:
            failures.append("receipt is missing canonical Ticket membership")
    if expected.get("scenario") == "successor":
        predecessor = repo / expected["supersedes"]
        predecessor_text = predecessor.read_text(encoding="utf-8") if predecessor.is_file() else ""
        successor_rel = receipt.relative_to(repo).as_posix()
        for expected_text in (
            "state: closed",
            "outcome: blocked",
            f"superseded_by: {json.dumps(successor_rel)}",
            "closed_at:",
        ):
            if expected_text not in predecessor_text:
                failures.append(f"predecessor is missing {expected_text}")
        if f"supersedes: {json.dumps(expected['supersedes'])}" not in receipt_text:
            failures.append("successor is missing the predecessor relation")
        ticket_text = (repo / ".scratch/outcome/issues/A.md").read_text(encoding="utf-8")
        if ticket_text.count("../solve-records/") != 2:
            failures.append("Ticket A does not retain both handoff backlinks")
    audit = repo / ".evals/handoff-audit.jsonl"
    events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()] if audit.is_file() else []
    matching_events = [
        event for event in events
        if event["argv"][:2] == ["ticket", "handoff"]
        and expected["key"] in event["argv"]
    ]
    if len(matching_events) != 1:
        failures.append(f"facade audit was {events!r}")
    if failures:
        print("FAIL outcome-handoff")
        for failure in failures:
            print(f"  FAIL: {failure}")
        return 1
    print("PASS outcome-handoff")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
