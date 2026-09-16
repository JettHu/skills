#!/usr/bin/env python3
"""Bounded Obsidian setup: inspect, configure, verify. JSON output, no UI automation."""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote

OWNER = '.workspace-config.json'
DEFAULT_OUTPUT = 'tracker-generated/workspace'


def ensure_runtime():
    explicit = os.environ.get('JETT_WORKSPACE_PYTHON')
    if not explicit and sys.version_info >= (3, 10):
        return
    if explicit and not Path(explicit).is_absolute():
        raise ValueError('JETT_WORKSPACE_PYTHON must be an absolute interpreter path')
    candidates = [explicit] if explicit else [shutil.which('python3'), '/opt/homebrew/bin/python3', '/usr/local/bin/python3']
    if not explicit and shutil.which('uv'):
        result = subprocess.run(['uv', 'python', 'find', '--no-python-downloads', '>=3.10'], capture_output=True, text=True, timeout=8)
        if result.returncode == 0:
            candidates.append(result.stdout.strip())
    for candidate in dict.fromkeys(p for p in candidates if p):
        try:
            good = subprocess.run([candidate, '-c', 'import sys;sys.exit(sys.version_info < (3,10))'], timeout=5, capture_output=True)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if good.returncode == 0:
            if Path(candidate).resolve() != Path(sys.executable).resolve():
                os.execv(candidate, [candidate, *sys.argv])
            return
    raise RuntimeError('Python 3.10+ required; set JETT_WORKSPACE_PYTHON to an installed interpreter. No downloads attempted.')


def renderer():
    sys.dont_write_bytecode = True
    path = Path(__file__).with_name('obsidian-workspace.py')
    spec = importlib.util.spec_from_file_location('workspace_renderer', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.query = module.load_query()
    return module


def read_json(path):
    return json.loads(path.read_text())


def absolute(value):
    return Path(value).expanduser().resolve()


def registry_path():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/obsidian/obsidian.json'
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', str(Path.home()))) / 'obsidian/obsidian.json'
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'obsidian/obsidian.json'


def vaults(path):
    if not path.is_file():
        return []
    registry = read_json(path)
    entries = registry.get('vaults', {})
    if not isinstance(entries, dict) or len(entries) > 100:
        raise ValueError('Unsupported or oversized Vault registry; supply the target Vault explicitly')
    return [dict(path=str(absolute(v['path'])), open=bool(v.get('open', False)))
            for v in entries.values() if isinstance(v, dict) and isinstance(v.get('path'), str)]


def plugin(vault):
    root = vault / '.obsidian'
    enabled = read_json(root / 'community-plugins.json') if (root / 'community-plugins.json').is_file() else []
    manifest = root / 'plugins/obsidian-kanban/manifest.json'
    data = read_json(manifest) if manifest.is_file() else {}
    version = str(data.get('version', ''))
    return dict(vault_initialized=root.is_dir(), kanban_version=version or None,
                kanban_enabled='obsidian-kanban' in enabled,
                ready=version.startswith('2.') and 'obsidian-kanban' in enabled)


def owner(root):
    path = root / OWNER
    if path.is_symlink():
        raise ValueError('Workspace config locator must not be a symlink')
    if not path.exists():
        return None
    value = read_json(path)
    if value.get('schema') != 'workspace-config-locator/v1' or not Path(value['config']).is_absolute():
        raise ValueError('Invalid workspace configuration locator')
    return absolute(value['config'])


def context(args, tool):
    repo = tool.query.repository(absolute(args.repo)) if getattr(args, 'repo', None) else None
    config = absolute(args.config) if args.config else repo / '.scratch/obsidian-workspace.json'
    existing = read_json(config) if config.exists() else None
    return repo, config, existing


def navigation(tool, root, state):
    projects = []
    for identity, entry in state.get('projects', {}).items():
        good = entry.get('last_success') or {}
        sample = None
        work = root / good.get('views', {}).get('Work', '__missing__')
        links = re.findall(r'\]\((sources/[^)]+)\)', work.read_text()) if work.is_file() else []
        for name in links[:1]:
            meta = good.get('manifest', {}).get(name, {})
            target = meta.get('target')
            if target:
                alias = root / good['directory'] / name
                sample = dict(alias=str(alias), source=target)
                break
        projects.append(dict(id=identity, repository=entry.get('repository'), status=entry.get('status'),
                             error=entry.get('error'), views={k: str(root / v) for k, v in good.get('views', {}).items()}, sample_source=sample))
    return projects


def verify_config(tool, path, active_vault=None):
    config = read_json(path)
    root, _ = tool.validate_config(config)
    vault = absolute(config['vault'])
    state = tool.read_state(root / 'Home.md') if (root / 'Home.md').is_file() else {}
    facts = navigation(tool, root, state)
    match = None if active_vault is None else absolute(active_vault) == vault
    expected = {p['id']: (p['repository'], p['selection']) for p in tool.validate_config(config)[1]}
    observed = {k: (v.get('repository'), v.get('attempted_selection')) for k, v in state.get('projects', {}).items()}
    return dict(configuration_matches_output=expected == observed, config=str(path), vault=str(vault), home=str(root / 'Home.md'),
                home_uri='obsidian://open?vault=' + quote(str(vault), safe='') + '&file=' + quote(str((root / 'Home.md').relative_to(vault)), safe=''),
                plugin=plugin(vault), latest_refresh=state.get('result', 'not-generated'), projects=facts,
                active_vault_matches=match, ui_verification='pending',
                next_action='open-selected-vault' if match is False else 'verify-home-and-ticket-in-ui',
                refresh_command=[sys.executable, str(Path(__file__).with_name('obsidian-workspace.py').resolve()), '--config', str(path)],
                refresh_environment={k: os.environ[k] for k in ('JETT_ULTRA_SKILL_DIR',) if k in os.environ})


def inspect(args, tool):
    repo, config, existing = context(args, tool)
    selected = absolute(existing['vault']) if existing else absolute(args.vault) if args.vault else None
    if existing and args.vault and selected != absolute(args.vault):
        raise ValueError('Selected Vault differs from existing configuration; existing binding remains unchanged')
    registry = absolute(args.registry) if args.registry else registry_path()
    candidates = vaults(registry)
    # Registry is advisory; even one open candidate never selects the target.
    result = dict(ok=True, config=str(config), config_exists=existing is not None,
                  repository=str(repo), python=sys.executable, vault=str(selected) if selected else None,
                  vault_candidates=candidates, discovery_sources=[str(config), str(registry)],
                  next_action='configure' if selected else 'select-vault')
    snapshot = tool.query.snapshot(repo)
    result['tracker'] = dict(ticket_count=len(snapshot['tickets']), receipt_count=len(snapshot['receipts']), incomplete=snapshot.get('incomplete'))
    if selected:
        result['plugin'] = plugin(selected)
        output = existing.get('generated', DEFAULT_OUTPUT) if existing else args.generated or DEFAULT_OUTPUT
        probe = existing or dict(vault=str(selected), generated=output, projects=[dict(id='probe', repository=str(repo))])
        root, _ = tool.validate_config(probe)
        known = owner(root)
        result['workspace_config'] = str(known) if known else None
        if known and known != config:
            result['next_action'] = 'use-workspace-config'
            result['config'] = str(known)
    return result


def choose_binding(config, repo, identity, selection):
    projects = config['projects']
    matches = [p for p in projects if absolute(p['repository']) == repo]
    if identity:
        matches = [p for p in projects if p['id'] == identity]
        if matches and absolute(matches[0]['repository']) != repo:
            raise ValueError('Project ID already belongs to a different canonical repository')
    elif len(matches) > 1:
        raise ValueError('Multiple bindings use this repository; specify --project-id')
    if matches:
        project = matches[0]
    else:
        identity = identity or re.sub('[^a-z0-9_-]+', '-', repo.name.lower()).strip('-_')[:48] or 'project'
        if any(p['id'] == identity for p in projects):
            identity += '-' + hashlib.sha256(str(repo).encode()).hexdigest()[:8]
        project = dict(id=identity, repository=str(repo))
        projects.append(project)
    if selection is not None:
        if selection == 'all':
            project.pop('selection', None)
        else:
            project['selection'] = selection
    return project['id']


def exclude_config(repo, config):
    try:
        relative = config.relative_to(repo)
    except ValueError:
        return
    tracked = subprocess.run(['git', '-C', str(repo), 'ls-files', '--error-unmatch', str(relative)], capture_output=True)
    if tracked.returncode == 0:
        raise ValueError('Machine configuration is tracked; choose an untracked local config path')
    ignored = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--no-index', '--quiet', str(relative)], capture_output=True)
    backup_ignored = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--no-index', '--quiet', str(relative) + '.backup-probe'], capture_output=True)
    lock_ignored = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--no-index', '--quiet', str(relative) + '.lock'], capture_output=True)
    if ignored.returncode == backup_ignored.returncode == lock_ignored.returncode == 0:
        return
    result = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--git-path', 'info/exclude'], capture_output=True, text=True, check=True)
    exclude = Path(result.stdout.strip())
    if not exclude.is_absolute():
        exclude = repo / exclude
    # Also ignores this config's bounded backups/lock. Config paths are literal Git patterns.
    escaped = ''.join('\\' + c if c in '\\*?[]!# ' else c for c in relative.as_posix())
    line = '/' + escaped + '*'
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        text = handle.read()
        if line not in text.splitlines():
            handle.write(('\n' if text and not text.endswith('\n') else '') + line + '\n')


def configure(args, tool):
    repo, path, previous = context(args, tool)
    if previous is None and not args.vault:
        raise ValueError('Choose --vault explicitly for first setup; the open window is not a selection')
    config = copy.deepcopy(previous) if previous else dict(vault=str(absolute(args.vault)), generated=args.generated or DEFAULT_OUTPUT, projects=[])
    if args.vault and absolute(args.vault) != absolute(config['vault']):
        raise ValueError('Vault is pinned by this configuration; changing the UI window cannot rebind it')
    if args.generated and args.generated != config.get('generated', DEFAULT_OUTPUT):
        raise ValueError('Existing generated output is pinned; choose a separate configuration for relocation')
    selection = 'all' if args.all_tickets else [] if args.no_tickets else args.ticket_id
    identity = choose_binding(config, repo, args.project_id, selection)
    root, _ = tool.validate_config(config)
    if not plugin(absolute(config['vault']))['ready']:
        raise ValueError('Selected Vault requires initialized Obsidian with enabled Kanban v2; retain target and complete authorized prerequisites')
    # Validate the new source before writing configuration. Existing projects may fail independently during refresh.
    tool.query.snapshot(repo)
    if root.exists() and any(p.name != '.setup.lock' for p in root.iterdir()):
        known = owner(root)
        if known and known != path:
            raise ValueError(f'Workspace already uses configuration {known}; use --config with that path')
        if not known:
            old = tool.read_state(root / 'Home.md') if (root / 'Home.md').is_file() else {}
            old_bindings = {k: v['repository'] for k, v in old.get('projects', {}).items()}
            expected = {p['id']: p['repository'] for p in (previous or {}).get('projects', [])}
            if not previous or old_bindings != expected:
                raise ValueError('Existing output ownership is unknown; supply its existing config or choose an empty generated directory')
    for managed in ('.setup.lock', 'Home.md', '.refresh.lock', 'generations'):
        if (root / managed).is_symlink():
            raise ValueError('Managed output must not be a symlink: ' + managed)
    exclude_config(repo, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    config_lock = path.with_name(path.name + '.lock')
    if config_lock.is_symlink():
        raise ValueError('Configuration lock must not be a symlink')
    root.mkdir(parents=True, exist_ok=True)
    with config_lock.open('a') as config_handle, (root / '.setup.lock').open('a') as lock:
        fcntl.flock(config_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if owner(root) not in (None, path):
            raise ValueError('Workspace configuration changed; inspect again')
        current = read_json(path) if path.exists() else None
        if current != previous:
            raise ValueError('Configuration changed since inspection; inspect again')
        backup = None
        if config != previous:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                with tempfile.NamedTemporaryFile(prefix=path.name + '.backup-', dir=path.parent, delete=False) as handle:
                    handle.write(path.read_bytes())
                    backup = handle.name
            tool.atomic_write(path, json.dumps(config, ensure_ascii=False, indent=2) + '\n')
        locator = dict(schema='workspace-config-locator/v1', config=str(path))
        if owner(root) is None:
            tool.atomic_write(root / OWNER, json.dumps(locator) + '\n')
        result = tool.refresh(config)
    result.update(config=str(path), project_id=identity, configuration_changed=config != previous, backup=backup)
    result['verification'] = verify_config(tool, path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'configure', 'verify'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--config', type=str, required=name == 'verify')
        if name != 'verify':
            cmd.add_argument('--repo', required=True)
            cmd.add_argument('--vault')
            cmd.add_argument('--generated')
        if name == 'inspect':
            cmd.add_argument('--registry', help='explicit Obsidian registry file; default is the platform registry')
        if name == 'configure':
            cmd.add_argument('--project-id')
            selection = cmd.add_mutually_exclusive_group()
            selection.add_argument('--ticket-id', action='append')
            selection.add_argument('--all-tickets', action='store_true')
            selection.add_argument('--no-tickets', action='store_true')
        if name == 'verify':
            cmd.add_argument('--active-vault', help='observed UI Vault path; mismatch never changes config')
    args = parser.parse_args()
    try:
        ensure_runtime()
        tool = renderer()
        if args.command == 'inspect':
            result = inspect(args, tool)
        elif args.command == 'configure':
            result = configure(args, tool)
        else:
            result = verify_config(tool, absolute(args.config), args.active_vault)
            result['ok'] = result['latest_refresh'] == 'success' and result['configuration_matches_output'] and result['plugin']['ready'] and result['active_vault_matches'] is not False
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        result = dict(ok=False, error=str(error), next_action='resolve-reported-prerequisite')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    sys.exit(main())
