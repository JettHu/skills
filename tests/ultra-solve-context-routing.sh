#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$ROOT" <<'PY'
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile


root = Path(sys.argv[1])
producer = (root / "skills/engineering/ultra/references/ticket-review-publication.md").read_text(
    encoding="utf-8"
)
solve = (root / "skills/engineering/ultra/solve.md").read_text(encoding="utf-8")
core = (root / "skills/engineering/ultra/SKILL.md").read_text(encoding="utf-8")
wrapper = (root / "skills/engineering/ultra-to-tickets/SKILL.md").read_text(
    encoding="utf-8"
)

for predicate in (
    "## Context Pointer Contract",
    "`to-tickets` is the sole producer",
    "write one optional compact",
    "`## Context` section",
    "`Source Spec`",
    "`Decisions`",
    "`Domain Context`",
    "source branch/ref",
    "why it matters",
    "nonessential",
    "`to-tickets` must\nnot guess, replace, or broaden",
):
    assert predicate in producer, f"context-pointer producer contract missing: {predicate}"

assert "Context Pointer Contract" in core, "core must route to-tickets through its producer contract"
assert "Context Pointer Contract" not in wrapper, "thin wrapper must not own a second context workflow"

for predicate in (
    "### Bootstrap: Design Context and Risk Routing",
    "runtime-injected `AGENTS.md` is already active guidance",
    "selected Ticket",
    "live Claim/discovery snapshot",
    "authoritative Ticket pointers",
    "context_pointer_missing_authoritative",
    "context_pointer_ref_unavailable_authoritative",
    "context_pointer_ambiguous_authoritative",
    "context_pointer_unavailable_nonessential",
    "one targeted fallback lookup",
    "does not scan all ADRs, all context files, or unrelated `.scratch` content",
    "state, permission, data, concurrency, migration, recovery, and cross-repository coupling",
    "target-native evidence is the sole owner",
    "at most one distinct bounded independent evidence pass",
):
    assert predicate in solve, f"context-pointer consumer contract missing: {predicate}"


@dataclass(frozen=True)
class Pointer:
    label: str
    path: str
    ref: str
    authoritative: bool
    reason: str


def render_context(pointers: list[Pointer]) -> str:
    if not pointers:
        return ""
    lines = ["## Context", ""]
    for pointer in pointers:
        classification = "authoritative" if pointer.authoritative else "nonessential"
        lines.append(
            f"- {pointer.label} ({classification}; ref: `{pointer.ref}`): "
            f"`{pointer.path}` — {pointer.reason}"
        )
    return "\n".join(lines) + "\n"


def bootstrap(ticket_context: str, refs: dict[str, Path]) -> tuple[bool, list[str]]:
    diagnostics = []
    for line in ticket_context.splitlines():
        if not line.startswith("- "):
            continue
        _, descriptor = line[2:].split(" (", 1)
        classification, remainder = descriptor.split("; ref: `", 1)
        ref, remainder = remainder.split("`): `", 1)
        path, _reason = remainder.split("` — ", 1)
        authoritative = classification == "authoritative"
        source_root = refs.get(ref)
        if source_root is None:
            diagnostics.append(
                "context_pointer_ref_unavailable_authoritative"
                if authoritative
                else "context_pointer_unavailable_nonessential"
            )
            continue
        if any(marker in path for marker in ("*", "?", "[")):
            diagnostics.append(
                "context_pointer_ambiguous_authoritative"
                if authoritative
                else "context_pointer_unavailable_nonessential"
            )
            continue
        matches = list(source_root.glob(path))
        if len(matches) == 1:
            continue
        if authoritative:
            diagnostics.append(
                "context_pointer_missing_authoritative"
                if not matches
                else "context_pointer_ambiguous_authoritative"
            )
        else:
            diagnostics.append("context_pointer_unavailable_nonessential")
    return not any(item.endswith("authoritative") for item in diagnostics), diagnostics


with tempfile.TemporaryDirectory() as temporary:
    fixture = Path(temporary)
    selected_ref = fixture / "refs/eval-base"
    (selected_ref / "docs/adr").mkdir(parents=True)
    (selected_ref / "spec.md").write_text("# Accepted behavior\n", encoding="utf-8")
    (selected_ref / "CONTEXT.md").write_text("# Domain context\n", encoding="utf-8")
    (selected_ref / "docs/adr/0042.md").write_text("# Decision\n", encoding="utf-8")
    refs = {"eval-base": selected_ref}
    current_checkout = fixture / "current"
    (current_checkout / "docs/prd").mkdir(parents=True)
    (current_checkout / "docs/prd/missing.md").write_text(
        "# Stale current-HEAD document\n", encoding="utf-8"
    )

    # The producer's rendered Context is the exact input consumed by Bootstrap.
    generated_ticket = render_context(
        [
            Pointer("Source Spec", "spec.md", "eval-base", True, "defines accepted behavior and validation"),
            Pointer("Decisions", "docs/adr/0042.md", "eval-base", True, "fixes the concurrency boundary"),
            Pointer("Domain Context", "CONTEXT.md", "eval-base", False, "names changed domain vocabulary"),
        ]
    )
    assert "Source Spec (authoritative; ref: `eval-base`)" in generated_ticket
    assert "Decisions (authoritative; ref: `eval-base`)" in generated_ticket
    assert "Domain Context (nonessential; ref: `eval-base`)" in generated_ticket
    assert generated_ticket.count("ref: `eval-base`") == 3
    assert generated_ticket.count(" — ") == 3
    # Resolve from the declared ref, not the executor's current checkout.
    assert bootstrap(generated_ticket, refs) == (True, [])

    # No selected extra context is valid; an omitted section is not a blocker.
    assert bootstrap(render_context([]), refs) == (True, [])

    # A path present only in the executor's current checkout is still missing at
    # the declared ref; authoritative missing and ambiguous pointers fail closed.
    assert bootstrap(
        render_context([Pointer("Source Spec", "docs/prd/missing.md", "eval-base", True, "defines behavior")]),
        refs,
    ) == (
        False,
        ["context_pointer_missing_authoritative"],
    )
    assert bootstrap(
        render_context([Pointer("Decisions", "docs/adr/0042*.md", "eval-base", True, "fixes boundary")]),
        refs,
    ) == (
        False,
        ["context_pointer_ambiguous_authoritative"],
    )

    # An unavailable nonessential pointer is visible but never blocks or substitutes another source.
    assert bootstrap(
        render_context([Pointer("Domain Context", "docs/context-map.md", "eval-base", False, "optional vocabulary")]),
        refs,
    ) == (
        True,
        ["context_pointer_unavailable_nonessential"],
    )
    assert bootstrap(generated_ticket, {}) == (
        False,
        [
            "context_pointer_ref_unavailable_authoritative",
            "context_pointer_ref_unavailable_authoritative",
            "context_pointer_unavailable_nonessential",
        ],
    )


def independent_passes(*, native_covers_goal: bool, high_risk: bool) -> int:
    if native_covers_goal:
        return 0
    return 1 if high_risk else 0


assert independent_passes(native_covers_goal=True, high_risk=True) == 0
assert independent_passes(native_covers_goal=False, high_risk=True) == 1
assert independent_passes(native_covers_goal=False, high_risk=False) == 0

print("ultra solve context-routing fixture passed")
PY
