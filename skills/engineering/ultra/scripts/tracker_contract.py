#!/usr/bin/env python3
"""Resolve the shared Ultra tracker index and selected adapter capability."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


INDEX = Path("docs/agents/ultra-tracker.md")
ADAPTER_FIELD = "Configured adapter"
CAPABILITY_FIELD = "Adapter capability document"
LEGACY_FIELDS = (
    "Frontier adapter",
    "Publication strategy",
    "Local Ticket representation",
    "Ticket state fields",
)
LEGACY_LINK = re.compile(r"\]\(([^)\s]+)\)")


class TrackerContractError(RuntimeError):
    """The shared tracker index or selected capability is unsafe to consume."""


@dataclass(frozen=True)
class TrackerDocuments:
    """The common tracker index and the one selected concrete capability."""

    index_path: Path
    index_text: str
    capability_path: Path
    capability_text: str
    configured_adapter: str

    @property
    def effective_text(self) -> str:
        """Return the text that identifies both common and concrete configuration."""
        if self.index_path == self.capability_path:
            return self.index_text
        return f"{self.index_text.rstrip()}\n\n{self.capability_text.lstrip()}"


def exact_value(text: str, field: str) -> str:
    """Read one exact top-level ``Field: value`` declaration."""
    values = re.findall(
        rf"(?m)^{re.escape(field)}:[ \t]*(\S(?:.*\S)?)[ \t]*$", text
    )
    if len(values) != 1:
        raise TrackerContractError(
            f"Tracker contract must define exactly one {field}"
        )
    return values[0].strip().strip("`")


def _read(path: Path, missing: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise TrackerContractError(f"{missing}: {path}") from error


def _resolve_capability(repo: Path, reference: str) -> Path:
    raw = reference.strip().strip("`")
    relative = Path(raw)
    if not raw or relative.is_absolute() or ".." in relative.parts:
        raise TrackerContractError(
            f"adapter capability document must stay inside the repository: {reference}"
        )
    candidate = (repo / relative).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError as error:
        raise TrackerContractError(
            f"adapter capability document must stay inside the repository: {reference}"
        ) from error
    if not candidate.is_file():
        raise TrackerContractError(f"missing adapter capability document: {candidate}")
    return candidate


def _legacy_capability_reference(index_text: str) -> str:
    """Recognize the pre-field Markdown link used by the local development docs."""
    references = [
        reference
        for reference in LEGACY_LINK.findall(index_text)
        if reference.startswith("ultra-tracker/") and reference.endswith(".md")
    ]
    if len(references) > 1:
        raise TrackerContractError(
            "Tracker contract must select one adapter capability document"
        )
    # The legacy link is relative to the index at ``docs/agents/``; normalize
    # it to the repository-root coordinate used by the explicit field.
    return f"docs/agents/{references[0]}" if references else ""


def read(repo: Path) -> TrackerDocuments:
    """Read the common index and resolve its selected capability document.

    Older generated contracts kept all concrete fields in the shared index. They
    remain readable while projects regenerate their managed extension. A new
    index that declares ``Configured adapter`` must also declare an explicit,
    repository-local capability document; a missing selected document therefore
    fails closed instead of falling back to guessed or stale content.
    """
    root = Path(repo).resolve()
    index_path = root / INDEX
    index_text = _read(index_path, "missing Tracker contract")

    adapter_values = re.findall(
        rf"(?m)^{re.escape(ADAPTER_FIELD)}:[ \t]*(\S(?:.*\S)?)[ \t]*$",
        index_text,
    )
    if len(adapter_values) > 1:
        raise TrackerContractError(
            f"Tracker contract must define exactly one {ADAPTER_FIELD}"
        )
    configured_adapter = adapter_values[0].strip().strip("`") if adapter_values else ""

    capability_values = re.findall(
        rf"(?m)^{re.escape(CAPABILITY_FIELD)}:[ \t]*(\S(?:.*\S)?)[ \t]*$",
        index_text,
    )
    if len(capability_values) > 1:
        raise TrackerContractError(
            f"Tracker contract must define exactly one {CAPABILITY_FIELD}"
        )

    if capability_values:
        reference = capability_values[0]
    elif configured_adapter:
        raise TrackerContractError(
            f"Tracker contract must define exactly one {CAPABILITY_FIELD}"
        )
    else:
        reference = _legacy_capability_reference(index_text)

    if reference:
        capability_path = _resolve_capability(root, reference)
        capability_text = _read(
            capability_path, "cannot read adapter capability document"
        )
        if (
            not configured_adapter
            and any(f"{field}:" in index_text for field in LEGACY_FIELDS)
            and not all(f"{field}:" in capability_text for field in LEGACY_FIELDS)
        ):
            # A local development index may already link a prose capability
            # document while its executable fields still live in the legacy
            # index. Keep that transitional format readable until regeneration.
            capability_path = index_path
            capability_text = index_text
    elif any(f"{field}:" in index_text for field in LEGACY_FIELDS):
        # Compatibility for old fixtures and already configured projects. This
        # is only a legacy path; split indexes never take it.
        capability_path = index_path
        capability_text = index_text
    else:
        raise TrackerContractError(
            f"Tracker contract must define one {CAPABILITY_FIELD} or a legacy concrete contract"
        )

    return TrackerDocuments(
        index_path=index_path,
        index_text=index_text,
        capability_path=capability_path,
        capability_text=capability_text,
        configured_adapter=configured_adapter,
    )
