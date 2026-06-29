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

assert_file_contains() {
  local file="$1"
  local expected="$2"
  grep -Fq "$expected" "$file" || fail "expected $file to contain: $expected"
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
}

run_script_from() {
  local repo="$1"
  shift
  (cd "$repo" && bash "$SCRIPT" "$@")
}

assert_payload_contains() {
  local repo="$1"
  local expected="$2"
  local payload
  payload="$(run_script_from "$repo" suggest-payload)"
  contains_word "$payload" "$expected" || fail "expected payload to contain $expected; got: $payload"
}

test_default_project_root_fixture() {
  log "default project worktree root"
  local repo="$TMP_DIR/default-repo"
  local target="$TMP_DIR/.agent-worktrees/default-repo/default-repo-context-sync"

  create_repo "$repo"
  mkdir -p "$repo/.scratch/context"
  printf 'tracked\n' > "$repo/README.md"
  printf 'local context\n' > "$repo/.scratch/context/task.md"
  (cd "$repo" && git add README.md && git_commit_all 'init default fixture')

  run_script_from "$repo" init --payload ".scratch" >/dev/null
  assert_file_contains "$repo/.agents/agent-worktree.env" 'WORKTREE_ROOT="../.agent-worktrees/default-repo"'

  run_script_from "$repo" create "context sync" >/dev/null

  assert_exists "$target/.scratch/context/task.md"
  run_script_from "$repo" verify "$target" >/dev/null
  run_script_from "$repo" remove "context sync" --delete-branch >/dev/null
  [[ ! -e "$target" ]] || fail "expected removed worktree: $target"
}

test_js_fixture() {
  log "js fixture"
  local repo="$TMP_DIR/js-repo"
  local worktrees="$TMP_DIR/js-worktrees"
  local target="$worktrees/js-repo-payment-retry"

  create_repo "$repo"
  mkdir -p "$repo/.scratch/payment/issues" "$repo/logs" "$repo/web/node_modules/demo"
  printf '{"scripts":{"test":"node --test"}}\n' > "$repo/package.json"
  printf '# Agent instructions\n' > "$repo/AGENTS.md"
  printf 'status: ready-for-agent\n' > "$repo/.scratch/payment/issues/01-retry.md"
  printf 'debug log\n' > "$repo/logs/current.log"
  printf 'module cache\n' > "$repo/web/node_modules/demo/index.js"
  (cd "$repo" && git add package.json && git_commit_all 'init js fixture')

  assert_payload_contains "$repo" "AGENTS.md"
  assert_payload_contains "$repo" ".scratch"
  assert_payload_contains "$repo" "logs"
  assert_payload_contains "$repo" "web/node_modules"

  run_script_from "$repo" init \
    --worktree-root "$worktrees" \
    --payload "AGENTS.md .scratch logs web/node_modules" >/dev/null
  run_script_from "$repo" create "payment retry" >/dev/null

  assert_exists "$target/AGENTS.md"
  assert_exists "$target/.scratch/payment/issues/01-retry.md"
  assert_exists "$target/logs/current.log"
  assert_exists "$target/web/node_modules/demo/index.js"
  run_script_from "$repo" verify "$target" >/dev/null

  run_script_from "$repo" remove "payment retry" --delete-branch >/dev/null
  [[ ! -e "$target" ]] || fail "expected removed worktree: $target"
}

test_python_fixture() {
  log "python fixture"
  local repo="$TMP_DIR/python-repo"
  local worktrees="$TMP_DIR/python-worktrees"
  local target="$worktrees/python-repo-queue-worker"

  create_repo "$repo"
  mkdir -p "$repo/docs/local" "$repo/.venv/bin" "$repo/.pytest_cache" "$repo/tmp"
  printf '[project]\nname = "fixture"\n' > "$repo/pyproject.toml"
  printf '# Agent instructions\n' > "$repo/AGENTS.md"
  printf 'DB_URL=sqlite:///tmp/local.sqlite\n' > "$repo/.envrc"
  printf 'local docs\n' > "$repo/docs/local/README.md"
  printf 'python executable placeholder\n' > "$repo/.venv/bin/python"
  printf 'cache\n' > "$repo/.pytest_cache/README"
  printf 'sqlite placeholder\n' > "$repo/tmp/local.sqlite"
  (cd "$repo" && git add pyproject.toml && git_commit_all 'init python fixture')

  assert_payload_contains "$repo" "AGENTS.md"
  assert_payload_contains "$repo" "docs/local"
  assert_payload_contains "$repo" ".envrc"
  assert_payload_contains "$repo" ".venv"
  assert_payload_contains "$repo" ".pytest_cache"
  assert_payload_contains "$repo" "tmp"

  run_script_from "$repo" init \
    --worktree-root "$worktrees" \
    --payload "AGENTS.md docs/local .envrc .venv .pytest_cache tmp" >/dev/null
  run_script_from "$repo" create "queue worker" >/dev/null

  assert_exists "$target/AGENTS.md"
  assert_exists "$target/docs/local/README.md"
  assert_exists "$target/.envrc"
  assert_exists "$target/.venv/bin/python"
  assert_exists "$target/.pytest_cache/README"
  assert_exists "$target/tmp/local.sqlite"
  run_script_from "$repo" verify "$target" >/dev/null

  (cd "$target" && bash "$SCRIPT" remove --current --delete-branch >/dev/null)
  [[ ! -e "$target" ]] || fail "expected removed current worktree: $target"
}

log "bash syntax"
bash -n "$SCRIPT"

if [[ -n "${QUICK_VALIDATE:-}" ]]; then
  log "quick validate"
  python "$QUICK_VALIDATE" "$SKILL_DIR"
fi

test_default_project_root_fixture
test_js_fixture
test_python_fixture

log "ok"
