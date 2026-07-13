#!/usr/bin/env python3
"""Prepare isolated Local Markdown review-publication model scenarios."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


INPUTS = (
    "skills/engineering/ultra/SKILL.md",
    "skills/engineering/ultra/references/ticket-review-publication.md",
    "skills/engineering/ultra/scripts/local_ticket_publication.py",
)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def register(adapter: Path, repo: Path, run_id: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(adapter),
            "register",
            "--repo",
            str(repo),
            "--representation",
            "tickets-file",
            "--location",
            ".scratch/feature/tickets.md",
            "--run-id",
            run_id,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def ticket(ticket_id: str, run_id: str, body: str, blockers: str = "") -> str:
    blocker_line = f"Blocked By: {blockers}" if blockers else "Blocked By:"
    return f"""<!-- ultra-ticket:begin id={ticket_id} -->
Status: review-pending
Ticket ID: {ticket_id}
Publication Run: {run_id}
Source Spec: APPROVED_SPEC.md
{blocker_line}
Flags:

## Ticket {ticket_id}

{body.rstrip()}
<!-- ultra-ticket:end -->
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    digests = {}
    for relative in INPUTS:
        text = (source / relative).read_text(encoding="utf-8")
        write(output / "skill-input" / relative, text)
        digests[relative] = sha256(text)
    contract_sha = sha256(json.dumps(digests, sort_keys=True))
    write(
        output / "contract-manifest.json",
        json.dumps({"inputs": digests, "contract_sha256": contract_sha}, indent=2) + "\n",
    )
    scenarios = [
        {"id": "01-derivable-review-fix", "run_id": "derivable-run"},
        {"id": "02-human-owned-choice", "run_id": "human-run"},
    ]
    write(output / "scenarios.json", json.dumps(scenarios, indent=2) + "\n")
    write(
        output / "AGENT_PROMPT.md",
        """# Fresh Agent Task

Work only inside this run root. Read `skill-input/skills/engineering/ultra/SKILL.md`
and its linked Ticket Review Publication reference, then process both scenarios
in `scenarios.json` independently. Do not read or run the grader.

For each scenario, read `TASK.md`, approved inputs, and the exact formal
`.scratch/feature/tickets.md`. Use the supplied copied adapter to re-register an
intentional review-fix membership change and to promote only when the contract
allows it. Write `run-decision.json` with keys `scenario`, `action`,
`human_choice`, `review_iterations`, `contract_sha256`, and `evidence` (an exact
contract excerpt). Do not ask the parent user ordinary split/blocker questions.
""",
    )

    adapter = output / "skill-input/skills/engineering/ultra/scripts/local_ticket_publication.py"

    first = output / "scenarios/01-derivable-review-fix"
    write(
        first / "APPROVED_SPEC.md",
        """# Approved account recovery Spec

Deliver two independently acceptable Tickets: backend token rotation with its
unit test, and frontend recovery UI with its component test. They are
independent and have no blocker edge between them.
""",
    )
    write(
        first / "REVIEW_FINDING.md",
        """The single Ticket is too large for independent acceptance. Split it
into backend and frontend Tickets, remove the invented blocker, and include the
approved validation command in each Ticket. This is fully derivable from the
approved Spec and needs no user decision.
""",
    )
    write(
        first / "TASK.md",
        """Apply the read-only review finding to the same formal tickets-file.
Preserve run `derivable-run`, use stable IDs `RECOVERY-BACKEND` and
`RECOVERY-FRONTEND`, re-register the intentional membership change, re-review,
and promote the complete corrected set without creating a confirmation file.
""",
    )
    write(
        first / "repo/.scratch/feature/tickets.md",
        "# Formal Tickets\n\n"
        + ticket(
            "RECOVERY-COMBINED",
            "derivable-run",
            "Implement backend token rotation and frontend recovery UI.\n\nValidation: test everything",
            "INVENTED-BLOCKER",
        ),
    )
    # The initial false blocker is intentionally review-fixable but cannot be
    # registered by the safe adapter. Seed its pre-review journal directly so
    # the fresh Agent must repair and explicitly re-register the set.
    initial_text = (first / "repo/.scratch/feature/tickets.md").read_text(encoding="utf-8")
    normalized = initial_text.replace("Status: review-pending", "Status: <state>")
    write(
        first / "repo/.scratch/feature/.ultra-publications/derivable-run.json",
        json.dumps(
            {
                "schema": "ultra-local-ticket-publication/v1",
                "run_id": "derivable-run",
                "representation": "tickets-file",
                "location": ".scratch/feature/tickets.md",
                "members": ["RECOVERY-COMBINED"],
                "body_digests": {"RECOVERY-COMBINED": sha256(normalized[normalized.index("Status:") : normalized.rindex("<!-- ultra-ticket:end -->")])},
                "phase": "review-pending",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    second = output / "scenarios/02-human-owned-choice"
    write(
        second / "APPROVED_SPEC.md",
        """# Approved release Ticket Spec

Prepare a Ticket for publishing the client library. The release owner and
whether this is a coordinated or independent release remain intentionally
undecided by the approved Spec.
""",
    )
    write(
        second / "TASK.md",
        """Review the formal Ticket. Because release ownership is genuinely
human-owned, do not invent the answer and do not promote. Write
`escalation.json` preserving the unresolved `release owner` choice. Leave the
same run resumable and non-claimable.
""",
    )
    write(
        second / "repo/.scratch/feature/tickets.md",
        "# Formal Tickets\n\n"
        + ticket(
            "CLIENT-RELEASE",
            "human-run",
            "Publish the client library.\n\nAcceptance depends on the unresolved release owner.",
        ),
    )
    register(adapter, second / "repo", "human-run")

    print(output)


if __name__ == "__main__":
    main()
