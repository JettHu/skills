#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python3 - "$REPO" <<'PY'
import json
import pathlib
import re
import sys

repo = pathlib.Path(sys.argv[1])
skill_files = sorted(repo.glob("skills/**/SKILL.md"))
if not skill_files:
    print("no SKILL.md files found", file=sys.stderr)
    sys.exit(1)

name_re = re.compile(r"^[a-z0-9-]+$")
seen = {}
errors = []

for skill_file in skill_files:
    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    rel = skill_file.relative_to(repo)

    if not lines or lines[0] != "---":
        errors.append(f"{rel}: missing opening frontmatter marker")
        continue

    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        errors.append(f"{rel}: missing closing frontmatter marker")
        continue

    metadata = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            errors.append(f"{rel}: invalid frontmatter line: {line}")
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')

    name = metadata.get("name", "")
    description = metadata.get("description", "")

    if not name:
        errors.append(f"{rel}: missing name")
    elif not name_re.match(name):
        errors.append(f"{rel}: invalid name: {name}")
    elif skill_file.parent.name != name:
        errors.append(f"{rel}: directory name does not match skill name: {name}")
    elif name in seen:
        errors.append(f"{rel}: duplicate skill name also found at {seen[name]}")
    else:
        seen[name] = rel

    if not description:
        errors.append(f"{rel}: missing description")

def valid_manifest_path(value):
    return isinstance(value, str) and value.startswith("./")

def skill_path_exists(base, value, manifest_rel):
    if not valid_manifest_path(value):
        errors.append(f"{manifest_rel}: path must start with ./, got: {value!r}")
        return

    target = (base / value).resolve()
    try:
        target.relative_to(repo.resolve())
    except ValueError:
        errors.append(f"{manifest_rel}: path escapes repo: {value}")
        return

    if not (target / "SKILL.md").is_file():
        errors.append(f"{manifest_rel}: missing SKILL.md for path: {value}")

plugin_json = repo / ".claude-plugin" / "plugin.json"
if plugin_json.is_file():
    manifest_rel = plugin_json.relative_to(repo)
    manifest = json.loads(plugin_json.read_text(encoding="utf-8"))
    if not manifest.get("name"):
        errors.append(f"{manifest_rel}: missing name")
    for value in manifest.get("skills", []):
        skill_path_exists(repo, value, manifest_rel)

marketplace_json = repo / ".claude-plugin" / "marketplace.json"
if marketplace_json.is_file():
    manifest_rel = marketplace_json.relative_to(repo)
    manifest = json.loads(marketplace_json.read_text(encoding="utf-8"))
    plugin_root = manifest.get("metadata", {}).get("pluginRoot", "./")
    if not valid_manifest_path(plugin_root):
        errors.append(f"{manifest_rel}: metadata.pluginRoot must start with ./")
        plugin_root = "./"

    for plugin in manifest.get("plugins", []):
        if not plugin.get("name"):
            errors.append(f"{manifest_rel}: plugin missing name")
        source = plugin.get("source", "./")
        if not valid_manifest_path(source):
            errors.append(f"{manifest_rel}: plugin source must start with ./")
            source = "./"
        plugin_base = (repo / plugin_root / source).resolve()
        try:
            plugin_base.relative_to(repo.resolve())
        except ValueError:
            errors.append(f"{manifest_rel}: plugin base escapes repo: {source}")
            plugin_base = repo
        for value in plugin.get("skills", []):
            skill_path_exists(plugin_base, value, manifest_rel)

if errors:
    for error in errors:
        print(error, file=sys.stderr)
    sys.exit(1)

for name, rel in sorted(seen.items()):
    print(f"valid skill: {name} ({rel.parent})")
PY

while IFS= read -r -d '' script; do
  bash -n "$script"
  printf 'valid shell: %s\n' "${script#"$REPO"/}"
done < <(
  find "$REPO/scripts" "$REPO/skills" "$REPO/tests" \
    -type f \
    -name '*.sh' \
    -not -path '*/node_modules/*' \
    -print0
)

while IFS= read -r -d '' script; do
  python3 -m py_compile "$script"
  printf 'valid python: %s\n' "${script#"$REPO"/}"
done < <(
  find "$REPO/skills" "$REPO/tests" \
    -type f \
    -name '*.py' \
    -not -path '*/node_modules/*' \
    -print0
)

if [[ -n "${QUICK_VALIDATE:-}" ]]; then
  while IFS= read -r -d '' skill_md; do
    python "$QUICK_VALIDATE" "$(dirname "$skill_md")"
  done < <(
    find "$REPO/skills" \
      -name SKILL.md \
      -not -path '*/node_modules/*' \
      -print0
  )
fi
