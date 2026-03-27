---
name: "stdlib-only-in-src"
description: "Zero external dependencies in src/ — stdlib-only Python 3.11+"
date: "2026-03-24"
tags:
  - "architecture"
  - "dependencies"
affects:
  - "src/"
---

# Stdlib only in src/

Everything under `src/` uses only Python standard library. No PyYAML, no third-party packages. Must work on any machine with Python 3.11+ without `pip install`.

This is critical for a Claude Code plugin — it runs in the user's environment where installing dependencies would be intrusive. The custom frontmatter parser in `utils/frontmatter.py` exists specifically to avoid a PyYAML dependency.
