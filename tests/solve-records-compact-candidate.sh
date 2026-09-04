#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/skills/engineering/solve-records/scripts/solve-records.py"
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

python3 - "$SCRIPT" "$TMPDIR_ROOT" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

script = Path(sys.argv[1])
root = Path(sys.argv[2]) / "project"
root.mkdir()
def git(*args, cwd=root):
    return subprocess.run(["git", *args], cwd=cwd, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True).stdout.strip()

git("init", "-b", "master")
git("config", "user.email", "test@example.test")
git("config", "user.name", "Solve Records Test")
(root / "app.txt").write_text("base\n", encoding="utf-8")
git("add", "app.txt")
git("commit", "-m", "base")
git("switch", "-c", "solve/compact")
(root / "app.txt").write_text("candidate\n", encoding="utf-8")
git("add", "app.txt")
git("commit", "-m", "candidate")
head_sha = git("rev-parse", "HEAD")
git("switch", "master")
worktree = root.parent / "candidate-wt"
git("worktree", "add", str(worktree), "solve/compact")

records = root / ".scratch" / "solve-records"
records.mkdir(parents=True)
record = records / "compact.md"
record.write_text(
    f"""---
state: open
outcome: candidate
tickets:
  - .scratch/feature/issues/01.md
handoff_key: compact-key
binding_digest: ignored
head: solve/compact
head_sha: {head_sha}
---

# Solve Record: Compact candidate

## Summary
Implemented the candidate. Validation: focused checks passed.
""", encoding="utf-8")

def run(*args):
    return subprocess.run([sys.executable, str(script), *args, "--repo", str(root), "--json"],
                          text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=False)

record_selector = ".scratch/solve-records/compact.md"

missing_record = records / "missing.md"
missing_record.write_text(
    record.read_text(encoding="utf-8")
    .replace("handoff_key: compact-key", "handoff_key: missing-key")
    .replace("head: solve/compact", "head: solve/missing")
    .replace(head_sha, "0" * 40),
    encoding="utf-8",
)
missing_before = missing_record.read_text(encoding="utf-8")
missing = run(
    "candidate-gate-record", "--record", ".scratch/solve-records/missing.md",
    "--checks", "passed", "--review", "passed", "--merge", "ready",
    "--rollout-config", "none",
)
assert missing.returncode != 0, missing.stdout + missing.stderr
assert "fatal" in missing.stderr, missing.stdout + missing.stderr
assert missing_record.read_text(encoding="utf-8") == missing_before

before = run("merge-gate", "--record", record_selector)
before_data = json.loads(before.stdout)
assert not before_data["eligible"]
assert any("base is unavailable" in reason for reason in before_data["reasons"])

enriched = run(
    "candidate-gate-record", "--record", record_selector,
    "--checks", "passed", "--review", "passed", "--merge", "ready",
    "--rollout-config", "none",
)
assert enriched.returncode == 0, enriched.stderr + enriched.stdout
after = run("merge-gate", "--record", record_selector)
after_data = json.loads(after.stdout)
assert after_data["eligible"], after_data
assert "Gate Evidence" in record.read_text(encoding="utf-8")

(root / "app.txt").write_text("user WIP\n", encoding="utf-8")
landing = run("landing-plan", "--record", record_selector)
landing_data = json.loads(landing.stdout)
assert landing_data["status"] == "blocked", landing_data
assert landing_data["dirty_overlap_paths"] == ["app.txt"], landing_data
assert any("app.txt" in reason for reason in landing_data["reasons"]), landing_data
assert (root / "app.txt").read_text(encoding="utf-8") == "user WIP\n"

print("solve-records compact candidate fixture passed")
PY
