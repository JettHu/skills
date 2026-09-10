#!/usr/bin/env python3
"""Generate a read-only maintainer board snapshot for local .scratch state."""

import argparse
import html
import hashlib
import os
import tempfile
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


ISSUE_BUCKETS = [
    "ready_for_agent",
    "claimed_or_in_progress",
    "needs_human",
    "needs_triage",
    "publication_attention",
    "blocked_or_dependent",
    "completed_with_solve_record",
    "completed_without_solve_record",
    "other",
]

SOLVE_RECORD_BUCKETS = [
    "ready",
    "manual",
    "cleanup",
    "recent",
    "historical",
    "recovery",
    "stale_or_malformed",
]
DEFAULT_VISIBLE_ITEMS = 5
RENDERER_VERSION = "maintainer-board-renderer/v2"
DEFAULT_HTML_PATH = Path(".scratch/maintainer-board/index.html")


def load_snapshot_module():
    skill = Path(__file__).resolve().parent.parent
    candidates = [skill.parent / "ultra/scripts"]
    if len(skill.parents) >= 2:
        candidates.append(skill.parents[1] / "engineering/ultra/scripts")
    directory = next((path for path in candidates if (path / "tracker_snapshot.py").is_file()), None)
    if directory is None:
        raise RuntimeError("Maintainer Board requires the bundled Tracker Snapshot owner")
    sys.path.insert(0, str(directory))
    try:
        import tracker_snapshot
    except ImportError as exc:
        raise RuntimeError(f"Tracker Snapshot helper unavailable: {exc}") from exc
    return tracker_snapshot


def repo_root(path):
    return load_snapshot_module().repository(path)


def classify_issue(issue):
    flags = set(issue["flags"])
    status = issue["status"]
    warning_codes = {warning.get("code") for warning in issue.get("warnings", [])}
    publication_attention = warning_codes & {
        "malformed-ticket",
        "missing-stable-identity",
        "readonly-metadata-syntax",
        "publication_invalid",
        "publication_not_promoted",
        "publication_adapter_missing",
    }
    if status == "review-pending":
        return "other"
    if publication_attention or (
        issue.get("publication_run") and not issue.get("publication_promoted")
    ):
        return "publication_attention"
    if issue.get("completed"):
        if issue["solve_records"]:
            return "completed_with_solve_record"
        return "completed_without_solve_record"
    if status == "wontfix":
        return "other"
    if status == "needs-triage":
        return "needs_triage"
    if status in {"ready-for-human", "needs-info"}:
        return "needs_human"
    if issue.get("claim_active"):
        return "claimed_or_in_progress"
    if any(not item.get("satisfied") for item in issue.get("blocker_facts", [])):
        return "blocked_or_dependent"
    if status == "ready-for-agent":
        return "ready_for_agent"
    return "other"


def bucket_items(items, buckets):
    result = {bucket: [] for bucket in buckets}
    for item in items:
        result[item["bucket"]].append(item)
    return result


def build_snapshot(repo, selection=None):
    facts = load_snapshot_module().snapshot(repo, selection)
    issues = []
    for ticket in facts["tickets"]:
        claim = ticket.get("claim", {})
        publication = ticket.get("publication", {})
        contract = ticket.get("contract", {})
        issue = dict(path=ticket["locator"], source_path=ticket["source_locator"], ticket_id=ticket.get("ticket_id", ""),
                     title=ticket["title"], status=ticket.get("state") or "malformed", feature=ticket.get("feature", ""),
                     category=ticket.get("category", ""), created=ticket.get("created", ""), metadata_format=ticket.get("metadata_format", "unknown"),
                     flags=claim.get("flags", []), claim_active=claim.get("active", False), completed=contract.get("completed", False), solve_branch=claim.get("branch", ""), solve_worktree=claim.get("worktree", ""),
                     parent=contract.get("parent", ""), checklist=contract.get("checklist", {"total": 0, "done": 0, "open": 0}),
                     solve_records=ticket.get("receipt_references", []), blocked_by=[b["reference"] for b in ticket.get("blockers", [])],
                     blocker_facts=ticket.get("blockers", []), eligibility=ticket["eligibility"],
                     publication_run=publication.get("run_id", ""), publication_promoted=publication.get("verified") is True,
                     publication_digest=publication.get("current_digest", ""), publication_original_digest=publication.get("original_digest", ""),
                     warnings=ticket["diagnostics"], completion_scope="Candidate gate complete; completed does not prove merge, deployment, or online smoke." if contract.get("completed") else "")
        issue["bucket"] = classify_issue(issue)
        issues.append(issue)
    issue_buckets = bucket_items(issues, ISSUE_BUCKETS)
    buckets = {name: [] for name in SOLVE_RECORD_BUCKETS}
    recent = []
    for fact in facts["receipts"]:
        record = dict(fact)
        readiness = record.pop("operation_readiness")
        record["merge_gate"] = readiness["merge"] or {"eligible": False, "reasons": ["readiness unavailable"]}
        record["cleanup_plan"] = readiness["cleanup"] or {"status": "unavailable"}
        consistency = record.pop("handoff_consistency")
        record["handoff_projection"] = "inconsistent_handoff_attention" if consistency["status"] in {"inconsistent", "unavailable"} else consistency["classification"]
        terminal = record.get("state") == "closed"
        cleanup_done = str(record.get("cleanup_done")).lower() == "true"
        outcome = record.get("outcome")
        if record.get("malformed"):
            bucket = "stale_or_malformed"
        elif outcome != "candidate" and terminal and record.get("superseded_by"):
            bucket = "historical"
        elif record.get("closed_candidate_terminal"):
            bucket = "recent" if cleanup_done else "cleanup"
            record["terminal_view"] = "closed"
        elif (terminal and outcome != "candidate") or record.get("legacy_terminal_outcome"):
            bucket = "historical" if cleanup_done else "cleanup"
            record["terminal_view"] = "closed"
        elif outcome != "candidate":
            bucket = "recovery"
            record["recovery_view"] = "resume" if outcome in {"blocked", "needs-info", "ready-for-human"} else "closed"
        elif record.get("body_conflict"):
            bucket = "stale_or_malformed"; record["stale_reason"] = record["body_conflict"]
        elif not record.get("refs_ok") and record.get("state") == "open":
            bucket = "stale_or_malformed"; record["stale_reason"] = record.get("ref_reason", "Git unavailable")
        elif record.get("state") in {"merged", "closed"} and not cleanup_done:
            bucket = "cleanup"
        elif record.get("state") == "merged":
            bucket = "recent"
        else:
            bucket = "ready" if record["merge_gate"].get("eligible") else "manual"
        if bucket == "recent": recent.append(record)
        else: buckets[bucket].append(record)
    buckets["recent"] = sorted(recent, key=lambda item: (item.get("merged_at") or item.get("created_at") or "", item.get("id") or "", item["path"]), reverse=True)[:10]
    return dict(schema_version="maintainer-board/v1", repo=facts["repository"]["root"], source_fingerprint=facts["source_fingerprint"],
                selection=facts["selection"], semantic_version=facts["semantic_version"], diagnostics=facts["diagnostics"], incomplete=facts["summary"]["incomplete"],
                issues=dict(count=len(issues), buckets=issue_buckets, counts={name: len(items) for name, items in issue_buckets.items()}, warnings=[dict(path=issue["path"], **warning) for issue in issues for warning in issue["warnings"]]),
                solve_records=dict(count=len(facts["receipts"]), buckets=buckets, counts={name: len(items) for name, items in buckets.items()}))


def render_pill(value, css_class=""):
    if not value:
        return ""
    class_names = ["pill"]
    if css_class:
        class_names.append(css_class)
    class_names.append(f"label-{slugify(value)}")
    class_attr = " ".join(class_names)
    return f"<span class='{class_attr}'>{html.escape(str(value))}</span>"


def slugify(value):
    value = str(value).strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "unknown"


def render_pills(values):
    return "".join(render_pill(value) for value in values if value)


def render_detail_rows(rows):
    rendered = []
    for label, value in rows:
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value)
        escaped = html.escape(str(value)).replace("\n", "<br>")
        rendered.append(f"<dt>{html.escape(label)}</dt><dd>{escaped}</dd>")
    if not rendered:
        return ""
    return f"<dl class='details-grid'>{''.join(rendered)}</dl>"


def render_warning_list(warnings):
    if not warnings:
        return ""
    items = "".join(
        f"<li><span class='warn-code'>{html.escape(warning['code'])}</span> {html.escape(warning['message'])}</li>"
        for warning in warnings
    )
    return f"<ul class='warnings'>{items}</ul>"


def record_cleanup_label(record):
    resource_cleanup = record.get("resource_cleanup") or ""
    if resource_cleanup and resource_cleanup != "pending":
        return resource_cleanup
    if str(record.get("cleanup_done")).lower() == "true":
        return "cleanup done"
    return "cleanup pending"


def record_cleanup_ownership(record):
    cleanup = record_cleanup_label(record).lower()
    if "user-owned" in cleanup or "adopted" in cleanup:
        return "user-owned adopted resources"
    if str(record.get("cleanup_done")).lower() == "true":
        return "no solve-owned cleanup pending"
    return "solve-owned cleanup pending"


def render_issue_card(issue, hidden=False):
    search = " ".join(
        str(value)
        for value in [
            issue["title"],
            issue["path"],
            issue["status"],
            issue["category"],
            issue["feature"],
            issue["completion_scope"],
            issue["publication_digest"],
            " ".join(issue["flags"]),
        ]
    )
    checklist = issue["checklist"]
    checklist_text = f"{checklist['done']}/{checklist['total']} checklist" if checklist["total"] else "no checklist"
    warning_text = f"{len(issue['warnings'])} warning" if len(issue["warnings"]) == 1 else f"{len(issue['warnings'])} warnings"
    top_pills = [
        issue["status"],
        "candidate gate complete" if issue["completion_scope"] else "",
        issue["category"],
        issue["feature"],
        checklist_text,
        warning_text if issue["warnings"] else "",
        *issue["flags"],
    ]
    detail_rows = [
        ("Path", issue["path"]),
        ("Status", issue["status"]),
        ("Completion scope", issue["completion_scope"]),
        ("Category", issue["category"]),
        ("Feature", issue["feature"]),
        ("Created", issue["created"]),
        ("Metadata format", issue["metadata_format"]),
        ("Parent", issue["parent"]),
        ("Publication run", issue["publication_run"]),
        ("Publication current digest", issue["publication_digest"]),
        ("Publication original digest", issue["publication_original_digest"]),
        ("Blocked by", issue["blocked_by"]),
        ("Solve branch", issue["solve_branch"]),
        ("Solve worktree", issue["solve_worktree"]),
        ("Solve records", issue["solve_records"]),
        ("Checklist", checklist_text),
    ]
    hidden_attr = " data-overflow='true' hidden" if hidden else ""
    return f"""
<article class="card issue-card" data-search="{html.escape(search.lower())}"{hidden_attr}>
  <h3>{html.escape(issue['title'])}</h3>
  <div class="path">{html.escape(issue['path'])}</div>
  <div class="pills">{render_pills(top_pills)}</div>
  {f'<div class="lifecycle-boundary">{html.escape(issue["completion_scope"])}</div>' if issue["completion_scope"] else ''}
  <details class="card-details">
    <summary>Details</summary>
    {render_detail_rows(detail_rows)}
    {render_warning_list(issue['warnings'])}
  </details>
</article>
"""


def render_record_card(record, hidden=False):
    search = " ".join(
        str(value)
        for value in [
            record.get("title", ""),
            record.get("id", ""),
            record.get("path", ""),
            record.get("state", ""),
            record.get("outcome", ""),
            record.get("head", ""),
            record.get("base", ""),
            record.get("resource_cleanup", ""),
            record.get("linked_ticket", ""),
            record.get("blocker_or_requested_information", ""),
            record.get("retained_resources", ""),
            record.get("resource_ownership", ""),
            record.get("recovery_action", ""),
        ]
    )
    cleanup = record_cleanup_label(record)
    cleanup_ownership = record_cleanup_ownership(record)
    top_pills = [
        record.get("state"),
        record.get("outcome"),
        record.get("checks"),
        record.get("merge"),
        cleanup,
    ]
    detail_rows = [
        ("Path", record.get("path")),
        ("ID", record.get("id")),
        ("State", record.get("state")),
        ("Outcome", record.get("outcome")),
        ("Linked Ticket", record.get("linked_ticket") or record.get("issues", [])),
        ("Blocker or requested information", record.get("blocker_or_requested_information")),
        ("Retained resources", record.get("retained_resources")),
        ("Resource owner", record.get("resource_ownership")),
        ("Next resume or cleanup action", record.get("recovery_action")),
        ("Checks", record.get("checks")),
        ("Merge", record.get("merge")),
        ("Cleanup", cleanup),
        ("Cleanup ownership", cleanup_ownership),
        ("Landing branch (base)", record.get("base")),
        ("Candidate branch (head)", record.get("head")),
        ("Worktree", record.get("worktree")),
        ("Issues", record.get("issues", [])),
        ("Stale reason", record.get("stale_reason")),
        ("Malformed", record.get("malformed")),
        ("Refs", record.get("ref_reason")),
    ]
    hidden_attr = " data-overflow='true' hidden" if hidden else ""
    return f"""
<article class="card record-card" data-search="{html.escape(search.lower())}"{hidden_attr}>
  <h3>{html.escape(record.get('title') or record.get('id') or record.get('path') or 'solve record')}</h3>
  <div class="path">{html.escape(record.get('path', ''))}</div>
  <div class="pills">{render_pills(top_pills)}</div>
  <details class="card-details">
    <summary>Details</summary>
    {render_detail_rows(detail_rows)}
  </details>
</article>
"""


def render_bucket(title, items, renderer, visible_items=DEFAULT_VISIBLE_ITEMS):
    cards = "".join(
        renderer(item, hidden=index >= visible_items)
        for index, item in enumerate(items)
    )
    empty = "<p class='empty'>none</p>" if not items else ""
    hidden_count = max(0, len(items) - visible_items)
    show_more = (
        f"<button class='show-more' type='button' data-hidden-count='{hidden_count}'>Show {hidden_count} more</button>"
        if hidden_count
        else ""
    )
    return f"""
<section class="bucket" data-expanded="false">
  <header><h2>{html.escape(title)}</h2><span>{len(items)}</span></header>
  <div class="cards">{cards}{empty}</div>
  {show_more}
</section>
"""


def titleize_bucket(bucket):
    return bucket.replace("_", " ").title()


def issue_display_items(bucket, items):
    if bucket not in {"completed_with_solve_record", "completed_without_solve_record"}:
        return items
    return sorted(
        items,
        key=lambda item: (
            item.get("completed") or item.get("updated") or item.get("created") or "",
            item.get("path") or "",
        ),
        reverse=True,
    )


def render_html(snapshot, visible_items=DEFAULT_VISIBLE_ITEMS):
    issue_counts = snapshot["issues"]["counts"]
    record_counts = snapshot["solve_records"]["counts"]
    issue_summary = "".join(
        f"<div><strong>{count}</strong><span>{html.escape(titleize_bucket(bucket))}</span></div>"
        for bucket, count in issue_counts.items()
    )
    record_summary = "".join(
        f"<div><strong>{count}</strong><span>{html.escape(titleize_bucket(bucket))}</span></div>"
        for bucket, count in record_counts.items()
    )
    issue_sections = "".join(
        render_bucket(
            titleize_bucket(bucket),
            issue_display_items(bucket, snapshot["issues"]["buckets"].get(bucket, [])),
            render_issue_card, visible_items,
        )
        for bucket in ISSUE_BUCKETS
    )
    record_sections = "".join(
        render_bucket(titleize_bucket(bucket), snapshot["solve_records"]["buckets"].get(bucket, []), render_record_card, visible_items)
        for bucket in SOLVE_RECORD_BUCKETS
    )
    repo = html.escape(snapshot["repo"])
    fingerprint = html.escape(snapshot.get("source_fingerprint", ""))
    global_diagnostics = render_warning_list(snapshot.get("diagnostics", []))
    observation = "Snapshot incomplete: inspect diagnostics before acting." if snapshot.get("incomplete") else "Last successful observation; currentness requires a new query. Readiness does not authorize an operation."
    selection = snapshot.get("selection", {})
    scope = ""
    if selection.get("mode") == "exact":
        requested = ", ".join(selection.get("requested") or []) or "(empty selection)"
        missing = ", ".join(selection.get("missing") or [])
        scope = '<p>Selected Tickets: ' + html.escape(requested) + '</p>'
        if missing: scope += '<p>Exact keys absent from source: ' + html.escape(missing) + '</p>'
    provenance = f'<aside class="snapshot-observation"><strong>{observation}</strong>{scope}{global_diagnostics}<div>tracker-snapshot/v1 · {fingerprint}</div></aside>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Maintainer Board</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d8dde5;
      --text: #1d2430;
      --muted: #5e6a7d;
      --green: #1f7a4d;
      --amber: #946200;
      --red: #b42318;
      --blue: #2459a6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 13px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--text);
      background: var(--bg);
    }}
    main {{ padding: 20px; max-width: 1680px; margin: 0 auto; }}
    .topbar {{
      display: flex;
      gap: 16px;
      align-items: flex-end;
      justify-content: space-between;
      margin-bottom: 16px;
    }}
    h1 {{ margin: 0 0 4px; font-size: 24px; font-weight: 720; }}
    .repo {{ color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; }}
    input {{
      width: min(460px, 100%);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 11px;
      font: inherit;
      background: var(--panel);
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
      gap: 8px;
      margin: 12px 0 20px;
    }}
    .summary div {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      min-width: 0;
    }}
    .summary strong {{ display: block; font-size: 20px; }}
    .summary span {{ color: var(--muted); font-size: 12px; }}
    .section-title {{
      margin: 22px 0 10px;
      font-size: 17px;
      border-bottom: 1px solid var(--line);
      padding-bottom: 6px;
    }}
    .lane-scroll {{
      overflow-x: auto;
      padding-bottom: 8px;
      scrollbar-gutter: stable;
    }}
    .grid {{
      display: grid;
      grid-auto-flow: column;
      grid-auto-columns: minmax(330px, 380px);
      grid-template-rows: 1fr;
      gap: 12px;
      align-items: start;
      width: max-content;
      min-width: 100%;
    }}
    .bucket {{
      background: #eef1f5;
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
    }}
    .bucket header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
    }}
    .bucket h2 {{ margin: 0; font-size: 13px; }}
    .bucket header span {{
      min-width: 24px;
      text-align: center;
      border-radius: 999px;
      background: var(--panel);
      border: 1px solid var(--line);
      color: var(--muted);
      padding: 1px 7px;
    }}
    .cards {{ display: grid; gap: 8px; padding: 8px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 4px solid var(--blue);
      border-radius: 6px;
      padding: 9px;
      min-width: 0;
    }}
    .record-card {{ border-left-color: var(--green); }}
    .card h3 {{ margin: 0 0 4px; font-size: 13px; line-height: 1.3; }}
    .path {{
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
      overflow-wrap: anywhere;
    }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 7px;
      color: var(--muted);
      background: #fbfcfd;
      font-size: 11px;
      font-weight: 620;
    }}
    .label-ready-for-agent,
    .label-ready,
    .label-passed,
    .label-completed,
    .label-candidate-gate-complete,
    .label-cleanup-done {{
      color: #116329;
      background: #dafbe1;
      border-color: #aceebb;
    }}
    .label-solve-in-progress,
    .label-open,
    .label-feature {{
      color: #0969da;
      background: #ddf4ff;
      border-color: #b6e3ff;
    }}
    .label-ready-for-human,
    .label-needs-info,
    .label-manual-required,
    .label-unavailable,
    .label-cleanup-pending,
    .label-documentation {{
      color: #9a6700;
      background: #fff8c5;
      border-color: #f0d98c;
    }}
    .label-stale,
    .label-stale-or-malformed,
    .label-bug {{
      color: #cf222e;
      background: #ffebe9;
      border-color: #ffcecb;
    }}
    .label-merged,
    .label-auto-merged {{
      color: #8250df;
      background: #fbefff;
      border-color: #eac4ff;
    }}
    .pills {{ display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 5px; }}
    .lifecycle-boundary {{
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
      margin: 2px 0 5px;
    }}
    .card-details {{
      margin-top: 7px;
      border-top: 1px solid var(--line);
      padding-top: 6px;
    }}
    .card-details summary {{
      cursor: pointer;
      color: var(--blue);
      font-size: 12px;
      font-weight: 650;
    }}
    .details-grid {{
      display: grid;
      grid-template-columns: minmax(86px, max-content) minmax(0, 1fr);
      gap: 5px 10px;
      margin: 7px 0 0;
    }}
    .details-grid dt {{
      color: var(--muted);
      font-size: 11px;
    }}
    .details-grid dd {{
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 11px;
    }}
    .warnings {{
      margin: 7px 0 0;
      padding-left: 18px;
      color: var(--red);
    }}
    .warn-code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .show-more {{
      width: calc(100% - 16px);
      margin: 0 8px 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--blue);
      cursor: pointer;
      font: inherit;
      font-size: 12px;
      padding: 6px 8px;
    }}
    .empty {{ margin: 0; color: var(--muted); padding: 6px 2px; }}
  </style>
</head>
<body>
<main>
  <div class="topbar">
    <div>
      <h1>Maintainer Board</h1>
      <div class="repo">{repo}</div>
    </div>
    <input id="search" type="search" placeholder="Filter cards by title, path, status, branch...">
  </div>
  {provenance}
  <h2 class="section-title">Issue Summary</h2>
  <div class="summary">{issue_summary}</div>
  <h2 class="section-title">Solve Record Summary</h2>
  <div class="summary">{record_summary}</div>
  <h2 class="section-title">Issues</h2>
  <div class="lane-scroll"><div class="grid">{issue_sections}</div></div>
  <h2 class="section-title">Solve Records</h2>
  <div class="lane-scroll"><div class="grid">{record_sections}</div></div>
</main>
<script>
  const search = document.getElementById('search');
  const cards = [...document.querySelectorAll('.card')];
  const buttons = [...document.querySelectorAll('.show-more')];
  function applyLimit() {{
    const query = search.value.trim().toLowerCase();
    for (const button of buttons) {{
      button.hidden = Boolean(query);
    }}
    for (const card of cards) {{
      const matches = !query || card.dataset.search.includes(query);
      if (query) {{
        card.hidden = !matches;
        continue;
      }}
      const bucket = card.closest('.bucket');
      const limited = card.dataset.overflow === 'true' && bucket.dataset.expanded !== 'true';
      card.hidden = limited;
    }}
  }}
  for (const button of buttons) {{
    const hiddenCount = button.dataset.hiddenCount;
    button.addEventListener('click', () => {{
      const bucket = button.closest('.bucket');
      const expanded = bucket.dataset.expanded === 'true';
      bucket.dataset.expanded = expanded ? 'false' : 'true';
      button.textContent = expanded ? `Show ${{hiddenCount}} more` : 'Show fewer';
      applyLimit();
    }});
  }}
  search.addEventListener('input', () => {{
    applyLimit();
  }});
  applyLimit();
</script>
</body>
</html>
"""


def emit_json(snapshot):
    print(json.dumps(snapshot, indent=2, sort_keys=True))


REFRESH_SCHEMA = "maintainer-board-refresh/v1"
REFRESH_START = "<!-- tracker-refresh:start -->"
REFRESH_END = "<!-- tracker-refresh:end -->"


def effective_options(visible_items=DEFAULT_VISIBLE_ITEMS):
    if not isinstance(visible_items, int) or isinstance(visible_items, bool) or not 1 <= visible_items <= 100:
        raise ValueError("visible_items must be an integer in 1..100")
    return {"visible_items": visible_items}


def render_signature(selection=None, options=None):
    selected = load_snapshot_module().normalize_selection(selection)
    options = effective_options(**(options or {}))
    return hashlib.sha256(json.dumps([RENDERER_VERSION, selected, options], sort_keys=True).encode()).hexdigest()


def generation(body, success):
    return hashlib.sha256(json.dumps([body, success.get("source_fingerprint"), success.get("render_signature")], sort_keys=True).encode()).hexdigest()


def read_artifact(path):
    if not path.exists():
        return None
    document = path.read_text(encoding="utf-8")
    if REFRESH_START not in document and REFRESH_END not in document:
        success = dict(source_fingerprint=None, render_signature=None, selection=None, options=None, provenance="legacy-unknown")
        success.update(generation=generation(document, success), body_sha256=hashlib.sha256(document.encode()).hexdigest())
        return document, dict(schema=REFRESH_SCHEMA, last_success=success, latest_refresh=dict(status="unknown", generation=success["generation"]))
    if document.count(REFRESH_START) != 1 or document.count(REFRESH_END) != 1:
        raise ValueError("generated artifact has ambiguous refresh boundaries")
    start = document.index(REFRESH_START); end = document.index(REFRESH_END, start) + len(REFRESH_END)
    block = document[start:end]
    match = re.search(r'<script id="tracker-refresh-state" type="application/json">(.*?)</script>', block, re.S)
    if not match:
        raise ValueError("generated artifact has no bound refresh state")
    state = json.loads(match.group(1)); body = document[:start] + document[end:]
    success = state.get("last_success", {})
    if (state.get("schema") != REFRESH_SCHEMA
            or success.get("body_sha256") != hashlib.sha256(body.encode()).hexdigest()
            or success.get("generation") != generation(body, success)
            or state.get("latest_refresh", {}).get("generation") != success.get("generation")):
        raise ValueError("generated artifact body and refresh generation disagree")
    return body, state


def managed_document(body, state):
    serialized = json.dumps(state, sort_keys=True, separators=(",", ":")).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    success, latest = state["last_success"], state["latest_refresh"]
    if success.get("provenance") == "legacy-unknown":
        label = "Retained previous document; its observation provenance is unknown."
    else:
        label = "Last successful observation; currentness requires a new query."
    detail = "Latest refresh succeeded." if latest["status"] == "success" else "Latest refresh failed; displayed facts may be stale."
    if latest.get("error"):
        detail += " " + latest["error"].get("detail", "")
    block = (REFRESH_START + '<script id="tracker-refresh-state" type="application/json">' + serialized + '</script>'
             + '<aside id="tracker-refresh-notice" role="status"><strong>' + html.escape(label) + '</strong><p>' + html.escape(detail)
             + '</p><small>Generation ' + html.escape(success["generation"]) + '</small></aside>' + REFRESH_END)
    marker = body.find("<body>")
    if marker < 0:
        raise ValueError("rendered artifact has no body boundary")
    marker += len("<body>")
    return body[:marker] + block + body[marker:]


def atomic_document(path, document):
    """Persist body and refresh state in one replacement; failures keep the prior file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        content = document.encode("utf-8"); offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if not written:
                raise OSError("generated artifact write made no progress")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor); descriptor = None
        os.replace(temporary, path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try: os.unlink(temporary)
        except FileNotFoundError: pass


def persist_document(path, body, state):
    document = managed_document(body, state)
    if path.exists() and path.read_text(encoding="utf-8") == document:
        return False
    atomic_document(path, document)
    return True


def successful_state(snapshot, body, selection, options):
    success = dict(source_fingerprint=snapshot["source_fingerprint"], semantic_version=snapshot.get("semantic_version"),
                   render_signature=render_signature(selection, options), renderer_version=RENDERER_VERSION,
                   selection=selection, options=options, provenance="observed")
    success.update(generation=generation(body, success), body_sha256=hashlib.sha256(body.encode()).hexdigest())
    return dict(schema=REFRESH_SCHEMA, last_success=success, latest_refresh=dict(status="success", generation=success["generation"]))


def write_html(snapshot, output_path, options=None):
    options = effective_options(**(options or {}))
    selection = load_snapshot_module().normalize_selection(snapshot.get("selection", {}).get("requested"))
    path = Path(output_path).absolute(); body = render_html(snapshot, **options)
    persist_document(path, body, successful_state(snapshot, body, selection, options))
    return path


def refresh(repo, output_path, selection=None, options=None):
    """Observe, render and publish one self-contained artifact; report every failure."""
    path = Path(output_path).absolute()
    attempted = dict(selection=selection, renderer_version=RENDERER_VERSION, options=options or {})
    try:
        selection = load_snapshot_module().normalize_selection(selection)
        options = effective_options(**(options or {}))
        attempted.update(selection=selection, options=options)
        snapshot = build_snapshot(repo, selection)
        body = render_html(snapshot, **options)
        state = successful_state(snapshot, body, selection, options)
    except Exception as error:
        failure = dict(code=getattr(error, "code", "observation-or-render-failed"), detail=str(error))
        result = dict(ok=False, status="failed", path=str(path), error=failure, persisted=False)
        try:
            previous = read_artifact(path)
            if previous:
                body, state = previous
                state["latest_refresh"] = dict(status="failed", generation=state["last_success"]["generation"], error=failure, attempted=attempted)
                result["changed"] = persist_document(path, body, state)
                result.update(persisted=True, generation=state["last_success"]["generation"])
        except Exception as persistence_error:
            result["persistence_error"] = dict(code="refresh-status-write-failed", detail=str(persistence_error))
        return result
    try:
        changed = persist_document(path, body, state)
    except Exception as error:
        return dict(ok=False, status="failed", path=str(path), persisted=False, error=dict(code="artifact-replace-failed", detail=str(error)))
    return dict(ok=True, status="updated" if changed else "unchanged", path=str(path), persisted=True,
                generation=state["last_success"]["generation"], source_fingerprint=snapshot["source_fingerprint"],
                render_signature=state["last_success"]["render_signature"], snapshot=snapshot)


def main(argv):
    parser = argparse.ArgumentParser(description="Observe and atomically refresh the local maintainer board")
    parser.add_argument("--repo", default=".", help="explicit canonical tracker repository")
    parser.add_argument("--json", action="store_true", help="emit JSON to stdout")
    parser.add_argument("--ticket-id", action="append", help="exact Ticket key; repeatable")
    parser.add_argument("--visible-items", type=int, default=DEFAULT_VISIBLE_ITEMS, help="initial cards visible per bucket, 1..100")
    parser.add_argument("--html", nargs="?", const="", help="refresh one self-contained HTML artifact")
    args = parser.parse_args(argv)
    try:
        options = effective_options(args.visible_items)
        html_output = None
        if args.html:
            html_output = Path(args.html)
        elif args.html is not None or not args.json:
            html_output = repo_root(args.repo) / DEFAULT_HTML_PATH
        if html_output is not None:
            result = refresh(args.repo, html_output, args.ticket_id, options)
            if not result["ok"]:
                print(json.dumps({"schema": REFRESH_SCHEMA, **result}, sort_keys=True))
                return 2
            if args.json:
                emit_json({**result["snapshot"], "refresh": {key: value for key, value in result.items() if key != "snapshot"}})
            else:
                print(result["path"])
        else:
            emit_json(build_snapshot(args.repo, args.ticket_id))
    except Exception as error:
        print(json.dumps(dict(schema=REFRESH_SCHEMA, ok=False, status="failed", persisted=False, error=dict(code=getattr(error, "code", "refresh-failed"), detail=str(error))), sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
