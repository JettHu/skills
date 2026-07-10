# Jett Skills

Agent repo-maintainer skills for Codex, Claude Code, and other Agent-Skills-compatible harnesses.

This repository is an installable skill catalog and a small maintainer workflow layer: PRD -> issues -> claim -> worktree -> solve -> review -> validation -> records -> land -> cleanup. Each installable skill lives under `skills/<category>/<skill-name>/`. Skill directories stay lean and contain only `SKILL.md` plus resources that the agent actually uses. Repository-level docs, tests, and install scripts live at the repo root.

## Quick Start

Install from GitHub with the skills CLI:

```bash
npx skills@latest add JettHu/skills
```

The installer shows grouped choices such as `Jett Skills` and `Personal`.

For local development, clone the catalog and link all skills into the local skill directories:

```bash
gh repo clone JettHu/skills ~/workspace/skills
cd ~/workspace/skills
scripts/link-skills.sh
```

By default this links every skill into:

- `~/.agents/skills`
- `~/.claude/skills`

To link into a specific destination:

```bash
scripts/link-skills.sh ~/.agents/skills
```

The installer creates symlinks, so `git pull` in this repository updates installed skills.

## Skills

### Engineering

| Skill | Purpose |
| --- | --- |
| [`solve-records`](skills/engineering/solve-records/SKILL.md) | List and explain local Attempt receipts, safely advance candidate records, and surface recovery next actions. |
| [`ultra`](skills/engineering/ultra/SKILL.md) | Coordinate enhanced skill runs and the `/ultra solve` issue-to-candidate workflow. |
| [`ultra-diagnose`](skills/engineering/ultra-diagnose/SKILL.md) | Completion-friendly entry for `/ultra diagnose`. |
| [`ultra-solve`](skills/engineering/ultra-solve/SKILL.md) | Completion-friendly entry for `/ultra solve`. |
| [`ultra-to-issues`](skills/engineering/ultra-to-issues/SKILL.md) | Completion-friendly entry for `/ultra to-issues`. |
| [`ultra-to-prd`](skills/engineering/ultra-to-prd/SKILL.md) | Completion-friendly entry for `/ultra to-prd`. |

### Personal

| Skill | Purpose |
| --- | --- |
| [`agent-worktree`](skills/personal/agent-worktree/SKILL.md) | Scaffold Agent-ready Git worktree hooks with local payload and dependency strategy config. |

### In Progress

Experimental skills belong in `skills/in-progress/` until their trigger wording, workflow, and validation story are stable enough to move into a permanent category.

## Commands

List skills:

```bash
scripts/list-skills.sh
```

Validate skill metadata and bundled shell scripts:

```bash
scripts/validate-skills.sh
```

Run the agent-worktree integration fixture:

```bash
tests/agent-worktree.sh
```

Run the solve-records behavior fixture:

```bash
tests/solve-records.sh
```

## Layout

```text
skills/
├── engineering/
│   ├── solve-records/
│   ├── ultra/
│   ├── ultra-diagnose/
│   ├── ultra-solve/
│   ├── ultra-to-issues/
│   └── ultra-to-prd/
├── personal/
│   └── agent-worktree/
└── in-progress/
```

## Existing Single-Skill Repos

These repositories are kept as transitional single-skill packages:

- [JettHu/ultra-skill](https://github.com/JettHu/ultra-skill)
- [JettHu/agent-worktree-skill](https://github.com/JettHu/agent-worktree-skill)

Prefer this catalog for new installs once it is wired into your local workflow.
