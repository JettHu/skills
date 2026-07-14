#!/usr/bin/env python3
"""Grade remote-publication eval scenarios from retained final state."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(root: Path) -> int:
    failures: list[str] = []
    for scenario in sorted(path for path in root.iterdir() if path.is_dir()):
        expected = json.loads((scenario / "EXPECTATIONS.json").read_text(encoding="utf-8"))
        remote = scenario / "REMOTE.json"
        if not expected["promote"]:
            escalation = scenario / "ESCALATION.md"
            if remote.exists() or not escalation.exists() or not escalation.read_text(encoding="utf-8").strip():
                failures.append(f"{scenario.name}: human-owned choice was not retained as an escalation")
            continue
        if not remote.exists():
            failures.append(f"{scenario.name}: missing remote state")
            continue
        state = json.loads(remote.read_text(encoding="utf-8"))
        tickets = state.get("tickets", [])
        if state.get("provider") != expected["provider"] or len(tickets) != 2:
            failures.append(f"{scenario.name}: wrong provider or Ticket count")
            continue
        if not all(item.get("ready") and "ready-for-agent" in item.get("labels", []) for item in tickets):
            failures.append(f"{scenario.name}: incomplete ready-state promotion")
        if any("review-pending" in item.get("labels", []) for item in tickets):
            failures.append(f"{scenario.name}: provisional member became claimable")
        by_key = {item.get("key"): item for item in tickets}
        if (
            "ultra-publication-set:" + expected["run_id"] not in by_key["A"].get("body", "")
            or by_key["A"].get("relationships") != {"blocks": ["B"]}
            or by_key["B"].get("relationships") != {"blocks": [], "parent": ["A"]}
        ):
            failures.append(f"{scenario.name}: publication identity or relationship verification failed")
        if expected["strategy"] == "local-staging" and (scenario / ".scratch/.ultra-staging" / expected["run_id"]).exists():
            failures.append(f"{scenario.name}: staging was not cleaned after promotion")
    print(json.dumps({"passed": not failures, "failures": failures}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
