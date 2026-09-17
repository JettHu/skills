#!/usr/bin/env python3
"""Bounded implementation probe; not a full solve lifecycle eval.

Run `fixture.py prepare /tmp/fresh-run`, give only that directory's PROMPT.md
and fixture to an independent agent, then run `fixture.py grade /tmp/fresh-run`.
Inspect its trace for reference discovery and proportional exploration, and its
final files for scope drift. Store prompt, settings, observations, and grade in
local .evals/. The grader verifies behavior, shared authority, and preservation;
it does not prove profile routing, full solve readiness, or absence of all drift.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def prepare(path):
    path.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / 'skills/engineering/ultra', path / 'ultra')
    (path / 'pricing.py').write_text('def discounted_total(cents, percent):\n    return cents * (100 - percent) // 100\n')
    (path / 'checkout.py').write_text('from pricing import discounted_total\ndef checkout_total(cents, percent):\n    return discounted_total(cents, percent)\n')
    (path / 'identity.py').write_text('def account_key(value):\n    return value.strip().casefold()\n')
    (path / 'labels.py').write_text('EMPTY_LABEL = "No saved requirement"\n')
    (path / 'TICKET.md').write_text('''Add quote_total(cents, percent) in quote.py using exactly the checkout discount rules. Add display_label(value) in display.py: strip outer whitespace while preserving case. Change labels.EMPTY_LABEL to "No requirement saved". Preserve existing public contracts. This is a bounded implementation exercise; no broader migration is approved.
''')
    prompt = '''Implement TICKET.md in this isolated fixture, applying ultra/solve.md's bounded exploration and group review guidance. This probe excludes tracker, Claim, worktree, commit, and outcome finalization stages. Read the applicable references through their pointers. All writes must stay in this directory; leave ultra/ and TICKET.md unchanged. Verify the resulting behavior and leave a concise RESULT.md describing decisions, evidence, and validation. Do not read the harness or other fixtures.
'''
    (path / 'PROMPT.md').write_text(prompt)
    baseline = {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in path.rglob('*') if p.is_file()}
    (path / 'baseline.json').write_text(json.dumps(baseline, indent=2))
    print(path)


def grade(path):
    baseline = json.loads((path / 'baseline.json').read_text())
    for name, digest in baseline.items():
        if name != 'labels.py':
            assert hashlib.sha256((path / name).read_bytes()).hexdigest() == digest, name
    code = '''import quote, pricing, display, identity, labels
assert quote.quote_total(101, 15) == 85
assert display.display_label("  MiXeD  ") == "MiXeD"
assert identity.account_key("  MiXeD  ") == "mixed"
assert labels.EMPTY_LABEL == "No requirement saved"
# Changing the shared rule must be observed through the new consumer.
pricing.discounted_total.__code__ = (lambda cents, percent: 777).__code__
assert quote.quote_total(101, 15) == 777, "quote owns a duplicate rule"
'''
    subprocess.run([sys.executable, '-c', code], cwd=path, check=True)
    assert (path / 'RESULT.md').is_file()
    print('PASS: shared pricing authority, distinct display contract, local edit, preserved inputs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'grade'))
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    (prepare if args.action == 'prepare' else grade)(args.path.resolve())
