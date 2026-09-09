#!/usr/bin/env python3
"""Copy native root/descendant rollouts and index actual tool calls; no prose grades."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def rows(path):
    for line in path.read_text().splitlines():
        try: yield json.loads(line)
        except ValueError: continue


def parent_ids(value):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('parent_thread_id', 'parent_session_id') and isinstance(item, str): found.add(item)
            else: found.update(parent_ids(item))
    elif isinstance(value, list):
        for item in value: found.update(parent_ids(item))
    return found


p = argparse.ArgumentParser(); p.add_argument('output', type=Path); p.add_argument('--sessions', required=True, type=Path); a = p.parse_args()
events = list(rows(a.output / 'root.jsonl'))
roots = [e['thread_id'] for e in events if e.get('type') == 'thread.started']
if len(roots) != 1: raise SystemExit('exactly one root thread.started event required')
index = {}
for path in a.sessions.rglob('*.jsonl'):
    with path.open() as stream:
        try: meta = json.loads(next(stream)).get('payload', {})
        except (ValueError, StopIteration): continue
    identity = meta.get('id') or meta.get('session_id')
    if identity: index[identity] = (path, meta)
selected = {roots[0]}
while True:
    new = {key for key, (_, meta) in index.items() if parent_ids(meta) & selected}
    if new <= selected: break
    selected.update(new)
trace_dir = a.output / 'native-traces'; trace_dir.mkdir(exist_ok=True)
report = {'root': roots[0], 'missing_rollouts': sorted(selected - index.keys()), 'sessions': [], 'observed_spawn_calls': 0, 'child_evidence': 'unavailable unless metadata-linked native descendants are present'}
for identity in sorted(selected & index.keys()):
    path, meta = index[identity]; destination = trace_dir / path.name; shutil.copy2(path, destination)
    calls, usage, contexts = [], None, []
    for row in rows(path):
        payload = row.get('payload', {})
        if row.get('type') == 'turn_context':
            contexts.append({k: payload.get(k) for k in ('model', 'effort', 'reasoning_effort', 'approval_policy', 'sandbox_policy')})
        if row.get('type') == 'response_item' and payload.get('type') in ('function_call', 'custom_tool_call', 'function_call_output', 'custom_tool_call_output'):
            calls.append({'timestamp': row.get('timestamp'), **payload})
            if payload.get('name', '').split('.')[-1] == 'spawn_agent':
                report['observed_spawn_calls'] += 1
        if payload.get('type') == 'token_count' and isinstance(payload.get('info'), dict):
            usage = payload['info'].get('total_token_usage')
    target = trace_dir / (identity + '-tools.json'); target.write_text(json.dumps(calls, indent=2) + '\n')
    report['sessions'].append({'id': identity, 'parent_ids': sorted(parent_ids(meta)), 'cli_version': meta.get('cli_version'), 'native_rollout': str(destination), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'turn_contexts': contexts, 'actual_total_token_usage': usage, 'tool_records': len(calls)})
report['metadata_linked_descendants'] = len((selected & index.keys()) - {roots[0]})
if report['observed_spawn_calls'] and not report['metadata_linked_descendants']:
    report['child_evidence'] = 'UNAVAILABLE: native spawn observed but no metadata-linked child rollout; root logs do not prove child writes or total tokens'
(a.output / 'trace-index.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
