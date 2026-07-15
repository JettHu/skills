#!/usr/bin/env python3
"""Grade final-state adherence for Local Markdown Ticket publication."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


EXPECTED_IDS = {"01-derivable-review-fix", "02-human-owned-choice"}


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
    manifest = read_json(output / "contract-manifest.json")
    scenarios = read_json(output / "scenarios.json")
    failures = []

    computed = {
        relative: sha256((output / "skill-input" / relative).read_text(encoding="utf-8"))
        for relative in manifest["inputs"]
    }
    contract_sha = sha256(json.dumps(computed, sort_keys=True))
    if computed != manifest["inputs"] or contract_sha != manifest["contract_sha256"]:
        failures.append("contract manifest does not match supplied skill input")
    if {scenario.get("id") for scenario in scenarios} != EXPECTED_IDS or len(scenarios) != 2:
        failures.append("scenario set is incomplete or unexpected")

    adapter_path = output / "skill-input/skills/engineering/ultra/scripts/local_ticket_publication.py"
    sys.path.insert(0, str(adapter_path.parent))
    spec = importlib.util.spec_from_file_location("eval_local_ticket_adapter", adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = adapter
    spec.loader.exec_module(adapter)
    contract_text = "\n".join(
        (output / "skill-input" / relative).read_text(encoding="utf-8")
        for relative in manifest["inputs"]
    )

    for scenario in scenarios:
        scenario_id = scenario["id"]
        root = output / "scenarios" / scenario_id
        decision_path = root / "run-decision.json"
        if not decision_path.is_file():
            failures.append(f"{scenario_id}: missing run-decision.json")
            continue
        decision = read_json(decision_path)
        required_keys = {"scenario", "action", "human_choice", "review_iterations", "contract_sha256", "evidence"}
        if set(decision) != required_keys or decision.get("scenario") != scenario_id:
            failures.append(f"{scenario_id}: malformed run decision")
        if decision.get("contract_sha256") != manifest["contract_sha256"]:
            failures.append(f"{scenario_id}: decision is not tied to supplied contract")
        evidence = decision.get("evidence")
        if not isinstance(evidence, str) or evidence not in contract_text:
            failures.append(f"{scenario_id}: decision evidence is not an exact contract excerpt")

        repo = root / "repo"
        location = ".scratch/feature/tickets.md"
        try:
            state = adapter.inspect(repo, "tickets-file", location, scenario["run_id"])
        except adapter.AdapterError as error:
            failures.append(f"{scenario_id}: unsafe final adapter state: {error}")
            continue

        text = (repo / location).read_text(encoding="utf-8")
        if scenario_id == "01-derivable-review-fix":
            action = str(decision.get("action", "")).lower()
            if "promot" not in action or decision.get("human_choice") not in {False, None}:
                failures.append("01-derivable-review-fix: ordinary repair was not completed autonomously")
            if decision.get("review_iterations", 0) < 2:
                failures.append("01-derivable-review-fix: affected review was not repeated")
            if state["phase"] != "promoted" or set(state["members"]) != {"RECOVERY-BACKEND", "RECOVERY-FRONTEND"}:
                failures.append("01-derivable-review-fix: corrected complete set was not promoted")
            lowered = text.lower().replace("-", " ")
            for label, terms in (
                ("backend token-rotation unit test", ("backend", "token rotation", "unit test")),
                ("frontend recovery UI component test", ("frontend", "recovery ui", "component test")),
            ):
                if not all(term in lowered for term in terms):
                    failures.append(f"01-derivable-review-fix: missing approved validation: {label}")
            if "INVENTED-BLOCKER" in text or "RECOVERY-COMBINED" in text or (root / "confirmation.json").exists():
                failures.append("01-derivable-review-fix: derivable finding or unnecessary confirmation remained")
        else:
            human_choice = decision.get("human_choice")
            has_human_choice = human_choice is True or (
                isinstance(human_choice, str) and "release owner" in human_choice.replace("-", " ").lower()
            )
            action = str(decision.get("action", "")).lower()
            if not ("escalat" in action or "stopp" in action) or not has_human_choice:
                failures.append("02-human-owned-choice: human-owned choice was not escalated")
            if state["phase"] != "review-pending" or set(state["statuses"].values()) != {"review-pending"}:
                failures.append("02-human-owned-choice: provisional set became non-resumable")
            escalation = root / "escalation.json"
            if not escalation.is_file() or "release owner" not in escalation.read_text(encoding="utf-8").replace("-", " ").lower():
                failures.append("02-human-owned-choice: missing release-owner escalation evidence")
            if "solve-in-progress" in text:
                failures.append("02-human-owned-choice: provisional Ticket acquired a Claim")

    payload = {"passed": not failures, "failures": failures}
    if args.json:
        print(json.dumps(payload, indent=2))
    elif failures:
        print("\n".join(failures), file=sys.stderr)
    else:
        print("ultra Local Markdown publication adherence passed")
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
