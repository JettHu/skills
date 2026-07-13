#!/usr/bin/env python3
"""Prepare isolated realistic prompts for Ultra canonical target routing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


SCENARIOS = [
    {
        "id": "01-to-spec-bounded",
        "target": "to-spec",
        "task": "Create a bounded Spec for an internal rename. No external API, standard, security requirement, or cross-system risk is involved.",
    },
    {
        "id": "02-to-spec-high-risk",
        "target": "to-spec",
        "task": "Create a Spec for a cross-system security-sensitive migration. Approved local context settles every external fact.",
    },
    {
        "id": "03-to-tickets-local",
        "target": "to-tickets",
        "task": "Turn an approved local Spec into Tickets. Current repository docs settle all acceptance criteria and blocker edges.",
    },
    {
        "id": "04-to-tickets-external-fact",
        "target": "to-tickets",
        "task": "Turn an approved Spec into Tickets. An official platform limit, absent from approved local context, directly determines one acceptance criterion.",
    },
    {
        "id": "05-review-fix",
        "target": "to-tickets",
        "task": "Review the exact generated Ticket artifact against APPROVED_CONTEXT.md. Correct every derivable defect without asking the user, then re-review the repaired artifact.",
        "artifact": """# Generated Tickets\n\n## Issue: rename endpoint\n\nAcceptance: rename it.\n\nBlocker: none.\n""",
        "context": """# Approved context\n\n- The replacement is `POST /v2/accounts/rename`.\n- Requests require `auth.required: true`.\n- Validation is `pnpm test -- endpoint-rename`.\n- No blocker exists.\n""",
    },
    {
        "id": "06-human-owned-choice",
        "target": "to-tickets",
        "task": "The approved Spec leaves the release-owner decision unresolved. Preserve the artifact surface and escalate that human-owned choice instead of inventing a blocker edge.",
    },
    {
        "id": "07-legacy-bridge",
        "target": "to-prd",
        "task": "Use the still-promoted legacy wrapper route for a bounded internal rename. It has no external or high-risk condition.",
    },
]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    source = args.source.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for relative in (
        Path("skills/engineering/ultra/SKILL.md"),
        Path("skills/engineering/ultra/PROFILES.md"),
    ):
        input_path = source / relative
        if not input_path.is_file():
            raise SystemExit(f"missing skill input: {input_path}")
        write(output / "skill-input" / relative, input_path.read_text(encoding="utf-8"))

    write(output / "scenarios.json", json.dumps(SCENARIOS, indent=2) + "\n")
    for scenario in SCENARIOS:
        root = output / "scenarios" / scenario["id"]
        root.mkdir(parents=True)
        write(root / "TASK.md", f"# {scenario['id']}\n\nRequested route: `/{'ultra ' + scenario['target']}`\n\n{scenario['task']}\n")
        if "artifact" in scenario:
            write(root / "artifact.md", scenario["artifact"])
        if "context" in scenario:
            write(root / "APPROVED_CONTEXT.md", scenario["context"])

    write(
        output / "AGENT_PROMPT.md",
        """# Fresh-session task\n\nFor every scenario, execute the requested route as a real `/ultra <target>` run: read only the supplied `skill-input/skills/engineering/ultra/SKILL.md` and `PROFILES.md`, then invoke the installed target skill when it is available. The fixture deliberately excludes its grader and expected results. Do not modify this prompt, `scenarios.json`, `TASK.md`, or `APPROVED_CONTEXT.md`.\n\nEvery output belongs in its existing directory under `<fixture-root>/scenarios/<scenario-id>/`; do not create a top-level `<fixture-root>/<scenario-id>/` directory. Write `result.json` there after each run with exactly `target`, `resolved_profile`, `code`, `research`, `review`, `human_choice`, and `review_iterations`. Record the route actually selected from the supplied runbook.\n\nFor `05-review-fix`, apply the full review-fix loop to that scenario's `artifact.md` against its read-only `APPROVED_CONTEXT.md`: repair all derivable defects, re-review the repaired artifact, and record two review iterations.\n\nFor `06-human-owned-choice`, write `escalation.json` in that scenario directory describing the unresolved release-owner choice and do not create an invented Ticket or blocker edge.\n\nWhen complete, do not run a grader.\n""",
    )
    print(output)


if __name__ == "__main__":
    main()
