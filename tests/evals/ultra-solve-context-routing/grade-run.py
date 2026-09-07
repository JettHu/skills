#!/usr/bin/env python3
"""Grade final state from the context-pointer routing model-adherence fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grade(repo: Path) -> list[str]:
    expectations = json.loads((repo / "EVAL_EXPECTATIONS.json").read_text(encoding="utf-8"))
    result_path = repo / "BOOTSTRAP_RESULT.json"
    failures: list[str] = []
    if not result_path.is_file():
        return ["missing BOOTSTRAP_RESULT.json"]
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"invalid result JSON: {error.msg}"]
    for key, expected in expectations["expected"].items():
        if result.get(key) != expected:
            failures.append(f"{key}: expected {expected!r}, got {result.get(key)!r}")
    for path, expected_hash in expectations["immutable"].items():
        current = repo / path
        if not current.is_file() or sha256(current) != expected_hash:
            failures.append(f"immutable input changed: {path}")
    changed = {
        relative.as_posix()
        for path in repo.rglob("*")
        if path.is_file()
        if ".git" not in (relative := path.relative_to(repo)).parts
        if relative.as_posix() not in {*expectations["immutable"], "EVAL_EXPECTATIONS.json", "EVAL_PROMPT.md", "BOOTSTRAP_RESULT.json"}
    }
    if changed:
        failures.append(f"unexpected created files: {sorted(changed)}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    repositories = [path / "repo" if (path / "repo").is_dir() else path for path in args.paths]
    failed = False
    for repo in repositories:
        failures = grade(repo)
        print(("PASS" if not failures else "FAIL"), repo.parent.name)
        for failure in failures:
            print("  FAIL:", failure)
        failed = failed or bool(failures)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
