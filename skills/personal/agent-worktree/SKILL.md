---
name: agent-worktree
description: Scaffold repo-level Agent-ready worktree hooks. Use only when enabling, reconfiguring, reinstalling, disabling, or uninstalling the repo-local hook or its payload/mode config; use native git worktree add for ordinary worktree creation.
---

# Agent Worktree

Scaffold a repo so future native Git worktrees become Agent-ready automatically. The leading word is **scaffold**: install or update repo-local hook/config, then leave daily worktree creation to Git.

Daily interface:

```bash
git worktree add <path> <branch-or-ref>
```

This skill does not choose solve branch names, worktree paths, base refs, grouping, validation, merge behavior, or cleanup behavior. `/ultra solve` owns solve workflow semantics. `$solve-records cleanup` owns solve resource cleanup.

## Bundled Script

Resolve `scripts/bootstrap-agent-worktree.sh` relative to this skill directory, not relative to the target repo. The script scaffolds:

- `.agents/agent-worktree.env`
- a self-contained managed block in `git rev-parse --git-path hooks/post-checkout`
- source checkout `info/exclude` entries for config and payload paths

The installed hook must not call back into this skill directory or any personal skill path.

## Default Path

If `.agents/agent-worktree.env` is missing and the user did not explicitly request defaults or provide exact payload/mode values:

1. Run `suggest-payload`.
2. Show the proposed payload and mode.
3. Ask the user to confirm, remove paths, add paths, or switch mode before writing config.

Skip the review only when the user explicitly says to use defaults, requests non-interactive setup, provides exact config values, or asks to reinstall an already configured hook.

After confirmation or explicit defaults:

```bash
bash scripts/bootstrap-agent-worktree.sh init --payload "<paths>" --mode link
```

Completion criterion: the script reports final payload, mode, and hook status; `.agents/agent-worktree.env` exists; the `post-checkout` hook contains exactly one managed block; source `info/exclude` hides the config and payload paths.

## Reconfigure

Map natural-language requests to these commands. They update env/hook/exclude only; they do not create, bootstrap, verify, remove, or delete worktrees.

```bash
bash scripts/bootstrap-agent-worktree.sh add-payload docs/local .scratch
bash scripts/bootstrap-agent-worktree.sh remove-payload node_modules
bash scripts/bootstrap-agent-worktree.sh regenerate-payload
bash scripts/bootstrap-agent-worktree.sh set-mode link
bash scripts/bootstrap-agent-worktree.sh set-mode copy
bash scripts/bootstrap-agent-worktree.sh reinstall-hook
```

`MODE=copy` is supported but must warn that copied payload edits are worktree-local and are lost when the worktree is removed. Prefer `MODE=link` for mutable Agent context such as `.scratch`, local docs, env files, dependency caches, and debug state.

## Disable Or Uninstall

Use either command when the user asks to disable, remove, or uninstall the Agent-ready worktree hook:

```bash
bash scripts/bootstrap-agent-worktree.sh disable
bash scripts/bootstrap-agent-worktree.sh uninstall
```

Completion criterion: only the managed hook block is removed, user hook content remains, and no payload files, solve records, issues, PRDs, or project content are deleted.

## Hook Contract

The managed block anchors are stable:

```bash
# --- agent-worktree managed block begin ---
# --- agent-worktree managed block end ---
```

The hook is reconciliation-style:

- Run only in linked worktrees during branch checkouts, including `git worktree add`.
- Read `.agents/agent-worktree.env` from the source checkout.
- Link or copy each valid repo-relative payload path into the target worktree.
- Add target `info/exclude` entries idempotently before payload paths can appear in Git status.
- Leave existing target paths intact.
- Skip or log missing payload sources without blocking other payload paths.
- Recover partial failures on a later hook trigger or by rerunning `$agent-worktree`.
- Keep normal successful execution quiet.
- Log exceptional details to `git rev-parse --git-path agent-worktree-hook.log`.

## Validation

For ordinary edits, run:

```bash
tests/agent-worktree.sh
scripts/validate-skills.sh
```

Use model evals only when changing invocation behavior or cross-skill solve orchestration, not for small wording or deterministic fixture updates.
