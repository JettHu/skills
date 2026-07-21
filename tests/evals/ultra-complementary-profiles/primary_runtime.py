#!/usr/bin/env python3
"""Shared isolated Codex CLI runtime adapter for Primary eval entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid


@dataclass(frozen=True)
class ProcessEvidence:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    error_code: str | None = None


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


class PrimaryRuntimeAdapter:
    """Own the exact disposable environment used by a Primary model attempt."""

    def __init__(
        self,
        *,
        evidence_repo: Path,
        primary_bin: str,
        model: str,
        reasoning_effort: str | None,
        timeout: int,
        ambient_env: dict[str, str] | None = None,
    ) -> None:
        self.evidence_repo = evidence_repo
        self.primary_bin = primary_bin
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.timeout = timeout
        self.ambient_env = dict(ambient_env or os.environ)
        self.runtime_root: Path | None = None
        self.runtime_home: Path | None = None
        self.codex_home: Path | None = None
        self.workspace_root: Path | None = None
        self.runtime_repo: Path | None = None
        self.backup_repo: Path | None = None
        self.env: dict[str, str] | None = None
        self.initial_codex_home_entries: list[str] = []
        self.auth_bridge_present = False
        self.cleanup_succeeded: bool | None = None
        self.cleanup_errors: list[str] = []
        self.started = False
        self.start_error_code: str | None = None
        self.start_error_detail: str | None = None
        self.preserved_workspace_path: str | None = None
        self.preserved_baseline_path: str | None = None
        self._cleanup_complete = False

    def start(self) -> "PrimaryRuntimeAdapter":
        if self.runtime_root is not None:
            raise RuntimeError("Primary runtime already started")
        try:
            self.runtime_root = Path(tempfile.mkdtemp(prefix="primary-eval-runtime-"))
            self.runtime_home = self.runtime_root / "home"
            self.codex_home = self.runtime_root / "codex-home"
            self.runtime_home.mkdir()
            self.codex_home.mkdir()
            self.backup_repo = self.runtime_root / "evaluator-owned-repo-backup"
            shutil.copytree(self.evidence_repo, self.backup_repo, symlinks=True)
            self.workspace_root = Path(tempfile.mkdtemp(prefix="agent-workspace-"))
            self.runtime_repo = self.workspace_root / f"workspace-{uuid.uuid4().hex[:12]}"
            shutil.move(str(self.evidence_repo), self.runtime_repo)

            ambient_home = Path(self.ambient_env.get("HOME", str(Path.home())))
            ambient_codex_home = Path(
                self.ambient_env.get("CODEX_HOME", str(ambient_home / ".codex"))
            )
            ambient_auth = ambient_codex_home / "auth.json"
            if ambient_auth.is_file():
                (self.codex_home / "auth.json").symlink_to(ambient_auth)
                self.auth_bridge_present = True
            self.initial_codex_home_entries = sorted(
                path.name for path in self.codex_home.iterdir()
            )
            self.env = self.ambient_env.copy()
            self.env["HOME"] = str(self.runtime_home)
            self.env["CODEX_HOME"] = str(self.codex_home)
            self.started = True
        except (OSError, shutil.Error) as exc:
            self.start_error_code = "primary_runtime_start_failed"
            self.start_error_detail = exc.__class__.__name__
            self.cleanup()
        return self

    def _require_started(self) -> tuple[Path, dict[str, str]]:
        if not self.started or self.runtime_repo is None or self.env is None:
            raise RuntimeError("Primary runtime is not started")
        return self.runtime_repo, self.env

    def version_command(self) -> list[str]:
        return [self.primary_bin, "--version"]

    def feature_command(self) -> list[str]:
        return [self.primary_bin, "features", "list"]

    def command(self, prompt: str) -> list[str]:
        runtime_repo, _ = self._require_started()
        command = [
            self.primary_bin,
            "--ask-for-approval",
            "never",
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "-C",
            str(runtime_repo),
            "--model",
            self.model,
        ]
        if self.reasoning_effort:
            command.extend(
                ["-c", f'model_reasoning_effort="{self.reasoning_effort}"']
            )
        command.append(prompt)
        return command

    def probe(self, command: list[str], timeout: int = 30) -> ProcessEvidence:
        runtime_repo, env = self._require_started()
        try:
            result = subprocess.run(
                command,
                cwd=runtime_repo,
                env=env,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
            return ProcessEvidence(result.returncode, result.stdout, result.stderr)
        except FileNotFoundError:
            return ProcessEvidence(127, "", "runtime binary not found", error_code="runtime_binary_unavailable")
        except OSError as exc:
            return ProcessEvidence(
                126,
                "",
                f"runtime probe failed: {exc.__class__.__name__}",
                error_code="runtime_binary_unavailable",
            )
        except subprocess.TimeoutExpired as exc:
            return ProcessEvidence(
                124,
                _text(exc.stdout),
                _text(exc.stderr),
                timed_out=True,
                error_code="runtime_timeout",
            )

    def execute(
        self,
        prompt: str,
        *,
        stdout_path: Path,
        stderr_path: Path,
    ) -> ProcessEvidence:
        evidence = self.probe(self.command(prompt), timeout=self.timeout)
        stdout_path.write_text(evidence.stdout, encoding="utf-8")
        stderr_path.write_text(evidence.stderr, encoding="utf-8")
        return evidence

    def cleanup(self) -> list[str]:
        if self._cleanup_complete:
            return list(self.cleanup_errors)
        self._cleanup_complete = True

        normal_restore_succeeded = False
        runtime_repo_exists = self.runtime_repo is not None and (
            self.runtime_repo.exists() or self.runtime_repo.is_symlink()
        )
        if runtime_repo_exists:
            try:
                if self.evidence_repo.exists() or self.evidence_repo.is_symlink():
                    raise FileExistsError(str(self.evidence_repo))
                shutil.move(str(self.runtime_repo), self.evidence_repo)
                runtime_repo_exists = False
                normal_restore_succeeded = True
            except (OSError, shutil.Error):
                self.cleanup_errors.append("runtime_workspace_restore_failed")
                recovery_repo = self.evidence_repo.with_name(
                    self.evidence_repo.name + "-runtime-recovery"
                )
                try:
                    if recovery_repo.exists() or recovery_repo.is_symlink():
                        raise FileExistsError(str(recovery_repo))
                    shutil.move(str(self.runtime_repo), recovery_repo)
                    self.preserved_workspace_path = str(recovery_repo)
                    runtime_repo_exists = False
                except (OSError, shutil.Error):
                    self.preserved_workspace_path = str(self.runtime_repo)
        elif self.runtime_repo is not None and self.started:
            self.cleanup_errors.append("runtime_workspace_restore_failed")

        if self.backup_repo is not None and self.backup_repo.exists():
            if normal_restore_succeeded:
                shutil.rmtree(self.backup_repo, ignore_errors=True)
            elif not self.evidence_repo.exists():
                try:
                    shutil.copytree(self.backup_repo, self.evidence_repo, symlinks=True)
                    shutil.rmtree(self.backup_repo, ignore_errors=True)
                except (OSError, shutil.Error):
                    self.cleanup_errors.append("runtime_evidence_backup_restore_failed")
            elif self.runtime_repo is None or not self.started:
                shutil.rmtree(self.backup_repo, ignore_errors=True)
            else:
                baseline_recovery = self.evidence_repo.with_name(
                    self.evidence_repo.name + "-baseline-recovery"
                )
                try:
                    if baseline_recovery.exists() or baseline_recovery.is_symlink():
                        raise FileExistsError(str(baseline_recovery))
                    shutil.move(str(self.backup_repo), baseline_recovery)
                    self.preserved_baseline_path = str(baseline_recovery)
                except (OSError, shutil.Error):
                    self.cleanup_errors.append("runtime_evidence_backup_restore_failed")
                    self.preserved_baseline_path = str(self.backup_repo)

        runtime_root = self.runtime_root
        workspace_root = self.workspace_root
        if runtime_root is not None:
            preserve_runtime_root = self.backup_repo is not None and self.backup_repo.exists()
            if preserve_runtime_root:
                if self.runtime_home is not None:
                    shutil.rmtree(self.runtime_home, ignore_errors=True)
                if self.codex_home is not None:
                    shutil.rmtree(self.codex_home, ignore_errors=True)
            else:
                shutil.rmtree(runtime_root, ignore_errors=True)
            if runtime_root.exists():
                self.cleanup_errors.append("runtime_home_cleanup_failed")
        if workspace_root is not None and not runtime_repo_exists:
            shutil.rmtree(workspace_root, ignore_errors=True)
        if workspace_root is not None and workspace_root.exists():
            self.cleanup_errors.append("runtime_workspace_cleanup_failed")
            if self.preserved_workspace_path is None and self.runtime_repo is not None:
                self.preserved_workspace_path = str(self.runtime_repo)
        self.started = False
        self.cleanup_succeeded = not self.cleanup_errors
        return list(self.cleanup_errors)

    def __enter__(self) -> "PrimaryRuntimeAdapter":
        return self.start()

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.cleanup()
