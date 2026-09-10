#!/usr/bin/env python3
"""Prepare/grade isolated exploration checkpoints; agent traces verify delegation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[3]


def hashes(repo):
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in repo.rglob('*') if p.is_file() and '.git' not in p.parts and p.name not in ('RESULT.json', 'baseline.json')}


def prepare(root, backend=None, frontend=None):
    for name in ('coupled', 'local'):
        repo = root / name; repo.mkdir(parents=True, exist_ok=False)
        (repo / 'solve.md').write_text((ROOT / 'skills/engineering/ultra/solve.md').read_text())
        (repo / 'backend').mkdir(); (repo / 'frontend').mkdir()
        (repo / 'backend/config.py').write_text('def save(value, version):\n    return {"requirement": value.strip(), "version": version + 1}\n')
        (repo / 'backend/pool.py').write_text('from config import save\ndef pool(config):\n    return {"requirement": config["requirement"], "version": config["version"]}\n')
        (repo / 'frontend/editor.js').write_text('export const saveDraft = (draft, version, api) => api.save({requirement: draft, version});\n')
        (repo / 'frontend/pool.js').write_text('export const display = response => response.requirement;\n')
        (repo / 'test_contract.py').write_text('import sys, unittest\nsys.path.insert(0, "backend")\nfrom config import save\nfrom pool import pool\nclass Contract(unittest.TestCase):\n def test_save_observe(self):\n  saved=save("  office  ", 3)\n  self.assertEqual(pool(saved), {"requirement":"office", "version":4})\nif __name__ == "__main__": unittest.main()\n')
        (repo / 'label.py').write_text('EMPTY_LABEL = "No saved requirement"\n')
        ticket = ('Add an optional saved requirement to the editor and pool display. Preserve trim, version conflict semantics and saved-only pool observations. Backend and frontend owners need their current entry points and validation paths before editing.' if name == 'coupled' else 'Change EMPTY_LABEL in label.py from "No saved requirement" to "No requirement saved". No behavior change. The full affected source is EMPTY_LABEL = "No saved requirement". Validation is inspecting the one-line diff; no new test is needed.')
        (repo / 'TICKET.md').write_text(ticket)
        (repo / 'CONTEXT.md').write_text('Saved config is the source of truth. Pool uses only the saved version. Draft changes do not change the observed pool. This fixture is a preparation-only checkpoint; Claim and execution worktree handling are outside this experiment.\n')
        (repo / 'EVAL_PROMPT.md').write_text('''Apply solve.md's Pre-Implementation Checkpoint exploration routing to TICKET.md and CONTEXT.md. Stop at an implementation-ready plan; do not implement, Claim, or create worktrees in this preparation-only experiment. Local reads and collaboration are available. If delegating, children may read only this fixture and return findings. All writes are limited to RESULT.json in this directory. Other fixtures and live projects are outside scope.\nWrite RESULT.json with keys route, assignments (question and evidence returned), evidence (file/symbol locations), validation, unresolved_blockers, and next_action. Report the actual work performed.\n''')
        if name == 'coupled' and backend and frontend:
            for old in ('backend', 'frontend'):
                shutil.rmtree(repo / old)
            (repo / 'test_contract.py').unlink()
            sources = {
                'backend': (backend, ['app/core/production_config.py', 'app/core/production_resolver.py', 'app/services/production_trigger_snapshot_loader.py', 'app/services/prepared_production_trigger_snapshot_loader.py', 'app/infrastructure/repositories/mysql_product_matching_preparation_scope_reader.py', 'app/services/product_candidate_pool_service.py', 'tests/test_production_configurations_api.py', 'tests/test_product_candidate_pool_service.py']),
                'frontend': (frontend, ['src/components/production-config/PlanSectionEditor.tsx', 'src/components/production-config/ProductionConfigEditor.tsx', 'src/components/production-config/DirectCandidatePoolDrawer.tsx', 'src/lib/api/productionConfigs.ts', 'src/lib/candidatePool/index.ts', 'src/components/production-config/__tests__/DirectCandidatePoolDrawer.test.tsx'])}
            for side, (source, files) in sources.items():
                for relative in files:
                    target = repo / side / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source / relative, target)
            (repo / 'TICKET.md').write_text('Expose one saved Direct plan matching_requirement in the editor and pool. Identify how persistence, preparation and automatic selection must consume the same value; preserve full-workflow behavior, manual selection and config version semantics. Map the frontend shared save flow and validation paths. These are source excerpts for planning, not runnable full applications; omitted imports do not need reconstruction.')
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        (repo / 'baseline.json').write_text(json.dumps(hashes(repo), indent=2))
    print(root)


def grade(repo):
    assert hashes(repo) == json.loads((repo / 'baseline.json').read_text()), 'fixture inputs changed'
    result = json.loads((repo / 'RESULT.json').read_text())
    for key in ('route', 'assignments', 'evidence', 'validation', 'unresolved_blockers', 'next_action'):
        assert key in result, key
    assert result['evidence'] and result['validation']
    assert not result['unresolved_blockers']
    print(json.dumps({'ok': True, 'fixture': repo.name, 'route': result['route'], 'scope': 'immutable inputs and complete checkpoint; evaluator must verify actual delegation and evidence correctness from traces'}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('action', choices=['prepare', 'grade']); p.add_argument('path', type=Path)
    p.add_argument('--backend', type=Path); p.add_argument('--frontend', type=Path)
    args = p.parse_args()
    if args.action == 'prepare': prepare(args.path.resolve(), args.backend, args.frontend)
    else: grade(args.path.resolve())
