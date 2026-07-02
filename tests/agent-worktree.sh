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
  haystack="${haystack//$'\n'/ }"
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
  mkdir -p "$repo/.scratch/issues" "$repo/docs/local" "$repo/node_modules"
  printf 'Status: ready-for-agent\n' > "$repo/.scratch/issues/01.md"
  printf 'local docs\n' > "$repo/docs/local/README.md"
  printf 'TOKEN=local\n' > "$repo/.env.local"
  printf 'dependency cache\n' > "$repo/node_modules/cache.txt"

  suggestion="$(run_script_from "$repo" suggest-payload)"
  contains_word "$suggestion" ".scratch" || fail "expected suggestion to include .scratch: $suggestion"
  contains_word "$suggestion" "docs/local" || fail "expected suggestion to include docs/local: $suggestion"
  contains_word "$suggestion" ".env.local" || fail "expected suggestion to include .env.local: $suggestion"
  ! contains_word "$suggestion" "node_modules" || fail "expected dependency dirs outside ordinary payload: $suggestion"

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

test_dependency_strategy_detection_and_config() {
  log "dependency strategy detection and config"
  local pnpm_repo="$TMP_DIR/deps-pnpm-repo"
  local uv_repo="$TMP_DIR/deps-uv-repo"
  local npm_repo="$TMP_DIR/deps-npm-repo"
  local rust_repo="$TMP_DIR/deps-rust-repo"
  local output before_count after_count

  create_repo "$pnpm_repo"
  mkdir -p "$pnpm_repo/.scratch" "$pnpm_repo/node_modules"
  printf '{}\n' > "$pnpm_repo/package.json"
  printf 'lockfileVersion: 9\n' > "$pnpm_repo/pnpm-lock.yaml"
  output="$(run_script_from "$pnpm_repo" suggest-payload)"
  grep -Fq 'dependency-ecosystem: pnpm' <<<"$output" || fail "expected pnpm detection: $output"
  grep -Fq 'dependency-strategy: bootstrap' <<<"$output" || fail "expected bootstrap suggestion: $output"
  grep -Fq 'pnpm install --offline --frozen-lockfile' <<<"$output" || fail "expected pnpm offline command: $output"
  ! grep -Eq '^payload: .*node_modules' <<<"$output" || fail "expected node_modules outside payload: $output"

  output="$(run_script_from "$pnpm_repo" init --payload ".scratch" --dependency-strategy bootstrap)"
  grep -Fq 'dependency bootstrap offline: pnpm install --offline --frozen-lockfile' <<<"$output" || fail "expected bootstrap command in setup output: $output"
  assert_file_contains "$pnpm_repo/.agents/agent-worktree.env" 'PAYLOAD=".scratch"'
  assert_file_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_STRATEGY="bootstrap"'
  assert_file_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_BOOTSTRAP_OFFLINE="pnpm install --offline --frozen-lockfile"'
  assert_file_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_BOOTSTRAP_ONLINE="pnpm install --frozen-lockfile"'
  assert_file_not_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_PAYLOAD='

  output="$(run_script_from "$pnpm_repo" set-dependency-strategy link --dependency-payload node_modules)"
  grep -Fq 'dependency strategy: link' <<<"$output" || fail "expected link strategy output: $output"
  assert_file_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_STRATEGY="link"'
  assert_file_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_PAYLOAD="node_modules"'
  assert_file_not_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_BOOTSTRAP_OFFLINE='

  before_count="$(git -C "$pnpm_repo" worktree list --porcelain | grep -c '^worktree ')"
  run_script_from "$pnpm_repo" set-dependency-strategy none >/dev/null
  after_count="$(git -C "$pnpm_repo" worktree list --porcelain | grep -c '^worktree ')"
  [[ "$before_count" == "$after_count" ]] || fail "dependency reconfigure should not create/delete worktrees"
  assert_exists "$pnpm_repo/node_modules"
  assert_file_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_STRATEGY="none"'
  assert_file_not_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_PAYLOAD='
  assert_file_not_contains "$pnpm_repo/.agents/agent-worktree.env" 'DEPENDENCY_BOOTSTRAP_OFFLINE='

  create_repo "$uv_repo"
  mkdir -p "$uv_repo/.venv"
  printf '[project]\nname = "fixture"\nversion = "0.1.0"\n' > "$uv_repo/pyproject.toml"
  printf 'version = 1\n' > "$uv_repo/uv.lock"
  output="$(run_script_from "$uv_repo" suggest-payload)"
  grep -Fq 'dependency-ecosystem: uv' <<<"$output" || fail "expected uv detection: $output"
  grep -Fq 'uv sync --offline --locked' <<<"$output" || fail "expected uv offline command: $output"
  ! grep -Eq '^payload: .*\.venv' <<<"$output" || fail "expected .venv outside payload: $output"

  create_repo "$npm_repo"
  printf '{}\n' > "$npm_repo/package.json"
  printf '{}\n' > "$npm_repo/package-lock.json"
  output="$(run_script_from "$npm_repo" suggest-payload)"
  grep -Fq 'dependency-ecosystem: no-fast-installer' <<<"$output" || fail "expected no-fast-installer detection: $output"
  grep -Fq 'dependency-strategy: none' <<<"$output" || fail "expected no bootstrap suggestion: $output"
  ! grep -Fq 'dependency-bootstrap-offline:' <<<"$output" || fail "expected no generated bootstrap command: $output"

  create_repo "$rust_repo"
  mkdir -p "$rust_repo/target" "$rust_repo/.gradle" "$rust_repo/build" "$rust_repo/vendor"
  printf '[package]\nname = "fixture"\nversion = "0.1.0"\n' > "$rust_repo/Cargo.toml"
  printf '# lock\n' > "$rust_repo/Cargo.lock"
  printf 'module fixture\n' > "$rust_repo/go.mod"
  printf 'plugins {}\n' > "$rust_repo/build.gradle"
  output="$(run_script_from "$rust_repo" suggest-payload)"
  grep -Fq 'dependency-strategy: none' <<<"$output" || fail "expected no default bootstrap for Rust/Go/JVM: $output"
  ! grep -Eq '^payload: .*target' <<<"$output" || fail "expected target outside payload: $output"
  ! grep -Eq '^payload: .*\.gradle' <<<"$output" || fail "expected .gradle outside payload: $output"
  ! grep -Eq '^payload: .*build' <<<"$output" || fail "expected build outside payload: $output"
  ! grep -Eq '^payload: .*vendor' <<<"$output" || fail "expected vendor outside payload: $output"
}

test_dependency_bootstrap_hook_diagnostics() {
  log "dependency bootstrap hook diagnostics"
  local repo="$TMP_DIR/bootstrap-repo"
  local target="$TMP_DIR/bootstrap-worktree"
  local fail_repo="$TMP_DIR/bootstrap-fail-repo"
  local fail_target="$TMP_DIR/bootstrap-fail-worktree"
  local timeout_repo="$TMP_DIR/bootstrap-timeout-repo"
  local timeout_target="$TMP_DIR/bootstrap-timeout-worktree"
  local missing_repo="$TMP_DIR/bootstrap-missing-repo"
  local missing_target="$TMP_DIR/bootstrap-missing-worktree"
  local invalid_repo="$TMP_DIR/bootstrap-invalid-repo"
  local invalid_target="$TMP_DIR/bootstrap-invalid-worktree"
  local none_repo="$TMP_DIR/bootstrap-none-repo"
  local none_target="$TMP_DIR/bootstrap-none-worktree"
  local fake_bin hook_log output

  fake_bin="$TMP_DIR/fake-bin"
  mkdir -p "$fake_bin"
  cat > "$fake_bin/pnpm" <<'EOF'
#!/bin/sh
case " $* " in
  *" --offline "*)
    printf 'ERR_PNPM_NO_OFFLINE_TARBALL missing cache\n' >&2
    exit 1
    ;;
  *)
    mkdir -p node_modules
    printf 'online ok\n' > node_modules/.bootstrap-ok
    exit 0
    ;;
esac
EOF
  chmod +x "$fake_bin/pnpm"

  create_repo "$repo"
  mkdir -p "$repo/.scratch" "$repo/node_modules"
  printf '{}\n' > "$repo/package.json"
  printf 'lockfileVersion: 9\n' > "$repo/pnpm-lock.yaml"
  run_script_from "$repo" init --payload ".scratch" --dependency-strategy bootstrap >/dev/null
  PATH="$fake_bin:$PATH" git -C "$repo" worktree add -b hook/bootstrap "$target" HEAD >/dev/null 2>&1
  assert_exists "$target/.scratch"
  assert_exists "$target/node_modules/.bootstrap-ok"
  [[ ! -L "$target/node_modules" ]] || fail "bootstrap must not fall back to linked node_modules"
  hook_log="$(git -C "$target" rev-parse --git-path agent-worktree-hook.log)"
  assert_file_contains "$hook_log" "offline-cache-miss retry"

  create_repo "$fail_repo"
  mkdir -p "$fail_repo/node_modules"
  run_script_from "$fail_repo" init --payload "" \
    --dependency-strategy bootstrap \
    --dependency-bootstrap-offline "printf ERR_PNPM_NO_OFFLINE_TARBALL >&2; exit 1" \
    --dependency-bootstrap-online "exit 42" >/dev/null
  git -C "$fail_repo" worktree add -b hook/bootstrap-fail "$fail_target" HEAD >/dev/null 2>&1
  assert_not_exists "$fail_target/node_modules"
  hook_log="$(git -C "$fail_target" rev-parse --git-path agent-worktree-hook.log)"
  assert_file_contains "$hook_log" "offline-cache-miss retry"
  assert_file_contains "$hook_log" "dependency bootstrap online failed: class=non-zero-exit status=42"

  create_repo "$timeout_repo"
  output="$(run_script_from "$timeout_repo" init --payload "" \
    --dependency-strategy bootstrap \
    --dependency-bootstrap-offline "sleep 2" \
    --dependency-timeout 1)"
  grep -Fq 'dependency bootstrap timeout: 1s' <<<"$output" || fail "expected timeout setup output: $output"
  git -C "$timeout_repo" worktree add -b hook/bootstrap-timeout "$timeout_target" HEAD >/dev/null 2>&1
  hook_log="$(git -C "$timeout_target" rev-parse --git-path agent-worktree-hook.log)"
  assert_file_contains "$hook_log" "dependency bootstrap offline failed: class=timeout status=124"

  create_repo "$missing_repo"
  run_script_from "$missing_repo" init --payload "" \
    --dependency-strategy bootstrap \
    --dependency-bootstrap-offline "agent-worktree-command-that-does-not-exist" >/dev/null
  git -C "$missing_repo" worktree add -b hook/bootstrap-missing "$missing_target" HEAD >/dev/null 2>&1
  hook_log="$(git -C "$missing_target" rev-parse --git-path agent-worktree-hook.log)"
  assert_file_contains "$hook_log" "dependency bootstrap offline failed: class=command-not-found status=127"

  create_repo "$invalid_repo"
  run_script_from "$invalid_repo" init --payload "" >/dev/null
  printf 'DEPENDENCY_STRATEGY="surprise"\n' >> "$invalid_repo/.agents/agent-worktree.env"
  git -C "$invalid_repo" worktree add -b hook/bootstrap-invalid "$invalid_target" HEAD >/dev/null 2>&1
  hook_log="$(git -C "$invalid_target" rev-parse --git-path agent-worktree-hook.log)"
  assert_file_contains "$hook_log" "invalid dependency config: class=invalid-config strategy=surprise"

  create_repo "$none_repo"
  mkdir -p "$none_repo/node_modules"
  run_script_from "$none_repo" init --payload "" --dependency-strategy none >/dev/null
  git -C "$none_repo" worktree add -b hook/bootstrap-none "$none_target" HEAD >/dev/null 2>&1
  assert_not_exists "$none_target/node_modules"
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
test_dependency_strategy_detection_and_config
test_dependency_bootstrap_hook_diagnostics

log "ok"
