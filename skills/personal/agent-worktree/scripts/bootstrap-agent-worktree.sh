#!/usr/bin/env bash
set -euo pipefail

DEFAULT_CONFIG_PATH=".agents/agent-worktree.env"
DEFAULT_WORKTREE_ROOT_PARENT="../.agent-worktrees"
DEFAULT_BRANCH_PREFIX="work/"
DEFAULT_BASE_REF="HEAD"
DEFAULT_PAYLOAD_CANDIDATES="AGENTS.md AGENTS.override.md CLAUDE.md CONTEXT.md docs/adr .agents/skills docs/agents docs/local .scratch .env .env.local .env.development .env.development.local .env.test .env.test.local .env.production .env.production.local .envrc logs log cache .cache tmp temp .tmp node_modules .venv venv env .tox .nox .pytest_cache .mypy_cache .ruff_cache vendor .bundle target .gradle"
DEFAULT_MODE="link"
MARKER="# Agent worktree local context"

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-agent-worktree.sh init [options]
  bootstrap-agent-worktree.sh suggest-payload [options]
  bootstrap-agent-worktree.sh create <name> [options]
  bootstrap-agent-worktree.sh bootstrap <target-worktree> [options]
  bootstrap-agent-worktree.sh verify <target-worktree> [options]
  bootstrap-agent-worktree.sh remove <name> [options]
  bootstrap-agent-worktree.sh remove --current [options]

Compatibility:
  bootstrap-agent-worktree.sh [--copy|--link] [--source <source-root>] <target-worktree>

Commands:
  init       Create/show repo-local config and ignore rules.
  suggest-payload
             Show candidate untracked local worktree PAYLOAD paths without writing config.
  create     Create or ensure a branch-backed Agent worktree, then bootstrap and verify it.
  bootstrap  Inject local worktree payload into an existing worktree.
  verify     Check an existing worktree has local payload and does not expose it to Git.
  remove     Remove a named or explicitly current Agent worktree.

Global options:
  --config <path>          Config path, default .agents/agent-worktree.env.
  --source <source-root>   Source checkout, default current Git repo; remove --current uses the primary worktree.
  --payload <paths>        Override PAYLOAD for this run; init writes it when config is missing.
  --link                   Override MODE=copy.
  --copy                   Override MODE=link.

Create options:
  --branch <branch>        Exact branch name. Highest priority.
  --base-ref <ref>         Override BASE_REF for newly created worktrees.
  --path <path>            Exact worktree path.

Init/create/remove options:
  --branch-prefix <prefix> Override BRANCH_PREFIX.
  --worktree-root <path>   Override WORKTREE_ROOT.

Remove options:
  --current                Remove the current worktree. Not valid from the source checkout.
  --delete-branch          Also delete the worktree branch after removing the worktree.
  --dry-run                Show what remove would do without changing anything.
  --force                  Allow dirty worktree removal and force branch deletion with --delete-branch.
USAGE
}

log() {
  printf '[agent-worktree] %s\n' "$*"
}

die() {
  printf '[agent-worktree] %s\n' "$*" >&2
  exit 2
}

command=""
source_root_arg=""
config_path_arg="$DEFAULT_CONFIG_PATH"
mode_override=""
branch_arg=""
branch_prefix_arg=""
base_ref_arg=""
payload_arg=""
worktree_root_arg=""
path_arg=""
current_arg="false"
delete_branch_arg="false"
dry_run_arg="false"
force_arg="false"
positionals=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    init|suggest-payload|create|bootstrap|verify|remove)
      if [[ -n "$command" ]]; then
        die "multiple commands provided: $command and $1"
      fi
      command="$1"
      shift
      ;;
    --copy)
      mode_override="copy"
      shift
      ;;
    --link)
      mode_override="link"
      shift
      ;;
    --source)
      [[ $# -ge 2 ]] || die "--source requires a path"
      source_root_arg="$2"
      shift 2
      ;;
    --config)
      [[ $# -ge 2 ]] || die "--config requires a path"
      config_path_arg="$2"
      shift 2
      ;;
    --branch)
      [[ $# -ge 2 ]] || die "--branch requires a branch name"
      branch_arg="$2"
      shift 2
      ;;
    --branch-prefix)
      [[ $# -ge 2 ]] || die "--branch-prefix requires a prefix"
      branch_prefix_arg="$2"
      shift 2
      ;;
    --base-ref)
      [[ $# -ge 2 ]] || die "--base-ref requires a git ref"
      base_ref_arg="$2"
      shift 2
      ;;
    --payload)
      [[ $# -ge 2 ]] || die "--payload requires a space-separated path list"
      payload_arg="$2"
      shift 2
      ;;
    --worktree-root)
      [[ $# -ge 2 ]] || die "--worktree-root requires a path"
      worktree_root_arg="$2"
      shift 2
      ;;
    --path)
      [[ $# -ge 2 ]] || die "--path requires a path"
      path_arg="$2"
      shift 2
      ;;
    --current)
      current_arg="true"
      shift
      ;;
    --delete-branch)
      delete_branch_arg="true"
      shift
      ;;
    --dry-run)
      dry_run_arg="true"
      shift
      ;;
    --force)
      force_arg="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      usage >&2
      die "unknown option: $1"
      ;;
    *)
      positionals+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$command" && ${#positionals[@]} -eq 1 ]]; then
  command="bootstrap"
fi

if [[ -z "$command" ]]; then
  usage >&2
  die "command is required"
fi

if [[ "$command" != "create" && "$command" != "remove" ]]; then
  [[ -z "$branch_arg" ]] || die "--branch is only valid with create or remove"
fi

if [[ "$command" != "init" && "$command" != "create" && "$command" != "remove" ]]; then
  [[ -z "$branch_prefix_arg" ]] || die "--branch-prefix is only valid with init, create, or remove"
  [[ -z "$worktree_root_arg" ]] || die "--worktree-root is only valid with init, create, or remove"
fi

if [[ "$command" != "create" && "$command" != "remove" ]]; then
  [[ -z "$path_arg" ]] || die "--path is only valid with create or remove"
fi

if [[ "$command" != "init" && "$command" != "create" ]]; then
  [[ -z "$base_ref_arg" ]] || die "--base-ref is only valid with init or create"
fi

if [[ "$command" == "remove" || "$command" == "suggest-payload" ]]; then
  [[ -z "$payload_arg" ]] || die "--payload is not valid with $command"
fi

if [[ "$command" != "remove" ]]; then
  [[ "$current_arg" == "false" ]] || die "--current is only valid with remove"
  [[ "$delete_branch_arg" == "false" ]] || die "--delete-branch is only valid with remove"
  [[ "$dry_run_arg" == "false" ]] || die "--dry-run is only valid with remove"
  [[ "$force_arg" == "false" ]] || die "--force is only valid with remove"
fi

infer_source_root() {
  local cwd_root primary_root

  if ! cwd_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)"; then
    die "could not infer source checkout; run from a git worktree or pass --source <source-root>"
  fi

  if [[ "$command" == "remove" && "$current_arg" == "true" ]]; then
    primary_root="$(
      git -C "$cwd_root" worktree list --porcelain |
        awk 'BEGIN { root = "" } /^worktree / { sub(/^worktree /, ""); print; exit }'
    )"

    if [[ -n "$primary_root" ]]; then
      printf '%s\n' "$primary_root"
      return
    fi
  fi

  printf '%s\n' "$cwd_root"
}

if [[ -z "$source_root_arg" ]]; then
  source_root_arg="$(infer_source_root)"
fi

source_root="$(cd "$source_root_arg" && pwd -P)"
source_root="$(git -C "$source_root" rev-parse --show-toplevel)"

if [[ "$config_path_arg" = /* ]]; then
  config_file="$config_path_arg"
else
  config_file="$source_root/$config_path_arg"
fi

detect_default_payload() {
  local rel
  local detected_items=()

  for rel in $DEFAULT_PAYLOAD_CANDIDATES; do
    append_detected_payload "$rel"
  done

  while IFS= read -r rel; do
    append_detected_payload "$rel"
  done < <(discover_payload_candidates)

  local IFS=" "
  printf '%s\n' "${detected_items[*]-}"
}

append_detected_payload() {
  local rel="$1"

  [[ -n "$rel" ]] || return
  case "$rel" in
    /*|../*|*/../*|*[[:space:]]*) return ;;
  esac

  if [[ ! -e "$source_root/$rel" && ! -L "$source_root/$rel" ]]; then
    return
  fi

  if path_tracked_by_git "$rel"; then
    return
  fi

  if [[ ${#detected_items[@]} -gt 0 ]] && payload_contains "$rel" "${detected_items[@]}"; then
    return
  fi

  detected_items+=("$rel")
}

discover_payload_candidates() {
  local path rel

  while IFS= read -r path; do
    rel="${path#"$source_root"/}"
    printf '%s\n' "$rel"
  done < <(
    find "$source_root" -maxdepth 3 \
      \( -path "$source_root/.git" -o -path "$source_root/.worktrees" -o -path "$source_root/.agent-worktrees" \) -prune -o \
      \( -type d \( -name node_modules -o -name .venv -o -name venv -o -name env -o -name .tox -o -name .nox -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name vendor -o -name .bundle -o -name target -o -name .gradle -o -name logs -o -name log -o -name cache -o -name .cache -o -name tmp -o -name temp -o -name .tmp \) -print -prune \) -o \
      \( -type f \( -name '.env' -o -name '.env.*' -o -name '.envrc' -o -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print \) |
      sort
  )
}

payload_contains() {
  local needle="$1"
  shift
  local item

  for item in "$@"; do
    if [[ "$item" == "$needle" ]]; then
      return 0
    fi
  done

  return 1
}

path_tracked_by_git() {
  local rel="$1"
  [[ -n "$(git -C "$source_root" ls-files -- "$rel")" ]]
}

print_payload_suggestion() {
  detect_default_payload
}

default_worktree_root() {
  printf '%s/%s\n' "$DEFAULT_WORKTREE_ROOT_PARENT" "$(basename "$source_root")"
}

WORKTREE_ROOT="$(default_worktree_root)"
BRANCH_PREFIX="$DEFAULT_BRANCH_PREFIX"
BASE_REF="$DEFAULT_BASE_REF"
PAYLOAD="$(detect_default_payload)"
MODE="$DEFAULT_MODE"

load_config() {
  local default_root detected_payload

  default_root="$(default_worktree_root)"
  detected_payload="$(detect_default_payload)"
  WORKTREE_ROOT="$default_root"
  BRANCH_PREFIX="$DEFAULT_BRANCH_PREFIX"
  BASE_REF="$DEFAULT_BASE_REF"
  PAYLOAD="$detected_payload"
  MODE="$DEFAULT_MODE"

  if [[ -f "$config_file" ]]; then
    # shellcheck disable=SC1090
    source "$config_file"
  fi

  WORKTREE_ROOT="${WORKTREE_ROOT:-$default_root}"
  BRANCH_PREFIX="${BRANCH_PREFIX:-$DEFAULT_BRANCH_PREFIX}"
  BASE_REF="${BASE_REF:-$DEFAULT_BASE_REF}"
  PAYLOAD="${PAYLOAD:-$detected_payload}"
  MODE="${MODE:-$DEFAULT_MODE}"

  if [[ -n "$base_ref_arg" ]]; then
    BASE_REF="$base_ref_arg"
  fi

  if [[ -n "$branch_prefix_arg" ]]; then
    BRANCH_PREFIX="$branch_prefix_arg"
  fi

  if [[ -n "$worktree_root_arg" ]]; then
    WORKTREE_ROOT="$worktree_root_arg"
  fi

  if [[ -n "$payload_arg" ]]; then
    PAYLOAD="$payload_arg"
  fi

  if [[ -n "$mode_override" ]]; then
    MODE="$mode_override"
  fi

  case "$MODE" in
    link|copy) ;;
    *) die "MODE must be link or copy, got: $MODE" ;;
  esac
}

repo_relative_config_path() {
  local path="$1"
  case "$path" in
    "$source_root"/*)
      printf '%s\n' "${path#"$source_root"/}"
      ;;
    *)
      return 1
      ;;
  esac
}

add_exclude_patterns() {
  local checkout="$1"
  shift
  local exclude_file pattern

  exclude_file="$(git -C "$checkout" rev-parse --git-path info/exclude)"
  mkdir -p "$(dirname "$exclude_file")"
  touch "$exclude_file"

  if ! grep -Fxq "$MARKER" "$exclude_file"; then
    printf '\n%s\n' "$MARKER" >> "$exclude_file"
  fi

  for pattern in "$@"; do
    if ! grep -Fxq "$pattern" "$exclude_file"; then
      printf '%s\n' "$pattern" >> "$exclude_file"
    fi
  done
}

payload_patterns() {
  local rel src
  for rel in $PAYLOAD; do
    printf '/%s\n' "$rel"
    src="$source_root/$rel"
    if [[ -d "$src" ]]; then
      printf '/%s/\n' "$rel"
    fi
  done
}

source_ignore_patterns() {
  local rel_config
  if rel_config="$(repo_relative_config_path "$config_file")"; then
    printf '/%s\n' "$rel_config"
  fi
  payload_patterns
}

ensure_source_exclude() {
  local patterns=()
  while IFS= read -r pattern; do
    patterns+=("$pattern")
  done < <(source_ignore_patterns)

  add_exclude_patterns "$source_root" "${patterns[@]}"
}

ensure_target_exclude() {
  local target_root="$1"
  local patterns=()
  while IFS= read -r pattern; do
    patterns+=("$pattern")
  done < <(payload_patterns)

  add_exclude_patterns "$target_root" "${patterns[@]}"
}

create_default_config() {
  local config_worktree_root config_branch_prefix config_base_ref config_payload config_mode default_root

  mkdir -p "$(dirname "$config_file")"

  if [[ -e "$config_file" ]]; then
    log "config exists: $config_file"
    if [[ -n "$worktree_root_arg" || -n "$branch_prefix_arg" || -n "$base_ref_arg" || -n "$payload_arg" || -n "$mode_override" ]]; then
      log "provided config options affect this run only; existing config was not edited"
    fi
    return
  fi

  default_root="$(default_worktree_root)"
  config_worktree_root="${worktree_root_arg:-$default_root}"
  config_branch_prefix="${branch_prefix_arg:-$DEFAULT_BRANCH_PREFIX}"
  config_base_ref="${base_ref_arg:-$DEFAULT_BASE_REF}"
  if [[ -n "$payload_arg" ]]; then
    config_payload="$payload_arg"
  else
    config_payload="$(detect_default_payload)"
  fi
  config_mode="${mode_override:-$DEFAULT_MODE}"

  cat > "$config_file" <<EOF
# Worktrees are created as \$WORKTREE_ROOT/<repo-name>-<slug>.
# Keep this outside the repo root so generated worktrees do not appear as untracked files.
WORKTREE_ROOT="$config_worktree_root"

# Branches are created as \$BRANCH_PREFIX<slug>.
BRANCH_PREFIX="$config_branch_prefix"

# New worktrees start from this git ref.
BASE_REF="$config_base_ref"

# Space-separated repo-root-relative local worktree payload paths.
# Generated from --payload when provided; otherwise from common untracked local Agent, runtime, and debug paths present in this repo.
PAYLOAD="$config_payload"

# MODE can be link or copy. Prefer link for shared local Agent context.
MODE="$config_mode"
EOF
  log "created config: $config_file"
  log "review PAYLOAD in config before relying on it for this repo"
}

print_effective_config() {
  log "source: $source_root"
  log "config: $config_file"
  log "WORKTREE_ROOT=$WORKTREE_ROOT"
  log "BRANCH_PREFIX=$BRANCH_PREFIX"
  log "BASE_REF=$BASE_REF"
  log "PAYLOAD=$PAYLOAD"
  log "MODE=$MODE"
}

target_root_for() {
  local target="$1"
  local target_abs

  target_abs="$(cd "$target" && pwd -P)"
  git -C "$target_abs" rev-parse --show-toplevel
}

same_link_target() {
  local dst="$1" src="$2"
  [[ -L "$dst" && "$(readlink "$dst")" == "$src" ]]
}

install_item() {
  local target_root="$1"
  local rel="$2"
  local src="$source_root/$rel"
  local dst="$target_root/$rel"

  if [[ ! -e "$src" && ! -L "$src" ]]; then
    log "skip missing source: $rel"
    return
  fi

  mkdir -p "$(dirname "$dst")"

  if same_link_target "$dst" "$src"; then
    log "already linked: $rel"
    return
  fi

  if [[ -e "$dst" || -L "$dst" ]]; then
    log "exists, leaving intact: $rel"
    return
  fi

  if [[ "$MODE" == "copy" ]]; then
    cp -R "$src" "$dst"
    log "copied: $rel"
  else
    ln -s "$src" "$dst"
    log "linked: $rel"
  fi
}

bootstrap_worktree() {
  local target="$1"
  local target_root rel

  target_root="$(target_root_for "$target")" || die "target is not a git worktree: $target"

  if [[ "$source_root" == "$target_root" ]]; then
    die "target is the source checkout; nothing to bootstrap"
  fi

  ensure_target_exclude "$target_root"

  for rel in $PAYLOAD; do
    install_item "$target_root" "$rel"
  done

  log "bootstrap complete: $target_root"
}

status_lists_payload_path() {
  local status="$1"
  local rel line path

  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    path="${line:3}"
    for rel in $PAYLOAD; do
      if [[ "$path" == "$rel" || "$path" == "$rel/"* ]]; then
        return 0
      fi
    done
  done <<< "$status"

  return 1
}

verify_worktree_status() {
  local target="$1"
  local target_root rel src dst status

  target_root="$(target_root_for "$target")" || {
    log "verify failed: target is not a git worktree: $target"
    return 1
  }

  if [[ "$source_root" == "$target_root" ]]; then
    log "verify failed: target is the source checkout"
    return 1
  fi

  for rel in $PAYLOAD; do
    src="$source_root/$rel"
    dst="$target_root/$rel"
    if [[ -e "$src" || -L "$src" ]]; then
      if [[ ! -e "$dst" && ! -L "$dst" ]]; then
        log "verify failed: missing payload in target: $rel"
        return 1
      fi
    fi
  done

  status="$(git -C "$target_root" status --short --untracked-files=all)"
  if status_lists_payload_path "$status"; then
    printf '%s\n' "$status" >&2
    log "verify failed: Git status lists local Agent context files"
    return 1
  fi

  if [[ -n "$status" ]]; then
    log "Git status has non-Agent changes:"
    printf '%s\n' "$status"
  else
    log "Git status clean"
  fi

  log "verify complete: $target_root"
}

verify_worktree() {
  verify_worktree_status "$1" || exit 2
}

normalize_slug() {
  local input="$1"
  local slug

  slug="$(
    printf '%s' "$input" |
      tr '[:upper:]' '[:lower:]' |
      sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
  )"

  [[ -n "$slug" ]] || die "name does not produce a valid slug: $input"
  printf '%s\n' "$slug"
}

join_positionals() {
  local joined="" arg
  for arg in "$@"; do
    if [[ -z "$joined" ]]; then
      joined="$arg"
    else
      joined="$joined $arg"
    fi
  done
  printf '%s\n' "$joined"
}

resolve_under_source() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$source_root/$path"
  fi
}

derive_named_worktree() {
  local name="$1"
  local repo_name effective_branch_prefix worktree_root

  DERIVED_SLUG="$(normalize_slug "$name")"
  effective_branch_prefix="${branch_prefix_arg:-$BRANCH_PREFIX}"
  DERIVED_BRANCH="${branch_arg:-$effective_branch_prefix$DERIVED_SLUG}"

  if [[ -n "$worktree_root_arg" ]]; then
    worktree_root="$worktree_root_arg"
  else
    worktree_root="$WORKTREE_ROOT"
  fi

  repo_name="$(basename "$source_root")"

  if [[ -n "$path_arg" ]]; then
    DERIVED_WORKTREE_PATH="$(resolve_under_source "$path_arg")"
  else
    worktree_root="$(resolve_under_source "$worktree_root")"
    DERIVED_WORKTREE_PATH="$worktree_root/$repo_name-$DERIVED_SLUG"
  fi
}

branch_exists() {
  local branch="$1"
  git -C "$source_root" show-ref --verify --quiet "refs/heads/$branch"
}

current_branch_for() {
  local target_root="$1"
  git -C "$target_root" symbolic-ref --quiet --short HEAD
}

require_clean_status() {
  local target_root="$1"
  local status
  status="$(git -C "$target_root" status --short --untracked-files=all)"
  if [[ -n "$status" ]]; then
    printf '%s\n' "$status" >&2
    die "newly created worktree is not clean"
  fi
}

create_or_ensure_worktree() {
  local name branch worktree_path
  local path_existed="false"
  local target_root current_branch parent_dir

  [[ ${#positionals[@]} -ge 1 ]] || die "create requires a name"
  name="$(join_positionals "${positionals[@]}")"
  derive_named_worktree "$name"
  branch="$DERIVED_BRANCH"
  worktree_path="$DERIVED_WORKTREE_PATH"

  if [[ -e "$worktree_path" || -L "$worktree_path" ]]; then
    path_existed="true"
    target_root="$(target_root_for "$worktree_path")" || die "path exists but is not a git worktree: $worktree_path"
    current_branch="$(current_branch_for "$target_root")" || die "existing worktree is detached: $target_root"

    if [[ "$current_branch" != "$branch" ]]; then
      die "existing worktree branch mismatch: expected $branch, got $current_branch"
    fi

    log "worktree already exists on expected branch: $target_root"

    if verify_worktree_status "$target_root"; then
      log "worktree already Agent-ready: $target_root"
      log "ready: branch=$branch path=$target_root"
      return
    fi

    log "worktree needs bootstrap: $target_root"
  else
    if branch_exists "$branch"; then
      die "branch already exists without expected worktree: $branch"
    fi

    parent_dir="$(dirname "$worktree_path")"
    mkdir -p "$parent_dir"
    git -C "$source_root" worktree add -b "$branch" "$worktree_path" "$BASE_REF"
    target_root="$(target_root_for "$worktree_path")"
    log "created worktree from $BASE_REF: $target_root"
  fi

  bootstrap_worktree "$target_root"
  verify_worktree "$target_root"

  if [[ "$path_existed" == "false" ]]; then
    require_clean_status "$target_root"
  fi

  log "ready: branch=$branch path=$target_root"
}

dirty_status_for() {
  local target_root="$1"
  git -C "$target_root" status --short --untracked-files=all
}

remove_worktree_path() {
  local target_root="$1"
  local branch="$2"
  local status

  if [[ "$source_root" == "$target_root" ]]; then
    die "refusing to remove the source checkout"
  fi

  status="$(dirty_status_for "$target_root")"
  if [[ "$dry_run_arg" == "true" ]]; then
    log "dry-run: worktree=$target_root"
    if [[ -n "$branch" ]]; then
      log "dry-run: branch=$branch"
    else
      log "dry-run: branch=<detached>"
    fi

    if [[ -n "$status" ]]; then
      log "dry-run: worktree has uncommitted changes:"
      printf '%s\n' "$status"
      if [[ "$force_arg" == "false" ]]; then
        log "dry-run: remove would fail without --force"
      fi
    else
      log "dry-run: worktree status clean"
    fi

    log "dry-run: would remove worktree: $target_root"
    log "dry-run: would run git worktree prune"

    if [[ "$delete_branch_arg" == "true" ]]; then
      if [[ -n "$branch" ]]; then
        if [[ "$force_arg" == "true" ]]; then
          log "dry-run: would force-delete branch: $branch"
        else
          log "dry-run: would delete merged branch: $branch"
        fi
      else
        log "dry-run: branch deletion requested, but target is detached"
      fi
    else
      log "dry-run: would keep branch"
    fi
    return
  fi

  if [[ -n "$status" && "$force_arg" == "false" ]]; then
    printf '%s\n' "$status" >&2
    die "worktree has uncommitted changes; use --force to remove it anyway"
  fi

  log "removing worktree: $target_root"
  if [[ "$force_arg" == "true" ]]; then
    git -C "$source_root" worktree remove --force "$target_root"
  else
    git -C "$source_root" worktree remove "$target_root"
  fi
  git -C "$source_root" worktree prune

  if [[ -e "$target_root" || -L "$target_root" ]]; then
    die "worktree path still exists after remove: $target_root"
  fi

  log "removed worktree: $target_root"

  if [[ "$delete_branch_arg" == "true" ]]; then
    [[ -n "$branch" ]] || die "--delete-branch requested, but target worktree was detached"

    if ! branch_exists "$branch"; then
      log "branch already absent: $branch"
      return
    fi

    if [[ "$force_arg" == "true" ]]; then
      git -C "$source_root" branch -D "$branch"
    else
      git -C "$source_root" branch -d "$branch"
    fi
    log "deleted branch: $branch"
  fi
}

remove_worktree() {
  local name target_root current_branch branch worktree_path

  if [[ "$current_arg" == "true" ]]; then
    [[ ${#positionals[@]} -eq 0 ]] || die "remove --current does not accept a name"
    [[ -z "$branch_arg" ]] || die "--branch is not valid with remove --current"
    [[ -z "$branch_prefix_arg" ]] || die "--branch-prefix is not valid with remove --current"
    [[ -z "$worktree_root_arg" ]] || die "--worktree-root is not valid with remove --current"
    [[ -z "$path_arg" ]] || die "--path is not valid with remove --current"

    target_root="$(target_root_for "$PWD")" || die "current directory is not inside a git worktree"
    [[ "$target_root" != "$source_root" ]] || die "remove --current is not valid from the source checkout"

    if current_branch="$(current_branch_for "$target_root")"; then
      branch="$current_branch"
    else
      branch=""
    fi

    # Leave the soon-to-be-removed worktree before deleting it so later shell
    # and Git cleanup never run from a missing current directory.
    cd "$source_root"
    remove_worktree_path "$target_root" "$branch"
    return
  fi

  [[ ${#positionals[@]} -ge 1 ]] || die "remove requires <name> or --current"
  name="$(join_positionals "${positionals[@]}")"
  derive_named_worktree "$name"
  branch="$DERIVED_BRANCH"
  worktree_path="$DERIVED_WORKTREE_PATH"

  [[ -e "$worktree_path" || -L "$worktree_path" ]] || die "expected worktree path does not exist: $worktree_path"
  target_root="$(target_root_for "$worktree_path")" || die "path exists but is not a git worktree: $worktree_path"
  current_branch="$(current_branch_for "$target_root")" || die "expected named worktree is detached: $target_root"

  if [[ "$current_branch" != "$branch" ]]; then
    die "worktree branch mismatch: expected $branch, got $current_branch"
  fi

  remove_worktree_path "$target_root" "$branch"
}

case "$command" in
  suggest-payload)
    [[ ${#positionals[@]} -eq 0 ]] || die "suggest-payload does not accept positional arguments"
    print_payload_suggestion
    ;;
  init)
    [[ ${#positionals[@]} -eq 0 ]] || die "init does not accept positional arguments"
    create_default_config
    load_config
    ensure_source_exclude
    print_effective_config
    ;;
  create)
    create_default_config
    load_config
    ensure_source_exclude
    create_or_ensure_worktree
    ;;
  bootstrap)
    [[ ${#positionals[@]} -eq 1 ]] || die "bootstrap requires exactly one target worktree"
    load_config
    bootstrap_worktree "${positionals[0]}"
    verify_worktree "${positionals[0]}"
    ;;
  verify)
    [[ ${#positionals[@]} -eq 1 ]] || die "verify requires exactly one target worktree"
    load_config
    verify_worktree "${positionals[0]}"
    ;;
  remove)
    load_config
    remove_worktree
    ;;
esac
