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
        self.env: dict[str, str] | None = None
        self.initial_codex_home_entries: list[str] = []
        self.auth_bridge_present = False
        self.cleanup_succeeded: bool | None = None
        self.cleanup_errors: list[str] = []

    def start(self) -> "PrimaryRuntimeAdapter":
        if self.runtime_root is not None:
            raise RuntimeError("Primary runtime already started")
        self.runtime_root = Path(tempfile.mkdtemp(prefix="primary-eval-runtime-"))
        self.runtime_home = self.runtime_root / "home"
        self.codex_home = self.runtime_root / "codex-home"
        self.runtime_home.mkdir()
        self.codex_home.mkdir()
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
        return self

    def _require_started(self) -> tuple[Path, dict[str, str]]:
        if self.runtime_repo is None or self.env is None:
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
        if self.runtime_root is None:
            return []
        try:
            if self.runtime_repo is not None and (
                self.runtime_repo.exists() or self.runtime_repo.is_symlink()
            ):
                shutil.move(str(self.runtime_repo), self.evidence_repo)
            elif not self.evidence_repo.exists():
                self.cleanup_errors.append("runtime_workspace_restore_failed")
                self.evidence_repo.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.cleanup_errors.append("runtime_workspace_restore_failed")
            self.evidence_repo.mkdir(parents=True, exist_ok=True)

        runtime_root = self.runtime_root
        workspace_root = self.workspace_root
        shutil.rmtree(runtime_root, ignore_errors=True)
        if workspace_root is not None:
            shutil.rmtree(workspace_root, ignore_errors=True)
        if runtime_root.exists():
            self.cleanup_errors.append("runtime_home_cleanup_failed")
        if workspace_root is not None and workspace_root.exists():
            self.cleanup_errors.append("runtime_workspace_cleanup_failed")
        self.cleanup_succeeded = not self.cleanup_errors
        return list(self.cleanup_errors)

    def __enter__(self) -> "PrimaryRuntimeAdapter":
        return self.start()

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.cleanup()
