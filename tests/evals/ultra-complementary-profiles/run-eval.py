#!/usr/bin/env python3
"""Prepare, execute, and grade resumable primary/Qoder Ultra profile eval runs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import uuid


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PREPARE = HERE / "prepare-fixture.py"
GRADER = HERE / "grade-run.py"
PAIR_VERDICT = HERE / "pair_verdict.py"
QODER_REQUIRED_AGENTS = ("Explore", "general-purpose")


def write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def next_attempt(root: Path) -> int:
    found = [int(path.name.removeprefix("attempt-")) for path in root.glob("attempt-[0-9][0-9][0-9]")]
    return max(found, default=0) + 1


def probe(args: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "runtime binary not found"
    except OSError as exc:
        return 126, "", f"runtime probe failed: {exc.__class__.__name__}"
    except subprocess.TimeoutExpired:
        return 124, "", "runtime probe timed out"


def qoder_authentication_available(exit_code: int, stdout: str) -> bool:
    """Fail closed unless Qoder's real status protocol says logged_in is true."""
    if exit_code != 0:
        return False
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(payload, dict) and payload.get("logged_in") is True


def qoder_required_agents_available(exit_code: int, stdout: str) -> bool:
    """Fail closed unless the isolated Qoder runtime lists required built-in agents."""
    if exit_code != 0:
        return False
    observed = {
        match.group(1)
        for line in stdout.splitlines()
        if (match := re.match(r"^\s*([A-Za-z0-9_-]+)\s+·\s+", line))
    }
    return set(QODER_REQUIRED_AGENTS) <= observed


def qoder_skill_isolation_clean(exit_code: int, stdout: str) -> bool:
    """Fail closed unless isolated Qoder reports that no skills are discoverable."""
    if exit_code != 0:
        return False
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    return lines == ["No skills discovered."]


def resolve_ref(ref: str) -> str:
    if ref == "working-tree":
        raise SystemExit(
            "model eval runs require committed treatment/ablation refs; "
            "working-tree is prepare-fixture-only"
        )
    value = ref
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{value}^{{commit}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(f"cannot resolve eval ref {ref}: {result.stderr.strip()}")
    return result.stdout.strip()


def classify_canary(
    treatment: dict,
    ablation: dict,
    allowed_ablation_failure_codes: list[str],
    required_ablation_difference_codes: list[str],
) -> dict:
    treatment_grade = treatment.get("grade", {})
    ablation_grade = ablation.get("grade", {})
    treatment_correct = (
        treatment.get("result", {}).get("run_exit_code") == 0
        and treatment_grade.get("repository_grade", {}).get("passed") is True
        and treatment_grade.get("profile_grade", {}).get("passed") is True
    )
    ablation_evidence_valid = (
        ablation.get("result", {}).get("run_exit_code") == 0
        and ablation_grade.get("repository_grade", {}).get("passed") is True
    )
    ablation_failure_codes = ablation_grade.get("profile_grade", {}).get("failure_codes", [])
    attributable_difference = (
        treatment_correct
        and ablation_evidence_valid
        and bool(ablation_failure_codes)
        and set(ablation_failure_codes) <= set(allowed_ablation_failure_codes)
        and set(required_ablation_difference_codes) <= set(ablation_failure_codes)
    )
    if not treatment_correct:
        conclusion = "treatment-invalid"
    elif not ablation_evidence_valid:
        conclusion = "ablation-evidence-invalid"
    elif not ablation_failure_codes:
        conclusion = "no-observed-attributable-difference"
    elif attributable_difference:
        conclusion = "attributable-profile-difference"
    else:
        conclusion = "ablation-non-attributable-profile-failure"
    return {
        "treatment_correct": treatment_correct,
        "ablation_evidence_valid": ablation_evidence_valid,
        "ablation_profile_failure_codes": ablation_failure_codes,
        "allowed_ablation_failure_codes": allowed_ablation_failure_codes,
        "required_ablation_difference_codes": required_ablation_difference_codes,
        "attributable_difference": attributable_difference,
        "conclusion": conclusion,
        "matrix_gate_passed": attributable_difference,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--treatment-ref", required=True)
    parser.add_argument("--ablation-ref", required=True)
    parser.add_argument("--runtime", choices=("primary", "qoder"), default="qoder")
    parser.add_argument("--model", required=True)
    parser.add_argument("--context-window", type=int)
    parser.add_argument("--reasoning-effort")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--qoder-bin", default="qodercli")
    parser.add_argument("--primary-bin", default="codex")
    parser.add_argument("--variant", choices=("both", "treatment", "ablation"), default="both")
    parser.add_argument(
        "--canary-gate",
        action="store_true",
        help="classify a treatment/ablation pair and pass only on an attributable profile difference",
    )
    parser.add_argument(
        "--pair-verdict",
        action="store_true",
        help="write a durable identity-checked verdict for an ordinary treatment/ablation pair",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if args.runtime == "qoder" and args.context_window is None:
        parser.error("--context-window is required for the Qoder runtime")
    variants = ("treatment", "ablation") if args.variant == "both" else (args.variant,)
    if args.canary_gate and args.variant != "both":
        parser.error("--canary-gate requires --variant both")
    if args.pair_verdict and args.variant != "both":
        parser.error("--pair-verdict requires --variant both")
    if args.pair_verdict and args.canary_gate:
        parser.error("use --canary-gate or --pair-verdict, not both")
    ref_shas = {
        "treatment": resolve_ref(args.treatment_ref),
        "ablation": resolve_ref(args.ablation_ref),
    }

    failed = False
    pair_results: dict[str, dict] = {}
    pair_id = uuid.uuid4().hex if len(variants) == 2 else None
    pair_attempt_roots: dict[str, Path] = {}
    for variant in variants:
        variant_root = output / args.run_id / args.scenario / variant
        attempt = next_attempt(variant_root)
        prepare = [
            sys.executable, str(PREPARE), "--output", str(output), "--run-id", args.run_id,
            "--scenario", args.scenario, "--variant", variant, "--attempt", str(attempt),
            "--treatment-ref", ref_shas["treatment"], "--ablation-ref", ref_shas["ablation"],
        ]
        subprocess.run(prepare, check=True)
        attempt_root = variant_root / f"attempt-{attempt:03d}"
        pair_attempt_roots[variant] = attempt_root
        repo = attempt_root / "repo"
        control_path = attempt_root / "control.json"
        control_snapshot = json.loads(control_path.read_text(encoding="utf-8"))
        control_path.unlink()
        prompt = (repo / "EVAL_PROMPT.md").read_text(encoding="utf-8")
        runtime_root = Path(tempfile.mkdtemp(prefix="ultra-eval-runtime-"))
        runtime_config = runtime_root / "config"
        runtime_home = runtime_root / "home"
        runtime_config.mkdir()
        runtime_home.mkdir()
        workspace_root = Path(tempfile.mkdtemp(prefix="agent-workspace-"))
        runtime_repo = workspace_root / f"workspace-{uuid.uuid4().hex[:12]}"
        shutil.move(str(repo), runtime_repo)
        runtime_env = os.environ.copy()
        runtime_env["HOME"] = str(runtime_home)
        runtime_errors: list[dict[str, object]] = []
        qoder_auth = Path.home() / ".qoder" / ".auth"
        if args.runtime == "qoder":
            if qoder_auth.is_dir():
                (runtime_config / ".auth").symlink_to(qoder_auth, target_is_directory=True)
            command = [
                args.qoder_bin, "-p", "--output-format", "stream-json", "--permission-mode",
                "bypass_permissions", "--cwd", str(runtime_repo), "--model", args.model,
                "--context-window", str(args.context_window),
                "--config-dir", str(runtime_config), "--setting-sources", "project",
                "--disable-builtin-skills",
            ]
            if args.reasoning_effort:
                command.extend(["--reasoning-effort", args.reasoning_effort])
            version_command = [args.qoder_bin, "--version"]
            preflight_command = [
                args.qoder_bin, "--config-dir", str(runtime_config),
                "status", "--output", "json",
            ]
            agent_preflight_command = [
                args.qoder_bin, "--config-dir", str(runtime_config),
                "--cwd", str(runtime_repo), "--setting-sources", "project",
                "--disable-builtin-skills", "agents", "list",
            ]
            skill_preflight_command = [
                args.qoder_bin, "--config-dir", str(runtime_config),
                "--cwd", str(runtime_repo), "--setting-sources", "project",
                "--disable-builtin-skills", "skills", "list",
            ]
        else:
            ambient_codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
            ambient_auth = ambient_codex_home / "auth.json"
            if ambient_auth.is_file():
                (runtime_config / "auth.json").symlink_to(ambient_auth)
            runtime_env["CODEX_HOME"] = str(runtime_config)
            command = [
                args.primary_bin, "--ask-for-approval", "never", "exec", "--json",
                "--sandbox", "workspace-write",
                "-C", str(runtime_repo),
                "--model", args.model,
            ]
            if args.reasoning_effort:
                command.extend(["-c", f'model_reasoning_effort="{args.reasoning_effort}"'])
            version_command = [args.primary_bin, "--version"]
            preflight_command = version_command
        command.append(prompt)
        contract_ref = args.treatment_ref if variant == "treatment" else args.ablation_ref
        invocation = {
            "argv": command,
            "shell": shlex.join(command),
            "cwd": str(runtime_repo),
            "evidence_repo": str(repo),
            "runtime": args.runtime,
            "runtime_version": None,
            "run_id": args.run_id,
            "pair_id": pair_id,
            "scenario": args.scenario,
            "variant": variant,
            "model": args.model,
            "context_window": args.context_window,
            "reasoning_effort": args.reasoning_effort or "default",
            "timeout_seconds": args.timeout,
            "runtime_isolation": {
                "contract_only_prompt": True,
                "slash_and_skill_invocation_forbidden": True,
                "global_skill_use_trace_graded": True,
                "ephemeral_user_config": True,
                "user_and_local_setting_sources_disabled": args.runtime == "qoder",
                "builtin_skills_disabled": args.runtime == "qoder",
                "ambient_home_isolated": True,
                "qoder_auth_bridge_only": args.runtime == "qoder",
                "qoder_auth_bridge_present": args.runtime == "qoder" and (runtime_config / ".auth").is_symlink(),
                "initial_runtime_config_entries": sorted(path.name for path in runtime_config.iterdir()),
                "neutral_opaque_cwd": True,
                **({
                    "primary_session_persistence": "temporary-codex-home",
                    "temporary_codex_home": str(runtime_config),
                    "primary_session_store_removed": None,
                } if args.runtime == "primary" else {}),
            },
            "authority": {
                "baseline_commit": control_snapshot["baseline_commit"],
                "expectations_sha256": control_snapshot["expectations_sha256"],
                "workspace_expectations_sha256": control_snapshot[
                    "workspace_expectations_sha256"
                ],
                "snapshotted_before_model_run": True,
            },
            "refs": {
                "treatment": {"requested": args.treatment_ref, "sha": ref_shas["treatment"]},
                "ablation": {"requested": args.ablation_ref, "sha": ref_shas["ablation"]},
                "selected_contract": {"requested": contract_ref, "sha": ref_shas[variant]},
            },
            "started_at": datetime.now(timezone.utc).isoformat(),
            "preflight": {"authentication_available": None, "exit_code": None},
            "errors": runtime_errors,
        }
        write(attempt_root / "invocation.json", json.dumps(invocation, indent=2) + "\n")
        timed_out = False
        run_exit = 125
        stdout = ""
        stderr = ""
        try:
            version_exit, version_stdout, version_stderr = probe(version_command, runtime_env)
            version_text = (version_stdout or version_stderr).strip()
            if version_exit == 0 and version_text:
                invocation["runtime_version"] = version_text.splitlines()[0]
            else:
                runtime_errors.append({"phase": "version", "code": "runtime_version_failed", "exit_code": version_exit})
            if not runtime_errors:
                preflight_exit, preflight_stdout, _ = probe(preflight_command, runtime_env)
                authentication_available = (
                    qoder_authentication_available(preflight_exit, preflight_stdout)
                    if args.runtime == "qoder"
                    else None
                )
                invocation["preflight"] = {
                    "authentication_available": authentication_available,
                    "exit_code": preflight_exit,
                    "protocol_field": "logged_in" if args.runtime == "qoder" else None,
                }
                if preflight_exit != 0 or authentication_available is False:
                    runtime_errors.append({"phase": "preflight", "code": "runtime_preflight_failed", "exit_code": preflight_exit})
                elif args.runtime == "qoder":
                    agent_exit, agent_stdout, _ = probe(agent_preflight_command, runtime_env)
                    skill_exit, skill_stdout, _ = probe(skill_preflight_command, runtime_env)
                    agent_capability_available = qoder_required_agents_available(
                        agent_exit, agent_stdout
                    )
                    skill_isolation_clean = qoder_skill_isolation_clean(
                        skill_exit, skill_stdout
                    )
                    invocation["preflight"].update({
                        "required_agents": list(QODER_REQUIRED_AGENTS),
                        "agent_capability_available": agent_capability_available,
                        "agent_probe_exit_code": agent_exit,
                        "skill_isolation_clean": skill_isolation_clean,
                        "skill_probe_exit_code": skill_exit,
                    })
                    if not agent_capability_available:
                        runtime_errors.append({
                            "phase": "preflight",
                            "code": "qoder_agent_capability_failed",
                            "exit_code": agent_exit,
                        })
                    if not skill_isolation_clean:
                        runtime_errors.append({
                            "phase": "preflight",
                            "code": "qoder_skill_isolation_failed",
                            "exit_code": skill_exit,
                        })
            if not runtime_errors:
                result = subprocess.run(
                    command, cwd=runtime_repo, env=runtime_env, text=True, capture_output=True,
                    timeout=args.timeout,
                )
                run_exit = result.returncode
                stdout, stderr = result.stdout, result.stderr
                if run_exit != 0:
                    runtime_errors.append({"phase": "execution", "code": "runtime_exit_nonzero", "exit_code": run_exit})
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            run_exit = 124
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            runtime_errors.append({"phase": "execution", "code": "runtime_timeout", "exit_code": 124})
        except (FileNotFoundError, OSError) as exc:
            run_exit = 127 if isinstance(exc, FileNotFoundError) else 126
            runtime_errors.append({"phase": "execution", "code": "runtime_binary_unavailable", "exit_code": run_exit})
        finally:
            try:
                if runtime_repo.exists() or runtime_repo.is_symlink():
                    shutil.move(str(runtime_repo), repo)
            except OSError:
                runtime_errors.append({"phase": "cleanup", "code": "runtime_workspace_restore_failed"})
                repo.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(runtime_root, ignore_errors=True)
            shutil.rmtree(workspace_root, ignore_errors=True)
            if args.runtime == "primary":
                invocation["runtime_isolation"]["primary_session_store_removed"] = (
                    not runtime_config.exists()
                )
        write(attempt_root / "raw-stdout.log", stdout)
        write(attempt_root / "raw-stderr.log", stderr)
        if runtime_errors:
            write(attempt_root / "error.json", json.dumps({"errors": runtime_errors}, indent=2) + "\n")
        grader_control = attempt_root / "grader-control.json"
        write(grader_control, json.dumps(control_snapshot, indent=2) + "\n")
        grade = subprocess.run(
            [
                sys.executable, str(GRADER), str(repo),
                "--control", str(grader_control),
                "--trace", str(attempt_root / "raw-stdout.log"), "--json",
            ],
            text=True,
            capture_output=True,
        )
        write(attempt_root / "grader-stdout.json", grade.stdout)
        write(attempt_root / "grader-stderr.log", grade.stderr)
        try:
            grade_payload = json.loads(grade.stdout)
            grade_result = grade_payload[0]
            invocation["observed_trace"] = grade_result.get("trace")
        except (json.JSONDecodeError, IndexError, AttributeError):
            grade_result = {}
            invocation["observed_trace"] = None
        invocation["finished_at"] = datetime.now(timezone.utc).isoformat()
        write(attempt_root / "invocation.json", json.dumps(invocation, indent=2) + "\n")
        result_record = {
            "variant": variant,
            "attempt": attempt,
            "run_exit_code": run_exit,
            "timed_out": timed_out,
            "error_codes": [str(error["code"]) for error in runtime_errors],
            "grader_exit_code": grade.returncode,
            "final_state_passed": grade_result.get("final_state_grade", {}).get("passed", False),
            "repository_passed": grade_result.get("repository_grade", {}).get("passed", False),
            "profile_passed": grade_result.get("profile_grade", {}).get("passed", False),
            "trace_passed": grade_result.get("trace_grade", {}).get("passed", False),
            "passed": not runtime_errors and run_exit == 0 and grade.returncode == 0,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "recovery": f"rerun the same command; a new attempt directory will be created after attempt-{attempt:03d}",
        }
        write(attempt_root / "result.json", json.dumps(result_record, indent=2) + "\n")
        print(json.dumps(result_record))
        pair_results[variant] = {"result": result_record, "grade": grade_result}
        failed = failed or not result_record["passed"]
    if args.pair_verdict:
        verdict_result = subprocess.run(
            [
                sys.executable, str(PAIR_VERDICT),
                "--treatment-attempt", str(pair_attempt_roots["treatment"]),
                "--ablation-attempt", str(pair_attempt_roots["ablation"]),
                "--output", str(output / args.run_id / args.scenario),
            ],
            text=True,
            capture_output=True,
        )
        if verdict_result.returncode:
            print(verdict_result.stderr or verdict_result.stdout, file=sys.stderr, end="")
            failed = True
        else:
            print(json.dumps({"pair_verdict": verdict_result.stdout.strip()}))
    if args.canary_gate:
        treatment_attempt_root = (
            output / args.run_id / args.scenario / "treatment"
            / f"attempt-{pair_results['treatment']['result']['attempt']:03d}"
        )
        control = json.loads((treatment_attempt_root / "grader-control.json").read_text(encoding="utf-8"))
        expectations = control["expectations"]
        verdict = classify_canary(
            pair_results["treatment"],
            pair_results["ablation"],
            expectations.get("ablation_attributable_failure_codes", []),
            expectations.get("ablation_required_difference_codes", []),
        )
        verdict.update(
            {
                "scenario": args.scenario,
                "pair_id": pair_id,
                "treatment_attempt": pair_results["treatment"]["result"]["attempt"],
                "ablation_attempt": pair_results["ablation"]["result"]["attempt"],
            }
        )
        verdict_name = (
            f"canary-verdict-treatment-{verdict['treatment_attempt']:03d}"
            f"-ablation-{verdict['ablation_attempt']:03d}.json"
        )
        verdict["verdict_file"] = verdict_name
        write(output / args.run_id / args.scenario / verdict_name, json.dumps(verdict, indent=2) + "\n")
        print(json.dumps(verdict))
        failed = not verdict["matrix_gate_passed"]
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
