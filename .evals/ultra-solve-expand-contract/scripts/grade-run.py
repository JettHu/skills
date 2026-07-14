#!/usr/bin/env python3
"""Grade the final state of the shared-integration adherence fixture."""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import subprocess
import sys


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


def metadata(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            break
        if ":" in line:
            key, value = line.split(":", 1)
            values[key] = value.strip()
    return values


def main() -> int:
    repo = Path(sys.argv[1]).resolve()
    expected = json.loads((repo / "EVAL_EXPECTATIONS.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    ticket_root = repo / ".scratch/feature/issues"
    graph = {
        "EXPAND": "[]",
        "BATCH-A": "[EXPAND]",
        "BATCH-B": "[EXPAND]",
        "CONTRACT": "[BATCH-A, BATCH-B]",
        "INTEGRATE-VERIFY": "[CONTRACT]",
    }
    for ticket_id, blockers in graph.items():
        data = metadata(ticket_root / f"{ticket_id}.md")
        if data.get("Status") != "completed" or data.get("Flags"):
            errors.append(f"{ticket_id} is not completed with Claim released")
        if data.get("Blocked By") != blockers:
            errors.append(f"{ticket_id} blocker graph drifted")
        if data.get("Integration branch") != expected["integration_branch"] or data.get("Integration owner") != "INTEGRATE-VERIFY":
            errors.append(f"{ticket_id} integration declaration drifted")
    for ticket_id in ("BATCH-A", "BATCH-B", "CONTRACT"):
        data = metadata(ticket_root / f"{ticket_id}.md")
        if data.get("Validation owner") != "INTEGRATE-VERIFY" or data.get("Validation result") != "scoped":
            errors.append(f"{ticket_id} claimed the wrong validation ownership")
    final = metadata(ticket_root / "INTEGRATE-VERIFY.md")
    if final.get("Validation owner") != "INTEGRATE-VERIFY" or final.get("Validation result") != "passed":
        errors.append("final Ticket does not own passed integration validation")
    try:
        main_sha = git(repo, "rev-parse", expected["target_branch"])
        integration_sha = git(repo, "rev-parse", expected["integration_branch"])
        if main_sha == integration_sha:
            errors.append("target branch changed or integration branch was never created")
        if git(repo, "status", "--porcelain"):
            errors.append("integration worktree is dirty")
        if subprocess.run([sys.executable, "scripts/check.py", "final"], cwd=repo).returncode:
            errors.append("final integration result is not green")
        record = (repo / ".scratch/feature/solve-records/eval-shared-integration.md").read_text(encoding="utf-8")
        if f"head: {expected['integration_branch']}" not in record or f"head_sha: {integration_sha}" not in record:
            errors.append("candidate receipt does not name the integration head")
        if "`python3 scripts/check.py final` - passed" not in record:
            errors.append("candidate receipt lacks final verification evidence")
        helper_path = repo / "skills/engineering/solve-records/scripts/solve-records.py"
        spec = importlib.util.spec_from_file_location("fixture_solve_records", helper_path)
        assert spec and spec.loader
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        parsed = helper.parse_record(repo, repo / ".scratch/feature/solve-records/eval-shared-integration.md")
        if parsed.get("malformed"):
            errors.append(f"candidate receipt is malformed: {parsed.get('malformed')}")
        if parsed.get("checks_status") != "passed" or parsed.get("review_status") != "passed":
            errors.append("candidate receipt lacks passed checks or review")
    except (OSError, RuntimeError) as error:
        errors.append(str(error))
    audit_path = repo / ".evals/sequence-audit.jsonl"
    audit = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()] if audit_path.exists() else []
    if not any(event.get("event") == "candidate" and event.get("ticket") == "INTEGRATE-VERIFY" for event in audit):
        errors.append("final Ticket did not create the candidate receipt")
    if errors:
        print("FAIL shared-integration")
        for error in errors:
            print(f"  FAIL: {error}")
        return 1
    print("PASS shared-integration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
