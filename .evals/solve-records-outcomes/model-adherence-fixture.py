
#!/usr/bin/env python3
"""Isolated fixture and final-state grader for solve-record outcome adherence."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


RECOVERY_IDS = ("blocked", "needs-info", "abandoned-user-owned")


def run(repo, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "git failed")
    return result


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def record_hashes(repo):
    paths = sorted(
        list(repo.glob(".scratch/solve-records/*.md"))
        + list(repo.glob(".scratch/*/solve-records/*.md"))
    )
    return {
        str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def snapshot(repo):
    return {
        "record_hashes": record_hashes(repo),
        "refs": run(repo, "show-ref", "--head").stdout,
        "worktrees": run(repo, "worktree", "list", "--porcelain").stdout,
    }


def candidate_record(issue, base_sha, head_sha, worktree):
    return f"""---
id: model-candidate
kind: solve_record
state: open
outcome: candidate
base: master
base_sha: {base_sha}
head: solve/model-adherence
head_sha: {head_sha}
issues:
  - {issue}
worktree: {worktree}
created_at: 2026-07-10T15:00:00+08:00
cleanup_done: false
---

# Solve Record: Model candidate

## Ticket
Linked Ticket: {issue}

## Outcome
Result: candidate
Branch/worktree/commit/PR: solve/model-adherence, {worktree}
Resource ownership: solve-owned; candidate cleanup owns the temporary worktree

## What Changed
- Fixture-only candidate.

## Verification
Status: passed

## Review
Post-Execution Review: passed

## Merge
Status: ready
- Rollout/config disposition: none; no operator action is needed.

## Resources
Cleanup: pending
"""


def recovery_record(record_id, outcome, state, issue, ownership, retained, action):
    return f"""---
id: {record_id}
kind: solve_record
state: {state}
outcome: {outcome}
issues:
  - {issue}
created_at: 2026-07-10T15:00:00+08:00
cleanup_done: false
---

# Solve Record: {record_id}

## Ticket
Linked Ticket: {issue}

## Outcome
Result: {outcome}
Branch/worktree/commit/PR: {retained}
Resource ownership: {ownership}

## Attempt Summary
- A substantive attempt reached a durable handoff.

## Confirmed Findings
- The recovery outcome is intentional and complete.

## Blocker Or Requested Information
- Candidate operations are not valid for this receipt.

## Resume Or Cleanup
Next action: {action}
- Use only the recorded ownership and safety evidence.

## Resources
Cleanup: pending
"""


def prepare(repo, snapshot_path):
    if repo.exists() and any(repo.iterdir()):
        raise RuntimeError(f"fixture repo must be empty: {repo}")
    repo.mkdir(parents=True, exist_ok=True)
    run(repo, "init", "-b", "master")
    run(repo, "config", "user.email", "outcome-eval@example.test")
    run(repo, "config", "user.name", "Outcome Eval")
    write(repo / "app.txt", "base\n")
    run(repo, "add", "app.txt")
    run(repo, "commit", "-m", "base")
    base_sha = run(repo, "rev-parse", "master").stdout.strip()

    run(repo, "checkout", "-b", "solve/model-adherence", "master")
    write(repo / "candidate.txt", "candidate\n")
    run(repo, "add", "candidate.txt")
    run(repo, "commit", "-m", "candidate")
    head_sha = run(repo, "rev-parse", "solve/model-adherence").stdout.strip()
    run(repo, "checkout", "master")

    candidate_worktree = repo.parent / "candidate-worktree"
    user_worktree = repo.parent / "user-owned-worktree"
    run(repo, "worktree", "add", str(candidate_worktree), "solve/model-adherence")
    run(repo, "branch", "feature/user-owned-recovery", "master")
    run(repo, "worktree", "add", str(user_worktree), "feature/user-owned-recovery")

    issue = ".scratch/model-adherence/issues/01.md"
    write(repo / issue, "Status: ready-for-agent\n")
    records = repo / ".scratch/model-adherence/solve-records"
    write(
        records / "model-candidate.md",
        candidate_record(issue, base_sha, head_sha, "../candidate-worktree"),
    )
    write(
        records / "blocked.md",
        recovery_record(
            "blocked",
            "blocked",
            "open",
            issue,
            "solve-owned; retain the branch for a future resume",
            "solve/model-adherence",
            "resume",
        ),
    )
    write(
        records / "needs-info.md",
        recovery_record(
            "needs-info",
            "needs-info",
            "open",
            issue,
            "no retained resources; no cleanup needed",
            "none",
            "provide information",
        ),
    )
    write(
        records / "abandoned-user-owned.md",
        recovery_record(
            "abandoned-user-owned",
            "abandoned",
            "closed",
            issue,
            "user-owned; leave the branch and worktree in place",
            "feature/user-owned-recovery, ../user-owned-worktree",
            "close",
        ),
    )

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(snapshot(repo), indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "repo": str(repo),
                "snapshot": str(snapshot_path),
                "candidate": ".scratch/model-adherence/solve-records/model-candidate.md",
                "recoveries": [
                    f".scratch/model-adherence/solve-records/{record_id}.md"
                    for record_id in RECOVERY_IDS
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )


def helper_json(helper, *args):
    result = subprocess.run(
        ["python3", str(helper), *args, "--json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "solve-record helper failed")
    return json.loads(result.stdout)


def grade(repo, snapshot_path, helper):
    before = json.loads(snapshot_path.read_text(encoding="utf-8"))
    after = snapshot(repo)
    dashboard = helper_json(helper, "dashboard", "--repo", str(repo))
    buckets = {
        name: {item["id"] for item in items}
        for name, items in dashboard["buckets"].items()
    }
    recovery_bucket = buckets.get("recovery", set())
    candidate_buckets = (
        buckets.get("ready", set())
        | buckets.get("manual", set())
        | buckets.get("cleanup", set())
        | buckets.get("recent", set())
    )
    gate_checks = {}
    for record_id in RECOVERY_IDS:
        merge = helper_json(helper, "merge-gate", "--repo", str(repo), "--record", record_id)
        landing = helper_json(helper, "landing-plan", "--repo", str(repo), "--record", record_id)
        cleanup = helper_json(helper, "cleanup-plan", "--repo", str(repo), "--record", record_id)
        expected = f"candidate-only operations are unavailable"
        gate_checks[record_id] = (
            not merge["eligible"]
            and landing["status"] == "blocked"
            and cleanup["status"] == "blocked"
            and any(expected in reason for reason in merge["reasons"])
            and any(expected in reason for reason in landing["reasons"])
            and expected in cleanup["reason"]
        )

    candidate_unmerged = run(
        repo,
        "merge-base",
        "--is-ancestor",
        "solve/model-adherence",
        "master",
        check=False,
    ).returncode != 0
    user_branch_exists = (
        run(repo, "show-ref", "--verify", "--quiet", "refs/heads/feature/user-owned-recovery", check=False).returncode
        == 0
    )
    user_worktree_exists = str((repo.parent / "user-owned-worktree").resolve()) in after["worktrees"]

    checks = {
        "records_unchanged": before["record_hashes"] == after["record_hashes"],
        "refs_unchanged": before["refs"] == after["refs"],
        "worktrees_unchanged": before["worktrees"] == after["worktrees"],
        "recoveries_only_in_recovery_bucket": set(RECOVERY_IDS) <= recovery_bucket
        and not (set(RECOVERY_IDS) & candidate_buckets),
        "candidate_remains_unmerged": candidate_unmerged,
        "user_owned_branch_preserved": user_branch_exists,
        "user_owned_worktree_preserved": user_worktree_exists,
        "recovery_candidate_operations_refused": all(gate_checks.values()),
    }
    result = {
        "passed": all(checks.values()),
        "checks": checks,
        "gate_checks": gate_checks,
        "dashboard": {
            name: sorted(items)
            for name, items in buckets.items()
        },
        "before_record_hashes": before["record_hashes"],
        "after_record_hashes": after["record_hashes"],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--repo", required=True, type=Path)
    prepare_parser.add_argument("--snapshot", required=True, type=Path)

    grade_parser = subparsers.add_parser("grade")
    grade_parser.add_argument("--repo", required=True, type=Path)
    grade_parser.add_argument("--snapshot", required=True, type=Path)
    grade_parser.add_argument("--helper", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.repo.resolve(), args.snapshot.resolve())
        return 0
    return grade(args.repo.resolve(), args.snapshot.resolve(), args.helper.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
