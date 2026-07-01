#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SKILL_DIR="$ROOT/skills/personal/agent-worktree"
SCRIPT="$SKILL_DIR/scripts/bootstrap-agent-worktree.sh"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/agent-worktree-test.XXXXXX")"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

log() {
  printf '[test] %s\n' "$*"
}

fail() {
  printf '[test] %s\n' "$*" >&2
  exit 1
}

contains_word() {
  local haystack="$1"
  local needle="$2"
  case " $haystack " in
    *" $needle "*) return 0 ;;
    *) return 1 ;;
  esac
}

assert_exists() {
  [[ -e "$1" || -L "$1" ]] || fail "expected path to exist: $1"
}

assert_not_exists() {
  [[ ! -e "$1" && ! -L "$1" ]] || fail "expected path to be absent: $1"
}

assert_file_contains() {
  local file="$1"
  local expected="$2"
  grep -Fq "$expected" "$file" || fail "expected $file to contain: $expected"
}

assert_file_not_contains() {
  local file="$1"
  local unexpected="$2"
  ! grep -Fq "$unexpected" "$file" || fail "expected $file not to contain: $unexpected"
}

assert_count() {
  local file="$1"
  local expected="$2"
  local count="$3"
  local actual
  actual="$(grep -Fxc "$expected" "$file" || true)"
  [[ "$actual" == "$count" ]] || fail "expected $expected count $count in $file, got $actual"
}

git_commit_all() {
  git -c user.name='Agent Worktree Tests' \
    -c user.email='agent-worktree-tests@example.invalid' \
    commit -m "$1" >/dev/null
}

create_repo() {
  local repo="$1"
  mkdir -p "$repo"
  git -C "$repo" init -q
  git -C "$repo" config user.name 'Agent Worktree Tests'
  git -C "$repo" config user.email 'agent-worktree-tests@example.invalid'
  printf 'tracked\n' > "$repo/README.md"
  git -C "$repo" add README.md
  (cd "$repo" && git_commit_all 'init fixture')
}

run_script_from() {
  local repo="$1"
  shift
  (cd "$repo" && bash "$SCRIPT" "$@")
}

run_script_expect_fail() {
  local repo="$1"
  shift
  local output
  set +e
  output="$(cd "$repo" && bash "$SCRIPT" "$@" 2>&1)"
  local status=$?
  set -e
  [[ "$status" -ne 0 ]] || fail "expected command to fail: $*"
  printf '%s\n' "$output"
}

hook_file_for() {
  git -C "$1" rev-parse --path-format=absolute --git-path hooks/post-checkout
}

exclude_file_for() {
  git -C "$1" rev-parse --path-format=absolute --git-path info/exclude
}

status_must_not_list_payload() {
  local repo="$1"
  local payload="$2"
  local status
  status="$(git -C "$repo" status --short --untracked-files=all)"
  if grep -Fq "$payload" <<<"$status"; then
    printf '%s\n' "$status" >&2
    fail "git status should not list payload path: $payload"
  fi
}

test_init_hook_and_native_worktree_add() {
  log "init hook and native worktree add"
  local repo="$TMP_DIR/native-repo"
  local target="$TMP_DIR/native-worktree"
  local suggestion output hook source_exclude target_exclude

  create_repo "$repo"
  mkdir -p "$repo/.scratch/issues" "$repo/docs/local"
  printf 'Status: ready-for-agent\n' > "$repo/.scratch/issues/01.md"
  printf 'local docs\n' > "$repo/docs/local/README.md"
  printf 'TOKEN=local\n' > "$repo/.env.local"

  suggestion="$(run_script_from "$repo" suggest-payload)"
  contains_word "$suggestion" ".scratch" || fail "expected suggestion to include .scratch: $suggestion"
  contains_word "$suggestion" "docs/local" || fail "expected suggestion to include docs/local: $suggestion"
  contains_word "$suggestion" ".env.local" || fail "expected suggestion to include .env.local: $suggestion"

  output="$(run_script_from "$repo" init --payload ".scratch docs/local .env.local")"
  assert_file_contains "$repo/.agents/agent-worktree.env" 'PAYLOAD=".scratch docs/local .env.local"'
  assert_file_contains "$repo/.agents/agent-worktree.env" 'MODE="link"'
  grep -Fq 'hook: installed' <<<"$output" || fail "expected installed hook status: $output"

  hook="$(hook_file_for "$repo")"
  assert_file_contains "$hook" '# --- agent-worktree managed block begin ---'
  assert_file_contains "$hook" '# --- agent-worktree managed block end ---'
  assert_file_not_contains "$hook" "$SKILL_DIR"
  assert_count "$hook" '# --- agent-worktree managed block begin ---' 1
  sh -n "$hook"

  source_exclude="$(exclude_file_for "$repo")"
  assert_file_contains "$source_exclude" '/.agents/agent-worktree.env'
  assert_file_contains "$source_exclude" '/.scratch'
  assert_file_contains "$source_exclude" '/.scratch/'
  assert_file_contains "$source_exclude" '/docs/local'
  assert_file_contains "$source_exclude" '/.env.local'
  status_must_not_list_payload "$repo" ".scratch"
  status_must_not_list_payload "$repo" ".agents/agent-worktree.env"

  git -C "$repo" worktree add -b hook/native "$target" HEAD >/dev/null 2>&1
  assert_exists "$target/.scratch/issues/01.md"
  assert_exists "$target/docs/local/README.md"
  assert_exists "$target/.env.local"
  [[ -L "$target/.scratch" ]] || fail "expected .scratch to be a symlink"
  [[ "$(cd "$(readlink "$target/.scratch")" && pwd -P)" == "$(cd "$repo/.scratch" && pwd -P)" ]] || fail "unexpected .scratch symlink target"

  target_exclude="$(exclude_file_for "$target")"
  assert_file_contains "$target_exclude" '/.scratch'
  assert_file_contains "$target_exclude" '/.scratch/'
  assert_file_contains "$target_exclude" '/docs/local'
  assert_file_contains "$target_exclude" '/.env.local'
  status_must_not_list_payload "$target" ".scratch"

  git -C "$target" checkout -b hook/native-repair >/dev/null 2>&1
  assert_count "$target_exclude" '/.scratch' 1
  assert_count "$target_exclude" '/docs/local' 1
}

test_reconfigure_disable_and_old_command_refusal() {
  log "reconfigure disable and old command refusal"
  local repo="$TMP_DIR/reconfigure-repo"
  local target="$TMP_DIR/disabled-worktree"
  local active_target="$TMP_DIR/active-before-disable"
  local hook output failed

  create_repo "$repo"
  mkdir -p "$repo/.scratch" "$repo/docs/local"
  printf 'scratch\n' > "$repo/.scratch/task.md"
  printf 'docs\n' > "$repo/docs/local/README.md"

  hook="$(hook_file_for "$repo")"
  mkdir -p "$(dirname "$hook")"
  cat > "$hook" <<'EOF'
#!/bin/sh
printf '' >/dev/null
exit 0
EOF
  chmod +x "$hook"

  run_script_from "$repo" init --payload ".scratch" >/dev/null
  assert_file_contains "$hook" "printf '' >/dev/null"
  assert_file_contains "$hook" "exit 0"
  assert_count "$hook" '# --- agent-worktree managed block begin ---' 1
  git -C "$repo" worktree add -b hook/active-before-disable "$active_target" HEAD >/dev/null 2>&1
  assert_exists "$active_target/.scratch/task.md"

  run_script_from "$repo" add-payload docs/local docs/local >/dev/null
  assert_file_contains "$repo/.agents/agent-worktree.env" 'PAYLOAD=".scratch docs/local"'

  run_script_from "$repo" remove-payload .scratch >/dev/null
  assert_file_contains "$repo/.agents/agent-worktree.env" 'PAYLOAD="docs/local"'
  assert_file_not_contains "$repo/.agents/agent-worktree.env" 'PAYLOAD=".scratch'

  output="$(run_script_from "$repo" set-mode copy)"
  assert_file_contains "$repo/.agents/agent-worktree.env" 'MODE="copy"'
  grep -Fq 'MODE=copy creates worktree-local payload copies' <<<"$output" || fail "expected copy-mode warning"

  run_script_from "$repo" reinstall-hook >/dev/null
  assert_count "$hook" '# --- agent-worktree managed block begin ---' 1

  failed="$(run_script_expect_fail "$repo" init --payload 'bad$name')"
  grep -Fq 'invalid repo-relative payload path' <<<"$failed" || fail "expected invalid payload refusal: $failed"

  printf 'MODE="$(unterminated\n' > "$repo/.agents/agent-worktree.env"
  run_script_from "$repo" disable >/dev/null
  assert_file_contains "$hook" "printf '' >/dev/null"
  assert_file_contains "$hook" "exit 0"
  assert_file_not_contains "$hook" '# --- agent-worktree managed block begin ---'

  git -C "$repo" worktree add -b hook/disabled "$target" HEAD >/dev/null 2>&1
  assert_not_exists "$target/docs/local"

  failed="$(run_script_expect_fail "$repo" create example)"
  grep -Fq 'use native git worktree add' <<<"$failed" || fail "expected native Git refusal: $failed"
}

test_custom_config_path() {
  log "custom config path"
  local repo="$TMP_DIR/custom-config-repo"
  local target="$TMP_DIR/custom-config-worktree"
  local hook

  create_repo "$repo"
  mkdir -p "$repo/.scratch"
  printf 'custom\n' > "$repo/.scratch/task.md"

  run_script_from "$repo" init --config .agents/custom-agent-worktree.env --payload ".scratch" >/dev/null
  assert_file_contains "$repo/.agents/custom-agent-worktree.env" 'PAYLOAD=".scratch"'
  hook="$(hook_file_for "$repo")"
  assert_file_contains "$hook" '.agents/custom-agent-worktree.env'
  assert_file_not_contains "$hook" '.agents/agent-worktree.env"'

  git -C "$repo" worktree add -b hook/custom-config "$target" HEAD >/dev/null 2>&1
  assert_exists "$target/.scratch/task.md"
}

test_copy_mode() {
  log "copy mode"
  local repo="$TMP_DIR/copy-repo"
  local target="$TMP_DIR/copy-worktree"
  local output

  create_repo "$repo"
  printf 'TOKEN=copy\n' > "$repo/.env.local"

  output="$(run_script_from "$repo" init --payload ".env.local" --copy)"
  grep -Fq 'MODE=copy creates worktree-local payload copies' <<<"$output" || fail "expected copy-mode warning"

  git -C "$repo" worktree add -b hook/copy "$target" HEAD >/dev/null 2>&1
  assert_exists "$target/.env.local"
  [[ ! -L "$target/.env.local" ]] || fail "expected copy mode to create a real file"
  [[ "$(cat "$target/.env.local")" == "TOKEN=copy" ]] || fail "unexpected copied file content"
}

test_partial_failure_recovery() {
  log "partial failure recovery"
  local repo="$TMP_DIR/partial-repo"
  local target="$TMP_DIR/partial-worktree"
  local hook_log target_exclude

  create_repo "$repo"
  mkdir -p "$repo/.scratch"
  printf 'scratch\n' > "$repo/.scratch/task.md"

  run_script_from "$repo" init --payload ".scratch .missing" >/dev/null
  git -C "$repo" worktree add -b hook/partial "$target" HEAD >/dev/null 2>&1

  assert_exists "$target/.scratch/task.md"
  assert_not_exists "$target/.missing"
  hook_log="$(git -C "$target" rev-parse --git-path agent-worktree-hook.log)"
  assert_file_contains "$hook_log" "missing source payload: .missing"

  mkdir -p "$repo/.missing"
  printf 'recovered\n' > "$repo/.missing/value.txt"
  run_script_from "$repo" init --payload ".scratch .missing" >/dev/null

  assert_exists "$target/.missing/value.txt"
  target_exclude="$(exclude_file_for "$target")"
  assert_count "$target_exclude" '/.missing' 1

  rm -rf "$target/.missing"
  git -C "$target" checkout -b hook/partial-repair >/dev/null 2>&1
  assert_exists "$target/.missing/value.txt"
  assert_count "$target_exclude" '/.missing' 1
}

log "bash syntax"
bash -n "$SCRIPT"

if [[ -n "${QUICK_VALIDATE:-}" ]]; then
  log "quick validate"
  python "$QUICK_VALIDATE" "$SKILL_DIR"
fi

test_init_hook_and_native_worktree_add
test_reconfigure_disable_and_old_command_refusal
test_custom_config_path
test_copy_mode
test_partial_failure_recovery

log "ok"
