#!/usr/bin/env python3
"""Grade final artifacts and routing decisions from the canonical-routing fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


EXPECTED = {
    "01-to-spec-bounded": {"target": "to-spec", "resolved_profile": "to-spec", "code": True, "research": False, "review": False, "human_choice": False, "review_iterations": 0},
    "02-to-spec-high-risk": {"target": "to-spec", "resolved_profile": "to-spec", "code": True, "research": False, "review": True, "human_choice": False, "review_iterations": 1},
    "03-to-tickets-local": {"target": "to-tickets", "resolved_profile": "to-tickets", "code": True, "research": False, "review": True, "human_choice": False, "review_iterations": 1},
    "04-to-tickets-external-fact": {"target": "to-tickets", "resolved_profile": "to-tickets", "code": True, "research": True, "review": True, "human_choice": False, "review_iterations": 1},
    "05-review-fix": {"target": "to-tickets", "resolved_profile": "to-tickets", "code": None, "research": False, "review": True, "human_choice": False, "review_iterations": 2},
    "06-human-owned-choice": {"target": "to-tickets", "resolved_profile": "to-tickets", "code": None, "research": False, "review": True, "human_choice": True, "review_iterations": 1},
    "07-legacy-bridge": {"target": "to-prd", "resolved_profile": "to-spec", "code": True, "research": False, "review": False, "human_choice": False, "review_iterations": 0},
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    scenarios = read_json(output / "scenarios.json")
    failures: list[str] = []

    for scenario in scenarios:
        scenario_id = scenario["id"]
        root = output / "scenarios" / scenario_id
        result_path = root / "result.json"
        if not result_path.is_file():
            failures.append(f"{scenario_id}: missing result.json")
            continue
        result = read_json(result_path)
        expected = EXPECTED[scenario_id]
        expected_keys = set(expected)
        if set(result) != expected_keys or any(
            expected[key] is not None and result[key] != expected[key] for key in expected
        ):
            failures.append(f"{scenario_id}: expected {expected}, got {result}")

        if scenario_id == "05-review-fix":
            artifact = (root / "artifact.md").read_text(encoding="utf-8")
            for required in (
                "# Generated Tickets",
                "## Ticket:",
                "POST /v2/accounts/rename",
                "auth.required: true",
                "pnpm test -- endpoint-rename",
            ):
                if required.casefold() not in artifact.casefold():
                    failures.append(f"05-review-fix: missing source-derived repair: {required}")
            if "## Issue:" in artifact or "Acceptance: rename it." in artifact:
                failures.append("05-review-fix: derivable defect remained in artifact")

        if scenario_id == "06-human-owned-choice":
            escalation = root / "escalation.json"
            if not escalation.is_file():
                failures.append("06-human-owned-choice: missing escalation.json")
            elif "release owner" not in escalation.read_text(encoding="utf-8").replace("-", " "):
                failures.append("06-human-owned-choice: escalation does not preserve release-owner choice")
            if (root / "artifact.md").exists():
                failures.append("06-human-owned-choice: invented artifact instead of escalation")

    payload = {"passed": not failures, "failures": failures}
    if args.json:
        print(json.dumps(payload, indent=2))
    elif failures:
        print("canonical routing adherence fixture failed", file=sys.stderr)
        print("\n".join(failures), file=sys.stderr)
    else:
        print("canonical routing adherence fixture passed")
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
