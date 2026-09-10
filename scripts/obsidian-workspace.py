#!/usr/bin/env python3
"""Disposable Obsidian projection of the shared, read-only Tracker Snapshot.

Home.md is the sole atomic publication point. It binds refresh status to immutable
project generations; a failed project retains its last successful generation.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import quote
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/engineering/ultra/scripts'))
import tracker_snapshot as query

RENDERER_VERSION = 'obsidian-workspace/v1'
STATE_MARKER = '<!-- obsidian-workspace-state:'


def serialized(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(serialized(value).encode()).hexdigest()


def label(value):
    # Entity data cannot create Markdown structure, checkboxes, HTML or links.
    text = str(value).replace('\n', ' ').replace('\r', ' ')
    return ''.join('&#' + str(ord(character)) + ';' if character in '\\`*_{}[]()#+-.!|' else html.escape(character, quote=True) for character in text)



def detail(name, value):
    return label(name) + ': ' + label(serialized(value) if isinstance(value, (dict, list)) else value)


def link(title, path):
    return '[' + label(title) + '](' + quote(str(path), safe='/._-') + ')'


def read_state(home):
    text = home.read_text()
    match = re.search(re.escape(STATE_MARKER) + r'([0-9a-f]+) -->', text)
    if not match:
        raise ValueError('Home.md has no recognized workspace state; refusing to replace it')
    state = json.loads(bytes.fromhex(match.group(1)))
    if state.get('schema') != 'obsidian-workspace-state/v1':
        raise ValueError('unsupported workspace state')
    return state


def validate_config(config):
    if set(config) - {'vault', 'generated', 'projects'}:
        raise ValueError('unknown workspace configuration field')
    vault_input = Path(config['vault']).expanduser()
    if not vault_input.is_absolute() or not vault_input.is_dir():
        raise ValueError('select one existing absolute vault path')
    vault = vault_input.resolve()
    generated = Path(config.get('generated', 'tracker-generated/asc09'))
    if generated.is_absolute() or not generated.parts or any(p in ('.', '..', '.obsidian') for p in generated.parts):
        raise ValueError('generated must name a dedicated relative cache directory')
    root = vault / generated
    if root.resolve() != root:
        raise ValueError('generated path must not traverse symlinks')
    projects = config['projects']
    if not isinstance(projects, list) or not projects:
        raise ValueError('configure at least one explicit project binding')
    seen = set()
    normalized = []
    for project in projects:
        if set(project) - {'id', 'repository', 'selection'}:
            raise ValueError('unknown project binding field')
        identity = project['id']
        if not isinstance(identity, str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', identity) or identity in seen:
            raise ValueError('project IDs must be unique lowercase safe names')
        seen.add(identity)
        repo = Path(project['repository']).expanduser()
        if not repo.is_absolute():
            raise ValueError('repository must be an explicit absolute canonical checkout')
        normalized.append(dict(id=identity, repository=str(repo.resolve()), selection=query.normalize_selection(project.get('selection'))))
    return root, sorted(normalized, key=lambda p: p['id'])


class Navigation:
    def __init__(self, repo, directory):
        self.repo = Path(repo)
        self.directory = directory

    def source(self, title, locator):
        # Only exact source paths supplied by Snapshot; never search by basename.
        target = (self.repo / locator).resolve()
        if not target.is_relative_to(self.repo) or not target.is_file():
            return label(title) + ' (source unavailable: ' + label(locator) + ')'
        name = 'sources/' + digest([str(self.repo), locator]) + '.md'
        alias = self.directory / name
        alias.parent.mkdir(exist_ok=True)
        if not alias.is_symlink():
            alias.symlink_to(target)
        return link(title, name)


def context_link(navigation, reference, source_locator, relative=False):
    if not reference:
        return ''
    # Snapshot retains explicit Parent Markdown syntax. Interpret its link only,
    # never Ticket metadata, blockers, publication or receipt lifecycle prose.
    match = re.fullmatch(r'\[([^]]*)\]\((.*)\)', reference)
    title, target = match.groups() if match else ('Source', reference.strip('`'))
    if target.startswith(('https://', 'http://')):
        return '[' + label(title) + '](' + quote(target, safe=':/?=&%._~-') + ')'
    locator = str(Path(source_locator).parent / target) if relative else target
    return navigation.source(title, locator)


def ticket_card(ticket, navigation, tickets, receipts):
    parts = [navigation.source(ticket['key'] + ' · ' + ticket['title'], ticket['source_locator']),
             detail('Canonical identity', ticket['locator']),
             detail('Ticket state', ticket['state']),
             detail('Claimable', ticket['eligibility']['claimable']),
             detail('Eligibility reasons', ticket['eligibility']['reasons'])]
    for name, value in (('Publication', ticket.get('publication')), ('Claim', ticket.get('claim')),
                        ('Feature', ticket.get('feature')), ('Category', ticket.get('category')),
                        ('Created', ticket.get('created'))):
        if value:
            parts.append(detail(name, value))
    contract = ticket.get('contract', {})
    parts.append(detail('Completed Ticket', contract.get('completed', False)))
    for field, relative in (('parent', True), ('source_spec', False)):
        if contract.get(field):
            parts.append(context_link(navigation, contract[field], ticket['source_locator'], relative))
    for blocker in ticket.get('blockers', []):
        parts.append(detail('Dependency', blocker))
        target = tickets.get(blocker.get('ticket_key'))
        if target:
            parts.append(navigation.source('Dependency ' + target['key'], target['source_locator']))
    for relation in ticket.get('receipt_relations', []):
        parts.append(detail('Receipt relation', relation))
        target = receipts.get(relation.get('receipt_key'))
        if target:
            parts.append(navigation.source('Receipt', target['locator']))
    for item in ticket['diagnostics']:
        parts.append(detail('Diagnostic', item))
    return '<br>'.join(parts)


def receipt_card(receipt, navigation, tickets):
    parts = [navigation.source(receipt.get('title') or receipt['key'], receipt['locator']),
             detail('Canonical receipt', receipt['key']),
             detail('Outcome', receipt.get('outcome')), detail('Receipt state', receipt.get('state')),
             'Human acceptance: not established by this projection; consult canonical owner',
             detail('Landing evidence', {key: receipt.get(key) for key in ('merge', 'merged_at', 'merged_sha')}),
             detail('Cleanup evidence', {key: receipt.get(key) for key in ('cleanup_done', 'resource_cleanup')}),
             detail('Operation observations', receipt['operation_readiness'])]
    for name in ('checks', 'review', 'head', 'head_sha', 'base', 'base_sha', 'worktree', 'refs_ok', 'ref_reason',
                 'body_conflict', 'resource_ownership', 'retained_resources', 'retained_resource_identities',
                 'recovery_action', 'blocker_or_requested_information', 'successor_relation', 'handoff_consistency',
                 'legacy_terminal_outcome', 'closed_candidate_terminal', 'created_at', 'closed_at', 'diagnostics'):
        if receipt.get(name) is not None:
            parts.append(detail(name, receipt[name]))
    if receipt.get('source_spec'):
        parts.append(context_link(navigation, receipt['source_spec'], receipt['locator']))
    for relation in receipt.get('ticket_relations', []):
        parts.append(detail('Ticket relation', relation))
        ticket = tickets.get(relation.get('ticket_key'))
        if ticket:
            parts.append(navigation.source('Ticket ' + ticket['key'], ticket['source_locator']))
    for name in ('supersedes', 'superseded_by'):
        if receipt.get(name):
            parts.append(navigation.source(name, receipt[name]))
    return '<br>'.join(parts)


def render_project(snapshot, project, directory):
    navigation = Navigation(project['repository'], directory)
    tickets = {item['key']: item for item in snapshot['tickets']}
    receipts = {item['key']: item for item in snapshot['receipts']}
    work = {name: [] for name in ('Claimable', 'Claimed', 'Needs human', 'Other work', 'Completed Tickets')}
    attention = {'Observation': [], 'Tickets': [], 'Receipts': []}
    for ticket in tickets.values():
        card = ticket_card(ticket, navigation, tickets, receipts)
        if ticket.get('contract', {}).get('completed'):
            lane = 'Completed Tickets'
        elif ticket['eligibility']['claimable']:
            lane = 'Claimable'
        elif ticket.get('claim', {}).get('active'):
            lane = 'Claimed'
        elif ticket['state'] in ('needs-info', 'ready-for-human'):
            lane = 'Needs human'
        else:
            lane = 'Other work'
        work[lane].append(card)
        if ticket['diagnostics'] or ticket['eligibility']['reasons'] and lane != 'Completed Tickets':
            attention['Tickets'].append(card)
    delivery = {name: [] for name in ('Candidates', 'Recovery', 'Closed and historical')}
    for receipt in receipts.values():
        card = receipt_card(receipt, navigation, tickets)
        lane = 'Closed and historical' if receipt.get('state') == 'closed' else 'Candidates' if receipt.get('outcome') == 'candidate' else 'Recovery'
        delivery[lane].append(card)
        # Receipt operations are separate observations; include all in Attention
        # so cleanup/manual/readiness diagnostics are never hidden by outcome lanes.
        attention['Receipts'].append(card)
    for item in snapshot['diagnostics']:
        attention['Observation'].append(detail('Diagnostic', item))
    attention['Observation'] += [detail('Source observations', snapshot['sources']), detail('Summary', snapshot['summary']),
                                 detail('Exact selection', snapshot['selection'])]
    observation = [link('Home — latest refresh result', '../../../Home.md'),
                   detail('Project namespace', project['id']), detail('Repository', project['repository']),
                   detail('Source fingerprint', snapshot['source_fingerprint']),
                   detail('Snapshot schema', snapshot['schema_version']), detail('Snapshot semantics', snapshot['semantic_version']),
                   detail('Renderer', RENDERER_VERSION), detail('Selection', snapshot['selection']),
                   'Snapshot incomplete: ' + str(snapshot['summary']['incomplete']),
                   'Last successful observation only; currentness unknown until refresh. Check Home for latest failure status.',
                   'Generated cards and dragging are disposable. Canonical operation owners recheck all mutation gates.']
    for name, lanes in (('Work', work), ('Delivery', delivery), ('Attention', attention)):
        lines = ['---', 'kanban-plugin: board', '---', '', '## Workspace', '', '- [ ] ' + '<br>'.join(observation), '']
        for lane, cards in lanes.items():
            lines += ['## ' + lane, '', *('- [ ] ' + card for card in cards), '']
        (directory / (name + '.md')).write_text('\n'.join(lines), encoding='utf-8')


def manifest(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        key = path.relative_to(directory).as_posix()
        if path.is_symlink():
            result[key] = {'target': os.readlink(path)}
        elif path.is_file():
            result[key] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def intact(root, good):
    directory = root / good['directory']
    return directory.is_dir() and manifest(directory) == good['manifest']


def generate(root, snapshot, project, good):
    generation = 'generations/' + uuid.uuid4().hex + '/' + project['id']
    directory = root / generation
    directory.mkdir(parents=True)
    try:
        render_project(snapshot, project, directory)
        files = manifest(directory)
        signature = digest([RENDERER_VERSION, snapshot['schema_version'], snapshot['semantic_version'], project])
        if good and good['source_fingerprint'] == snapshot['source_fingerprint'] and good['render_signature'] == signature and files == good['manifest'] and intact(root, good):
            shutil.rmtree(directory.parent)
            return good
        # Finish all contents before Home can reference this generation.
        for path in directory.rglob('*.md'):
            if not path.is_symlink():
                with path.open('rb') as handle:
                    os.fsync(handle.fileno())
        return dict(source_fingerprint=snapshot['source_fingerprint'], selection=project['selection'],
                    render_signature=signature, directory=generation, manifest=files,
                    schema_version=snapshot['schema_version'], semantic_version=snapshot['semantic_version'],
                    views={name: generation + '/' + name + '.md' for name in ('Work', 'Delivery', 'Attention')})
    except BaseException:
        shutil.rmtree(directory.parent)
        raise


def atomic_write(path, content):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix='.refresh-', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def home_text(state):
    lines = ['# Tracker Workspace', '', 'Generated disposable cache. Personal notes belong outside this directory.', '',
             'Latest refresh result: ' + state['result'],
             'Currentness: unknown until another observation. Operation owners recheck gates at mutation time.', '']
    for identity, project in state['projects'].items():
        lines += ['## ' + label(identity), '', detail('Repository', project['repository']), '',
                  detail('Latest refresh', project['status']), '', detail('Attempted selection', project['attempted_selection']), '']
        if project.get('retained_integrity'):
            lines += [detail('Retained content integrity', project['retained_integrity']), '']
        if project.get('error'):
            lines += [detail('Error', project['error']), '', 'Currentness unknown; last successful content retained.', '']
        good = project.get('last_success')
        if good:
            lines += [detail('Last successful observation', good['source_fingerprint']), '',
                      detail('Selection', good['selection']), '', detail('Render signature', good['render_signature']), '',
                      ' · '.join(link(view, path) for view, path in sorted(good['views'].items())), '']
        else:
            lines += ['No successful observation available.', '']
    lines.append(STATE_MARKER + serialized(state).encode().hex() + ' -->\n')
    return '\n'.join(lines)


def refresh(config):
    root, projects = validate_config(config)
    root.mkdir(parents=True, exist_ok=True)
    for name in ('.refresh.lock', 'Home.md', 'generations'):
        if (root / name).is_symlink():
            raise ValueError('managed cache paths must not be symlinks: ' + name)
    if not (root / 'Home.md').exists() and any(root.iterdir()):
        # A failed first run can leave our lock/generations, but never adopt notes.
        if any(path.name not in {'.refresh.lock', 'generations'} for path in root.iterdir()):
            raise ValueError('generated directory contains unowned content')
    with (root / '.refresh.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        home = root / 'Home.md'
        previous = read_state(home) if home.exists() else {'projects': {}}
        state = {'schema': 'obsidian-workspace-state/v1', 'projects': {}}
        for project in projects:
            identity = project['id']
            prior = previous['projects'].get(identity, {})
            good = prior.get('last_success') if prior.get('repository') == project['repository'] else None
            entry = dict(repository=project['repository'], attempted_selection=project['selection'], status='success', last_success=good)
            try:
                snapshot = query.snapshot(Path(project['repository']), project['selection'])
                entry['last_success'] = generate(root, snapshot, project, good)
            except (OSError, RuntimeError, ValueError) as error:
                entry.update(status='failed', error=str(error))
                if good:
                    try:
                        if not intact(root, good):
                            entry['retained_integrity'] = 'damaged; last-success fingerprint does not certify edited cache'
                    except OSError as integrity_error:
                        entry['retained_integrity'] = 'unreadable; ' + str(integrity_error)
            state['projects'][identity] = entry
        failures = sum(item['status'] == 'failed' for item in state['projects'].values())
        state['result'] = 'success' if not failures else 'failed' if failures == len(projects) else 'partial failure'
        try:
            content = home_text(state)
            if not home.exists() or home.read_text() != content:
                atomic_write(home, content)
        except OSError as error:
            return dict(ok=False, persisted=False, error=str(error))
        return dict(ok=not failures, persisted=True, status=state['result'], home=str(home))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path, help='JSON: one vault, generated directory, explicit project bindings')
    args = parser.parse_args()
    try:
        result = refresh(json.loads(args.config.read_text()))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        result = dict(ok=False, persisted=False, error=str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    sys.exit(main())
