# Domain Docs

This repository uses a single domain context.

## Before Exploring

- Read the root `CONTEXT.md` for the current domain vocabulary and ownership boundaries.
- Read ADRs under `docs/adr/` that touch the area being changed.
- If either surface is absent, proceed without treating its absence as a prerequisite.

## Vocabulary

Use the terms defined in `CONTEXT.md` in Ticket titles, implementation plans, tests, documentation, and reviews. Avoid synonyms that the glossary explicitly rejects. When a required concept is missing, verify that it reflects a real domain gap before adding terminology.

## ADR Conflicts

Surface a conflict with an existing ADR explicitly. Do not silently override a settled decision; either follow it or identify why it needs a separate decision update.

## Layout

```text
/
├── CONTEXT.md
└── docs/
    └── adr/
```
