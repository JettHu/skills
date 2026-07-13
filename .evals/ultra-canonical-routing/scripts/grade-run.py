#!/usr/bin/env python3
"""Grade final artifacts and routing decisions from the canonical-routing fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


EXPECTED = {
    "01-to-spec-bounded": {"requested_route": "to-spec", "resolved_profile": "to-spec", "code": True, "research": False, "review": False, "human_choice": False, "review_iterations": 0, "evidence": "| to-spec | yes | cond | cond | — |"},
    "02-to-spec-high-risk": {"requested_route": "to-spec", "resolved_profile": "to-spec", "code": True, "research": False, "review": True, "human_choice": False, "review_iterations": 1, "evidence": "The Spec is large, ambiguous, cross-system, or high-risk"},
    "03-to-tickets-local": {"requested_route": "to-tickets", "resolved_profile": "to-tickets", "code": True, "research": False, "review": True, "human_choice": False, "review_iterations": 1, "evidence": "| to-tickets | yes | cond | yes | — |"},
    "04-to-tickets-external-fact": {"requested_route": "to-tickets", "resolved_profile": "to-tickets", "code": True, "research": True, "review": True, "human_choice": False, "review_iterations": 1, "evidence": "A source-verifiable external fact directly determines an acceptance criterion or blocker edge"},
    "05-review-fix": {"requested_route": "to-tickets", "resolved_profile": "to-tickets", "code": None, "research": False, "review": True, "human_choice": False, "review_iterations": 2, "evidence": "The main Agent fixes every finding derivable from approved context and current code"},
    "06-human-owned-choice": {"requested_route": "to-tickets", "resolved_profile": "to-tickets", "code": None, "research": False, "review": True, "human_choice": True, "review_iterations": 1, "evidence": "Ask the user only for an unresolved scope, product-semantic, ownership, release-policy"},
    "07-legacy-bridge": {"requested_route": "to-prd", "resolved_profile": "to-spec", "code": True, "research": False, "review": False, "human_choice": False, "review_iterations": 0, "evidence": "| to-prd | to-spec | Temporary internal bridge"},
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    scenarios = read_json(output / "scenarios.json")
    manifest = read_json(output / "contract-manifest.json")
    computed_inputs = {
        relative: sha256((output / "skill-input" / relative).read_text(encoding="utf-8"))
        for relative in manifest["inputs"]
    }
    computed_contract = sha256(json.dumps(computed_inputs, sort_keys=True))
    contract_text = "\n".join(
        (output / "skill-input" / relative).read_text(encoding="utf-8") for relative in computed_inputs
    )
    failures: list[str] = []
    if manifest["inputs"] != computed_inputs or manifest["contract_sha256"] != computed_contract:
        failures.append("contract manifest does not match supplied runbook/profile input")

    for scenario in scenarios:
        scenario_id = scenario["id"]
        root = output / "scenarios" / scenario_id
        decision_path = root / "routing-decision.json"
        if not decision_path.is_file():
            failures.append(f"{scenario_id}: missing routing-decision.json")
            continue
        decision = read_json(decision_path)
        expected = EXPECTED[scenario_id]
        expected_keys = set(expected) | {"contract_sha256"}
        if set(decision) != expected_keys or any(
            expected[key] is not None and decision[key] != expected[key] for key in expected if key != "evidence"
        ):
            failures.append(f"{scenario_id}: route decision does not match expected routing: {decision}")
        if decision.get("contract_sha256") != manifest["contract_sha256"]:
            failures.append(f"{scenario_id}: routing decision is not tied to the supplied contract")
        evidence = decision.get("evidence")
        if not isinstance(evidence, list) or expected["evidence"] not in evidence:
            failures.append(f"{scenario_id}: routing decision lacks required rule evidence")
        elif any(not isinstance(item, str) or item not in contract_text for item in evidence):
            failures.append(f"{scenario_id}: routing decision evidence is not traceable to supplied contract input")

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
