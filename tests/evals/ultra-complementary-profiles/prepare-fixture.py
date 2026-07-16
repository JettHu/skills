#!/usr/bin/env python3
"""Prepare equivalent isolated treatment/ablation fixtures for Ultra profiles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import textwrap


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATHS = (
    "skills/engineering/ultra/SKILL.md",
    "skills/engineering/ultra/PROFILES.md",
)


def clean(value: str) -> str:
    return textwrap.dedent(value).strip() + "\n"


SCENARIOS = {
    "architecture-native-ownership": {
        "target": "improve-codebase-architecture",
        "task": "Review the hot order-routing module and produce one evidence-backed deepening candidate without changing production code.",
        "native": "Unconditionally scope the hot spot, read the glossary and ADR, and perform exactly one repository exploration pass before producing the report. Native exploration owns candidate discovery and uses Explore delegation when available, otherwise a serial equivalent.",
        "events": ["target-native-explore", "target-native-candidate", "ultra-post-review", "validation"],
        "forbidden": ["ultra-code-explore", "ultra-research"],
        "artifact": "artifacts/architecture-report.md",
        "tokens": ["Order Router", "route_order", "ADR-0001", "validation: python3 scripts/check.py"],
        "result": "unchanged",
        "tracker": "ready-for-agent",
        "trace_expectations": {
            "capability_tools": ["Agent"],
            "capability_agents": ["Explore"],
            "agent_calls": [{"role": "Explore", "min": 1, "max": 1}],
            "max_total_agent_calls": 1,
            "require_delegated_model": True,
        },
    },
    "diagnosis-feedback-loop-first": {
        "target": "diagnosing-bugs",
        "task": "Diagnose and fix the deterministic order-routing bug. Local evidence is sufficient; no external research is needed.",
        "native": "Build and run the red-capable feedback loop before hypotheses, exploration toward a theory, or research. Then reproduce, fix, rerun, and record the diagnosis.",
        "events": ["target-feedback-loop-red", "target-fix", "target-feedback-loop-green", "ultra-code-review", "validation"],
        "forbidden": ["ultra-code-explore", "ultra-research-before-loop"],
        "artifact": "artifacts/diagnosis.md",
        "tokens": ["python3 scripts/check.py", "red", "green"],
        "result": "fixed",
        "tracker": "ready-for-agent",
    },
    "spec-independent-code-trigger": {
        "target": "to-spec",
        "task": "Produce a Spec for a security-sensitive change spanning the order router and audit writer. Current local evidence settles external facts.",
        "native": "Explore the repository only if current codebase understanding is absent, then write the Spec through the target workflow.",
        "events": ["target-native-explore", "ultra-independent-code", "target-artifact", "ultra-fresh-review", "validation"],
        "forbidden": ["ultra-research", "duplicate-architecture-goal"],
        "artifact": "artifacts/spec.md",
        "tokens": ["Order Router", "Audit Writer", "security", "python3 scripts/check.py"],
        "result": "unchanged",
        "tracker": "review-pending",
    },
    "tickets-review-publication": {
        "target": "to-tickets",
        "task": "Turn the approved local Spec into a complete Ticket set, review and repair it, then promote it through the local publication adapter.",
        "native": "Gather the source, optionally explore when understanding is absent, and own drafting plus blocker assignment.",
        "events": ["target-native-explore", "target-draft", "ultra-complete-set-review", "ultra-publication", "validation"],
        "forbidden": ["ultra-research", "duplicate-drafting-goal"],
        "artifact": "artifacts/tickets.md",
        "tokens": ["Ticket 01", "Blocked by", "python3 scripts/check.py"],
        "result": "unchanged",
        "tracker": "ready-for-agent",
        "initial_tracker": "review-pending",
    },
    "short-evidence-complete": {
        "target": "to-spec",
        "task": "Produce a bounded Spec. APPROVED_EVIDENCE.md is short and currently covers every additive dependency-and-validation goal.",
        "native": "Use current repository understanding and produce the Spec. Do not infer that short context is insufficient.",
        "events": ["covered-additive-code", "target-artifact", "validation"],
        "forbidden": ["ultra-independent-code", "ultra-research"],
        "artifact": "artifacts/spec.md",
        "tokens": ["Order Router", "python3 scripts/check.py"],
        "result": "unchanged",
        "tracker": "review-pending",
        "evidence": "Current surfaces: app/router.py and route_order contract. Risk: audit ordering is unchanged. Validation: python3 scripts/check.py.",
    },
    "long-stale-context": {
        "target": "to-spec",
        "task": "Produce a cross-system Spec. HISTORY.md is long but predates ADR-0001 and lacks a current validation path.",
        "native": "Explore when current understanding is absent, then produce the Spec.",
        "events": ["target-native-explore", "ultra-independent-code", "target-artifact", "ultra-fresh-review", "validation"],
        "forbidden": ["covered-additive-code", "ultra-research"],
        "artifact": "artifacts/spec.md",
        "tokens": ["Order Router", "Audit Writer", "python3 scripts/check.py"],
        "result": "unchanged",
        "tracker": "review-pending",
        "history": ("Old discussion about a retired batch router. " * 120) + "No current contract or validation evidence.\n",
    },
    "triage-native-exploration": {
        "target": "triage",
        "task": "Triage the reported order-routing regression and verify the claim using the repository fixture.",
        "native": "Gather the report, explore the repository, check redundancy and prior rejection, and verify the claim. These stages are unconditional and target-owned.",
        "events": ["target-native-explore", "target-claim-verification", "target-artifact", "validation"],
        "forbidden": ["ultra-code-explore", "ultra-post-review"],
        "artifact": "artifacts/triage.md",
        "tokens": ["Order Router", "confirmed", "python3 scripts/check.py"],
        "result": "unchanged",
        "tracker": "needs-triage",
    },
}


def run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    return result.stdout


def read_ref(ref: str, relative: str) -> str:
    if ref == "working-tree":
        return (ROOT / relative).read_text(encoding="utf-8")
    return run(["git", "show", f"{ref}:{relative}"], ROOT)


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(repo: Path, scenario_id: str, variant: str, ref: str) -> None:
    scenario = SCENARIOS[scenario_id]
    if repo.exists():
        raise SystemExit(f"refusing to overwrite existing fixture: {repo}")
    repo.mkdir(parents=True)
    validation_lines = [
        "from pathlib import Path",
        f"expected = {scenario['result']!r}",
        "actual = Path('app/result.txt').read_text(encoding='utf-8').strip()",
        "if actual != expected:",
        "    raise SystemExit(f'expected {expected}, got {actual}')",
    ]
    if scenario_id == "diagnosis-feedback-loop-first":
        validation_lines.extend(
            [
                "import importlib.util",
                "spec = importlib.util.spec_from_file_location('router', 'app/router.py')",
                "router = importlib.util.module_from_spec(spec)",
                "spec.loader.exec_module(router)",
                "if router.route_order('priority') != 'priority':",
                "    raise SystemExit('priority order still follows the legacy route')",
            ]
        )
    common = {
        "AGENTS.md": "# Eval fixture\n\nFollow EVAL_PROMPT.md. Do not read files outside this repository.\n",
        "CONTEXT.md": "# Domain\n\nOrder Router selects a route. Audit Writer records the decision.\n",
        "docs/adr/ADR-0001.md": "# ADR-0001\n\nroute_order must return a route before Audit Writer persists it.\n",
        "app/router.py": "def route_order(order):\n    return 'legacy' if order == 'priority' else 'standard'\n",
        "app/expected.txt": f"{scenario['result']}\n",
        "app/result.txt": "unchanged\n",
        ".scratch/eval/issues/01-order-routing.md": f"Status: {scenario.get('initial_tracker', scenario['tracker'])}\n\n# Order routing eval Ticket\n",
        "scripts/check.py": "\n".join(validation_lines) + "\n",
        "TARGET_SKILL.md": clean(
            f"""
            # {scenario['target']} native contract

            {scenario['native']}

            Write the requested artifact, but do not perform a stage owned by Ultra.
            """
        ),
    }
    if "evidence" in scenario:
        common["APPROVED_EVIDENCE.md"] = scenario["evidence"] + "\n"
    if "history" in scenario:
        common["HISTORY.md"] = scenario["history"]
    for relative, value in common.items():
        write(repo / relative, value)

    contract_hashes = {}
    for relative in CONTRACT_PATHS:
        value = read_ref(ref, relative)
        write(repo / "skill-input" / relative, value)
        contract_hashes[relative] = hashlib.sha256(value.encode()).hexdigest()

    expectations = {
        "scenario": scenario_id,
        "variant": variant,
        "contract_ref": ref,
        "required_events": scenario["events"],
        "forbidden_events": scenario["forbidden"],
        "artifact": scenario["artifact"],
        "artifact_tokens": scenario["tokens"],
        "expected_result": scenario["result"],
        "expected_tracker_status": scenario["tracker"],
        "contract_hashes": contract_hashes,
        "trace_expectations": scenario.get("trace_expectations"),
    }
    write(repo / "EVAL_EXPECTATIONS.json", json.dumps(expectations, indent=2) + "\n")
    write(
        repo / "EVAL_PROMPT.md",
        clean(
            f"""
            # End-to-end Ultra profile task

            Execute `/ultra {scenario['target']}` for this task:

            {scenario['task']}

            Read `skill-input/skills/engineering/ultra/SKILL.md`, `skill-input/skills/engineering/ultra/PROFILES.md`, `TARGET_SKILL.md`, and repository evidence. Treat those as the complete portable contracts. Do not read `EVAL_EXPECTATIONS.json`.

            Perform the real file changes required by the task. Write the primary result to `{scenario['artifact']}`; that path is part of the public task contract, not a hidden grader expectation. Keep `.scratch/eval/issues/01-order-routing.md` at the workflow state justified by the task. Run `python3 scripts/check.py` as the final validation.

            As durable execution evidence, write `artifacts/stage-evidence.json` with an `events` array. Append one object per stage in actual order, each with exactly `name`, `owner`, `goal`, and `evidence`. Use stable stage names that describe the contract (for example `target-native-explore`, `ultra-post-review`, or `validation`). Record a covered-but-skipped additive goal as `covered-additive-code`; never record model response prose as evidence.

            Do not run any external grader and do not edit this prompt, `EVAL_EXPECTATIONS.json`, or the supplied skill inputs.
            """
        ),
    )
    run(["git", "init", "-q", "-b", "main"], repo)
    run(["git", "config", "user.name", "Ultra Eval"], repo)
    run(["git", "config", "user.email", "ultra-eval@example.invalid"], repo)
    run(["git", "add", "."], repo)
    run(["git", "commit", "-qm", "prepare equivalent eval fixture"], repo)
    manifest = {
        "scenario": scenario_id,
        "variant": variant,
        "contract_ref": ref,
        "common_hashes": {
            relative: sha256(repo / relative)
            for relative in sorted(common | {"EVAL_PROMPT.md": "", "TARGET_SKILL.md": ""})
            if (repo / relative).is_file()
        },
    }
    write(repo.parent / "fixture-manifest.json", json.dumps(manifest, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--variant", choices=("both", "treatment", "ablation"), default="both")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--treatment-ref", default="working-tree")
    parser.add_argument("--ablation-ref", required=True)
    args = parser.parse_args()
    scenario_ids = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    variants = ("treatment", "ablation") if args.variant == "both" else (args.variant,)
    refs = {"treatment": args.treatment_ref, "ablation": args.ablation_ref}
    for scenario_id in scenario_ids:
        for variant in variants:
            root = args.output.resolve() / args.run_id / scenario_id / variant / f"attempt-{args.attempt:03d}"
            prepare(root / "repo", scenario_id, variant, refs[variant])
            print(root / "repo")


if __name__ == "__main__":
    main()
