#!/usr/bin/env bash
set -euo pipefail

DEFAULT_CONFIG_PATH=".agents/agent-worktree.env"
DEFAULT_PAYLOAD_CANDIDATES="AGENTS.md AGENTS.override.md CLAUDE.md CONTEXT.md docs/adr .agents/skills docs/agents docs/local .scratch .env .env.local .env.development .env.development.local .env.test .env.test.local .env.production .env.production.local .envrc"
DEFAULT_MODE="link"
DEFAULT_DEPENDENCY_STRATEGY="none"
DEFAULT_DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="120"
EXCLUDE_MARKER="# Agent worktree local context"
HOOK_BEGIN="# --- agent-worktree managed block begin ---"
HOOK_END="# --- agent-worktree managed block end ---"

usage() {
  cat <<'USAGE'
Usage:
  bootstrap-agent-worktree.sh [init] [options]
  bootstrap-agent-worktree.sh suggest-payload [options]
  bootstrap-agent-worktree.sh add-payload <path>... [options]
  bootstrap-agent-worktree.sh remove-payload <path>... [options]
  bootstrap-agent-worktree.sh regenerate-payload [options]
  bootstrap-agent-worktree.sh set-mode <link|copy> [options]
  bootstrap-agent-worktree.sh set-dependency-strategy <bootstrap|link|none> [options]
  bootstrap-agent-worktree.sh reinstall-hook [options]
  bootstrap-agent-worktree.sh disable [options]
  bootstrap-agent-worktree.sh uninstall [options]

Options:
  --source <source-root>   Source checkout, default current Git repo.
  --config <path>          Config path, default .agents/agent-worktree.env.
  --payload <paths>        Space-separated repo-relative payload list for init.
  --mode <link|copy>       Payload injection mode.
  --link                   Same as --mode link.
  --copy                   Same as --mode copy.
  --dependency-strategy <bootstrap|link|none>
                           Dependency handling strategy, separate from payload.
  --dependency-payload <paths>
                           Explicit dependency paths for dependency link mode.
  --dependency-bootstrap-offline <command>
                           Offline/cache-only bootstrap command.
  --dependency-bootstrap-online <command>
                           Online lockfile-respecting fallback command.
  --dependency-timeout <seconds>
                           Bootstrap timeout, default 120.

Notes:
  Daily worktree creation is native Git:
    git worktree add <path> <branch-or-ref>
  This script only scaffolds the repo-local post-checkout hook and payload config.
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
payload_arg=""
mode_arg=""
dependency_strategy_arg=""
dependency_payload_arg=""
dependency_bootstrap_offline_arg=""
dependency_bootstrap_online_arg=""
dependency_timeout_arg=""
positionals=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    init|suggest-payload|add-payload|remove-payload|regenerate-payload|set-mode|set-dependency-strategy|reinstall-hook|disable|uninstall)
      if [[ -n "$command" ]]; then
        die "multiple commands provided: $command and $1"
      fi
      command="$1"
      shift
      ;;
    create|bootstrap|verify|remove|doctor|repair)
      die "$1 is no longer an agent-worktree interface; use native git worktree add for creation and \$solve-records cleanup for solve resource cleanup"
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
    --payload)
      [[ $# -ge 2 ]] || die "--payload requires a space-separated path list"
      payload_arg="$2"
      shift 2
      ;;
    --mode)
      [[ $# -ge 2 ]] || die "--mode requires link or copy"
      mode_arg="$2"
      shift 2
      ;;
    --link)
      mode_arg="link"
      shift
      ;;
    --copy)
      mode_arg="copy"
      shift
      ;;
    --dependency-strategy)
      [[ $# -ge 2 ]] || die "--dependency-strategy requires bootstrap, link, or none"
      dependency_strategy_arg="$2"
      shift 2
      ;;
    --dependency-payload)
      [[ $# -ge 2 ]] || die "--dependency-payload requires a space-separated path list"
      dependency_payload_arg="$2"
      shift 2
      ;;
    --dependency-bootstrap-offline)
      [[ $# -ge 2 ]] || die "--dependency-bootstrap-offline requires a command"
      dependency_bootstrap_offline_arg="$2"
      shift 2
      ;;
    --dependency-bootstrap-online)
      [[ $# -ge 2 ]] || die "--dependency-bootstrap-online requires a command"
      dependency_bootstrap_online_arg="$2"
      shift 2
      ;;
    --dependency-timeout)
      [[ $# -ge 2 ]] || die "--dependency-timeout requires seconds"
      dependency_timeout_arg="$2"
      shift 2
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

if [[ -z "$command" ]]; then
  command="init"
fi

infer_source_root() {
  local cwd_root
  if ! cwd_root="$(git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)"; then
    die "could not infer source checkout; run from a git worktree or pass --source <source-root>"
  fi
  printf '%s\n' "$cwd_root"
}

if [[ -z "$source_root_arg" ]]; then
  source_root_arg="$(infer_source_root)"
fi

source_root="$(cd "$source_root_arg" && pwd -P)"
source_root="$(git -C "$source_root" rev-parse --show-toplevel)"
common_dir="$(git -C "$source_root" rev-parse --path-format=absolute --git-common-dir)"
if [[ "$common_dir" == */.git && -d "${common_dir%/.git}" ]]; then
  source_root="${common_dir%/.git}"
fi

if [[ "$config_path_arg" = /* ]]; then
  config_file="$config_path_arg"
else
  config_file="$source_root/$config_path_arg"
fi

validate_mode() {
  case "$1" in
    link|copy) ;;
    *) die "MODE must be link or copy, got: $1" ;;
  esac
}

validate_dependency_strategy() {
  case "$1" in
    bootstrap|link|none) ;;
    *) die "DEPENDENCY_STRATEGY must be bootstrap, link, or none, got: $1" ;;
  esac
}

validate_timeout_seconds() {
  case "$1" in
    ""|*[!0-9]*) die "DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS must be a positive integer, got: $1" ;;
    0) die "DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS must be greater than zero" ;;
  esac
}

validate_config_value() {
  local value="$1"
  case "$value" in
    *\"*|*$'\n'*)
      die "config values must not contain double quotes or newlines"
      ;;
  esac
}

validate_payload_path() {
  local rel="$1"
  case "$rel" in
    ""|/*|../*|*/../*|*[[:space:]]*|*[![:alnum:]_./-]*)
      die "invalid repo-relative payload path: $rel"
      ;;
  esac
}

path_tracked_by_git() {
  local rel="$1"
  [[ -n "$(git -C "$source_root" ls-files -- "$rel")" ]]
}

payload_contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

normalize_payload() {
  local raw="$1"
  local rel
  local items=()
  for rel in $raw; do
    validate_payload_path "$rel"
    if [[ ${#items[@]} -eq 0 ]] || ! payload_contains "$rel" "${items[@]}"; then
      items+=("$rel")
    fi
  done
  local IFS=" "
  printf '%s\n' "${items[*]-}"
}

discover_payload_candidates() {
  local path rel
  while IFS= read -r path; do
    rel="${path#"$source_root"/}"
    printf '%s\n' "$rel"
  done < <(
    find "$source_root" -maxdepth 3 \
      \( -path "$source_root/.git" -o -path "$source_root/.worktrees" -o -path "$source_root/.agent-worktrees" \) -prune -o \
      \( -type d \( -name node_modules -o -name .venv -o -name venv -o -name env -o -name .tox -o -name .nox -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name vendor -o -name .bundle -o -name target -o -name .gradle -o -name build -o -name .next -o -name dist -o -name logs -o -name log -o -name cache -o -name .cache -o -name tmp -o -name temp -o -name .tmp \) -prune \) -o \
      \( -type f \( -name '.env' -o -name '.env.*' -o -name '.envrc' -o -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print \) |
      sort
  )
}

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

detect_dependency_ecosystem() {
  if [[ -f "$source_root/pnpm-lock.yaml" ]]; then
    printf 'pnpm\n'
  elif [[ -f "$source_root/uv.lock" ]]; then
    printf 'uv\n'
  elif [[ -f "$source_root/package-lock.json" || -f "$source_root/yarn.lock" || -f "$source_root/bun.lockb" || -f "$source_root/requirements.txt" || -f "$source_root/Cargo.lock" || -f "$source_root/go.mod" || -f "$source_root/pom.xml" || -f "$source_root/build.gradle" || -f "$source_root/build.gradle.kts" ]]; then
    printf 'no-fast-installer\n'
  else
    printf 'none\n'
  fi
}

dependency_strategy_for_ecosystem() {
  case "$1" in
    pnpm|uv) printf 'bootstrap\n' ;;
    *) printf 'none\n' ;;
  esac
}

dependency_bootstrap_offline_for_ecosystem() {
  case "$1" in
    pnpm) printf 'pnpm install --offline --frozen-lockfile\n' ;;
    uv) printf 'uv sync --offline --locked\n' ;;
  esac
}

dependency_bootstrap_online_for_ecosystem() {
  case "$1" in
    pnpm) printf 'pnpm install --frozen-lockfile\n' ;;
    uv) printf 'uv sync --locked\n' ;;
  esac
}

dependency_generated_paths_for_ecosystem() {
  case "$1" in
    pnpm) printf 'node_modules\n' ;;
    uv) printf '.venv\n' ;;
  esac
}

print_payload_and_dependency_suggestion() {
  local payload ecosystem strategy offline online generated_paths
  payload="$(detect_default_payload)"
  ecosystem="$(detect_dependency_ecosystem)"
  strategy="$(dependency_strategy_for_ecosystem "$ecosystem")"
  offline="$(dependency_bootstrap_offline_for_ecosystem "$ecosystem")"
  online="$(dependency_bootstrap_online_for_ecosystem "$ecosystem")"
  generated_paths="$(dependency_generated_paths_for_ecosystem "$ecosystem")"

  printf 'payload: %s\n' "${payload:-<empty>}"
  printf 'dependency-ecosystem: %s\n' "$ecosystem"
  printf 'dependency-strategy: %s\n' "$strategy"
  if [[ "$strategy" == "bootstrap" ]]; then
    printf 'dependency-bootstrap-offline: %s\n' "$offline"
    printf 'dependency-bootstrap-online: %s\n' "$online"
    printf 'dependency-generated-paths: %s\n' "$generated_paths"
    printf 'dependency-timeout-seconds: %s\n' "$DEFAULT_DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS"
  fi
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

PAYLOAD="$(detect_default_payload)"
MODE="$DEFAULT_MODE"
DEPENDENCY_STRATEGY="$DEFAULT_DEPENDENCY_STRATEGY"
DEPENDENCY_PAYLOAD=""
DEPENDENCY_BOOTSTRAP_OFFLINE=""
DEPENDENCY_BOOTSTRAP_ONLINE=""
DEPENDENCY_GENERATED_PATHS=""
DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="$DEFAULT_DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS"

load_config() {
  PAYLOAD="$(detect_default_payload)"
  MODE="$DEFAULT_MODE"
  DEPENDENCY_STRATEGY="$DEFAULT_DEPENDENCY_STRATEGY"
  DEPENDENCY_PAYLOAD=""
  DEPENDENCY_BOOTSTRAP_OFFLINE=""
  DEPENDENCY_BOOTSTRAP_ONLINE=""
  DEPENDENCY_GENERATED_PATHS=""
  DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="$DEFAULT_DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS"

  if [[ -f "$config_file" ]]; then
    parse_config_file "$config_file"
  fi

  PAYLOAD="$(normalize_payload "${PAYLOAD:-}")"
  MODE="${MODE:-$DEFAULT_MODE}"
  validate_mode "$MODE"
  DEPENDENCY_STRATEGY="${DEPENDENCY_STRATEGY:-$DEFAULT_DEPENDENCY_STRATEGY}"
  validate_dependency_strategy "$DEPENDENCY_STRATEGY"
  DEPENDENCY_PAYLOAD="$(normalize_payload "${DEPENDENCY_PAYLOAD:-}")"
  DEPENDENCY_GENERATED_PATHS="$(normalize_payload "${DEPENDENCY_GENERATED_PATHS:-}")"
  DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="${DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS:-$DEFAULT_DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS}"
  validate_timeout_seconds "$DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS"

  if [[ -n "$payload_arg" ]]; then
    PAYLOAD="$(normalize_payload "$payload_arg")"
  fi

  if [[ -n "$mode_arg" ]]; then
    validate_mode "$mode_arg"
    MODE="$mode_arg"
  fi

  if [[ -n "$dependency_strategy_arg" ]]; then
    validate_dependency_strategy "$dependency_strategy_arg"
    DEPENDENCY_STRATEGY="$dependency_strategy_arg"
  fi

  if [[ -n "$dependency_payload_arg" ]]; then
    DEPENDENCY_PAYLOAD="$(normalize_payload "$dependency_payload_arg")"
  fi

  if [[ -n "$dependency_bootstrap_offline_arg" ]]; then
    validate_config_value "$dependency_bootstrap_offline_arg"
    DEPENDENCY_BOOTSTRAP_OFFLINE="$dependency_bootstrap_offline_arg"
  fi

  if [[ -n "$dependency_bootstrap_online_arg" ]]; then
    validate_config_value "$dependency_bootstrap_online_arg"
    DEPENDENCY_BOOTSTRAP_ONLINE="$dependency_bootstrap_online_arg"
  fi

  if [[ -n "$dependency_timeout_arg" ]]; then
    validate_timeout_seconds "$dependency_timeout_arg"
    DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="$dependency_timeout_arg"
  fi

  resolve_dependency_config
}

resolve_dependency_config() {
  local ecosystem
  case "$DEPENDENCY_STRATEGY" in
    none)
      DEPENDENCY_PAYLOAD=""
      DEPENDENCY_BOOTSTRAP_OFFLINE=""
      DEPENDENCY_BOOTSTRAP_ONLINE=""
      DEPENDENCY_GENERATED_PATHS=""
      ;;
    link)
      DEPENDENCY_BOOTSTRAP_OFFLINE=""
      DEPENDENCY_BOOTSTRAP_ONLINE=""
      DEPENDENCY_GENERATED_PATHS=""
      if [[ -z "$DEPENDENCY_PAYLOAD" ]]; then
        die "dependency link strategy requires --dependency-payload <paths>"
      fi
      ;;
    bootstrap)
      DEPENDENCY_PAYLOAD=""
      ecosystem="$(detect_dependency_ecosystem)"
      if [[ -z "$DEPENDENCY_BOOTSTRAP_OFFLINE" ]]; then
        DEPENDENCY_BOOTSTRAP_OFFLINE="$(dependency_bootstrap_offline_for_ecosystem "$ecosystem")"
      fi
      if [[ -z "$DEPENDENCY_BOOTSTRAP_ONLINE" ]]; then
        DEPENDENCY_BOOTSTRAP_ONLINE="$(dependency_bootstrap_online_for_ecosystem "$ecosystem")"
      fi
      if [[ -z "$DEPENDENCY_GENERATED_PATHS" ]]; then
        DEPENDENCY_GENERATED_PATHS="$(dependency_generated_paths_for_ecosystem "$ecosystem")"
      fi
      if [[ -z "$DEPENDENCY_BOOTSTRAP_OFFLINE" && -z "$DEPENDENCY_BOOTSTRAP_ONLINE" ]]; then
        die "dependency bootstrap strategy requires generated or explicit bootstrap commands"
      fi
      validate_config_value "$DEPENDENCY_BOOTSTRAP_OFFLINE"
      validate_config_value "$DEPENDENCY_BOOTSTRAP_ONLINE"
      ;;
  esac
}

parse_config_value() {
  local raw="$1"
  local value="${raw#*=}"
  if [[ "$value" == \"* ]]; then
    [[ "$value" == *\" ]] || die "invalid quoted config value: $raw"
    value="${value:1:${#value}-2}"
  fi
  printf '%s\n' "$value"
}

parse_config_file() {
  local file="$1"
  local line value
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      PAYLOAD=*)
        value="$(parse_config_value "$line")"
        PAYLOAD="$value"
        ;;
      MODE=*)
        value="$(parse_config_value "$line")"
        MODE="$value"
        ;;
      DEPENDENCY_STRATEGY=*)
        value="$(parse_config_value "$line")"
        DEPENDENCY_STRATEGY="$value"
        ;;
      DEPENDENCY_PAYLOAD=*)
        value="$(parse_config_value "$line")"
        DEPENDENCY_PAYLOAD="$value"
        ;;
      DEPENDENCY_BOOTSTRAP_OFFLINE=*)
        value="$(parse_config_value "$line")"
        DEPENDENCY_BOOTSTRAP_OFFLINE="$value"
        ;;
      DEPENDENCY_BOOTSTRAP_ONLINE=*)
        value="$(parse_config_value "$line")"
        DEPENDENCY_BOOTSTRAP_ONLINE="$value"
        ;;
      DEPENDENCY_GENERATED_PATHS=*)
        value="$(parse_config_value "$line")"
        DEPENDENCY_GENERATED_PATHS="$value"
        ;;
      DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS=*)
        value="$(parse_config_value "$line")"
        DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="$value"
        ;;
    esac
  done < "$file"
}

report_dependency_plan() {
  case "$DEPENDENCY_STRATEGY" in
    bootstrap)
      log "dependency strategy: bootstrap"
      [[ -z "$DEPENDENCY_BOOTSTRAP_OFFLINE" ]] || log "dependency bootstrap offline: $DEPENDENCY_BOOTSTRAP_OFFLINE"
      [[ -z "$DEPENDENCY_BOOTSTRAP_ONLINE" ]] || log "dependency bootstrap online: $DEPENDENCY_BOOTSTRAP_ONLINE"
      log "dependency bootstrap timeout: ${DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS}s"
      ;;
    link)
      log "dependency strategy: link"
      log "dependency payload: $DEPENDENCY_PAYLOAD"
      ;;
    none)
      log "dependency strategy: none"
      ;;
  esac
}

write_config() {
  local config_rel
  config_rel="$(repo_relative_config_path "$config_file")" ||
    die "--config must resolve inside the source checkout so the managed hook can read it"
  validate_payload_path "$config_rel"
  mkdir -p "$(dirname "$config_file")"
  cat > "$config_file" <<EOF
# Repo-local config for the agent-worktree post-checkout hook.
# Keep this file local unless this repo intentionally commits a sanitized default.

# Space-separated repo-root-relative local worktree payload paths.
PAYLOAD="$PAYLOAD"

# MODE can be link or copy. Prefer link for shared mutable Agent context.
MODE="$MODE"

# Dependency handling is separate from ordinary Agent context payload.
DEPENDENCY_STRATEGY="$DEPENDENCY_STRATEGY"
EOF
  case "$DEPENDENCY_STRATEGY" in
    bootstrap)
      {
        printf 'DEPENDENCY_BOOTSTRAP_OFFLINE="%s"\n' "$DEPENDENCY_BOOTSTRAP_OFFLINE"
        printf 'DEPENDENCY_BOOTSTRAP_ONLINE="%s"\n' "$DEPENDENCY_BOOTSTRAP_ONLINE"
        printf 'DEPENDENCY_GENERATED_PATHS="%s"\n' "$DEPENDENCY_GENERATED_PATHS"
        printf 'DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="%s"\n' "$DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS"
      } >> "$config_file"
      ;;
    link)
      printf 'DEPENDENCY_PAYLOAD="%s"\n' "$DEPENDENCY_PAYLOAD" >> "$config_file"
      ;;
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

  exclude_file="$(git -C "$checkout" rev-parse --path-format=absolute --git-path info/exclude)"
  mkdir -p "$(dirname "$exclude_file")"
  touch "$exclude_file"

  if ! grep -Fxq "$EXCLUDE_MARKER" "$exclude_file"; then
    printf '\n%s\n' "$EXCLUDE_MARKER" >> "$exclude_file"
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

dependency_payload_patterns() {
  local rel src
  if [[ "$DEPENDENCY_STRATEGY" == "link" ]]; then
    for rel in $DEPENDENCY_PAYLOAD; do
      printf '/%s\n' "$rel"
      src="$source_root/$rel"
      if [[ -d "$src" ]]; then
        printf '/%s/\n' "$rel"
      fi
    done
  elif [[ "$DEPENDENCY_STRATEGY" == "bootstrap" ]]; then
    for rel in $DEPENDENCY_GENERATED_PATHS; do
      printf '/%s\n' "$rel"
      printf '/%s/\n' "$rel"
    done
  fi
}

source_ignore_patterns() {
  local rel_config
  if rel_config="$(repo_relative_config_path "$config_file")"; then
    printf '/%s\n' "$rel_config"
  fi
  payload_patterns
  dependency_payload_patterns
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
  while IFS= read -r pattern; do
    patterns+=("$pattern")
  done < <(dependency_payload_patterns)
  add_exclude_patterns "$target_root" "${patterns[@]}"
}

same_link_target() {
  local dst="$1" src="$2"
  [[ -L "$dst" && "$(readlink "$dst")" == "$src" ]]
}

install_payload_item() {
  local target_root="$1"
  local rel="$2"
  local src="$source_root/$rel"
  local dst="$target_root/$rel"

  if [[ ! -e "$src" && ! -L "$src" ]]; then
    log "skip missing source: $rel"
    return
  fi

  mkdir -p "$(dirname "$dst")" || {
    log "skip payload with unwritable parent: $rel"
    return
  }

  if same_link_target "$dst" "$src"; then
    return
  fi

  if [[ -e "$dst" || -L "$dst" ]]; then
    return
  fi

  if [[ "$MODE" == "copy" ]]; then
    cp -R "$src" "$dst" || log "copy failed: $rel"
  else
    ln -s "$src" "$dst" || log "link failed: $rel"
  fi
}

install_dependency_link_item() {
  local target_root="$1"
  local rel="$2"
  local src="$source_root/$rel"
  local dst="$target_root/$rel"

  if [[ ! -e "$src" && ! -L "$src" ]]; then
    log "skip missing dependency payload: $rel"
    return
  fi

  mkdir -p "$(dirname "$dst")" || {
    log "skip dependency payload with unwritable parent: $rel"
    return
  }

  if same_link_target "$dst" "$src"; then
    return
  fi

  if [[ -e "$dst" || -L "$dst" ]]; then
    return
  fi

  ln -s "$src" "$dst" || log "link failed for dependency payload: $rel"
}

reconcile_worktree_payload() {
  local target_root="$1"
  local rel
  [[ "$target_root" != "$source_root" ]] || return
  ensure_target_exclude "$target_root"
  for rel in $PAYLOAD; do
    install_payload_item "$target_root" "$rel"
  done
  if [[ "$DEPENDENCY_STRATEGY" == "link" ]]; then
    for rel in $DEPENDENCY_PAYLOAD; do
      install_dependency_link_item "$target_root" "$rel"
    done
  fi
}

reconcile_registered_worktrees() {
  local line target_root resolved_target resolved_source
  resolved_source="$(cd "$source_root" && pwd -P)"
  while IFS= read -r line; do
    case "$line" in
      worktree\ *)
        target_root="${line#worktree }"
        [[ -d "$target_root" ]] || continue
        resolved_target="$(cd "$target_root" && pwd -P)"
        [[ "$resolved_target" != "$resolved_source" ]] || continue
        reconcile_worktree_payload "$resolved_target"
        ;;
    esac
  done < <(git -C "$source_root" worktree list --porcelain)
}

render_hook_block() {
  local config_rel
  config_rel="$(repo_relative_config_path "$config_file")" ||
    die "--config must resolve inside the source checkout so the managed hook can read it"
  validate_payload_path "$config_rel"
  cat <<'HOOK'
# --- agent-worktree managed block begin ---
# Self-contained Agent worktree payload reconciliation. Managed by $agent-worktree.
agent_worktree_hook_main() {
  [ "${3:-}" = "1" ] || return 0

  common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" ||
    common_dir="$(git rev-parse --git-common-dir 2>/dev/null)" ||
    return 0
  case "$common_dir" in
    /*) ;;
    *) common_dir="$(pwd -P)/$common_dir" ;;
  esac

  source_root="${common_dir%/.git}"
  target_root="$(git rev-parse --show-toplevel 2>/dev/null)" || return 0
  [ "$source_root" != "$target_root" ] || return 0

HOOK
  printf '  config="$source_root/%s"\n' "$config_rel"
  cat <<'HOOK'
  [ -f "$config" ] || return 0

  PAYLOAD=""
  MODE="link"
  DEPENDENCY_STRATEGY="none"
  DEPENDENCY_PAYLOAD=""
  DEPENDENCY_BOOTSTRAP_OFFLINE=""
  DEPENDENCY_BOOTSTRAP_ONLINE=""
  DEPENDENCY_GENERATED_PATHS=""
  DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="120"
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      PAYLOAD=*)
        value="${line#PAYLOAD=}"
        value="${value#\"}"
        value="${value%\"}"
        PAYLOAD="$value"
        ;;
      MODE=*)
        value="${line#MODE=}"
        value="${value#\"}"
        value="${value%\"}"
        MODE="$value"
        ;;
      DEPENDENCY_STRATEGY=*)
        value="${line#DEPENDENCY_STRATEGY=}"
        value="${value#\"}"
        value="${value%\"}"
        DEPENDENCY_STRATEGY="$value"
        ;;
      DEPENDENCY_PAYLOAD=*)
        value="${line#DEPENDENCY_PAYLOAD=}"
        value="${value#\"}"
        value="${value%\"}"
        DEPENDENCY_PAYLOAD="$value"
        ;;
      DEPENDENCY_BOOTSTRAP_OFFLINE=*)
        value="${line#DEPENDENCY_BOOTSTRAP_OFFLINE=}"
        value="${value#\"}"
        value="${value%\"}"
        DEPENDENCY_BOOTSTRAP_OFFLINE="$value"
        ;;
      DEPENDENCY_BOOTSTRAP_ONLINE=*)
        value="${line#DEPENDENCY_BOOTSTRAP_ONLINE=}"
        value="${value#\"}"
        value="${value%\"}"
        DEPENDENCY_BOOTSTRAP_ONLINE="$value"
        ;;
      DEPENDENCY_GENERATED_PATHS=*)
        value="${line#DEPENDENCY_GENERATED_PATHS=}"
        value="${value#\"}"
        value="${value%\"}"
        DEPENDENCY_GENERATED_PATHS="$value"
        ;;
      DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS=*)
        value="${line#DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS=}"
        value="${value#\"}"
        value="${value%\"}"
        DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS="$value"
        ;;
    esac
  done < "$config"

  case "${MODE:-link}" in
    link|copy) ;;
    *) MODE="link" ;;
  esac

  exclude_file="$(git rev-parse --path-format=absolute --git-path info/exclude 2>/dev/null)" || return 0
  log_file="$(git rev-parse --path-format=absolute --git-path agent-worktree-hook.log 2>/dev/null || true)"
  mkdir -p "$(dirname "$exclude_file")" || return 0
  touch "$exclude_file" || return 0
  had_error=0

  agent_worktree_log_error() {
    had_error=1
    [ -n "$log_file" ] || return 0
    printf '%s %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$*" >> "$log_file" 2>/dev/null || true
  }

  agent_worktree_log_notice() {
    [ -n "$log_file" ] || return 0
    printf '%s %s\n' "$(date +%Y-%m-%dT%H:%M:%S%z)" "$*" >> "$log_file" 2>/dev/null || true
  }

  agent_worktree_add_exclude() {
    pattern="$1"
    if ! grep -qxF "$pattern" "$exclude_file" 2>/dev/null; then
      printf '%s\n' "$pattern" >> "$exclude_file" ||
        agent_worktree_log_error "exclude write failed: $pattern"
    fi
  }

  agent_worktree_valid_rel_path() {
    rel="$1"
    case "$rel" in
      ""|/*|../*|*/../*|*[!A-Za-z0-9._/-]*)
        return 1
        ;;
      *)
        return 0
        ;;
    esac
  }

  agent_worktree_exclude_path() {
    rel="$1"
    agent_worktree_add_exclude "/$rel"
    if [ -d "$source_root/$rel" ]; then
      agent_worktree_add_exclude "/$rel/"
    fi
  }

  for rel in ${PAYLOAD:-}; do
    if ! agent_worktree_valid_rel_path "$rel"; then
      agent_worktree_log_error "invalid payload path: $rel"
      continue
    fi

    src="$source_root/$rel"
    dst="$target_root/$rel"
    agent_worktree_exclude_path "$rel"

    if [ ! -e "$src" ] && [ ! -L "$src" ]; then
      agent_worktree_log_error "missing source payload: $rel"
      continue
    fi

    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
      continue
    fi

    if [ -e "$dst" ] || [ -L "$dst" ]; then
      continue
    fi

    mkdir -p "$(dirname "$dst")" || {
      agent_worktree_log_error "mkdir failed for payload: $rel"
      continue
    }

    if [ "${MODE:-link}" = "copy" ]; then
      cp -R "$src" "$dst" || agent_worktree_log_error "copy failed for payload: $rel"
    else
      ln -s "$src" "$dst" || agent_worktree_log_error "link failed for payload: $rel"
    fi
  done

  for rel in ${DEPENDENCY_GENERATED_PATHS:-}; do
    if agent_worktree_valid_rel_path "$rel"; then
      agent_worktree_add_exclude "/$rel"
      agent_worktree_add_exclude "/$rel/"
    else
      agent_worktree_log_error "invalid dependency generated path: $rel"
    fi
  done

  if [ "${DEPENDENCY_STRATEGY:-none}" = "link" ]; then
    for rel in ${DEPENDENCY_PAYLOAD:-}; do
      if ! agent_worktree_valid_rel_path "$rel"; then
        agent_worktree_log_error "invalid dependency payload path: $rel"
        continue
      fi
      src="$source_root/$rel"
      dst="$target_root/$rel"
      agent_worktree_exclude_path "$rel"
      if [ ! -e "$src" ] && [ ! -L "$src" ]; then
        agent_worktree_log_error "missing source dependency payload: $rel"
        continue
      fi
      if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
        continue
      fi
      if [ -e "$dst" ] || [ -L "$dst" ]; then
        continue
      fi
      mkdir -p "$(dirname "$dst")" || {
        agent_worktree_log_error "mkdir failed for dependency payload: $rel"
        continue
      }
      ln -s "$src" "$dst" || agent_worktree_log_error "link failed for dependency payload: $rel"
    done
  fi

  agent_worktree_classify_status() {
    status="$1"
    case "$status" in
      124) printf 'timeout\n' ;;
      127) printf 'command-not-found\n' ;;
      *) printf 'non-zero-exit\n' ;;
    esac
  }

  agent_worktree_run_with_timeout() {
    cmd="$1"
    agent_worktree_last_output_file="$(mktemp "${TMPDIR:-/tmp}/agent-worktree-bootstrap.XXXXXX" 2>/dev/null || printf '%s\n' "${TMPDIR:-/tmp}/agent-worktree-bootstrap.$$")"
    (
      cd "$target_root" || exit 125
      sh -c "$cmd"
    ) > "$agent_worktree_last_output_file" 2>&1 &
    agent_worktree_pid="$!"
    agent_worktree_started_at="$(date +%s)"
    while kill -0 "$agent_worktree_pid" 2>/dev/null; do
      agent_worktree_now="$(date +%s)"
      agent_worktree_elapsed=$((agent_worktree_now - agent_worktree_started_at))
      if [ "$agent_worktree_elapsed" -ge "$DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS" ]; then
        kill "$agent_worktree_pid" 2>/dev/null || true
        sleep 1
        kill -9 "$agent_worktree_pid" 2>/dev/null || true
        wait "$agent_worktree_pid" 2>/dev/null || true
        return 124
      fi
      sleep 0.1 2>/dev/null || sleep 0
    done
    wait "$agent_worktree_pid"
    agent_worktree_status="$?"
    return "$agent_worktree_status"
  }

  agent_worktree_output_is_offline_miss() {
    output_file="$1"
    grep -Eiq 'ERR_PNPM_NO_OFFLINE_TARBALL|No package.*cache|not found in.*cache|offline.*cache|cache.*miss|offline.*miss' "$output_file" 2>/dev/null
  }

  agent_worktree_log_command_output() {
    output_file="$1"
    [ -n "$log_file" ] || return 0
    [ -f "$output_file" ] || return 0
    sed 's/^/dependency bootstrap output: /' "$output_file" >> "$log_file" 2>/dev/null || true
  }

  agent_worktree_log_bootstrap_failure() {
    phase="$1"
    status="$2"
    cmd="$3"
    class="$(agent_worktree_classify_status "$status")"
    agent_worktree_log_error "dependency bootstrap $phase failed: class=$class status=$status command=$cmd"
    agent_worktree_log_command_output "$agent_worktree_last_output_file"
    rm -f "$agent_worktree_last_output_file" 2>/dev/null || true
  }

  agent_worktree_run_dependency_bootstrap() {
    case "${DEPENDENCY_STRATEGY:-none}" in
      none|link)
        return 0
        ;;
      bootstrap)
        ;;
      *)
        agent_worktree_log_error "invalid dependency config: class=invalid-config strategy=${DEPENDENCY_STRATEGY:-}"
        return 0
        ;;
    esac

    case "${DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS:-}" in
      ""|*[!0-9]*|0)
        agent_worktree_log_error "invalid dependency config: class=invalid-config timeout=${DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS:-}"
        return 0
        ;;
    esac

    if [ -z "${DEPENDENCY_BOOTSTRAP_OFFLINE:-}" ] && [ -z "${DEPENDENCY_BOOTSTRAP_ONLINE:-}" ]; then
      agent_worktree_log_error "invalid dependency config: class=invalid-config missing bootstrap command"
      return 0
    fi

    if [ -n "${DEPENDENCY_BOOTSTRAP_OFFLINE:-}" ]; then
      agent_worktree_run_with_timeout "$DEPENDENCY_BOOTSTRAP_OFFLINE"
      status="$?"
      if [ "$status" -eq 0 ]; then
        rm -f "$agent_worktree_last_output_file" 2>/dev/null || true
        return 0
      fi

      if [ "$status" -ne 127 ] && [ "$status" -ne 124 ] && agent_worktree_output_is_offline_miss "$agent_worktree_last_output_file" && [ -n "${DEPENDENCY_BOOTSTRAP_ONLINE:-}" ]; then
        agent_worktree_log_notice "dependency bootstrap offline-cache-miss retry: status=$status command=$DEPENDENCY_BOOTSTRAP_OFFLINE"
        agent_worktree_log_command_output "$agent_worktree_last_output_file"
        rm -f "$agent_worktree_last_output_file" 2>/dev/null || true
      else
        agent_worktree_log_bootstrap_failure "offline" "$status" "$DEPENDENCY_BOOTSTRAP_OFFLINE"
        return 0
      fi
    fi

    if [ -n "${DEPENDENCY_BOOTSTRAP_ONLINE:-}" ]; then
      agent_worktree_run_with_timeout "$DEPENDENCY_BOOTSTRAP_ONLINE"
      status="$?"
      if [ "$status" -eq 0 ]; then
        rm -f "$agent_worktree_last_output_file" 2>/dev/null || true
        return 0
      fi
      agent_worktree_log_bootstrap_failure "online" "$status" "$DEPENDENCY_BOOTSTRAP_ONLINE"
    fi
  }

  agent_worktree_run_dependency_bootstrap

  if [ "$had_error" -ne 0 ] && [ -n "$log_file" ]; then
    printf 'agent-worktree hook: setup incomplete; see %s\n' "$log_file" >&2
  fi
}

agent_worktree_hook_main "$@"
# --- agent-worktree managed block end ---
HOOK
}

hook_path() {
  git -C "$source_root" rev-parse --path-format=absolute --git-path hooks/post-checkout
}

count_anchor() {
  local anchor="$1"
  local file="$2"
  grep -Fxc "$anchor" "$file" 2>/dev/null || true
}

assert_single_managed_block_shape() {
  local file="$1"
  local begin_count end_count
  [[ -f "$file" ]] || return
  begin_count="$(count_anchor "$HOOK_BEGIN" "$file")"
  end_count="$(count_anchor "$HOOK_END" "$file")"
  if [[ "$begin_count" != "$end_count" || "$begin_count" -gt 1 ]]; then
    die "expected zero or one agent-worktree managed block in $file"
  fi
}

install_hook() {
  local hook_file block_file stripped_file tmp_file
  hook_file="$(hook_path)"
  mkdir -p "$(dirname "$hook_file")"

  if [[ ! -f "$hook_file" ]]; then
    printf '#!/bin/sh\n\n' > "$hook_file"
  fi

  assert_single_managed_block_shape "$hook_file"
  block_file="$(mktemp)"
  stripped_file="$(mktemp)"
  tmp_file="$(mktemp)"
  render_hook_block > "$block_file"

  awk -v begin="$HOOK_BEGIN" -v end="$HOOK_END" '
    $0 == begin { in_block = 1; next }
    in_block && $0 == end { in_block = 0; next }
    !in_block { print }
  ' "$hook_file" > "$stripped_file"

  awk -v block="$block_file" '
    function print_block() {
      while ((getline line < block) > 0) print line
      close(block)
    }
    NR == 1 && /^#!/ {
      print
      print ""
      print_block()
      inserted = 1
      next
    }
    NR == 1 && !/^#!/ {
      print "#!/bin/sh"
      print ""
      print_block()
      print ""
      inserted = 1
    }
    { print }
    END {
      if (NR == 0) {
        print "#!/bin/sh"
        print ""
        print_block()
      }
    }
  ' "$stripped_file" > "$tmp_file"

  if ! sh -n "$tmp_file"; then
    rm -f "$block_file" "$stripped_file" "$tmp_file"
    die "generated hook failed sh -n"
  fi

  mv "$tmp_file" "$hook_file"
  rm -f "$block_file" "$stripped_file"
  chmod +x "$hook_file"
}

remove_hook_block() {
  local hook_file tmp_file begin_count
  hook_file="$(hook_path)"
  [[ -f "$hook_file" ]] || return
  assert_single_managed_block_shape "$hook_file"
  begin_count="$(count_anchor "$HOOK_BEGIN" "$hook_file")"
  [[ "$begin_count" -eq 1 ]] || return

  tmp_file="$(mktemp)"
  awk -v begin="$HOOK_BEGIN" -v end="$HOOK_END" '
    $0 == begin { in_block = 1; next }
    in_block && $0 == end { in_block = 0; next }
    !in_block { print }
  ' "$hook_file" > "$tmp_file"

  if ! sh -n "$tmp_file"; then
    rm -f "$tmp_file"
    die "hook would be invalid after removing managed block"
  fi

  mv "$tmp_file" "$hook_file"
  chmod +x "$hook_file"
}

append_payload() {
  local rel
  local items=()
  for rel in $PAYLOAD; do
    validate_payload_path "$rel"
    items+=("$rel")
  done
  for rel in "$@"; do
    validate_payload_path "$rel"
    if [[ ${#items[@]} -eq 0 ]] || ! payload_contains "$rel" "${items[@]}"; then
      items+=("$rel")
    fi
  done
  local IFS=" "
  PAYLOAD="${items[*]-}"
}

subtract_payload() {
  local rel remove
  local items=()
  for rel in $PAYLOAD; do
    remove="false"
    for candidate in "$@"; do
      validate_payload_path "$candidate"
      if [[ "$rel" == "$candidate" ]]; then
        remove="true"
      fi
    done
    [[ "$remove" == "true" ]] || items+=("$rel")
  done
  local IFS=" "
  PAYLOAD="${items[*]-}"
}

report_status() {
  local hook_file status
  hook_file="$(hook_path)"
  if [[ -f "$hook_file" ]] && grep -Fxq "$HOOK_BEGIN" "$hook_file"; then
    status="installed"
  else
    status="disabled"
  fi

  log "payload: ${PAYLOAD:-<empty>}"
  log "mode: $MODE"
  case "$DEPENDENCY_STRATEGY" in
    bootstrap)
      log "dependency strategy: bootstrap"
      [[ -z "$DEPENDENCY_BOOTSTRAP_OFFLINE" ]] || log "dependency bootstrap offline: $DEPENDENCY_BOOTSTRAP_OFFLINE"
      [[ -z "$DEPENDENCY_BOOTSTRAP_ONLINE" ]] || log "dependency bootstrap online: $DEPENDENCY_BOOTSTRAP_ONLINE"
      [[ -z "$DEPENDENCY_GENERATED_PATHS" ]] || log "dependency generated paths: $DEPENDENCY_GENERATED_PATHS"
      log "dependency bootstrap timeout: ${DEPENDENCY_BOOTSTRAP_TIMEOUT_SECONDS}s"
      ;;
    link)
      log "dependency strategy: link"
      log "dependency payload: $DEPENDENCY_PAYLOAD"
      ;;
    none)
      log "dependency strategy: none"
      ;;
  esac
  log "hook: $status ($hook_file)"
  if [[ "$MODE" == "copy" ]]; then
    log "warning: MODE=copy creates worktree-local payload copies; copied payload edits are lost when the worktree is removed"
  fi
}

case "$command" in
  suggest-payload)
    [[ ${#positionals[@]} -eq 0 ]] || die "suggest-payload does not accept positional arguments"
    [[ -z "$payload_arg" ]] || die "--payload is not valid with suggest-payload"
    [[ -z "$mode_arg" ]] || die "--mode/--copy/--link is not valid with suggest-payload"
    [[ -z "$dependency_strategy_arg" ]] || die "--dependency-strategy is not valid with suggest-payload"
    [[ -z "$dependency_payload_arg" ]] || die "--dependency-payload is not valid with suggest-payload"
    [[ -z "$dependency_bootstrap_offline_arg" ]] || die "--dependency-bootstrap-offline is not valid with suggest-payload"
    [[ -z "$dependency_bootstrap_online_arg" ]] || die "--dependency-bootstrap-online is not valid with suggest-payload"
    [[ -z "$dependency_timeout_arg" ]] || die "--dependency-timeout is not valid with suggest-payload"
    print_payload_and_dependency_suggestion
    ;;
  init)
    [[ ${#positionals[@]} -eq 0 ]] || die "init does not accept positional arguments"
    load_config
    report_dependency_plan
    write_config
    ensure_source_exclude
    install_hook
    reconcile_registered_worktrees
    report_status
    ;;
  add-payload)
    [[ ${#positionals[@]} -gt 0 ]] || die "add-payload requires at least one path"
    [[ -z "$payload_arg" ]] || die "--payload is not valid with add-payload"
    load_config
    append_payload "${positionals[@]}"
    report_dependency_plan
    write_config
    ensure_source_exclude
    install_hook
    reconcile_registered_worktrees
    report_status
    ;;
  remove-payload)
    [[ ${#positionals[@]} -gt 0 ]] || die "remove-payload requires at least one path"
    [[ -z "$payload_arg" ]] || die "--payload is not valid with remove-payload"
    load_config
    subtract_payload "${positionals[@]}"
    report_dependency_plan
    write_config
    ensure_source_exclude
    install_hook
    reconcile_registered_worktrees
    report_status
    ;;
  regenerate-payload)
    [[ ${#positionals[@]} -eq 0 ]] || die "regenerate-payload does not accept positional arguments"
    [[ -z "$payload_arg" ]] || die "--payload is not valid with regenerate-payload"
    load_config
    PAYLOAD="$(detect_default_payload)"
    report_dependency_plan
    write_config
    ensure_source_exclude
    install_hook
    reconcile_registered_worktrees
    report_status
    ;;
  set-mode)
    [[ ${#positionals[@]} -le 1 ]] || die "set-mode accepts at most one mode"
    load_config
    if [[ ${#positionals[@]} -eq 1 ]]; then
      validate_mode "${positionals[0]}"
      MODE="${positionals[0]}"
    fi
    report_dependency_plan
    write_config
    ensure_source_exclude
    install_hook
    reconcile_registered_worktrees
    report_status
    ;;
  set-dependency-strategy)
    [[ ${#positionals[@]} -le 1 ]] || die "set-dependency-strategy accepts at most one strategy"
    if [[ ${#positionals[@]} -eq 1 ]]; then
      [[ -z "$dependency_strategy_arg" ]] || die "provide dependency strategy once"
      validate_dependency_strategy "${positionals[0]}"
      dependency_strategy_arg="${positionals[0]}"
    fi
    load_config
    report_dependency_plan
    write_config
    ensure_source_exclude
    install_hook
    reconcile_registered_worktrees
    report_status
    ;;
  reinstall-hook)
    [[ ${#positionals[@]} -eq 0 ]] || die "reinstall-hook does not accept positional arguments"
    load_config
    report_dependency_plan
    ensure_source_exclude
    install_hook
    reconcile_registered_worktrees
    report_status
    ;;
  disable|uninstall)
    [[ ${#positionals[@]} -eq 0 ]] || die "$command does not accept positional arguments"
    [[ -z "$payload_arg" ]] || die "--payload is not valid with $command"
    [[ -z "$mode_arg" ]] || die "--mode/--copy/--link is not valid with $command"
    [[ -z "$dependency_strategy_arg" ]] || die "--dependency-strategy is not valid with $command"
    [[ -z "$dependency_payload_arg" ]] || die "--dependency-payload is not valid with $command"
    [[ -z "$dependency_bootstrap_offline_arg" ]] || die "--dependency-bootstrap-offline is not valid with $command"
    [[ -z "$dependency_bootstrap_online_arg" ]] || die "--dependency-bootstrap-online is not valid with $command"
    [[ -z "$dependency_timeout_arg" ]] || die "--dependency-timeout is not valid with $command"
    remove_hook_block
    log "hook: disabled ($(hook_path))"
    if [[ -f "$config_file" ]]; then
      log "config: preserved $config_file"
    fi
    ;;
esac
