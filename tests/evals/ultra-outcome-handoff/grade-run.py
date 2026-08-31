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
    ticket = repo / ".scratch/outcome/issues/A.md"
    ticket_text = ticket.read_text(encoding="utf-8")
    receipt_text = receipt.read_text(encoding="utf-8") if receipt.is_file() else ""
    if "Status: completed" not in ticket_text or "solve-in-progress" in ticket_text:
        failures.append("Ticket is not completed with its Claim released")
    if ticket_text.count(f"../solve-records/{name}") != 1:
        failures.append("Ticket does not contain exactly one canonical backlink")
    for expected_text in ("outcome: candidate", "state: open", "head: solve/eval-A", f'handoff_key: "{expected["key"]}"'):
        if expected_text not in receipt_text:
            failures.append(f"receipt is missing {expected_text}")
    for legacy_field in ("\nid:", "\nkind:", "\nissues:", "\ncleanup_done:"):
        if legacy_field in receipt_text:
            failures.append(f"canonical writer emitted legacy field {legacy_field.strip()}")
    if "tickets:\n  - .scratch/outcome/issues/A.md" not in receipt_text:
        failures.append("receipt is missing canonical Ticket membership")
    audit = repo / ".evals/handoff-audit.jsonl"
    events = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()] if audit.is_file() else []
    if len(events) != 1 or events[0]["argv"][:2] != ["ticket", "handoff"]:
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
