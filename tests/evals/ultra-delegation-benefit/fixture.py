#!/usr/bin/env python3
"""Bounded paired ASC-04 fixtures; reuse stage-ownership final-state pattern."""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
POLICY = 'skills/engineering/ultra/solve.md'
TRACKER = 'skills/engineering/ultra/scripts/ultra_tracker.py'
CASES = {
    'local': ('Trim surrounding whitespace in display_name; preserve internal spaces and Unicode.', ['app/display.py']),
    'cross-module': ('Expose invoice totals through service.invoice: quantities multiply unit cents, subtotal is summed, discount is an integer percentage rounded down in cents, total is subtotal minus discount. Preserve input rows. Reject negative quantity, negative cents, and discount outside 0..100 with ValueError.', ['app/pricing.py', 'app/service.py']),
    'diagnosis': ('A cached account total returns another tenant\'s value when account ids collide, and remains stale after add. Diagnose from app/cache.py and app/store.py, repair both observable defects, and record the reproducer and causal explanation in diagnosis.md. Missing accounts return zero.', ['app/cache.py', 'app/store.py', 'diagnosis.md']),
    'permission': ('Repair document publication: only the owner with editor role may publish a draft. Published documents cannot be published again. Unauthorized or invalid transitions raise PermissionError or ValueError respectively, without mutating the document. Return the published copy and preserve the input.', ['app/permissions.py', 'app/documents.py']),
    'worker-failure': ('Repair bulk_summary to count values and sum integer values, including negatives and an empty list. Required environment preflight is python3 scripts/preflight.py before application edits. A preflight failure ends the current assigned stage; the active writer must stop and relinquish its assignment, without retrying. The coordinator may inspect that failure, verify the writer stopped, and resume the same Attempt once. Report a concrete blocker if no recovery is possible.', ['app/summary.py']),
}
BASE = {
'app/__init__.py': '',
'app/display.py': 'def display_name(value):\n    return value\n',
'app/pricing.py': 'def calculate(rows, discount):\n    return {"subtotal": 0, "total": 0}\n',
'app/service.py': 'from app.pricing import calculate\ndef invoice(rows, discount=0):\n    return {"total": 0}\n',
'app/cache.py': 'values = {}\ndef key(tenant, account):\n    return account\n',
'app/store.py': 'from app.cache import values, key\nrows = {}\ndef add(tenant, account, amount):\n    rows.setdefault((tenant, account), []).append(amount)\ndef total(tenant, account):\n    k = key(tenant, account)\n    if k not in values:\n        values[k] = sum(rows.get((tenant, account), []))\n    return values[k]\n',
'app/permissions.py': 'def may_publish(doc, actor):\n    return actor["role"] == "editor"\n',
'app/documents.py': 'from app.permissions import may_publish\ndef publish(doc, actor):\n    if not may_publish(doc, actor):\n        raise PermissionError("forbidden")\n    doc["state"] = "published"\n    return doc\n',
'app/summary.py': 'def bulk_summary(values):\n    return {"count": 0, "sum": 0}\n',
}
CHECKS = {
'local': '''from app.display import display_name
for raw, expected in [("  Alice  ", "Alice"), ("a  b", "a  b"), ("\\t李 四\\n", "李 四"), ("", "")]:
    assert display_name(raw) == expected
''',
'cross-module': '''from app.service import invoice
from copy import deepcopy
for rows, discount in [([], 0), ([{"quantity": 3, "unit_cents": 101}], 33), ([{"quantity": 2, "unit_cents": 40}, {"quantity": 1, "unit_cents": 21}], 100)]:
    before = deepcopy(rows); subtotal = sum(r["quantity"] * r["unit_cents"] for r in rows)
    assert invoice(rows, discount) == {"subtotal": subtotal, "total": subtotal - subtotal * discount // 100}
    assert rows == before
for rows, discount in [([{"quantity": -1, "unit_cents": 1}], 0), ([{"quantity": 1, "unit_cents": -1}], 0), ([], -1), ([], 101)]:
    try: invoice(rows, discount)
    except ValueError: pass
    else: raise AssertionError("invalid invoice accepted")
''',
'diagnosis': '''from app.store import add, total
assert total("empty", "id") == 0
add("a", "id", 3); add("b", "id", 8)
assert total("a", "id") == 3 and total("b", "id") == 8
add("a", "id", -1)
assert total("a", "id") == 2 and total("b", "id") == 8
assert len(open("diagnosis.md").read().strip()) > 80
''',
'permission': '''from app.documents import publish
from copy import deepcopy
for actor in [{"id": "owner", "role": "reader"}, {"id": "other", "role": "editor"}]:
    doc = {"owner": "owner", "state": "draft"}; before = deepcopy(doc)
    try: publish(doc, actor)
    except PermissionError: pass
    else: raise AssertionError("unauthorized publication")
    assert doc == before
actor = {"id": "owner", "role": "editor"}
doc = {"owner": "owner", "state": "draft"}
assert publish(doc, actor) == {"owner": "owner", "state": "published"}
assert doc["state"] == "draft"
for state in ["published", "archived"]:
    doc = {"owner": "owner", "state": state}
    try: publish(doc, actor)
    except ValueError: pass
    else: raise AssertionError("invalid transition")
    assert doc["state"] == state
''',
'worker-failure': '''from app.summary import bulk_summary
for values in [[], [3, -4, 7], [0], list(range(30))]:
    assert bulk_summary(values) == {"count": len(values), "sum": sum(values)}
''',
}


# A richer, symptom-driven follow-up; original diagnosis remains a microtask smoke.
CASES['diagnosis-v2'] = (
    'The report service sometimes returns the wrong balance after successful ingestion. '
    'Reproduce and diagnose using support/replay.json and the existing pipeline. '
    'Required contract: event ids are unique within a tenant; retrying an identical event is idempotent; '
    'accounts are tenant-scoped; a report reflects every successfully accepted event immediately; '
    'a correction supersedes the earlier event with the same id and higher revision, while an older revision is ignored. '
    'Zero amounts are valid. Do not change the public ingest/report signatures. '
    'Repair the observed failures and explain each causal chain and discriminating reproducer in diagnosis.md.',
    ['app/events.py', 'app/projection.py', 'app/reports.py', 'diagnosis.md'])
DIAG_BASE = {
'app/events.py': '''events = {}
generations = {}
def ingest(event):
    key = event["id"]
    old = events.get(key)
    if old is not None:
        return False
    events[key] = dict(event)
    generations[event["account"]] = generations.get(event["account"], 0) + 1
    return True
''',
'app/projection.py': '''from app.events import events
def project(tenant, account):
    return sum(e["amount"] for e in events.values() if e["tenant"] == tenant and e["account"] == account)
''',
'app/reports.py': '''from app.events import generations
from app.projection import project
cache = {}
def report(tenant, account):
    generation = generations.get(account, 0)
    if account not in cache:
        cache[account] = (generation, project(tenant, account))
    return {"balance": cache[account][1]}
''',
'support/replay.json': '''{"requests":[
{"op":"ingest","tenant":"west","account":"42","id":"e1","revision":1,"amount":7},
{"op":"report","tenant":"west","account":"42","expected":7},
{"op":"ingest","tenant":"east","account":"42","id":"e1","revision":1,"amount":19},
{"op":"report","tenant":"east","account":"42","expected":19},
{"op":"ingest","tenant":"west","account":"42","id":"e1","revision":2,"amount":11},
{"op":"report","tenant":"west","account":"42","expected":11}
],"observed":"HTTP requests succeed, but east shows west balance and west correction is not visible"}
''',
}
CHECKS['diagnosis-v2'] = '''from app.events import ingest
from app.reports import report
def event(t, a, i, r, value): return {"tenant": t, "account": a, "id": i, "revision": r, "amount": value}
assert report("west", "42") == {"balance": 0}
a = event("west", "42", "e1", 1, 7)
assert ingest(a) is True
assert report("west", "42") == {"balance": 7}
assert ingest(dict(a)) is False
assert ingest(event("east", "42", "e1", 1, 19)) is True
assert report("east", "42") == {"balance": 19}
assert report("west", "42") == {"balance": 7}
assert ingest(event("west", "42", "e1", 2, 11)) is True
assert report("west", "42") == {"balance": 11}
assert ingest(a) is False
assert report("west", "42") == {"balance": 11}
assert ingest(event("west", "42", "e2", 1, -3)) is True
assert report("west", "42") == {"balance": 8}
assert ingest(event("east", "other", "e2", 1, 0)) is True
assert report("east", "other") == {"balance": 0}
assert report("east", "42") == {"balance": 19}
assert len(open("diagnosis.md").read().strip()) > 80
'''


def run(repo, *args):
    return subprocess.check_output(args, cwd=repo, text=True, stderr=subprocess.PIPE).strip()


def write(repo, path, value):
    target = repo / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(value)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_policy(text):
    start = text.index('Direct implementation is the narrow branch.')
    end = text.index('The root always retains sequencing', start)
    text = text[:start] + '''Choose implementation ownership by expected benefit at the Checkpoint. Root implementation is allowed when delegation adds no material parallel progress, useful context isolation, or independent judgment. Use one bounded implementation subagent when one of those benefits exceeds coordination cost and runtime capability plus verified worktree identity are available. Record the selected benefit or direct-execution rationale from current evidence; uncertainty alone does not mandate a worker.

A delegated implementation subagent is the only active writer in its verified assigned worktree until explicit handoff. Root waits for completion or a confirmed stopped writer, then re-reads actual changes and integrates. Separate independent worktrees may run in parallel; dependent or shared-worktree stages remain serialized. Missing implementation delegation, unverifiable worktree, an active writer, or required concurrent non-namespaced shared mutation requires a recorded safe fallback; never write concurrently with an active writer.

For read-only exploration and verification use delegation when its expected benefit exceeds cost. Preserve all risk-proportional independent acceptance requirements: choosing root implementation never waives required independent judgment. The coordinator retains canonical gates and final responsibility.

''' + text[end:]
    old = 'Direct root implementation requires positive evidence that the Ticket is simple, familiar, local, low-risk, fully specified, and obviously verifiable. Existing high-quality exploration in the active context may satisfy part of that evidence and avoid duplicate fan-out. A clear local fix alone is not enough.'
    assert old in text
    text = text.replace(old, 'Choose direct or delegated implementation using the benefit-based Stage Ownership rule above. Existing exploration can supply current evidence; preserve applicable independent acceptance regardless of implementation ownership.')
    old = 'docs/config-only work is direct only when all six direct-branch properties have positive current evidence.'
    assert old in text
    return text.replace(old, 'docs/config-only work follows the same benefit-based Stage Ownership decision.')


def prepare(output, case, policy):
    output.mkdir(parents=True, exist_ok=False)
    repo = output / 'repo'; repo.mkdir()
    # Copy the complete actual catalog, not the former four-file stub.
    for prefix in ('skills', 'docs/agents'):
        for name in run(ROOT, 'git', 'ls-files', prefix).splitlines():
            source = ROOT / name
            if source.is_file():
                target = repo / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    # Tracker docs are canonical ignored local sources in this catalog.
    docs = Path(__file__).resolve().parent / 'tracker-context'
    for source in docs.rglob('*.md'):
        target = repo / 'docs/agents' / source.relative_to(docs)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    if policy == 'benefit': write(repo, POLICY, candidate_policy((repo / POLICY).read_text()))
    for path, value in BASE.items(): write(repo, path, value)
    if case == 'diagnosis-v2':
        for path, value in DIAG_BASE.items(): write(repo, path, value)
    write(repo, '.gitignore', '.scratch/\n__pycache__/\n')
    write(repo, 'scripts/check.py', 'import sys\nfrom pathlib import Path\nsys.dont_write_bytecode = True\nsys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n' + CHECKS[case] + '\nprint("checks passed")\n')
    write(repo, 'scripts/preflight.py', '''from pathlib import Path
import subprocess
common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"], text=True).strip()
marker = Path(common).resolve() / "eval-preflight-consumed"
if not marker.exists():
    marker.write_text("injected once\\n")
    raise SystemExit("INJECTED_WORKER_STAGE_FAILURE: stop assigned stage and relinquish writer; coordinator may resume once")
print("preflight recovered")
''')
    write(repo, 'AGENTS.md', '''# Disposable ASC-04 fixture
Use only this repository's embedded skills and tracker documents; do not substitute personal installed skill sources. Start at skills/engineering/ultra/SKILL.md and solve.md. All their runtime dependencies are included. Selected Ticket: .scratch/eval/issues/EVAL.md. Resolve the canonical tracker from this original checkout. Main is protected: no merge, push, deploy, or cleanup. Application scope is the Ticket's explicit file allowlist; tests, policy and fixture configuration are immutable. Run python3 scripts/check.py. Native delegation is available; use the selected embedded policy for routing. Preserve one active writer per worktree, root integration and all canonical Claim/handoff gates. State, permissions, data and recovery work require one read-only independent acceptance pass. Keep all worktrees below the fixture's parent directory. No external services are required.
''')
    write(repo, '.scratch/eval/reference.md', 'Approved scope: complete only the selected Ticket. No landing authorization.\n')
    body, allowed = CASES[case]
    write(repo, '.scratch/eval/issues/EVAL.md', f'Status: review-pending\nTicket ID: EVAL\nPublication Run: eval\nSource Spec: .scratch/eval/reference.md\n\n# {case}\n\n## What to build\n{body}\n\n## Acceptance criteria\n- Only modify: {", ".join(allowed)}.\n- All requirements above and python3 scripts/check.py pass.\n- Finalize a candidate with canonical facade and retained worktree, without advancing main.\n')
    run(repo, 'git', 'init', '-q', '-b', 'main'); run(repo, 'git', 'config', 'user.name', 'ASC Eval'); run(repo, 'git', 'config', 'user.email', 'eval@example.invalid')
    run(repo, 'git', 'add', '.'); run(repo, 'git', 'commit', '-qm', 'fixture baseline')
    initial = run(repo, 'git', 'rev-parse', 'HEAD')
    for verb in ('register', 'promote'):
        result = run(repo, sys.executable, TRACKER, 'publication', verb, '--run-id', 'eval', '--location', '.scratch/eval/issues')
        write(output, f'prepare-{verb}.json', result + '\n')
    frontier = run(repo, sys.executable, TRACKER, 'ticket', 'frontier', '--ticket-id', 'EVAL')
    write(output, 'prepare-frontier.json', frontier + '\n')
    oracle = dict(case=case, policy=policy, initial=initial, allowed=allowed, files={p: digest(repo / p) for p in run(repo, 'git', 'ls-files').splitlines()}, source_sha=run(ROOT, 'git', 'rev-parse', 'HEAD'), check=CHECKS[case])
    write(output, 'oracle.json', json.dumps(oracle, indent=2) + '\n')
    (output / 'oracle.json').chmod(0o444)
    write(output, 'prompt.md', 'Read AGENTS.md and execute /ultra solve .scratch/eval/issues/EVAL.md. Complete the Ticket and canonical outcome handoff, retaining the candidate for inspection.\n')
    print(output)


def grade(output):
    output = output.resolve()
    oracle = json.loads((output / 'oracle.json').read_text()); repo = output / 'repo'; errors = []
    def require(ok, message):
        if not ok: errors.append(message)
    require(run(repo, 'git', 'rev-parse', 'main') == oracle['initial'], 'main changed')
    spec = importlib.util.spec_from_file_location('asc_records', ROOT / 'skills/engineering/solve-records/scripts/solve-records.py')
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    receipts = [r for r in helper.discover(repo) if '.scratch/eval/issues/EVAL.md' in r.get('issues', [])]
    require(len(receipts) == 1, 'exactly one linked canonical receipt required')
    receipt = receipts[0] if len(receipts) == 1 else {}
    require(receipt.get('issues') == ['.scratch/eval/issues/EVAL.md'], 'receipt membership differs from exact Ticket scope')
    require(not run(repo, 'git', 'status', '--porcelain'), 'canonical checkout is dirty')
    for path, sha in oracle['files'].items():
        require((repo / path).is_file() and digest(repo / path) == sha, 'canonical initial content changed: ' + path)
    require(receipt.get('outcome') == 'candidate' and receipt.get('state') == 'open' and not receipt.get('malformed'), 'open valid candidate missing')
    registered = run(repo, 'git', 'worktree', 'list', '--porcelain').split('\n\n')
    matches = [block.splitlines()[0][9:] for block in registered if ('branch refs/heads/' + receipt.get('head', '<missing>')) in block.splitlines()]
    require(len(matches) == 1, 'candidate branch lacks one registered worktree')
    candidate = Path(matches[0]) if len(matches) == 1 else output / 'missing-candidate'
    require(candidate.resolve().is_relative_to(output.resolve()), 'candidate outside assigned fixture boundary')
    require(candidate.is_dir(), 'candidate worktree missing')
    if candidate.is_dir():
        head = run(candidate, 'git', 'rev-parse', 'HEAD')
        require(head == receipt.get('head_sha'), 'receipt head mismatch')
        require(run(candidate, 'git', 'merge-base', oracle['initial'], 'HEAD') == oracle['initial'], 'candidate does not descend from initial base')
        require(Path(run(candidate, 'git', 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve() == (repo / '.git').resolve(), 'candidate belongs to different Git repository')
        changed = set(run(candidate, 'git', 'diff', '--name-only', oracle['initial'], 'HEAD').splitlines())
        require(bool(changed) and changed <= set(oracle['allowed']), 'committed scope violation or no work')
        require(not run(candidate, 'git', 'status', '--porcelain'), 'candidate is dirty')
        for path, sha in oracle['files'].items():
            if path not in oracle['allowed']:
                require((candidate / path).is_file() and digest(candidate / path) == sha, 'protected candidate file changed: ' + path)
                require((repo / path).is_file() and digest(repo / path) == sha, 'protected canonical file changed: ' + path)
        # Never execute a model-editable checker as the final oracle.
        result = subprocess.run([sys.executable, '-B', '-c', oracle['check']], cwd=candidate, text=True, capture_output=True)
        require(result.returncode == 0, 'external behavioral oracle failed: ' + result.stderr[-1200:])
    ticket = (repo / '.scratch/eval/issues/EVAL.md').read_text()
    sys.path.insert(0, str(ROOT / 'skills/engineering/ultra/scripts'))
    import local_ticket_frontier as frontier
    try:
        contract, _ = frontier.read_contract(repo)
        tickets = frontier.load_tickets(repo, contract)
        selected = [item for item in tickets if item.identity == 'EVAL']
        require(len(selected) == 1 and selected[0].status == contract.completed_state and contract.claim_value not in selected[0].flags, 'Ticket not canonically completed/released')
        require(len(selected) == 1 and selected[0].branch == receipt.get('head') and Path(selected[0].worktree).resolve() == candidate.resolve(), 'retained Ticket assignment differs from candidate')
    except (ValueError, RuntimeError) as error:
        require(False, 'Ticket parser rejected state: ' + str(error))
    import local_outcome_handoff as handoff
    backlink = os.path.relpath(repo / receipt.get('path', 'missing'), repo / '.scratch/eval/issues')
    require(handoff.backlink_count(ticket, backlink) == 1, 'canonical receipt backlink missing or duplicated')
    # No automated claim that prose proves stage ownership or independent review.
    report = dict(case=oracle['case'], policy=oracle['policy'], artifact_passed=not errors, errors=errors, receipt=receipt, trace_review='REQUIRED: native root and child tool traces, writer intervals, independent review, failure relinquish/resume', child_total_tokens=None)
    print(json.dumps(report, indent=2)); return bool(errors)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('action', choices=['prepare', 'grade']); p.add_argument('output', type=Path); p.add_argument('--case', choices=CASES, default='local'); p.add_argument('--policy', choices=['current', 'benefit'], default='current'); a = p.parse_args()
    if a.action == 'prepare': prepare(a.output.resolve(), a.case, a.policy)
    else: raise SystemExit(grade(a.output.resolve()))
