---
name: setup-obsidian-workspace
description: Connect a canonical Local Markdown tracker to an Obsidian Kanban workspace, adjust project bindings, or repair an incomplete setup. Use for workspace setup requests; routine refresh uses the configured renderer command.
---

# Setup Obsidian Workspace

Connect a canonical tracker to one selected Vault; leave verified navigation and a repeatable refresh command.

## Inspect and select

Run `python3 <skill-dir>/scripts/setup-workspace.py inspect --repo <project-path>`, adding the user-provided `--config` or `--vault` when present. The helper checks the local config, bounded Obsidian registry, runtime dependencies and canonical tracker. Follow its JSON result; use command `--help` for options.

Reuse the configured Vault and output. Registry candidates, including the open Vault, are suggestions only. Ask for the target when it remains unresolved. When `use-workspace-config` is returned, inspect that config before adding the project. Keep the selected target fixed even when another Vault is open in the UI.

Completion: the configuration and target are identified, or one concrete missing choice/prerequisite is reported.

## Configure

Run the helper's `configure --repo <project-path> --config <config-path>` with `--vault <selected-path>` for first setup. Pass selection options only when the user requests a selection change. The helper preserves existing bindings, assigns stable project IDs, backs up and atomically updates config, establishes local ignore coverage, and refreshes owned output.

Complete authorized Obsidian/Kanban prerequisites in the selected Vault. For dependency errors, existing output ownership, custom path schemes or refresh failures, read [the workspace contract](references/workspace.md). Keep failed or partial refreshes visible and resolve the reported cause before claiming setup succeeded.

Completion: configuration and refresh results are known; a failure leaves a specific recovery step.

## Verify navigation

Run `verify --config <config-path>` on the helper. Its compact result supplies Home, project views, a sample source and the exact refresh command/environment. Open Home in the selected Vault, then the project's Kanban view and canonical Ticket. For an empty tracker, verify the empty view and source identity. Verify affected existing bindings when changing them.

If the UI shows another Vault, open the selected Vault; `verify --active-vault <observed-path>` checks this mismatch without changing the target. UI-unavailable runs remain pending. Report the config, Home, refresh command and observed result. Explain that generated board edits are disposable, while editing a linked Ticket changes its canonical source.

Completion: actual navigation is verified, or the exact remaining UI blocker is reported without claiming success.
