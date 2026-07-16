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


def stage_marker(name: str) -> str:
    return f"[eval-stage:{name}]"


def clean(value: str) -> str:
    return textwrap.dedent(value).strip() + "\n"


SCENARIOS = {
    "architecture-native-ownership": {
        "target": "improve-codebase-architecture",
        "task": "Review the hot order-routing module and produce one evidence-backed deepening candidate without changing production code.",
        "native": (
            "Unconditionally scope the hot spot, read the glossary and ADR, and perform exactly one "
            "repository exploration pass before producing the report. Native exploration owns candidate "
            "discovery and uses Explore delegation when available, otherwise a serial equivalent."
        ),
        "events": ["target-native-explore", "target-native-candidate", "ultra-post-review", "validation"],
        "recordable_extra_events": ["ultra-code-explore"],
        "forbidden": ["ultra-code-explore", "ultra-research"],
        "artifact": "artifacts/architecture-report.md",
        "tokens": ["Order Router", "route_order", "ADR-0001"],
        "result": "unchanged",
        "tracker": "ready-for-agent",
        "event_aliases": {"target-native-report": "target-native-candidate"},
        "ablation_attributable_failure_codes": ["extra_exploration_call"],
        "ablation_required_difference_codes": ["extra_exploration_call"],
    },
    "diagnosis-feedback-loop-first": {
        "target": "diagnosing-bugs",
        "task": "Diagnose and fix the deterministic order-routing bug. Local evidence is sufficient; no external research is needed.",
        "native": "Build and run the red-capable feedback loop before hypotheses, exploration toward a theory, or research. Then reproduce, fix, rerun, and record the diagnosis.",
        "events": ["target-feedback-loop-red", "target-fix", "target-feedback-loop-green", "ultra-code-review", "validation"],
        "forbidden": ["ultra-code-explore", "ultra-research-before-loop"],
        "artifact": "artifacts/diagnosis.md",
        "tokens": ["red", "green"],
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
        "tokens": ["Order Router", "Audit Writer", "security"],
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
        "tokens": ["Ticket 01", "Blocked by"],
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
        "tokens": ["Order Router"],
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
        "tokens": ["Order Router", "Audit Writer"],
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
        "tokens": ["Order Router", "confirmed"],
        "result": "unchanged",
        "tracker": "needs-triage",
    },
}


SCENARIO_AUTHORITY = {
    "architecture-native-ownership": {
        "artifact_sections": ["Candidate", "Source Evidence", "ADR and Risk Review"],
        "artifact_sources": ["app/router.py", "docs/adr/ADR-0001.md"],
        "trace_required_events": ["target-native-explore"],
        "trace_reconcile_events": ["target-native-explore", "ultra-code-explore"],
    },
    "diagnosis-feedback-loop-first": {
        "artifact_sections": ["Reproduction", "Root Cause", "Fix", "Validation"],
        "artifact_sources": ["app/router.py", "scripts/check.py"],
        "trace_required_events": ["ultra-code-review"],
        "trace_reconcile_events": ["ultra-code-review"],
        "allowed_changes": ["app/router.py", "app/result.txt"],
        "validation_runs": {"count": 2, "statuses": ["failed", "completed"]},
    },
    "spec-independent-code-trigger": {
        "artifact_sections": ["Scope", "Security Risks", "Validation Plan"],
        "artifact_sources": ["app/router.py", "docs/adr/ADR-0001.md"],
        "trace_required_events": ["target-native-explore", "ultra-independent-code", "ultra-fresh-review"],
        "trace_reconcile_events": ["target-native-explore", "ultra-independent-code", "ultra-fresh-review"],
    },
    "tickets-review-publication": {
        "artifact_sections": ["Ticket 01", "Blockers", "Review and Publication Evidence"],
        "artifact_sources": ["CONTEXT.md", ".scratch/eval/issues/01-order-routing.md"],
        "trace_required_events": ["target-native-explore", "ultra-complete-set-review"],
        "trace_reconcile_events": ["target-native-explore", "ultra-complete-set-review"],
        "allowed_changes": [
            ".scratch/eval/issues/01-order-routing.md",
            "artifacts/publication-receipt.json",
        ],
        "publication_command": "python3 scripts/publish.py",
    },
    "short-evidence-complete": {
        "artifact_sections": ["Scope", "Current Evidence", "Validation Plan"],
        "artifact_sources": ["APPROVED_EVIDENCE.md", "app/router.py"],
        "max_agent_calls": 0,
    },
    "long-stale-context": {
        "artifact_sections": ["Scope", "Current Code Evidence", "Fresh Review", "Validation Plan"],
        "artifact_sources": ["HISTORY.md", "app/router.py", "docs/adr/ADR-0001.md"],
        "trace_required_events": ["target-native-explore", "ultra-independent-code", "ultra-fresh-review"],
        "trace_reconcile_events": ["target-native-explore", "ultra-independent-code", "ultra-fresh-review"],
    },
    "triage-native-exploration": {
        "artifact_sections": ["Claim", "Repository Evidence", "Triage Decision"],
        "artifact_sources": ["app/router.py", "docs/adr/ADR-0001.md"],
        "trace_required_events": ["target-native-explore"],
        "trace_reconcile_events": ["target-native-explore"],
    },
}


def stage_vocabulary(scenario: dict) -> list[str]:
    """Return names this scenario may truthfully record, not historical forbiddens."""
    return sorted({
        *scenario["events"],
        *scenario.get("event_aliases", {}),
        *scenario.get("recordable_extra_events", []),
    })


def event_owner(name: str) -> str:
    if name.startswith("target-"):
        return "target"
    if name.startswith("ultra-"):
        return "ultra"
    return "root"


def trace_expectations(scenario_id: str, scenario: dict) -> dict:
    authority = SCENARIO_AUTHORITY[scenario_id]
    vocabulary = stage_vocabulary(scenario)
    required_trace_events = authority.get("trace_required_events", [])
    command_calls = [{
        "command": "python3 scripts/check.py",
        "min": authority.get("validation_runs", {}).get("count", 1),
        "max": authority.get("validation_runs", {}).get("count", 1),
        "min_successful": 1,
    }]
    if authority.get("publication_command"):
        command_calls.append({
            "command": authority["publication_command"], "min": 1, "max": 1,
            "min_successful": 1,
        })
    result = {
        "capability_tools": ["Agent"],
        "forbidden_tools": ["Skill"],
        "known_stage_markers": {name: stage_marker(name) for name in vocabulary},
        "require_marker_for_agent_calls": True,
        "required_marker_events": required_trace_events,
        "reconcile_events": authority.get("trace_reconcile_events", []),
        "max_total_agent_calls": authority.get("max_agent_calls"),
        "require_delegated_model": bool(required_trace_events),
        "command_calls": command_calls,
    }
    statuses = authority.get("validation_runs", {}).get("statuses")
    if statuses:
        result["command_sequence"] = [
            {"command": "python3 scripts/check.py", "status": status}
            for status in statuses
        ]
    if scenario_id == "architecture-native-ownership":
        result["extra_exploration_calls"] = {
            "native_markers": [stage_marker("target-native-explore")],
            "extra_markers": [stage_marker("ultra-code-explore")],
            "max": 0,
        }
    return result


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
    authority = SCENARIO_AUTHORITY[scenario_id]
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
    native_marker_events = [
        name for name in authority.get("trace_required_events", [])
        if name.startswith("target-")
    ]
    native_marker_contract = "\n".join(
        f"When delegating native stage `{name}`, include literal marker `{stage_marker(name)}` in its prompt."
        for name in native_marker_events
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

            {native_marker_contract}

            Write the requested artifact, but do not perform a stage owned by Ultra.
            """
        ),
    }
    if authority.get("publication_command"):
        common["scripts/publish.py"] = clean(
            """
            import json
            from pathlib import Path

            receipt = {"adapter": "local-publication", "status": "promoted"}
            path = Path("artifacts/publication-receipt.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(receipt, indent=2) + "\\n", encoding="utf-8")
            """
        )
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

    vocabulary = stage_vocabulary(scenario)
    aliases = scenario.get("event_aliases", {})
    event_owners = {
        aliases.get(name, name): event_owner(aliases.get(name, name))
        for name in vocabulary
    }
    allowed_changes = {
        scenario["artifact"],
        "artifacts/stage-evidence.json",
        *authority.get("allowed_changes", []),
    }
    expectations = {
        "schema_version": 2,
        "scenario": scenario_id,
        "variant": variant,
        "contract_ref": ref,
        "stage_vocabulary": vocabulary,
        "required_events": scenario["events"],
        "recordable_extra_events": scenario.get("recordable_extra_events", []),
        "event_owners": event_owners,
        "artifact": scenario["artifact"],
        "artifact_tokens": scenario["tokens"],
        "artifact_sections": authority["artifact_sections"],
        "artifact_sources": authority["artifact_sources"],
        "expected_result": scenario["result"],
        "expected_tracker_status": scenario["tracker"],
        "allowed_changes": sorted(allowed_changes),
        "contract_hashes": contract_hashes,
        "trace_expectations": trace_expectations(scenario_id, scenario),
        "event_aliases": aliases,
        "ablation_attributable_failure_codes": scenario.get("ablation_attributable_failure_codes", []),
        "ablation_required_difference_codes": scenario.get("ablation_required_difference_codes", []),
    }
    expectations_text = json.dumps(expectations, indent=2) + "\n"
    public_expectations = {
        key: expectations[key]
        for key in (
            "schema_version", "scenario", "variant", "contract_ref",
            "stage_vocabulary", "recordable_extra_events", "artifact",
            "artifact_tokens", "artifact_sections", "artifact_sources",
            "expected_result", "expected_tracker_status", "contract_hashes",
            "event_aliases",
        )
    }
    public_expectations_text = json.dumps(public_expectations, indent=2) + "\n"
    write(repo / "EVAL_EXPECTATIONS.json", public_expectations_text)
    artifact_tokens = ", ".join(f"`{token}`" for token in scenario["tokens"])
    public_stage_vocabulary = vocabulary
    stage_vocabulary_text = ", ".join(f"`{name}`" for name in public_stage_vocabulary)
    artifact_sections = ", ".join(f"`## {name}`" for name in authority["artifact_sections"])
    artifact_sources = ", ".join(f"`{name}`" for name in authority["artifact_sources"])
    covered_additive_instruction = (
        " Record a covered-but-skipped additive goal as `covered-additive-code`."
        if "covered-additive-code" in public_stage_vocabulary
        else ""
    )
    if scenario_id == "diagnosis-feedback-loop-first":
        validation_instruction = (
            "Run `python3 scripts/check.py` before the fix and require a failing exit, then run the exact "
            "command once after the fix and require success. Record the red and green executions in their "
            "actual stages. Runtime command order and immutable final validation are graded."
        )
    else:
        validation_instruction = (
            "Execute `python3 scripts/check.py` exactly once and require a successful exit. "
            "Record that command in the `validation` event evidence. Runtime execution and live repository state are graded; "
            "the primary artifact does not need to repeat the command."
        )
    publication_instruction = ""
    if authority.get("publication_command"):
        publication_instruction = (
            f"Run the supplied publication adapter `{authority['publication_command']}` exactly once and require success. "
            "Its receipt is part of the externally graded final state."
        )
    write(
        repo / "EVAL_PROMPT.md",
        clean(
            f"""
            # End-to-end Ultra profile task

            Execute the contract-only `{scenario['target']}` workflow for this task:

            {scenario['task']}

            Read `skill-input/skills/engineering/ultra/SKILL.md`, `skill-input/skills/engineering/ultra/PROFILES.md`, `TARGET_SKILL.md`, and repository evidence. Treat only those supplied files as the workflow contracts. Do not invoke any slash command or Skill tool, do not use installed/global skills, and do not read `EVAL_EXPECTATIONS.json` or files outside this repository.

            Perform the real file changes required by the task. Write the primary result to `{scenario['artifact']}`; that path is part of the public task contract, not a hidden grader expectation. The artifact must include these case-insensitive mechanical coverage terms: {artifact_tokens}. It must contain substantive Markdown sections {artifact_sections}, with repository evidence cited from these existing paths: {artifact_sources}.

            Mechanical final-state contract: keep `.scratch/eval/issues/01-order-routing.md` at exact status `{scenario['tracker']}`.

            {validation_instruction}

            {publication_instruction}

            As durable execution evidence, write `artifacts/stage-evidence.json` with an `events` array. Append one object per completed stage in actual execution order, each with exactly `name`, `owner`, `goal`, and `evidence`; do not add anticipated or expected stages. Use the applicable names from this scenario-specific stable vocabulary: {stage_vocabulary_text}. When delegating any stage, include exactly one neutral `[eval-stage:<stage-name>]` marker from that vocabulary in the Agent prompt and record the same stage in the ledger. Record the successful validation as `validation`.{covered_additive_instruction} Never record model response prose as evidence.

            Do not run any external grader and do not edit this prompt, `EVAL_EXPECTATIONS.json`, or the supplied skill inputs.
            """
        ),
    )
    run(["git", "init", "-q", "-b", "main"], repo)
    run(["git", "config", "user.name", "Ultra Eval"], repo)
    run(["git", "config", "user.email", "ultra-eval@example.invalid"], repo)
    run(["git", "add", "."], repo)
    run(["git", "commit", "-qm", "prepare equivalent eval fixture"], repo)
    baseline_commit = run(["git", "rev-parse", "HEAD"], repo).strip()
    control = {
        "control_schema_version": 1,
        "baseline_commit": baseline_commit,
        "expectations_sha256": hashlib.sha256(expectations_text.encode()).hexdigest(),
        "workspace_expectations_sha256": hashlib.sha256(
            public_expectations_text.encode()
        ).hexdigest(),
        "expectations": expectations,
    }
    control_path = repo.parent / "control.json"
    write(control_path, json.dumps(control, indent=2) + "\n")
    manifest = {
        "scenario": scenario_id,
        "variant": variant,
        "contract_ref": ref,
        "baseline_commit": baseline_commit,
        "control_sha256": sha256(control_path),
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
