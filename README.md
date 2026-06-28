# Jett Skills

Personal agent skills for Codex, Claude Code, and other Agent-Skills-compatible harnesses.

This repository is a catalog: each installable skill lives under `skills/<category>/<skill-name>/`. The skill directories stay lean and contain only `SKILL.md` plus resources that the agent actually uses. Repository-level docs, tests, and install scripts live at the repo root.

## Quick Start

Clone the catalog and link all skills into the local skill directories:

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

### Orchestration

| Skill | Purpose |
| --- | --- |
| [`ultra`](skills/orchestration/ultra/SKILL.md) | Wrap agent skills with adaptive pre-exploration, structured post-review, and `/ultra solve` issue execution. |

### Workflow

| Skill | Purpose |
| --- | --- |
| [`agent-worktree`](skills/workflow/agent-worktree/SKILL.md) | Create, verify, repair, and remove Agent-ready Git worktrees with local-only payload. |

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

## Layout

```text
skills/
├── orchestration/
│   └── ultra/
└── workflow/
    └── agent-worktree/
```

This follows the catalog shape used by [mattpocock/skills](https://github.com/mattpocock/skills), while keeping OpenAI/Codex metadata such as `agents/openai.yaml` where useful.

## Existing Single-Skill Repos

These repositories are kept as transitional single-skill packages:

- [JettHu/ultra-skill](https://github.com/JettHu/ultra-skill)
- [JettHu/agent-worktree-skill](https://github.com/JettHu/agent-worktree-skill)

Prefer this catalog for new installs once it is wired into your local workflow.
