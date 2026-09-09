#!/usr/bin/env python3
"""Prepare and grade bounded routing and coordinator-completion model runs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

CASES = ('implementation', 'review-only', 'explicit', 'unrelated', 'alias-current', 'alias-legacy', 'alias-missing')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(source, output):
    output.mkdir(parents=True, exist_ok=False)
    for case in CASES:
        root = output / case
        root.mkdir()
        shutil.copytree(source / 'skills/engineering/ultra', root / 'skills/ultra')
        shutil.copytree(source / 'skills/engineering/ultra-solve', root / 'skills/ultra-solve')
        # A sentinel runbook isolates dispatch from the real tracker lifecycle.
        (root / 'skills/ultra/solve.md').write_text('Routing fixture: on entry write `solve-entered.txt` containing `entered`. This substitutes the solve backend; finish after recording entry.\n')
        (root / 'LIMITS.md').write_text('The empty batch costs 0. Each item costs 3.\n')
        (root / 'cost.py').write_text('def cost(items):\n    return max(1, len(items)) * 3\n')
        (root / 'check.py').write_text('from cost import cost\nassert cost([]) == 0\nassert cost([1, 2]) == 6\n')
        if case in ('implementation', 'review-only'):
            (root / 'REVIEW.md').write_text('Independent review of cost.py: empty input returns 3, contradicting LIMITS.md. check.py reproduces this. No other findings.\n')
            request = ('Continue the implementation of batch pricing under /ultra tdd. The target has finished; consume REVIEW.md at the post-review checkpoint and complete the request.' if case == 'implementation' else 'Review the batch pricing implementation using the /ultra tdd post-review checkpoint and REVIEW.md. This request is review-only.')
            request += ' LIMITS.md is the approved scope. The target-native stage and independent review already ran; their artifacts are present.'
        elif case == 'explicit':
            request = '$ultra-solve execute the prepared fixture Ticket.'
        elif case == 'unrelated':
            request = 'Explain what a ready-for-agent Ticket means and review whether cost.py follows LIMITS.md. Do not implement anything.'
        else:
            request = '/ultra write-a-skill Draft a short agent-facing guide for checking batch pricing.'
            target = 'writing-for-agents' if case == 'alias-current' else 'write-a-skill'
            if case != 'alias-missing':
                target_root = root / 'skills' / target
                target_root.mkdir()
                (target_root / 'SKILL.md').write_text(f'---\nname: {target}\ndescription: Writing agent documents, including skills.\n---\nWrite the requested short guide to GUIDE.md using LIMITS.md. Record this fixture target invocation by writing `{target}` to target-entered.txt.\n')
        inventory = '\n'.join(f'- {p.parent.name}: {p.relative_to(root)}' for p in sorted((root / 'skills').glob('*/SKILL.md')))
        (root / 'AGENTS.md').write_text('This is an isolated behavioral fixture. Available skills for this run are ONLY the following local files; read their instructions when invoked. Global skills are outside this fixture inventory.\n' + inventory + '\n')
        (root / 'prompt.txt').write_text(request + '\n')
        subprocess.run(['git', 'init', '-q', str(root)], check=True)
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', 'commit', '-qm', 'fixture'], check=True)
        manifest = {'case':case, 'files':{str(p.relative_to(root)):digest(p) for p in root.rglob('*') if p.is_file() and '.git' not in p.parts}}
        (root / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (output / 'source.json').write_text(json.dumps({str(p.relative_to(source)):digest(p) for p in [source/'skills/engineering/ultra/SKILL.md', source/'skills/engineering/ultra/PROFILES.md']}, indent=2)+'\n')

def grade(root, transcript=None):
    manifest = json.loads((root/'manifest.json').read_text())
    case = manifest['case']
    for name, before in manifest['files'].items():
        if case == 'implementation' and name == 'cost.py':
            continue
        assert digest(root/name) == before, f'modified protected file {name}'
    installed = {str(p.relative_to(root)) for p in (root/'skills').rglob('*') if p.is_file()}
    expected_installed = {name for name in manifest['files'] if name.startswith('skills/')}
    assert installed == expected_installed, 'fixture skill installation changed'
    messages = []
    if transcript:
        for line in transcript.read_text().splitlines():
            try: event = json.loads(line)
            except json.JSONDecodeError: continue
            item = event.get('item', {})
            if event.get('type') == 'item.completed' and item.get('type') == 'agent_message':
                messages.append(item.get('text', ''))
    final = messages[-1].lower() if messages else ''
    assert final, 'missing actual model final response'
    if case == 'implementation':
        subprocess.run(['python3', 'check.py'], cwd=root, check=True)
        assert digest(root/'cost.py') != manifest['files']['cost.py']
    elif case in ('review-only', 'unrelated'):
        assert 'cost' in final and ('empty' in final or '空' in final), 'missing concrete pricing finding'
        assert not (root/'solve-entered.txt').exists()
    elif case == 'explicit':
        assert (root/'solve-entered.txt').read_text().strip() == 'entered'
    elif case in ('alias-current','alias-legacy'):
        expected = 'writing-for-agents' if case == 'alias-current' else 'write-a-skill'
        assert (root/'target-entered.txt').read_text().strip() == expected
        assert (root/'GUIDE.md').stat().st_size > 0
    else:
        assert 'writing-for-agents' in final and any(term in final for term in ('missing', 'unavailable', 'not installed', '缺失', '未安装')), 'missing dependency not reported'
        assert not (root/'target-entered.txt').exists()
        assert not (root/'GUIDE.md').exists()
    print(json.dumps({'case':case,'result':'pass'}))

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare','grade'])
    parser.add_argument('--transcript',type=Path)
    parser.add_argument('--source',type=Path,default=Path.cwd())
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    prepare(args.source.resolve(),args.output.resolve()) if args.mode=='prepare' else grade(args.output.resolve(),args.transcript)
