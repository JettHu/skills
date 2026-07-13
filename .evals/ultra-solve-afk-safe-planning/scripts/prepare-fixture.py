#!/usr/bin/env python3
"""Create isolated current-contract model-adherence fixtures for /ultra solve."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import textwrap
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = ROOT / ".evals/ultra-solve-afk-safe-planning/runs"
SKILL_PATHS = (
    "skills/engineering/ultra/SKILL.md",
    "skills/engineering/ultra/solve.md",
    "skills/engineering/ultra/agents/openai.yaml",
    "skills/engineering/ultra-to-issues/SKILL.md",
    "skills/engineering/ultra-to-issues/references/agent-brief.md",
    "skills/engineering/solve-records/SKILL.md",
    "skills/engineering/solve-records/references/record-format.md",
    "skills/engineering/solve-records/scripts/solve-records.py",
)


def text(value: str) -> str:
    return textwrap.dedent(value).strip() + "\n"


def run(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout or "command failed")
    return result.stdout


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def read_ref(ref: str, path: str) -> str:
    if ref == "working-tree":
        return (ROOT / path).read_text(encoding="utf-8")
    return run(["git", "show", f"{ref}:{path}"], ROOT)


def issue(title: str, body: str) -> str:
    return text(
        f"""
        ---
        status: ready-for-agent
        labels:
          - ready-for-agent
        ---

        # {title}

        {body}
        """
    )


def common(issue_path: str, title: str) -> dict[str, str]:
    return {
        "AGENTS.md": text(
            """
            # Eval Fixture Guidance

            Treat embedded `skills/engineering/` files as authoritative.
            The local tracker is `.scratch/afk-safe/issues/`; receipts belong in
            `.scratch/afk-safe/solve-records/`; external Digests belong in
            `.scratch/afk-safe/execution-digests/`. `main` is the landing branch.

            Do not merge, push, or clean up. A finished candidate needs the current
            outcome-aware candidate receipt. A meaningful stopped Attempt needs the
            matching recovery receipt; a fully cleaned transient Attempt stays
            recordless.
            """
        ),
        "EVAL_PROMPT.md": text(
            f"""
            You are in a fresh isolated Git repository. Read `AGENTS.md`,
            `skills/engineering/ultra/SKILL.md`,
            `skills/engineering/ultra/solve.md`, and the linked receipt format.

            Execute this user-invoked workflow exactly:

            /ultra solve {issue_path}

            Do not merge, push, or clean up. Leave the final Ticket, external
            Digest lifecycle, receipt, candidate worktree, and validation evidence
            for the committed final-state grader. Do not edit EVAL_EXPECTATIONS.json.
            """
        ),
        ".scratch/afk-safe/solve-records/.gitkeep": "",
        "app/__init__.py": "",
        "README.md": f"# {title}\n",
    }


def simple() -> dict:
    path = ".scratch/afk-safe/issues/01-simple.md"
    files = common(path, "Simple direct execution")
    files.update(
        {
            path: issue(
                "Format a greeting",
                """
                ## Acceptance Criteria

                - `greeting("Ada")` returns `Hello, Ada!`.
                - Leading and trailing whitespace is ignored.
                - The change stays in the greeting helper.

                ## Agent Brief

                Constraints: Keep the public function name.
                Validation: Run `python3 scripts/check.py`.
                """,
            ),
            "app/greeting.py": "def greeting(name: str) -> str:\n    return f'hello, {name.strip()}'\n",
            "scripts/check.py": text(
                """
                from pathlib import Path
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.greeting import greeting
                assert greeting("Ada") == "Hello, Ada!"
                assert greeting("  Grace ") == "Hello, Grace!"
                print("simple passed")
                """
            ),
        }
    )
    return {"id": "01-simple", "issue_path": path, "files": files, "expected": {"outcome": "candidate", "digest": "absent", "check": True}}


def digest_worthy() -> dict:
    path = ".scratch/afk-safe/issues/02-fanout-preedit.md"
    files = common(path, "Fan-out and Pre-Edit review")
    files.update(
        {
            path: issue(
                "Add configured checkout discount",
                """
                ## Acceptance Criteria

                - `SAVE10` preserves `total` and adds `discounted_total`.
                - A known code adds `applied_discount_code`.
                - The public contract declares both new fields.
                - Validate behavior and contract together.

                ## Agent Brief

                Constraints: Keep existing `total` semantics.
                Validation: Run `python3 scripts/check.py`.
                Hints: `app/pricing.py`, `app/checkout.py`, `app/contracts.py`.
                """,
            ),
            "config/discounts.json": '{"SAVE10": 0.10}\n',
            "app/pricing.py": "def subtotal(invoice):\n    return sum(item['price'] for item in invoice['lines'])\n",
            "app/checkout.py": "from app.pricing import subtotal\n\ndef checkout_response(invoice):\n    return {'total': subtotal(invoice)}\n",
            "app/contracts.py": "PUBLIC_FIELDS = {'total'}\n",
            "scripts/check.py": text(
                """
                from pathlib import Path
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.checkout import checkout_response
                from app.contracts import PUBLIC_FIELDS
                result = checkout_response({'discount_code': 'SAVE10', 'lines': [{'price': 100}]})
                assert result == {'total': 100, 'discounted_total': 90, 'applied_discount_code': 'SAVE10'}
                assert {'discounted_total', 'applied_discount_code'} <= PUBLIC_FIELDS
                print("fanout passed")
                """
            ),
        }
    )
    return {"id": "02-fanout-preedit", "issue_path": path, "files": files, "expected": {"outcome": "candidate", "digest": "present", "digest_markers": ["Strategy:", "Validation plan:", "Pre-Edit"], "check": True}}


def first_deviation() -> dict:
    path = ".scratch/afk-safe/issues/03-first-deviation.md"
    files = common(path, "First deviation and distillation")
    files.update(
        {
            path: issue(
                "Normalize slugs after compatibility discovery",
                """
                ## Acceptance Criteria

                - `slugify("Hello, Agent World!")` returns `hello-agent-world`.
                - Public URLs remain ASCII-safe.

                ## Material compatibility deviation

                A caller requires ASCII-safe transport while the current policy permits
                Unicode slugs. This first record-worthy deviation must use the external
                Digest and be distilled into the final candidate receipt.
                """,
            ),
            "config/slug-policy.json": '{"unicode_slugs": true}\n',
            "app/slugs.py": "def slugify(value):\n    return value.lower().replace(' ', '-')\n",
            "app/urls.py": "from app.slugs import slugify\n\ndef public_url(value):\n    return '/posts/' + slugify(value)\n",
            "scripts/check.py": text(
                """
                from pathlib import Path
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.slugs import slugify
                assert slugify("Hello, Agent World!") == "hello-agent-world"
                print("deviation passed")
                """
            ),
        }
    )
    return {"id": "03-first-deviation", "issue_path": path, "files": files, "expected": {"outcome": "candidate", "digest": "distilled", "check": True}}


def stale_hint() -> dict:
    path = ".scratch/afk-safe/issues/04-stale-hint.md"
    files = common(path, "Stale hint")
    files.update(
        {
            path: issue(
                "Render customer tax id",
                """
                ## Acceptance Criteria

                - `render_receipt` includes `Tax ID: <value>` when present.
                - Existing total rendering remains unchanged.
                - Do not add a compatibility shim for deleted receipt modules.

                ## Agent Brief

                Constraints: Keep the current receipt API.
                Validation: Run `python3 scripts/check.py`.
                Hints: Start with `app/legacy_receipts.py`. This hint may be stale.
                """,
            ),
            "app/receipt.py": "def render_receipt(order):\n    return f\"Total: {order['total']}\"\n",
            "scripts/check.py": text(
                """
                from pathlib import Path
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.receipt import render_receipt
                assert "Total: 42" in render_receipt({'total': 42, 'customer': {'tax_id': 'TAX-123'}})
                assert "Tax ID: TAX-123" in render_receipt({'total': 42, 'customer': {'tax_id': 'TAX-123'}})
                print("stale hint passed")
                """
            ),
        }
    )
    return {"id": "04-stale-hint", "issue_path": path, "files": files, "expected": {"outcome": "candidate", "digest": "absent", "forbidden": ["app/legacy_receipts.py"], "check": True}}


def recovery() -> dict:
    path = ".scratch/afk-safe/issues/05-recovery-handoff.md"
    files = common(path, "Meaningful recovery handoff")
    files.update(
        {
            path: issue(
                "Choose public identity field",
                """
                ## Acceptance Criteria

                - Decide whether a public API exposes email, internal id, or an opaque id.
                - Implement the approved contract and security rationale.

                ## Human Review Needed

                Product and security approval is absent. Route this human-owned decision
                without inventing a contract.
                """,
            ),
            "app/users.py": "def public_user(user):\n    return {'name': user['name']}\n",
            "scripts/check.py": "print('recovery fixture')\n",
        }
    )
    return {"id": "05-recovery-handoff", "issue_path": path, "files": files, "expected": {"outcome": "ready-for-human", "digest": "absent", "check": False}}


def no_residue() -> dict:
    path = ".scratch/afk-safe/issues/06-no-digest-residue.md"
    files = common(path, "No unnecessary Digest residue")
    files.update(
        {
            "app/greeting.py": "def greeting(name: str) -> str:\n    return f'hello, {name.strip()}'\n",
            "scripts/check.py": text(
                """
                from pathlib import Path
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.greeting import greeting
                assert greeting("Ada") == "Hello, Ada!"
                print("no residue passed")
                """
            ),
        }
    )
    files[path] = issue(
        "One-file punctuation fix",
        """
        ## Acceptance Criteria

        - `greeting("Ada")` returns `Hello, Ada!`.
        - Keep the implementation local and run `python3 scripts/check.py`.
        """,
    )
    return {"id": "06-no-digest-residue", "issue_path": path, "files": files, "expected": {"outcome": "candidate", "digest": "absent", "check": True}}


def failed_check() -> dict:
    path = ".scratch/afk-safe/issues/07-failed-check-retained.md"
    files = common(path, "Failed required validation with recovery value")
    files.update(
        {
            path: issue(
                "Normalize an invoice reference before required staging validation",
                """
                ## Acceptance Criteria

                - `normalize_reference(" inv-42 ")` returns `INV-42`.
                - Run `python3 scripts/check.py`; this required check also needs the
                  staging marker outside the repository.
                - The staging marker is intentionally unavailable in this fixture.
                  Preserve the implementation, failed-check evidence, branch, and
                  worktree for resume. Keep the marker and validation script unchanged.
                - Route the meaningful failed Attempt to `blocked`; it is not a
                  candidate. Release the Claim after the recovery handoff because no
                  actor remains actively assigned.

                ## Agent Brief

                Constraints: Keep `normalize_reference` public and preserve recovery resources.
                Validation: Run `python3 scripts/check.py` and record its failure exactly.
                """,
            ),
            "app/invoice.py": "def normalize_reference(value: str) -> str:\n    return value.strip()\n",
            "scripts/check.py": text(
                """
                from pathlib import Path
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.invoice import normalize_reference
                assert normalize_reference(" inv-42 ") == "INV-42"
                marker = Path("/tmp/ultra-solve-eval-staging-marker-must-remain-absent")
                assert marker.is_file(), "required staging validation failed: marker unavailable"
                print("staging validation passed")
                """
            ),
        }
    )
    return {
        "id": "07-failed-check-retained",
        "issue_path": path,
        "files": files,
        "expected": {
            "outcome": "blocked",
            "ticket_status": "ready-for-human",
            "digest": "present",
            "digest_markers": ["Strategy:", "Validation plan:"],
            "check": False,
            "claim": "released",
            "backlink_count": 1,
            "receipt_count": 1,
            "retained_markers": ["solve/", "worktree"],
            "required_check_fails": True,
        },
    }


def resume_reuse() -> dict:
    path = ".scratch/afk-safe/issues/08-resume-reuse.md"
    record_id = "08-resume-reuse"
    record_path = f".scratch/afk-safe/solve-records/{record_id}.md"
    files = common(path, "Resume the same retained recovery context")
    files.update(
        {
            path: text(
                f"""
                ---
                status: ready-for-agent
                labels:
                  - ready-for-agent
                ---

                # Resume normalization on the retained Attempt

                ## Acceptance Criteria

                - Reclaim this Ticket and continue on `solve/eval-resume` in
                  `../resume-worktree`; those resources and the recovery context remain valid.
                - `normalize_reference(" inv-42 ")` returns `INV-42` and
                  `python3 scripts/check.py` passes now that the fixture marker exists.
                - Reuse `{record_id}` in place, finalize it as the candidate receipt,
                  and keep exactly one backlink and one receipt for this Attempt.
                - Release the Claim at candidate handoff. Do not create a clean-restart
                  branch or a second receipt.

                ## Comments

                ### Solve Record

                - `../solve-records/{record_id}.md`
                """
            ),
            record_path: text(
                f"""
                ---
                id: {record_id}
                kind: solve_record
                state: open
                outcome: blocked
                issues:
                  - {path}
                created_at: 2026-07-13T12:00:00+08:00
                cleanup_done: false
                ---

                # Solve Record: Retained normalization Attempt

                ## Ticket
                Linked Ticket: `{path}`

                ## Outcome
                Result: blocked
                Branch/worktree/commit/PR: `solve/eval-resume`, `../resume-worktree`
                Resource ownership: solve-owned; the resumed Attempt owns the retained branch and worktree

                ## Attempt Summary
                - Normalization was started on the retained resources.

                ## Confirmed Findings
                - Required staging validation was blocked by a missing marker.

                ## Blocker Or Requested Information
                - Wait for the fixture staging marker.

                ## Resume Or Cleanup
                Next action: resume
                - Reclaim the Ticket and continue on the recorded resources.

                ## Resources
                Cleanup: pending
                - `solve/eval-resume`, `../resume-worktree`; solve-owned and retained for resume
                """
            ),
            "app/invoice.py": "def normalize_reference(value: str) -> str:\n    return value.strip()\n",
            "scripts/check.py": text(
                """
                from pathlib import Path
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.invoice import normalize_reference
                assert normalize_reference(" inv-42 ") == "INV-42"
                assert Path("STAGING_READY").is_file()
                print("resume passed")
                """
            ),
            "STAGING_READY": "ready\n",
        }
    )
    return {
        "id": "08-resume-reuse",
        "issue_path": path,
        "files": files,
        "setup": "resume_resources",
        "expected": {
            "outcome": "candidate",
            "digest": "absent",
            "check": True,
            "claim": "released",
            "backlink_count": 1,
            "receipt_count": 1,
            "receipt_id": record_id,
            "initial_outcome": "blocked",
            "initial_receipt_path": record_path,
            "head": "solve/eval-resume",
            "worktree_suffix": "resume-worktree",
        },
    }


SCENARIOS = {
    scenario["id"]: scenario
    for scenario in (
        simple(),
        digest_worthy(),
        first_deviation(),
        stale_hint(),
        recovery(),
        no_residue(),
        failed_check(),
        resume_reuse(),
    )
}


def init_repo(repo: Path) -> None:
    run(["git", "init", "-b", "main", str(repo)])
    run(["git", "config", "user.email", "eval@example.test"], repo)
    run(["git", "config", "user.name", "Ultra Solve Eval"], repo)
    run(["git", "add", "."], repo)
    run(["git", "commit", "-m", "eval base"], repo)


def setup_resume_resources(repo: Path) -> None:
    worktree = repo.parent / "resume-worktree"
    run(["git", "worktree", "add", "-b", "solve/eval-resume", str(worktree), "eval-base"], repo)
    invoice = worktree / "app/invoice.py"
    invoice.write_text(
        "def normalize_reference(value: str) -> str:\n    return value.strip().upper()\n",
        encoding="utf-8",
    )
    run(["git", "add", "app/invoice.py"], worktree)
    run(["git", "commit", "-m", "wip: retain normalization attempt"], worktree)


def create_fixture(root: Path, scenario: dict, ref: str, force: bool) -> Path:
    repo = root / scenario["id"] / "repo"
    if repo.exists():
        if not force:
            raise SystemExit(f"fixture already exists: {repo}")
        shutil.rmtree(repo.parent)
    for path in SKILL_PATHS:
        write(repo / path, read_ref(ref, path))
    for path, value in scenario["files"].items():
        write(repo / path, value)
    init_repo(repo)
    expectation = {"scenario": scenario["id"], "issue_path": scenario["issue_path"], "treatment_ref": ref, "base_ref": "eval-base", "expected": scenario["expected"]}
    write(repo / "EVAL_EXPECTATIONS.json", json.dumps(expectation, indent=2, sort_keys=True) + "\n")
    run(["git", "add", "EVAL_EXPECTATIONS.json"], repo)
    run(["git", "commit", "-m", "eval expectations"], repo)
    run(["git", "tag", "eval-base"], repo)
    if scenario.get("setup") == "resume_resources":
        setup_resume_resources(repo)
    return repo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-id", default=f"run-{time.strftime('%Y%m%d-%H%M%S')}")
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--treatment-ref", required=True, help="committed treatment SHA, branch, or tag")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    run_root = args.output / args.run_id
    selected = SCENARIOS.values() if args.scenario == "all" else (SCENARIOS[args.scenario],)
    repos = [create_fixture(run_root, scenario, args.treatment_ref, args.force) for scenario in selected]
    write(run_root / "MANIFEST.md", "# Ultra Solve Eval Run\n\n" + "\n".join(f"- `{repo}`" for repo in repos) + "\n")
    print(run_root)


if __name__ == "__main__":
    main()
