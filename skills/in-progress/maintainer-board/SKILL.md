---
name: maintainer-board
description: Generate a read-only local HTML dashboard for a repository's .scratch issues and solve records. Use when the user asks for an issues board, solve-records board, maintainer board, local dashboard, or static board snapshot for the current repo or another local checkout.
---

# Maintainer Board

Generate the board and report the generated HTML path.

Run the bundled script from the target repository shell:

```bash
python /path/to/maintainer-board/scripts/maintainer-board.py
```

No arguments means:

- target repo: the current working directory's Git root
- HTML output: `<repo>/.scratch/maintainer-board/index.html`

If the user gives another checkout, pass it explicitly:

```bash
python /path/to/maintainer-board/scripts/maintainer-board.py --repo /path/to/repo
```

The default HTML output still belongs to that target repo.

For a raw machine snapshot instead of HTML, use:

```bash
python /path/to/maintainer-board/scripts/maintainer-board.py --json
```

Treat the helper as read-only except for writing the HTML path. It does not run tests, builds, installer discovery, merges, cleanup, Agents, or models. It derives issue state from explicit metadata/frontmatter, not natural-language prose. Use `$solve-records` for advancing, merging, closing, or cleaning solve records.
