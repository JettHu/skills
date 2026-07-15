#!/usr/bin/env python3
"""Render and apply the managed Ultra tracker extension."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from local_ticket_surface import SurfacePatternError, configured_location_regex


BASE_CONTRACT = Path("docs/agents/issue-tracker.md")
EXTENSION_CONTRACT = Path("docs/agents/ultra-tracker.md")
STAGING_ROOT = ".scratch/.ultra-staging/"
CANCELLATION_POLICIES = {
    "retain-until-explicit-cleanup": "retain the named review-pending run until explicit cleanup.",
    "delete-on-cancel": "delete only the named review-pending run after exact membership and preimage validation.",
}
BLOCK_START = "<!-- setup-ultra-skills:begin -->"
BLOCK_END = "<!-- setup-ultra-skills:end -->"
PUBLICATION_FIELDS = (
    "Draft or review-pending representation:",
    "Review update operation:",
    "Publish or promote operation:",
    "Partial-publish recovery:",
)
COORDINATION_FIELDS = (
    "Claim and release:",
    "State mapping:",
    "Blocker and frontier lookup:",
    "Branch/worktree/PR links:",
    "Solve Record backlinks:",
    "Unsupported operations:",
)
CUSTOM_FIELDS = PUBLICATION_FIELDS + COORDINATION_FIELDS


class ConfigurationError(ValueError):
    """A setup input cannot produce a safe managed extension."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render or apply the Ultra tracker extension."
    )
    parser.add_argument("--repo", default=".", help="Repository root.")
    parser.add_argument(
        "--preset",
        required=True,
        choices=("github", "gitlab", "local-markdown", "other"),
        help="Tracker family established by the base contract.",
    )
    parser.add_argument(
        "--publication-strategy",
        required=True,
        choices=("remote-review-pending", "local-review-pending", "local-staging", "custom"),
        help="Durable review-publication policy.",
    )
    parser.add_argument(
        "--instructions",
        required=True,
        help="Existing AGENTS.md or CLAUDE.md path relative to the repository.",
    )
    parser.add_argument(
        "--review-pending-marker",
        default="review-pending",
        help="Remote label or project-status marker for provisional Tickets.",
    )
    parser.add_argument(
        "--publication-marker-prefix",
        default="ultra-publication-set",
        help="Stable body-comment prefix for one remote publication run.",
    )
    parser.add_argument(
        "--cancellation-policy",
        choices=tuple(CANCELLATION_POLICIES),
        default="retain-until-explicit-cleanup",
        help="Executable Local Markdown cancellation policy.",
    )
    parser.add_argument(
        "--local-ticket-representation",
        choices=("file-per-ticket", "tickets-file"),
        default="file-per-ticket",
        help="Configured Local Markdown storage representation.",
    )
    parser.add_argument(
        "--local-ticket-path",
        help="Configured Local Markdown directory pattern or tickets-file path.",
    )
    parser.add_argument(
        "--custom-prose",
        help="Required backend policy prose for the other preset.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the rendered contract and managed instruction block.",
    )
    return parser.parse_args()


def require_single_line(value: str, label: str) -> str:
    if not value.strip() or "\n" in value or "\r" in value:
        raise ConfigurationError(f"{label} must be one non-empty line")
    return value.strip()


def resolve_inside(repo: Path, relative_path: str, label: str) -> Path:
    candidate = (repo / relative_path).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError as error:
        raise ConfigurationError(f"{label} must stay inside the repository") from error
    return candidate


def validate_policy(args: argparse.Namespace) -> None:
    allowed = {
        "local-markdown": {"local-review-pending"},
        "github": {"remote-review-pending", "local-staging"},
        "gitlab": {"remote-review-pending", "local-staging"},
        "other": {"custom"},
    }
    if args.publication_strategy not in allowed[args.preset]:
        choices = ", ".join(sorted(allowed[args.preset]))
        raise ConfigurationError(
            f"{args.preset} supports {choices}, not {args.publication_strategy}"
        )
    args.review_pending_marker = require_single_line(
        args.review_pending_marker, "review-pending marker"
    )
    args.publication_marker_prefix = require_single_line(
        args.publication_marker_prefix, "publication marker prefix"
    )
    if args.preset == "local-markdown":
        default_path = (
            ".scratch/<feature>/issues/<ticket-file>.md"
            if args.local_ticket_representation == "file-per-ticket"
            else ".scratch/<feature>/tickets.md"
        )
        args.local_ticket_path = require_single_line(
            args.local_ticket_path or default_path, "local Ticket path"
        )
        try:
            configured_location_regex(
                args.local_ticket_representation, args.local_ticket_path
            )
        except SurfacePatternError as error:
            raise ConfigurationError(str(error)) from error
    elif args.cancellation_policy != "retain-until-explicit-cleanup":
        raise ConfigurationError(
            "--cancellation-policy applies only to the local-markdown preset"
        )
    if args.preset == "other":
        if not (args.custom_prose and args.custom_prose.strip()):
            raise ConfigurationError("the other preset requires --custom-prose")
        args.custom_policy = parse_custom_policy(args.custom_prose)


def parse_custom_policy(custom_prose: str) -> dict[str, str]:
    policy = {}
    for field in CUSTOM_FIELDS:
        matches = re.findall(
            rf"(?m)^{re.escape(field)}[ \t]*(\S.*)$", custom_prose
        )
        if not matches:
            raise ConfigurationError(f"custom policy is missing {field}")
        if len(matches) > 1:
            raise ConfigurationError(f"custom policy defines {field} more than once")
        policy[field] = matches[0].strip()
    return policy


def remote_publication(marker: str, run_prefix: str) -> list[str]:
    return [
        "## Ticket Review Publication",
        "",
        "Publication strategy: remote-review-pending",
        f"Draft or review-pending representation: remote Tickets carry `{marker}` until promotion.",
        f"Publication-set identity: every provisional Ticket body carries `<!-- {run_prefix}:<run-id> -->`.",
        "Review update operation: locate the publication-set marker, re-read the matching remote Ticket, and update that same artifact in place.",
        "Publish or promote operation: create missing members, wire parent and blocking links, verify bodies and links, then replace the provisional marker with the base-contract ready state for the complete set.",
        "Partial-publish recovery: retain the run id and remote IDs; a later attempt re-discovers members by the body marker, creates only missing members, re-verifies links, and promotes only the complete set.",
        "",
    ]


def staging_publication() -> list[str]:
    return [
        "## Ticket Review Publication",
        "",
        "Publication strategy: local-staging",
        f"Draft or review-pending representation: ignored drafts live under `{STAGING_ROOT}<run-id>/tickets.md`; `manifest.json` records title keys, remote IDs, relationships, and promotion status.",
        "Review update operation: review and revise the durable local draft before remote creation.",
        "Publish or promote operation: create unready remote Tickets, record their IDs in the manifest, wire and re-read every relationship, then apply the base-contract ready state and verify promotion.",
        "Partial-publish recovery: retain the draft and manifest until every remote body, relationship, and ready state has been re-read; resume from recorded IDs and pending manifest entries without creating duplicates.",
        "Ticket discovery exclusion: skip `.scratch/.ultra-staging/` during Ticket discovery and frontier scans.",
        "",
    ]


def local_publication(
    cancellation_policy: str, representation: str, ticket_path: str
) -> list[str]:
    lines = [
        "## Ticket Review Publication",
        "",
        "Publication strategy: local-review-pending",
        f"Local Ticket representation: {representation}",
        f"Local Ticket path: {ticket_path}",
        "Stable identity: every formal Ticket carries unique `Ticket ID` and `Publication Run` metadata.",
        "Draft or review-pending representation: formal Tickets are created at the configured path with `Status: review-pending`; they are the sole source of Ticket content.",
    ]
    if representation == "tickets-file":
        lines.append(
            "Tickets-file section boundary: each Ticket is enclosed by `<!-- ultra-ticket:begin id=<Ticket-ID> -->` and `<!-- ultra-ticket:end -->`; heading- or title-based identity is unsafe."
        )
    lines.extend(
        [
            "Publication journal: `.ultra-publications/<run-id>.json` beside the configured surface records only complete-set membership, reviewed body digests, representation, location, and phase; it is not a Ticket draft.",
            "Publication operation `register`: stage=after formal draft creation and after every semantic repair; inputs=repository, configured representation/location, run ID, and explicit membership-change authorization when needed; success evidence=review-pending phase plus exact member IDs and body digests; errors=structured fail-closed refusal with no Ticket mutation; resume=re-run after repairing the reported contract or artifact; manual fallback=prohibited.",
            "Publication operation `inspect`: stage=review and recovery diagnosis; inputs=repository, configured representation/location, and run ID; success evidence=phase, exact members, and canonical statuses; errors=structured fail-closed refusal with no mutation; resume=repair the reported contract or artifact and re-run; manual fallback=prohibited.",
            "Publication operation `promote`: stage=only after semantic review passes; inputs=repository, configured representation/location, and registered run ID; success evidence=promoted phase after complete-set re-verification; errors=structured fail-closed refusal retaining resumable state; resume=re-run the same operation after resolving the reported error; manual fallback=prohibited.",
            "Publication operation `cleanup`: stage=cancelled review-pending run only; inputs=repository, configured representation/location, run ID, and explicit authorization when policy requires it; success evidence=exact cleaned member IDs; errors=structured fail-closed refusal with retained artifacts; resume=repair policy/artifact mismatch or resume promotion as reported; manual fallback=prohibited.",
            "Review update operation: reviewers are read-only; the main Agent semantically repairs the same formal Tickets in place and routes the corrected set through `register`.",
            "Publish or promote operation: route the reviewed registered set through `promote`; the adapter owns all transaction mechanics.",
            "Partial-publish recovery: inspect the durable run, then resume the operation named by its phase; never reproduce transaction mechanics manually.",
            "Claim safety: publication exposes no Claim operation. Route whole-tracker discovery, blockers, snapshots, and conflict-detecting Claim through the configured frontier adapter.",
            f"Cancellation policy: {cancellation_policy}",
            f"Cancellation behavior: {CANCELLATION_POLICIES[cancellation_policy]}",
            "",
        ]
    )
    return lines


def custom_publication(policy: dict[str, str]) -> list[str]:
    return [
        "## Ticket Review Publication",
        "",
        "Publication strategy: custom",
        *[f"{field} {policy[field]}" for field in PUBLICATION_FIELDS],
        "",
    ]


def custom_coordination(policy: dict[str, str]) -> list[str]:
    return [
        "## Solve Coordination",
        "",
        *[f"{field} {policy[field]}" for field in COORDINATION_FIELDS],
        "",
    ]


def coordination(preset: str) -> list[str]:
    if preset == "local-markdown":
        resource_links = "during execution, store only configured Claim branch/worktree identity in Ticket metadata. At handoff, resource identity, ownership, and cleanup remain authoritative in the Solve Record or native PR/MR; Ticket notes may add concise lifecycle backlinks but never duplicate those facts."
        claim = "route the discovery snapshot, ready/blocker/publication re-read, active Claim, and execution branch/worktree assignment through the bundled frontier adapter; release follows the outcome workflow."
    elif preset == "github":
        resource_links = "record branch, worktree, commit, and pull-request links in the configured development-link or concise issue-comment surface."
        claim = "re-read a ready, unblocked, unassigned Ticket and assign the session actor through the configured GitHub operation; release the assignment when the Attempt ends without a terminal state."
    elif preset == "gitlab":
        resource_links = "record branch, worktree, commit, and merge-request links in the configured development-link or concise issue-note surface."
        claim = "re-read a ready, unblocked, unassigned Ticket and assign the session actor through the configured GitLab operation; release the assignment when the Attempt ends without a terminal state."
    else:
        resource_links = "use only the custom policy's named durable link surface; every unnamed link operation is unsupported."
        claim = "use the custom policy's conflict-detecting Claim and release operation; batch execution is unsupported until that operation is named."

    lines = [
        "## Solve Coordination",
        "",
        f"Claim and release: {claim}",
        "State mapping: `review-pending` is an Ultra adapter state, not a sixth global triage role. `ready-for-agent` is the sole claimable state; active Claim and terminal states follow the base tracker contract.",
        "Blocker and frontier lookup: use the base contract's blocker representation. The frontier contains only ready, unblocked, unclaimed Tickets; provisional or staged Tickets remain outside it.",
        f"Branch/worktree/PR links: {resource_links}",
        "Solve Record backlinks: add the durable receipt path or URL to the Ticket's configured backlink surface; the receipt remains the outcome record and the Ticket remains the work order.",
        "Unsupported operations: record any backend capability absent from this extension as unsupported. Batch mutation requires conflict-detecting Claim and safe blocker lookup; otherwise use an explicit single-Ticket path.",
        "",
    ]
    if preset == "local-markdown":
        lines[2:2] = [
            "Frontier adapter: bundled-local-markdown-v1",
            "Ticket ID field aliases: Ticket ID, ID",
            "Publication Run field aliases: Publication Run",
            "Source field aliases: Source Spec, Parent",
            "Ticket state fields: Status, State",
            "Ticket state values: review-pending, ready-for-agent, completed, ready-for-human, needs-info",
            "Ready state: ready-for-agent",
            "Completed state: completed",
            "Human-blocked states: ready-for-human, needs-info",
            "Blocker metadata fields: Blocked By, Blockers",
            "Blocker body heading: Blocked by",
            "Claim field: Flags",
            "Claim field aliases: Flags, Labels",
            "Claim value: solve-in-progress",
            "Solve branch field: Solve Branch",
            "Solve branch field aliases: Solve Branch, Branch",
            "Solve worktree field: Solve Worktree",
            "Solve worktree field aliases: Solve Worktree, Worktree",
            "",
        ]
    return lines


def render_contract(args: argparse.Namespace) -> str:
    common = [
        "# Ultra Tracker Extension",
        "",
        "Base tracker: docs/agents/issue-tracker.md",
        "",
        "This managed extension adds Ultra-specific operations. The base tracker contract and triage documents remain authoritative for their own concerns.",
        "",
    ]
    if args.publication_strategy == "remote-review-pending":
        publication = remote_publication(
            args.review_pending_marker, args.publication_marker_prefix
        )
    elif args.publication_strategy == "local-staging":
        publication = staging_publication()
    elif args.publication_strategy == "local-review-pending":
        publication = local_publication(
            args.cancellation_policy,
            args.local_ticket_representation,
            args.local_ticket_path,
        )
    else:
        return "\n".join(
            common
            + custom_publication(args.custom_policy)
            + custom_coordination(args.custom_policy)
        ).rstrip() + "\n"
    return "\n".join(common + publication + coordination(args.preset)).rstrip() + "\n"


def managed_block() -> str:
    return "\n".join(
        [
            BLOCK_START,
            "### Ultra tracker extension",
            "",
            "Ultra review publication, Claim, frontier, resource-link, and Solve Record rules live in `docs/agents/ultra-tracker.md`.",
            BLOCK_END,
        ]
    )


def replace_instruction_block(text: str) -> str:
    block = managed_block()
    start = text.find(BLOCK_START)
    if start >= 0:
        end = text.find(BLOCK_END, start)
        if end < 0:
            raise ConfigurationError("existing Ultra managed block has no end marker")
        return text[:start] + block + text[end + len(BLOCK_END) :]

    heading = re.search(r"(?m)^## Agent skills\s*$", text)
    if heading:
        following = re.search(r"(?m)^## (?!Agent skills\s*$)", text[heading.end() :])
        insertion = heading.end() + (following.start() if following else len(text[heading.end() :]))
        prefix = text[:insertion].rstrip()
        suffix = text[insertion:]
        return f"{prefix}\n\n{block}\n\n{suffix.lstrip()}"

    return f"{text.rstrip()}\n\n## Agent skills\n\n{block}\n"


def needs_staging_ignore(gitignore: str) -> bool:
    normalized = {line.strip() for line in gitignore.splitlines() if line.strip()}
    return not any(
        rule in normalized
        for rule in (".scratch/", "/.scratch/", STAGING_ROOT, f"/{STAGING_ROOT}")
    )


def preview(path: Path, content: str) -> str:
    return f"--- {path.as_posix()} ---\n{content}"


def main() -> int:
    args = parse_args()
    try:
        validate_policy(args)
        repo = Path(args.repo).resolve()
        if not repo.is_dir():
            raise ConfigurationError(f"repository does not exist: {repo}")
        base = repo / BASE_CONTRACT
        if not base.is_file():
            raise ConfigurationError(
                "missing docs/agents/issue-tracker.md; run the base tracker setup first"
            )
        instructions = resolve_inside(repo, args.instructions, "instructions path")
        if not instructions.is_file():
            raise ConfigurationError(f"instructions file does not exist: {args.instructions}")

        contract = render_contract(args)
        updated_instructions = replace_instruction_block(
            instructions.read_text(encoding="utf-8")
        )
        changes = [(repo / EXTENSION_CONTRACT, contract), (instructions, updated_instructions)]

        if args.publication_strategy == "local-staging":
            gitignore = repo / ".gitignore"
            existing_ignore = (
                gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
            )
            if needs_staging_ignore(existing_ignore):
                suffix = "" if not existing_ignore or existing_ignore.endswith("\n") else "\n"
                changes.append((gitignore, f"{existing_ignore}{suffix}{STAGING_ROOT}\n"))

        if not args.apply:
            for path, content in changes:
                print(preview(path.relative_to(repo), content), end="" if content.endswith("\n") else "\n")
            return 0

        for path, content in changes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"updated {path.relative_to(repo)}")
        return 0
    except ConfigurationError as error:
        print(f"setup-ultra-skills: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
