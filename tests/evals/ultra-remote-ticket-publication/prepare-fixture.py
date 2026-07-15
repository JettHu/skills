#!/usr/bin/env python3
"""Prepare credential-free final-state scenarios for remote publication review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    scenarios = (
        ("01-github-remote-review-fix", "github", "remote-review-pending", "remote-review-fix"),
        ("02-gitlab-remote-review-fix", "gitlab", "remote-review-pending", "remote-review-fix"),
        ("03-github-staging-partial-resume", "github", "local-staging", "staging-partial-resume"),
        ("04-gitlab-staging-partial-resume", "gitlab", "local-staging", "staging-partial-resume"),
        ("05-gitlab-remote-human", "gitlab", "remote-review-pending", "human-escalation"),
    )
    for name, provider, strategy, mode in scenarios:
        scenario = root / name
        write(
            scenario / "SPEC.json",
            json.dumps({"tickets": [{"key": "A", "title": "Parent", "body": "Parent", "blocks": ["B"]}, {"key": "B", "title": "Child", "body": "Child", "parent": "A"}]}, indent=2) + "\n",
        )
        expected = {"provider": provider, "strategy": strategy, "mode": mode, "run_id": name}
        write(scenario / "EXPECTATIONS.json", json.dumps(expected, indent=2) + "\n")
        if mode == "remote-review-fix":
            action = """Run the adapter once with `--reviewed --fail-at verify` and retain the resulting REMOTE.json as PARTIAL_STATE.json. Then edit the still-provisional parent Ticket body in REMOTE.json from `Parent` to `Reviewer-fixed Parent`, resume with `--reviewed`, and promote the complete set."""
        elif mode == "staging-partial-resume":
            action = """Run the adapter once with `--reviewed --fail-at wire` and retain the staged manifest as PARTIAL_MANIFEST.json. Then resume with `--reviewed`; promotion must verify the complete set and remove the staging directory."""
        else:
            action = "The release owner is unresolved: write ESCALATION.md, create no REMOTE.json, and do not promote."
        prompt = f"""You are the main Agent using the copied Ultra remote publication contract.

Scenario: {name}
Provider: {provider}; strategy: {strategy}.
Use the fixture adapter at `../../skills/engineering/ultra/scripts/remote_ticket_publication.py` and this scenario's SPEC.json. Use the exact publication run ID `{name}`. Persist remote state as REMOTE.json. For local staging use `.scratch/.ultra-staging/`. {action}

Do not read EXPECTATIONS.json or a grader. Your result is graded from final files, not this response.
"""
        write(scenario / "EVAL_PROMPT.md", prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
