#!/usr/bin/env python3
"""Approved Local Markdown contract changes, owned by publication."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from datetime import datetime, timezone

import local_ticket_publication as pub

SCHEMA = 'ticket-amendment/v1'
HEAD_FIELD = 'Contract Amendment'


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise pub.AdapterError(f'duplicate amendment JSON field: {key}')
        result[key] = value
    return result


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as error:
        raise pub.AdapterError(f'invalid amendment JSON: {path}') from error


def safe_path(repo, value):
    if not isinstance(value, str) or not value:
        raise pub.AdapterError('amendment path is missing')
    path = (repo / value).resolve()
    if not path.is_relative_to(repo):
        raise pub.AdapterError('amendment path escapes canonical repository')
    return path


def head(ticket):
    return pub.one(pub.parse_metadata(ticket.inner), pub.normalize_key(HEAD_FIELD))


def replace_sections(text, replacements, blocker_heading):
    allowed = {'What to build', 'Acceptance criteria', 'Parent', blocker_heading}
    if not isinstance(replacements, dict) or not replacements or set(replacements) - allowed:
        raise pub.AdapterError('amendment replaces must name supported whole contract sections')
    for name, body in replacements.items():
        if not isinstance(body, str) or re.search(r'^#{1,2} ', body, re.M):
            raise pub.AdapterError('replacement must contain section body only')
        matches = list(re.finditer(rf'^## {re.escape(name)}[ \t]*\n.*?(?=^## |\Z)', text, re.M | re.S))
        if len(matches) > 1 or (not body.strip() and name != blocker_heading):
            raise pub.AdapterError(f'ambiguous or empty replacement section: {name}')
        replacement = f'## {name}\n\n{body.strip()}\n\n'
        if matches:
            match = matches[0]
            text = text[:match.start()] + replacement + text[match.end():]
        elif name == blocker_heading:
            text = text.rstrip() + '\n\n' + replacement
        else:
            raise pub.AdapterError(f'replaced clause does not exist: {name}')
    return text


def validate(repo, tickets, journal, recovering=None):
    """Verify one explicit single chain per Ticket, including immutable file bytes."""
    chains = {}
    identities = set()
    audited_paths = {a['path'] for a in journal.get('amendments', [])}
    location = safe_path(repo, journal['location'])
    directory = pub.journal_dir(location, journal['representation']) / 'amendments' / journal['run_id']
    for path in directory.glob('*.json'):
        safe_path(repo, str(path))
        pending = read_json(path)
        if not isinstance(pending, dict):
            raise pub.AdapterError('amendment conflict: malformed amendment file')
        if str(path.relative_to(repo)) not in audited_paths | {recovering} and pending.get('status') != 'draft':
            raise pub.AdapterError('amendment conflict: unpublished approved intent; retry original request')
    for audit in pub.publication_audits(journal):
        if audit['operation'] != 'amendment':
            continue
        path = safe_path(repo, audit.get('path'))
        raw = path.read_text(encoding='utf-8')
        if sha(raw) != audit.get('file_digest'):
            raise pub.AdapterError('amendment conflict: approved file digest changed')
        item = read_json(path)
        required = {'schema', 'id', 'ticket', 'status', 'approval', 'predecessor', 'replaces',
                    'original_text', 'effective_text', 'old_digest', 'new_digest', 'previous_status', 'execution_ticket'}
        if not isinstance(item, dict) or not required.issubset(item):
            raise pub.AdapterError('amendment conflict: malformed approved file')
        chain = chains.setdefault(item['ticket'], [])
        previous = chain[-1]['id'] if chain else None
        if (item['schema'] != SCHEMA or item['status'] != 'approved' or not item['approval'] or
                item['id'] in identities or item['predecessor'] != previous or
                item['ticket'] != audit['ticket_id'] or item['id'] != audit.get('amendment_id') or
                item['old_digest'] != audit['old_digest'] or item['new_digest'] != audit['new_digest'] or
                item['execution_ticket'] != item['ticket']):
            raise pub.AdapterError('amendment conflict: fork, cycle, broken chain or unapproved member')
        identities.add(item['id'])
        chain.append(item)
    for ticket in tickets:
        chain = chains.get(ticket.ticket_id, [])
        if head(ticket) != (chain[-1]['id'] if chain else ''):
            raise pub.AdapterError('amendment conflict: canonical Ticket head differs from approved chain')
    return chains


def facts(repo, ticket, journal):
    chain = validate(repo, [ticket], journal).get(ticket.ticket_id, [])
    directory = pub.journal_dir(safe_path(repo, journal['location']), journal['representation']) / 'amendments' / journal['run_id']
    drafts = []
    for path in sorted(directory.glob('*.json')):
        item = read_json(path)
        if item.get('status') == 'draft' and item.get('ticket') == ticket.ticket_id:
            drafts.append(dict(id=item.get('id'), path=str(path.relative_to(repo)), status='draft'))
    paths = {a['amendment_id']: a['path'] for a in journal.get('amendments', [])}
    return dict(head=chain[-1]['id'] if chain else None, drafts=drafts,
                chain=[dict(id=a['id'], path=paths[a['id']], predecessor=a['predecessor'], status='effective' if a is chain[-1] else 'superseded',
                            approval=a['approval'], replaces=list(a['replaces'])) for a in chain],
                historical_completion=any(a['previous_status'] == 'completed' for a in chain),
                execution_ticket=ticket.ticket_id)


def apply(repo, representation, raw_location, run_id, ticket_id, expected_digest, request_path):
    import local_ticket_frontier as frontier
    if not request_path or not re.fullmatch(r'[0-9a-f]{64}', expected_digest or ''):
        raise pub.AdapterError('amendment requires request and expected SHA-256 digest')
    request = read_json(Path(request_path))
    required = {'id', 'ticket', 'status', 'approval', 'predecessor', 'replaces'}
    if not isinstance(request, dict) or set(request) != required:
        raise pub.AdapterError('amendment request must define exactly id, ticket, status, approval, predecessor, replaces')
    if (not isinstance(request['id'], str) or not pub.SAFE_ID.fullmatch(request['id']) or
            request['ticket'] != ticket_id or request['status'] != 'approved' or
            not isinstance(request['approval'], str) or not request['approval'].strip() or
            (request['predecessor'] is not None and
             (not isinstance(request['predecessor'], str) or not pub.SAFE_ID.fullmatch(request['predecessor'])))):
        raise pub.AdapterError('amendment requires stable identity, exact Ticket and explicit approval')
    with frontier.frontier_lock(repo), pub.stable_mutation_surface(repo, representation, raw_location) as (location, contract):
        journal_path = pub.journal_path(location, representation, run_id)
        journal = pub.read_journal(journal_path)
        if journal.get('phase') != 'promoted':
            raise pub.AdapterError('amendment requires promoted publication')
        tickets = pub.load_tickets_at(location, representation, contract)
        selected = pub.run_tickets(tickets, run_id)
        target = next((t for t in selected if t.ticket_id == ticket_id), None)
        if target is None:
            raise pub.AdapterError('amendment Ticket not in publication')
        path = pub.journal_dir(location, representation) / 'amendments' / run_id / f'{request["id"]}.json'
        safe_path(repo, str(path))
        relative = str(path.relative_to(repo))
        audits = [a for a in journal.get('amendments', []) if a.get('amendment_id') == request['id']]
        if audits:
            pub.validate_against_journal_at(repo, representation, location, run_id, contract)
            stored = read_json(path)
            if len(audits) != 1 or any(stored.get(k) != v for k, v in request.items()) or stored['old_digest'] != expected_digest:
                raise pub.AdapterError('amendment conflict: ID already bound to different request')
            return dict(status='unchanged', amendment=relative, ticket_id=ticket_id)
        current = pub.current_publication_snapshot(journal)
        if current.get(ticket_id) != expected_digest:
            raise pub.AdapterError('amendment conflict: stale expected digest')
        frontier_contract, _ = frontier.read_contract(repo)
        ft = frontier.parse_ticket(repo, target.path, target.text, target.inner_start, target.inner_end, frontier_contract,
                                   ticket_id if representation == 'tickets-file' else '')
        if frontier_contract.claim_value in ft.flags:
            raise pub.AdapterError('amendment conflict: active Attempt must hand off and release Claim first')
        # An existing immutable file is the recoverable intent after an interrupted write.
        pending = path.exists() and read_json(path).get('status') != 'draft'
        if pending:
            stored = read_json(path)
            if any(stored.get(k) != v for k, v in request.items()) or stored.get('old_digest') != expected_digest:
                raise pub.AdapterError('amendment conflict: pending ID bound to different input')
            original = stored['original_text']
        else:
            pub.validate_against_journal_at(repo, representation, location, run_id, contract)
            original = target.inner
        old = pub.ticket_from_inner(target.path, original, 0, len(original), contract)
        if old is None or old.body_digest != expected_digest or (request['predecessor'] or '') != head(old):
            raise pub.AdapterError('amendment conflict: stale predecessor, fork or missing original')
        validate(repo, [old if t.ticket_id == ticket_id else t for t in selected], journal, recovering=relative)
        changed = replace_sections(original, request['replaces'], contract.blocker_heading)
        changed = frontier.replace_or_insert_field(changed, (HEAD_FIELD,), HEAD_FIELD, request['id'])
        changed = pub.replace_metadata_field(changed, target.state_field, frontier_contract.ready_state)
        # Previous checked boxes are evidence for the old contract, never the new one.
        changed = re.sub(r'(?m)^(\s*[-*] )\[[xX]\]', r'\1[ ]', changed).rstrip() + '\n'
        for aliases, canonical in ((frontier_contract.branch_aliases, frontier_contract.branch_field),
                                   (frontier_contract.worktree_aliases, frontier_contract.worktree_field)):
            changed = frontier.replace_or_insert_field(changed, aliases, canonical, '')
        desired = pub.ticket_from_inner(target.path, changed, 0, len(changed), contract)
        if desired is None:
            raise pub.AdapterError('amendment produced invalid Ticket')
        if any(pub.normalize_key(k) in pub.parse_metadata(changed) for k in contract.blocker_fields) and contract.blocker_heading in request['replaces']:
            # Avoid leaving a shadow dependency surface that disagrees with the heading.
            for field in contract.blocker_fields:
                key = pub.normalize_key(field)
                if key in pub.parse_metadata(changed):
                    changed = pub.replace_metadata_field(changed, pub.metadata_spelling(changed, key), '')
            desired = pub.ticket_from_inner(target.path, changed, 0, len(changed), contract)
        hypothetical = [desired if t.ticket_id == ticket_id else t for t in tickets]
        pub.validate_blocker_targets(repo, hypothetical)
        if pub.current_publication_members(journal) != sorted(t.ticket_id for t in selected):
            raise pub.AdapterError('amendment conflict: publication membership drift')
        for t in selected:
            allowed = {expected_digest, desired.body_digest} if t.ticket_id == ticket_id else {current[t.ticket_id]}
            if t.body_digest not in allowed:
                raise pub.AdapterError('amendment conflict: Ticket drift during retry')
        item = dict(request, schema=SCHEMA, original_text=original, effective_text=changed,
                    old_digest=expected_digest, new_digest=desired.body_digest,
                    previous_status=old.status, execution_ticket=ticket_id)
        encoded = json.dumps(item, indent=2, sort_keys=True) + '\n'
        if pending and path.read_text() != encoded:
            raise pub.AdapterError('amendment conflict: pending file does not match derived contract')
        pub.atomic_write(path, encoded)
        if os.environ.get('ULTRA_AMENDMENT_FAIL_AFTER') == 'intent':
            raise pub.AdapterError('injected amendment interruption after intent')
        pub.atomic_write(target.path, target.text[:target.inner_start] + changed + target.text[target.inner_end:])
        if os.environ.get('ULTRA_AMENDMENT_FAIL_AFTER') == 'ticket':
            raise pub.AdapterError('injected amendment interruption after Ticket')
        pub.append_audit(journal, 'amendments', dict(operation='amendment', ticket_id=ticket_id,
            amendment_id=request['id'], old_digest=expected_digest, new_digest=desired.body_digest,
            path=relative, file_digest=sha(encoded), reason=request['approval'], timestamp=datetime.now(timezone.utc).isoformat()))
        pub.write_journal(journal_path, journal)
        if os.environ.get('ULTRA_AMENDMENT_FAIL_AFTER') == 'journal':
            raise pub.AdapterError('injected amendment interruption after journal')
        pub.validate_against_journal_at(repo, representation, location, run_id, contract)
        return dict(status='success', amendment=relative, ticket_id=ticket_id, new_digest=desired.body_digest)


def current_revisions(repo, tickets):
    import local_ticket_frontier as frontier
    contract, _ = frontier.read_contract(repo)
    frontier.apply_publication_gates(repo, tickets, contract)
    revisions = {}
    for ticket in tickets:
        if not ticket.publication_ready:
            raise pub.AdapterError(f'contract amendment/publication is not verified: {ticket.identity}')
        if ticket.amendment and ticket.amendment['head']:
            revisions[ticket.path.relative_to(repo).as_posix()] = ticket.amendment['head']
    return revisions


def receipt_revisions(text):
    values = re.findall(r'^contract_revisions: (.+)$', text, re.M)
    if not values:
        return {}
    try:
        result = json.loads(values[0])
    except ValueError as error:
        raise pub.AdapterError('malformed receipt contract revisions') from error
    if len(values) != 1 or not isinstance(result, dict) or any(not isinstance(v, str) for v in result.values()):
        raise pub.AdapterError('malformed receipt contract revisions')
    return result


def candidate_reason(repo, record):
    """Old receipts remain history; only a new Attempt binds the revised contract."""
    if not (repo / pub.CONTRACT).is_file():
        return ''
    import local_ticket_frontier as frontier
    try:
        contract, _ = frontier.read_contract(repo)
        tickets = frontier.load_tickets(repo, contract)
        aliases = {a: t for t in tickets for a in t.aliases}
        linked = [aliases.get(ref) for ref in record.get('tickets', record.get('issues', []))]
        selected = [t for t in linked if t is not None]
        revisions = current_revisions(repo, selected)
        saved = receipt_revisions((repo / record['path']).read_text())
        if revisions != saved:
            return 'contract amendment invalidates old candidate evidence; execute the current Ticket contract in a new Attempt'
    except (pub.AdapterError, frontier.FrontierError, OSError, ValueError) as error:
        return f'contract amendment verification unavailable: {error}'
    return ''
