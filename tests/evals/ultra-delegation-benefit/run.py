#!/usr/bin/env python3
"""Run one ASC-04 cell with the fixed paired settings and external time bound."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

p = argparse.ArgumentParser(); p.add_argument('output', type=Path)
p.add_argument('--cli', type=Path, default=Path('/Applications/ChatGPT.app/Contents/Resources/codex'))
p.add_argument('--timeout', type=int, default=600)
a = p.parse_args(); output = a.output.resolve()
if not 1 <= a.timeout <= 1800: p.error('timeout must be 1..1800 seconds and fixed across each pair')
if (output / 'root.jsonl').exists(): p.error('refusing to overwrite an existing model run')
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
command = [str(a.cli), 'exec', '--ignore-user-config', '--enable', 'multi_agent', '-m', 'gpt-6-astra', '-c', 'model_reasoning_effort="high"', '-c', 'approval_policy="never"', '-s', 'danger-full-access', '--json', '-C', str(output / 'repo'), '-']
record = {'command': command, 'cli_version': subprocess.check_output([str(a.cli), '--version'], text=True).strip(), 'timeout_seconds': a.timeout, 'prompt_sha256': sha(output / 'prompt.md'), 'oracle_sha256_before': sha(output / 'oracle.json'), 'started_unix': time.time()}
(output / 'invocation.json').write_text(json.dumps(record, indent=2) + '\n')
start = time.monotonic()
with (output / 'prompt.md').open() as prompt, (output / 'root.jsonl').open('w') as log, (output / 'stderr.log').open('w') as err:
    process = subprocess.Popen(command, stdin=prompt, stdout=log, stderr=err, start_new_session=True)
    try:
        code = process.wait(timeout=a.timeout); record['timed_out'] = False
    except subprocess.TimeoutExpired:
        record['timed_out'] = True
        os.killpg(process.pid, signal.SIGTERM)
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL); process.wait()
        code = 124
        record['child_cleanup'] = 'Native remote child state may survive CLI termination; inspect and stop active writers before grading.'
record.update(exit_code=code, elapsed_seconds=time.monotonic() - start, finished_unix=time.time(), oracle_sha256_after=sha(output / 'oracle.json'))
record['oracle_unchanged'] = record['oracle_sha256_before'] == record['oracle_sha256_after']
(output / 'invocation.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record, indent=2))
raise SystemExit(code if record['oracle_unchanged'] else 3)
