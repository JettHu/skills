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
        ("01-github-remote", "github", "remote-review-pending", True),
        ("02-gitlab-remote-human", "gitlab", "remote-review-pending", False),
        ("03-github-staging-resume", "github", "local-staging", True),
        ("04-gitlab-staging-resume", "gitlab", "local-staging", True),
    )
    for name, provider, strategy, promote in scenarios:
        scenario = root / name
        write(
            scenario / "SPEC.json",
            json.dumps({"tickets": [{"key": "A", "title": "Parent", "body": "Parent", "blocks": ["B"]}, {"key": "B", "title": "Child", "body": "Child", "parent": "A"}]}, indent=2) + "\n",
        )
        expected = {"provider": provider, "strategy": strategy, "promote": promote, "run_id": name}
        write(scenario / "EXPECTATIONS.json", json.dumps(expected, indent=2) + "\n")
        prompt = f"""You are the main Agent using the copied Ultra remote publication contract.

Scenario: {name}
Provider: {provider}; strategy: {strategy}.
Use the fixture adapter at `../../skills/engineering/ultra/scripts/remote_ticket_publication.py` and this scenario's SPEC.json. Persist remote state as REMOTE.json. For local staging use `.scratch/.ultra-staging/`. {"Perform an in-place review fix and promote the complete set." if promote else "The release owner is unresolved: write ESCALATION.md, create no REMOTE.json, and do not promote."}

Do not read EXPECTATIONS.json or a grader. Your result is graded from final files, not this response.
"""
        write(scenario / "EVAL_PROMPT.md", prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
