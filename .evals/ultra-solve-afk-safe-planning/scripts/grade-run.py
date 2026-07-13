#!/usr/bin/env python3
"""Grade current-contract ultra-solve fixtures from final repository state."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Grade:
    repo: Path
    scenario: str
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def check(self, condition: bool, message: str) -> None:
        (self.passed if condition else self.failed).append(message)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    return {
        key.strip().lower(): value.strip()
        for line in text[4:end].splitlines()
        if ":" in line and not line.startswith("  - ")
        for key, value in [line.split(":", 1)]
    }


def issue_status(text: str) -> str:
    return frontmatter(text).get("status", "").lower()


def helper(repo: Path):
    path = repo / "skills/engineering/solve-records/scripts/solve-records.py"
    spec = importlib.util.spec_from_file_location("eval_solve_records", path)
    if not spec or not spec.loader:
        raise SystemExit(f"missing canonical helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def receipt_for(module, repo: Path, issue_path: str) -> dict | None:
    for record in module.discover(repo):
        if issue_path in record.get("issues", []):
            return record
    return None


def candidate_dir(repo: Path, receipt: dict | None) -> Path:
    if not receipt or not receipt.get("worktree"):
        return repo
    path = Path(receipt["worktree"])
    return path if path.is_absolute() else (repo / path).resolve()


def run_check(path: Path) -> bool:
    check = path / "scripts/check.py"
    result = subprocess.run(["python3", str(check)], cwd=path, text=True, capture_output=True)
    return result.returncode == 0


def digest_path(repo: Path, issue_path: str) -> Path:
    return repo / ".scratch/afk-safe/execution-digests" / f"{Path(issue_path).stem}.md"


def grade(repo: Path) -> Grade:
    expectation = json.loads(read(repo / "EVAL_EXPECTATIONS.json"))
    expected = expectation["expected"]
    issue_path = expectation["issue_path"]
    issue_text = read(repo / issue_path)
    result = Grade(repo, expectation["scenario"])
    result.check(bool(issue_text), "Ticket exists")
    wanted_status = "completed" if expected["outcome"] == "candidate" else expected["outcome"]
    result.check(issue_status(issue_text) == wanted_status, f"Ticket status is {wanted_status}")
    result.check("\n## Execution Digest\n" not in issue_text, "Ticket has no inline Digest")

    module = helper(repo)
    receipt = receipt_for(module, repo, issue_path)
    result.check(receipt is not None, "linked receipt exists")
    if not receipt:
        return result
    result.check(not receipt.get("malformed"), "receipt passes canonical parser")
    result.check(receipt.get("outcome") == expected["outcome"], f"receipt outcome is {expected['outcome']}")
    dashboard = module.dashboard(repo, module.discover(repo))
    buckets = dashboard["buckets"]
    summary = next((item for values in buckets.values() for item in values if item.get("path") == receipt.get("path")), None)
    result.check(summary is not None, "receipt is classified by canonical dashboard")

    digest = digest_path(repo, issue_path)
    digest_mode = expected["digest"]
    if digest_mode == "present":
        digest_text = read(digest)
        result.check(bool(digest_text), "external Digest exists")
        for marker in expected.get("digest_markers", []):
            result.check(marker in digest_text, f"Digest contains {marker}")
    elif digest_mode == "distilled":
        result.check(not digest.exists(), "non-resumable Digest was removed")
        result.check("execution digest" in receipt.get("text", "").lower(), "receipt records Digest distillation")
    else:
        result.check(not digest.exists(), "no unnecessary external Digest")

    if expected["outcome"] == "candidate":
        result.check(receipt.get("base") and receipt.get("head") and receipt.get("worktree"), "candidate has live Git fields")
        result.check(any(item.get("id") == receipt.get("id") for item in buckets["ready"] + buckets["manual"]), "candidate uses a candidate dashboard route")
        if expected.get("check"):
            result.check(run_check(candidate_dir(repo, receipt)), "candidate check passes")
    else:
        result.check(not any(receipt.get(field) for field in ("base", "base_sha", "head", "head_sha", "worktree")), "recovery receipt has no candidate-only fields")
        result.check(any(item.get("id") == receipt.get("id") for item in buckets["recovery"]), "recovery receipt uses recovery dashboard route")

    for forbidden in expected.get("forbidden", []):
        result.check(not any(repo.parent.glob(f"**/{forbidden}")), f"forbidden path absent: {forbidden}")
    return result


def expectation_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if (path / "EVAL_EXPECTATIONS.json").is_file():
            files.append(path / "EVAL_EXPECTATIONS.json")
        else:
            files.extend(path.glob("**/repo/EVAL_EXPECTATIONS.json"))
    return sorted(set(files))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    files = expectation_files(args.paths)
    if not files:
        raise SystemExit("no EVAL_EXPECTATIONS.json found")
    grades = [grade(path.parent) for path in files]
    if args.json:
        print(json.dumps([{"scenario": item.scenario, "repo": str(item.repo), "passed": item.passed, "failed": item.failed} for item in grades], indent=2))
    else:
        for item in grades:
            print(("PASS" if not item.failed else "FAIL"), item.scenario)
            for failure in item.failed:
                print("  FAIL:", failure)
    if any(item.failed for item in grades):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
