#!/usr/bin/env python3
"""Render and apply the managed Ultra tracker extension."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


BASE_CONTRACT = Path("docs/agents/issue-tracker.md")
EXTENSION_CONTRACT = Path("docs/agents/ultra-tracker.md")
STAGING_ROOT = ".scratch/.ultra-staging/"
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
        default="Keep review-pending files until explicit cleanup.",
        help="Recorded Local Markdown cancellation policy.",
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


def local_publication(cancellation_policy: str) -> list[str]:
    return [
        "## Ticket Review Publication",
        "",
        "Publication strategy: local-review-pending",
        "Draft or review-pending representation: formal Ticket files are created in the configured issue directory with `Status: review-pending`.",
        "Review update operation: reviewers and the main Agent revise the same formal files in place.",
        "Publish or promote operation: after review passes, set the same Ticket files to `Status: ready-for-agent`.",
        "Partial-publish recovery: interrupted review retains the formal files in `review-pending`; resumption re-reads and updates those files rather than creating replacements.",
        f"Cancellation policy: {cancellation_policy}",
        "",
    ]


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
        resource_links = "store `Solve Branch`, `Solve Worktree`, and PR or commit links in the Ticket's structured metadata or its established backlink surface."
        claim = "re-read a ready Ticket, record its branch and worktree, and transition it to the configured active Claim representation before execution; release that Claim when the Attempt ends."
    elif preset == "github":
        resource_links = "record branch, worktree, commit, and pull-request links in the configured development-link or concise issue-comment surface."
        claim = "re-read a ready, unblocked, unassigned Ticket and assign the session actor through the configured GitHub operation; release the assignment when the Attempt ends without a terminal state."
    elif preset == "gitlab":
        resource_links = "record branch, worktree, commit, and merge-request links in the configured development-link or concise issue-note surface."
        claim = "re-read a ready, unblocked, unassigned Ticket and assign the session actor through the configured GitLab operation; release the assignment when the Attempt ends without a terminal state."
    else:
        resource_links = "use only the custom policy's named durable link surface; every unnamed link operation is unsupported."
        claim = "use the custom policy's conflict-detecting Claim and release operation; batch execution is unsupported until that operation is named."

    return [
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
        publication = local_publication(args.cancellation_policy)
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
