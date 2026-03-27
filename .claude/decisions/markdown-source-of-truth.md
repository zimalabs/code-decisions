---
name: "markdown-source-of-truth"
description: "Markdown files are the source of truth — FTS5 index is derived and disposable"
date: "2026-03-24"
tags:
  - "architecture"
  - "storage"
affects:
  - "src/decision/store/index.py"
  - "src/decision/store/store.py"
---

# Markdown is source of truth, FTS5 is derived

The SQLite FTS5 index (`index.db`) is a derived cache over the markdown decision files. Delete it and it rebuilds automatically on next access. This means the markdown files in `.claude/decisions/` are the canonical store — the index exists only for fast search.

This keeps the system simple and debuggable: you can read, edit, and git-diff decisions with any text editor. Corruption in the index is a non-event.
