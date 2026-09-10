#!/usr/bin/env python3
"""Compatibility CLI; the setup skill owns the Obsidian renderer."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).resolve().parents[1] /
                      'skills/in-progress/setup-obsidian-workspace/scripts/obsidian-workspace.py'),
                  run_name='__main__')
