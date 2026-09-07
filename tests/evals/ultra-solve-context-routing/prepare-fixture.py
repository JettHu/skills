#!/usr/bin/env python3
"""Create isolated model-adherence fixtures for Ultra context-pointer routing."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL_PATHS = (
    "skills/engineering/ultra/SKILL.md",
    "skills/engineering/ultra/PROFILES.md",
    "skills/engineering/ultra/solve.md",
    "skills/engineering/ultra/references/ticket-review-publication.md",
    "skills/engineering/ultra-to-tickets/SKILL.md",
)


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(value).strip() + "\n", encoding="utf-8")


def run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)


def treatment(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def ticket(context: str, risk: str) -> str:
    return textwrap.dedent(
        f"""
        Status: ready-for-agent
        Ticket ID: CTX-EVAL

        # Context routing evaluation

        ## Acceptance criteria

        - Complete only the pre-implementation context assessment.

        ## Risk

        {risk}

        {context}
        """
    ).strip() + "\n"


SCENARIOS = (
    {
        "id": "01-authoritative-current",
        "context": """## Context

- Source Spec (authoritative; ref: `eval-base`): `docs/prd/behavior.md` — defines accepted behavior.
- Decisions (authoritative; ref: `eval-base`): `docs/adr/0042.md` — fixes the concurrency boundary.
""",
        "risk": "Local behavior change; no high-risk signal.",
        "expected": {
            "disposition": "executable",
            "diagnostics": [],
            "authoritative_sources": ["eval-base:docs/prd/behavior.md", "eval-base:docs/adr/0042.md"],
            "nonessential_unavailable": [],
            "fallback_lookups": 0,
            "independent_evidence_passes": 0,
        },
    },
    {
        "id": "02-authoritative-missing",
        "context": """## Context

- Source Spec (authoritative; ref: `eval-base`): `docs/prd/missing.md` — defines an approval boundary.
""",
        "risk": "Permission boundary.",
        "current_head_only": {
            "docs/prd/missing.md": "# Stale current-HEAD document\n\nThis file is not available at eval-base."
        },
        "expected": {
            "disposition": "needs-info",
            "diagnostics": ["context_pointer_missing_authoritative"],
            "authoritative_sources": ["eval-base:docs/prd/missing.md"],
            "nonessential_unavailable": [],
            "fallback_lookups": 0,
            "independent_evidence_passes": 0,
        },
    },
    {
        "id": "03-nonessential-unavailable",
        "context": """## Context

- Source Spec (authoritative; ref: `eval-base`): `docs/prd/behavior.md` — defines accepted behavior.
- Domain Context (nonessential; ref: `eval-base`): `CONTEXT-MAP.md` — provides optional vocabulary.
""",
        "risk": "Local behavior change; no high-risk signal.",
        "expected": {
            "disposition": "executable",
            "diagnostics": ["context_pointer_unavailable_nonessential"],
            "authoritative_sources": ["eval-base:docs/prd/behavior.md"],
            "nonessential_unavailable": ["eval-base:CONTEXT-MAP.md"],
            "fallback_lookups": 0,
            "independent_evidence_passes": 0,
        },
    },
    {
        "id": "04-native-evidence-suppressed",
        "context": """## Context

- Source Spec (authoritative; ref: `eval-base`): `docs/prd/behavior.md` — defines permission behavior.
""",
        "risk": "Permission and concurrency work. The target-native permission review already owns the exact acceptance evidence objective.",
        "expected": {
            "disposition": "executable",
            "diagnostics": [],
            "authoritative_sources": ["eval-base:docs/prd/behavior.md"],
            "nonessential_unavailable": [],
            "fallback_lookups": 0,
            "independent_evidence_passes": 0,
        },
    },
)


def create_scenario(output: Path, scenario: dict) -> None:
    repo = output / scenario["id"] / "repo"
    repo.mkdir(parents=True)
    for path in SKILL_PATHS:
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(treatment(path), encoding="utf-8")
    write(
        repo / "AGENTS.md",
        """
        # Runtime guidance

        This file is injected as active guidance. The evaluation prompt already
        supplies it, so do not reread it during Bootstrap.
        """,
    )
    write(repo / "docs/prd/behavior.md", "# Accepted behavior\n\nThe named behavior is approved.")
    write(repo / "docs/adr/0042.md", "# Concurrency decision\n\nThe named boundary is binding.")
    issue_path = ".scratch/context-routing/issues/CTX-EVAL.md"
    write(repo / issue_path, ticket(scenario["context"], scenario["risk"]))
    write(repo / "LIVE_CLAIM.json", '{"ticket":"CTX-EVAL","snapshot":"current"}')
    run(["git", "init", "-q", "-b", "main"], repo)
    run(["git", "config", "user.email", "eval@example.invalid"], repo)
    run(["git", "config", "user.name", "Eval"], repo)
    run(["git", "add", "."], repo)
    run(["git", "commit", "-qm", "eval base"], repo)
    run(["git", "tag", "eval-base"], repo)
    current_head_only = scenario.get("current_head_only", {})
    for relative_path, contents in current_head_only.items():
        write(repo / relative_path, contents)
    if current_head_only:
        run(["git", "add", *current_head_only], repo)
        run(["git", "commit", "-qm", "advance current head"], repo)
    immutable = {
        path: hashlib.sha256((repo / path).read_bytes()).hexdigest()
        for path in (
            *SKILL_PATHS,
            "AGENTS.md",
            issue_path,
            "LIVE_CLAIM.json",
            "docs/prd/behavior.md",
            "docs/adr/0042.md",
            *current_head_only,
        )
    }
    expectations = {"issue_path": issue_path, "expected": scenario["expected"], "immutable": immutable}
    write(repo / "EVAL_EXPECTATIONS.json", json.dumps(expectations, indent=2))
    write(
        repo / "EVAL_PROMPT.md",
        f"""
        The evaluator has already dispatched `/ultra solve`; do not invoke an installed
        skill or read files outside this fixture repository. Perform only the
        Pre-Implementation Checkpoint for `{issue_path}` after a successful Claim. This
        is a Bootstrap-only assessment: do not implement, claim, transition a Ticket,
        create a receipt, or modify any existing file.

        Runtime guidance is already injected; do not reread `AGENTS.md`. Before the
        assessment, read only the Context Pointer Contract and Bootstrap sections in the
        embedded fixture runbook. Read the selected Ticket, then `LIVE_CLAIM.json`, then
        each exact Context document at its declared ref. Do not scan unrelated ADRs,
        context files, or scratch content. Use the exact named diagnostics from Bootstrap;
        list every selected authoritative ref/path in `authoritative_sources`, including
        a document that is absent at its declared ref; a nonessential unavailable pointer
        must appear both in `diagnostics` and in `nonessential_unavailable`, without substitution.
        For high-risk work, do not add
        an independent pass when the Ticket says target-native evidence already owns that
        exact objective.

        Write only `BOOTSTRAP_RESULT.json` with this exact JSON shape:
        {{
          "disposition": "executable or needs-info",
          "diagnostics": ["named diagnostics"],
          "authoritative_sources": ["<ref>:<path>"],
          "nonessential_unavailable": ["<ref>:<path>"],
          "fallback_lookups": 0,
          "independent_evidence_passes": 0
        }}
        """,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scenario", choices=["all", *[item["id"] for item in SCENARIOS]], default="all")
    args = parser.parse_args()
    if args.output.exists():
        shutil.rmtree(args.output)
    selected = SCENARIOS if args.scenario == "all" else tuple(item for item in SCENARIOS if item["id"] == args.scenario)
    for scenario in selected:
        create_scenario(args.output, scenario)


if __name__ == "__main__":
    main()
