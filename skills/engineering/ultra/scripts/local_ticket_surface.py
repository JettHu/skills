#!/usr/bin/env python3
"""Canonical Local Markdown Ticket surface grammar shared by setup and runtime."""

from __future__ import annotations

import re


REPRESENTATIONS = {"file-per-ticket", "tickets-file"}
FEATURE_PLACEHOLDER = "<feature>"
TICKET_FILE_COMPONENT = "<ticket-file>.md"


class SurfacePatternError(ValueError):
    """A configured Local Ticket path cannot name one safe durable surface."""


def configured_location_regex(representation: str, raw: str) -> re.Pattern[str]:
    """Compile one canonical contract path into its authorized runtime surface."""
    if representation not in REPRESENTATIONS:
        raise SurfacePatternError(
            f"unsupported Local Ticket representation: {representation}"
        )
    if raw.startswith("/") or "\\" in raw:
        raise SurfacePatternError(
            "configured Local Ticket path must be a relative POSIX path"
        )
    parts = raw.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise SurfacePatternError("configured Local Ticket path is not safely normalized")

    for part in parts:
        if "<" in part or ">" in part:
            if part not in {FEATURE_PLACEHOLDER, TICKET_FILE_COMPONENT}:
                raise SurfacePatternError(
                    f"configured Local Ticket path has an unknown or embedded placeholder: {part}"
                )
    if parts.count(FEATURE_PLACEHOLDER) > 1:
        raise SurfacePatternError(
            "configured Local Ticket path may contain <feature> at most once"
        )

    if representation == "file-per-ticket":
        if parts.count(TICKET_FILE_COMPONENT) != 1 or parts[-1] != TICKET_FILE_COMPONENT:
            raise SurfacePatternError(
                "configured file-per-ticket path must end with exactly one complete <ticket-file>.md component"
            )
        surface_parts = parts[:-1]
    else:
        if TICKET_FILE_COMPONENT in parts:
            raise SurfacePatternError(
                "configured tickets-file path must identify one durable file"
            )
        surface_parts = parts

    if not surface_parts:
        raise SurfacePatternError("configured Local Ticket path has no durable surface")
    pieces = ["[^/]+" if part == FEATURE_PLACEHOLDER else re.escape(part) for part in surface_parts]
    return re.compile(r"\A" + "/".join(pieces) + r"\Z")
