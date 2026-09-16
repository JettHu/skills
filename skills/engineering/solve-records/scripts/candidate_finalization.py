"""Evidence-only finalization of an existing candidate; never mutates Git."""
import copy
import fcntl
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

SECTION = 'Finalization'
VERSION = 'candidate-finalization/v1'


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def read(helper, record):
    block = helper.section(record['text'], SECTION).strip()
    if not block:
        return None
    try:
        if len(helper.sections(record['text'], SECTION)) != 1:
            raise ValueError('duplicate Finalization sections')
        if not block.startswith('```json\n') or not block.endswith('\n```'):
            raise ValueError('expected one JSON block')
        data = json.loads(block[8:-4])
        if data['schema'] != VERSION or data['binding_digest'] != digest(data['binding']):
            raise ValueError('binding mismatch')
        members = data['binding']['repositories']
        rows = data['repositories']
        if not isinstance(members, list) or not members or not isinstance(rows, list):
            raise ValueError('invalid repository set')
        if [m['repo'] for m in members] != [m['repo'] for m in rows]:
            raise ValueError('result membership differs from prepared scope')
        for member, row in zip(members, rows):
            if any(row[key] != member[key] for key in ('base', 'head', 'landing_sha')):
                raise ValueError('result identity differs from prepared scope')
            if row['landing'] not in {'pending', 'verified'} or type(row['cleanup_done']) is not bool:
                raise ValueError('invalid landing or cleanup result')
            if not isinstance(row['resources'], dict) or not isinstance(row['blockers'], list):
                raise ValueError('invalid resource observation')
        if type(data['landing_complete']) is not bool or type(data['cleanup_done']) is not bool:
            raise ValueError('invalid aggregate evidence')
        if data['status'] not in {'pending', 'cleanup-pending', 'complete'}:
            raise ValueError('invalid aggregate status')
        if data['binding']['candidate'] != candidate_identity(record):
            raise ValueError('candidate identity changed after preparation')
        return data
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f'invalid finalization evidence: {exc}') from exc


def candidate_identity(record):
    return {key: record.get(key) for key in ('path', 'tickets', 'outcome', 'head', 'head_sha', 'base', 'base_sha', 'worktree', 'handoff_key')}


def git(helper, repo, *args):
    return helper.run_git(repo, *args).stdout.strip()


def ancestor(helper, repo, before, after):
    return helper.run_git(repo, 'merge-base', '--is-ancestor', before, after, check=False).returncode == 0


def branch_sha(helper, repo, branch):
    return helper.run_git(repo, 'rev-parse', '--verify', f'refs/heads/{branch}', check=False).stdout.strip()


def worktrees(helper, repo):
    # Bypass process-local read caches: every write rechecks live Git evidence.
    helper.WORKTREE_INFO_CACHE.clear()
    return helper.registered_worktree_info(repo)


def inode(path):
    info = path.stat()
    return [info.st_dev, info.st_ino]


def require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f'{label} evidence is required')
    return value


def prepare(helper, repo, record, request):
    if record['state'] != 'open':
        raise RuntimeError('preparation requires an open candidate; historical missing evidence remains pending verification')
    if not isinstance(request, dict):
        raise RuntimeError('evidence must be an object')
    authorization = require_text(request.get('authorization'), 'authorization')
    scope = require_text(request.get('scope_evidence'), 'complete repository scope')
    members = request.get('repositories')
    if not isinstance(members, list) or not members:
        raise RuntimeError('complete repositories evidence is required')
    bound = []
    seen = set()
    for supplied in members:
        if not isinstance(supplied, dict):
            raise RuntimeError("repository evidence must be an object")
        m = copy.deepcopy(supplied)
        for key in ('repo', 'base', 'base_sha', 'head', 'head_sha', 'worktree', 'landing_sha', 'ownership_evidence'):
            require_text(m.get(key), key)
        root = Path(m['repo']).resolve()
        if root != helper.repo_root(root):
            raise RuntimeError('repository must name its checkout root')
        m['repo'] = str(root)
        common = str(helper.common_dir(root))
        if common in seen:
            raise RuntimeError('duplicate repository in selected scope')
        seen.add(common)
        m['common_dir'] = common
        m['common_dir_identity'] = inode(Path(common))
        for ref in ('head', 'base'):
            if helper.run_git(root, 'check-ref-format', '--branch', m[ref], check=False).returncode:
                raise RuntimeError(f'invalid {ref} branch')
            if branch_sha(helper, root, m[ref]) != m[f'{ref}_sha']:
                raise RuntimeError(f'{root}: stale {ref} or wrong target')
        if m['head'] == m['base']:
            raise RuntimeError('candidate and target must be distinct')
        if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', m['landing_sha']):
            raise RuntimeError('landing_sha must be a full commit SHA')
        wt = Path(m['worktree']).absolute()
        if wt.is_symlink() or wt.resolve() != wt:
            raise RuntimeError('worktree path must be canonical and not a symlink')
        m['worktree'] = str(wt)
        if wt == root or wt == repo or root in wt.parents or repo in wt.parents:
            raise RuntimeError('candidate resource is a protected checkout or inside repository root')
        if worktrees(helper, root).get(wt, {}).get('branch') != m['head']:
            raise RuntimeError('candidate worktree registration/branch mismatch')
        if str(helper.common_dir(wt)) != common or git(helper, wt, 'rev-parse', 'HEAD') != m['head_sha']:
            raise RuntimeError('candidate worktree identity mismatch')
        if git(helper, wt, 'status', '--porcelain', '--untracked-files=all'):
            raise RuntimeError('candidate worktree is dirty')
        m['worktree_identity'] = inode(wt)
        m['worktree_git_dir'] = git(helper, wt, 'rev-parse', '--absolute-git-dir')
        owners = m.get('ownership')
        if not isinstance(owners, dict) or set(owners) != {'branch', 'worktree'} or any(v not in {'solve-owned', 'user-owned'} for v in owners.values()):
            raise RuntimeError('explicit branch and worktree ownership is required')
        evidence = m.get('gate_evidence', {})
        if not isinstance(evidence, dict):
            raise RuntimeError('gate_evidence must be an object')
        if evidence.get('audit') != 'passed' or evidence.get('dependencies') != 'satisfied':
            raise RuntimeError('requirement audit and dependencies evidence is required')
        text = '\n'.join((f"Checks: {evidence.get('checks', '')}", f"Review: {evidence.get('review', '')}",
                          f"Merge: {evidence.get('merge', '')}", f"Rollout/config disposition: {evidence.get('rollout_config', '')}",
                          f"Activation: {evidence.get('activation', 'none')}"))
        projected = dict(record, **{k: m[k] for k in ('head', 'head_sha', 'base', 'base_sha', 'worktree')},
                         checks=evidence.get('checks'), review=evidence.get('review'), merge=evidence.get('merge'),
                         text='## Gate Evidence\n' + text)
        if root == repo:
            for key in ('head', 'head_sha', 'base', 'base_sha', 'worktree'):
                actual = record.get(key)
                if key == 'worktree' and actual:
                    actual = str((repo / actual).resolve())
                if actual != m[key]:
                    raise RuntimeError(f'primary {key} does not match canonical receipt gate evidence')
            ownership = record.get('resource_ownership', '').lower()
            if ownership.startswith('user-owned') and any(v != 'user-owned' for v in owners.values()):
                raise RuntimeError('ownership contradicts the canonical user-owned resource evidence')
            # Canonical gate facts cannot be upgraded through a manifest assertion.
            projected = record
        plan = helper.landing_plan(root, projected, m['landing_sha'])
        if plan['status'] != 'ready':
            raise RuntimeError(f'{root}: landing gate: {plan["reasons"]}')
        m['gate_record'] = {key: projected.get(key) for key in ('checks', 'review', 'merge', 'notes')}
        m['gate_record']['text'] = '\n'.join('## ' + name + '\n' + helper.section(projected['text'], name)
                                               for name in ('Gate Evidence', 'Merge', 'Notes'))
        extras = m.get('additional_resources', [])
        if not isinstance(extras, list):
            raise RuntimeError('additional_resources must be a complete list')
        identities = {('branch', m['head']), ('worktree', m['worktree'])}
        for extra in extras:
            bind_additional_resource(helper, root, m, extra)
            identity = (extra['kind'], extra['identity'])
            if identity in identities:
                raise RuntimeError('duplicate resource identity')
            identities.add(identity)
        bound.append(m)
    if str(repo) not in {m['repo'] for m in bound}:
        raise RuntimeError('selected scope must include the canonical receipt repository')
    binding = dict(candidate=candidate_identity(record), authorization=authorization, scope_evidence=scope,
                   repositories=bound)
    return dict(schema=VERSION, binding=binding, binding_digest=digest(binding), prepared_at=now(), repositories=[])


def bind_additional_resource(helper, repo, member, extra):
    if not isinstance(extra, dict) or extra.get('kind') not in {'branch', 'worktree'}:
        raise RuntimeError('additional resource must be a branch or worktree')
    for key in ('identity', 'head_sha', 'ownership_evidence'):
        require_text(extra.get(key), key)
    if extra.get('owner') not in {'solve-owned', 'user-owned'}:
        raise RuntimeError('additional resource ownership is required')
    if not ancestor(helper, repo, extra['head_sha'], member['landing_sha']):
        raise RuntimeError('additional resource commit is outside validated landing')
    if extra['kind'] == 'branch':
        if extra['identity'] == member['base'] or branch_sha(helper, repo, extra['identity']) != extra['head_sha']:
            raise RuntimeError('additional branch is target or has stale identity')
    else:
        path = Path(extra['identity'])
        if not path.is_absolute() or path.is_symlink() or path.resolve() != path or path == repo or repo in path.parents:
            raise RuntimeError('additional worktree is protected or not canonical')
        registry = worktrees(helper, repo)
        if path not in registry or registry[path]['branch'] != extra.get('branch', ''):
            raise RuntimeError('additional worktree registration mismatch; name branch or empty detached branch')
        if extra.get('branch') == member['base']:
            raise RuntimeError('additional worktree is on target branch')
        if str(helper.common_dir(path)) != member['common_dir'] or git(helper, path, 'rev-parse', 'HEAD') != extra['head_sha']:
            raise RuntimeError('additional worktree identity mismatch')
        if git(helper, path, 'status', '--porcelain', '--untracked-files=all'):
            raise RuntimeError('additional worktree is dirty')
        extra['path_identity'] = inode(path)
        extra['git_dir'] = git(helper, path, 'rev-parse', '--absolute-git-dir')


def observe_additional_resource(helper, repo, member, extra, landed):
    name = extra['identity']
    try:
        registry = worktrees(helper, repo)
        if extra['kind'] == 'branch':
            head = branch_sha(helper, repo, name)
            present = bool(head)
            if head and head != extra['head_sha']:
                raise RuntimeError('additional branch head changed')
            paths = [str(path) for path, info in registry.items() if info['branch'] == name]
            declared = [member['worktree']] + [e['identity'] for e in member.get('additional_resources', []) if e['kind'] == 'worktree']
            if any(path not in declared for path in paths):
                raise RuntimeError('additional branch is registered in an undeclared worktree')
        else:
            path = Path(name)
            present = os.path.lexists(path)
            if present:
                if path.is_symlink() or path.resolve() != path or inode(path) != extra['path_identity']:
                    raise RuntimeError('additional worktree path replaced')
                if path not in registry or registry[path]['branch'] != extra.get('branch', ''):
                    raise RuntimeError('additional worktree registration changed')
                if str(helper.common_dir(path)) != member['common_dir'] or git(helper, path, 'rev-parse', 'HEAD') != extra['head_sha']:
                    raise RuntimeError('additional worktree identity changed')
                if git(helper, path, 'status', '--porcelain', '--untracked-files=all'):
                    raise RuntimeError('additional worktree is dirty')
            elif path in registry or Path(extra['git_dir']).exists():
                raise RuntimeError('additional worktree missing or moved but administrative registration remains')
        if extra['owner'] == 'user-owned':
            return ('retained-user-owned', '') if present else ('unverified', f'{name}: user-owned resource missing')
        if present:
            return 'retained', f'{name}: safe cleanup remains pending'
        return ('removed', '') if landed else ('unverified', f'{name}: missing before verified landing')
    except (OSError, RuntimeError) as exc:
        return 'unverified', f'{name}: {exc}'


def landing_plan(helper, repo, record, landing_sha=None, target_repo=None):
    amendment_reason = helper.amendment_gate_reason(repo, record)
    if amendment_reason:
        return dict(status='blocked', reasons=[amendment_reason])
    data = read(helper, record)
    target = str(Path(target_repo).resolve()) if target_repo else str(repo)
    matches = [m for m in data['binding']['repositories'] if m['repo'] == target]
    if len(matches) != 1:
        raise RuntimeError('target repository is outside prepared scope')
    member = matches[0]
    if landing_sha and landing_sha != member['landing_sha']:
        raise RuntimeError('landing SHA differs from prepared identity')
    observed = observe_member(helper, member, {})
    if observed['landing'] == 'verified':
        return dict(status='blocked', reasons=['prepared landing already completed; reconcile, never merge again'])
    if observed.get('evidence_conflict'):
        return dict(status='blocked', reasons=observed['blockers'])
    projected = dict(member['gate_record'], state='open', outcome='candidate', path=record['path'], tickets=record.get('tickets', []),
                     **{key: member[key] for key in ('base', 'base_sha', 'head', 'head_sha', 'worktree')})
    return helper.landing_plan(Path(target), projected, member['landing_sha'])


def observe_member(helper, member, previous):
    helper.COMMON_DIR_CACHE.clear()
    m = member
    repo, wt = Path(m['repo']), Path(m['worktree'])
    result = dict(repo=m['repo'], base=m['base'], head=m['head'], landing_sha=m['landing_sha'],
                  landing='pending', cleanup_done=False, resources={}, blockers=[])
    if previous.get('merged_at'):
        result['merged_at'] = previous['merged_at']
    try:
        if str(helper.common_dir(repo)) != m['common_dir'] or inode(Path(m['common_dir'])) != m['common_dir_identity']:
            raise RuntimeError('repository identity changed')
        base = branch_sha(helper, repo, m['base'])
        head = branch_sha(helper, repo, m['head'])
        if not base or not ancestor(helper, repo, m['base_sha'], base):
            raise RuntimeError('target missing or diverged from prepared base')
        if head and head != m['head_sha']:
            raise RuntimeError('stale candidate head')
        landed = ancestor(helper, repo, m['landing_sha'], base)
        if landed:
            result['landing'] = 'verified'
            result.setdefault('merged_at', now())
        elif base != m['base_sha']:
            raise RuntimeError('target advanced without prepared landing; revalidation required')
        else:
            result['blockers'].append('land the prepared SHA through current authorization, acceptance and WIP gates')
        registry = worktrees(helper, repo)
        registered = registry.get(wt)
        exists = os.path.lexists(wt)
        if exists:
            if wt.is_symlink() or wt.resolve() != wt or inode(wt) != m['worktree_identity']:
                raise RuntimeError('worktree path was replaced')
            if not registered or registered.get('branch') != m['head'] or str(helper.common_dir(wt)) != m['common_dir']:
                raise RuntimeError('worktree registration or ownership identity changed')
            if git(helper, wt, 'rev-parse', 'HEAD') != m['head_sha']:
                raise RuntimeError('worktree HEAD changed')
            if git(helper, wt, 'status', '--porcelain', '--untracked-files=all'):
                raise RuntimeError('worktree is dirty; cleanup blocked')
        elif registered or Path(m['worktree_git_dir']).exists():
            raise RuntimeError('worktree path missing but registration remains (possibly moved); inspect before pruning')
        if any(path != wt and info.get('branch') == m['head'] for path, info in registry.items()):
            raise RuntimeError('candidate branch registered at another path')
        for resource, present in (('worktree', exists), ('branch', bool(head))):
            owner = m['ownership'][resource]
            if owner == 'user-owned':
                status = 'retained-user-owned' if present else 'unverified'
                if not present:
                    result['blockers'].append(f'user-owned {resource} missing; disposition requires evidence')
            else:
                status = 'retained' if present else ('removed' if landed else 'unverified')
                if present:
                    result['blockers'].append(f'{resource}: safe cleanup remains pending')
                elif not landed:
                    result['blockers'].append(f'{resource} missing before verified landing')
            result['resources'][resource] = status
        for index, extra in enumerate(m.get('additional_resources', [])):
            status, blocker = observe_additional_resource(helper, repo, m, extra, landed)
            result['resources'][f"additional:{index}:{extra['kind']}"] = status
            if blocker:
                result['blockers'].append(blocker)
        result['cleanup_done'] = landed and all(v in {'removed', 'retained-user-owned'} for v in result['resources'].values())
    except (RuntimeError, OSError) as exc:
        result['blockers'].append(str(exc))
        result['evidence_conflict'] = True
    return result


def observe(helper, data):
    updated = copy.deepcopy(data)
    previous = {m['repo']: m for m in data['repositories']}
    updated['repositories'] = [observe_member(helper, m, previous.get(m['repo'], {})) for m in data['binding']['repositories']]
    rows = updated['repositories']
    complete = all(m['landing'] == 'verified' for m in rows)
    updated['landing_complete'] = complete
    updated['cleanup_done'] = complete and all(m['cleanup_done'] for m in rows)
    updated['status'] = 'complete' if updated['cleanup_done'] else ('cleanup-pending' if complete else 'pending')
    return updated


def scalar(text, key, value):
    end = text.index('\n---', 4)
    header, body = text[:end], text[end:]
    pattern = rf'(?m)^{re.escape(key)}:.*$'
    line = f'{key}: {value}'
    header = re.sub(pattern, lambda _: line, header) if re.search(pattern, header) else header + '\n' + line
    return header + body


def plan(helper, record):
    data = read(helper, record)
    if not data:
        return dict(status='pending', reason='missing verified target and resource inventory; prepare while resources are verifiable')
    return observe(helper, data)


def write(helper, repo, record, phase, evidence=None):
    lock_path = Path(git(helper, repo, 'rev-parse', '--git-path', 'ultra-frontier.lock'))
    if not lock_path.is_absolute():
        lock_path = repo / lock_path
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (repo / record['path']).read_text() != record['text']:
            raise RuntimeError('concurrent receipt change; reread before retry')
        return write_locked(helper, repo, record, phase, evidence)


def write_locked(helper, repo, record, phase, evidence=None):
    if record.get('malformed') or record.get('outcome') != 'candidate' or record.get('state') not in {'open', 'merged'}:
        raise RuntimeError('finalization requires a valid open or merged candidate receipt')
    if record.get('external_provider') or record.get('external_url'):
        raise RuntimeError('remote-primary receipt requires remote merge evidence; local finalization is unavailable')
    raw_path = repo / record['path']
    path = raw_path.resolve()
    if not path.is_relative_to(repo) or raw_path.is_symlink():
        raise RuntimeError('canonical receipt must remain inside repository')
    old = record['text']
    existing = read(helper, record)
    if phase == 'prepare':
        if not evidence:
            raise RuntimeError('prepare requires --evidence with complete selected scope')
        try:
            request = json.loads(Path(evidence).read_text())
            if not isinstance(request, dict):
                raise ValueError('evidence must be an object')
        except (OSError, ValueError) as exc:
            raise RuntimeError(f'invalid evidence input: {exc}') from exc
        if existing:
            # Repeated preparation uses the original immutable scope, including after cleanup.
            expected = existing['binding']
            for key in ('authorization', 'scope_evidence'):
                if request.get(key) != expected[key]:
                    raise RuntimeError('finalization scope changed; inspect original prepared evidence')
            supplied = request.get('repositories')
            derived = {'common_dir', 'common_dir_identity', 'worktree_identity', 'worktree_git_dir', 'gate_record'}
            original = [{k: copy.deepcopy(v) for k, v in m.items() if k not in derived} for m in expected['repositories']]
            for member in original:
                for extra in member.get('additional_resources', []):
                    extra.pop('path_identity', None)
                    extra.pop('git_dir', None)
            if supplied != original:
                raise RuntimeError('finalization repository scope or identity changed')
            data = existing
        else:
            data = prepare(helper, repo, record, request)
    else:
        if evidence:
            raise RuntimeError('reconcile uses only the original prepared evidence')
        if not existing:
            raise RuntimeError('missing verified preparation; historical evidence remains pending, never infer cleanup from absence')
        data = existing
    updated = observe(helper, data)
    rendered = helper.replace_or_append_section(old, SECTION, '```json\n' + json.dumps(updated, indent=2, sort_keys=True) + '\n```')
    if updated['landing_complete']:
        primary = next(m for m in updated['repositories'] if m['repo'] == str(repo))
        rendered = scalar(rendered, 'state', 'merged')
        summary = helper.section(rendered, 'Summary')
        if record.get('summary_status'):
            rendered = helper.replace_or_append_section(rendered, 'Summary', re.sub(r'(?m)^Status:.*$', 'Status: merged', summary))
        rendered = scalar(rendered, 'merged_sha', primary['landing_sha'])
        rendered = scalar(rendered, 'merged_at', (record.get('merged_at') if record['state'] == 'merged' else None) or max(m['merged_at'] for m in updated['repositories']))
    rendered = scalar(rendered, 'cleanup_done', str(updated['cleanup_done']).lower())
    # A second live observation plus compare-before-replace catches evidence/receipt drift.
    checked = observe(helper, updated)
    if checked != updated or path.read_text() != old:
        raise RuntimeError('concurrent receipt or Git evidence change; retry reconciliation')
    if os.environ.get('ULTRA_FINALIZATION_FAIL_BEFORE_WRITE') == '1':
        raise RuntimeError('injected interruption before canonical receipt write; retry same operation')
    if rendered != old:
        helper.atomic_write(path, rendered)
    if path.read_text() != rendered:
        raise RuntimeError('receipt postcondition changed; retry reconciliation')
    return dict(path=record['path'], status=updated['status'], state='merged' if updated['landing_complete'] else record['state'],
                cleanup_done=updated['cleanup_done'], repositories=updated['repositories'])
