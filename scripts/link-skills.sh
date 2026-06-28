#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
force="false"
dest_args=()

usage() {
  cat <<'USAGE'
Usage:
  scripts/link-skills.sh [--force] [destination ...]

If no destination is provided, links every skill into:
  ~/.agents/skills
  ~/.claude/skills

By default, existing non-symlink skill directories are left intact.
Pass --force to replace them.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      force="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      usage >&2
      printf 'unknown option: %s\n' "$1" >&2
      exit 2
      ;;
    *)
      dest_args+=("$1")
      shift
      ;;
  esac
done

if [[ ${#dest_args[@]} -gt 0 ]]; then
  DESTS=("${dest_args[@]}")
else
  DESTS=("$HOME/.agents/skills" "$HOME/.claude/skills")
fi

names=()
srcs=()
while IFS= read -r -d '' skill_md; do
  src="$(dirname "$skill_md")"
  names+=("$(basename "$src")")
  srcs+=("$src")
done < <(
  find "$REPO/skills" \
    -name SKILL.md \
    -not -path '*/node_modules/*' \
    -not -path '*/deprecated/*' \
    -print0
)

if [[ ${#names[@]} -eq 0 ]]; then
  printf 'no skills found under %s/skills\n' "$REPO" >&2
  exit 1
fi

for dest in "${DESTS[@]}"; do
  mkdir -p "$dest"

  for i in "${!names[@]}"; do
    name="${names[$i]}"
    src="${srcs[$i]}"
    target="$dest/$name"

    if [[ -e "$target" || -L "$target" ]]; then
      if [[ -L "$target" ]]; then
        ln -sfn "$src" "$target"
        printf 'linked %s -> %s (%s)\n' "$name" "$src" "$dest"
        continue
      fi

      if [[ "$force" == "true" ]]; then
        rm -rf "$target"
      else
        printf 'skipped existing non-symlink: %s\n' "$target" >&2
        continue
      fi
    fi

    ln -s "$src" "$target"
    printf 'linked %s -> %s (%s)\n' "$name" "$src" "$dest"
  done
done
