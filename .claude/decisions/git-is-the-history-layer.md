---
name: "git-is-the-history-layer"
description: "Edit decisions in place, delete when obsolete. Git tracks the full evolution — no supersedes/withdrawn ceremony needed."
date: "2026-03-25"
tags:
  - "architecture"
  - "plugin-architecture"
affects:
  - "src/decision/core/decision.py"
  - "src/decision/policy/content_validation.py"
  - "src/decision/store/"
  - ".claude/decisions/"
---

# Git is the history layer — edit decisions in place

Decisions are edited in place and deleted when obsolete. Git's immutable commit history preserves the full evolution chain — `git log -p .claude/decisions/slug.md` shows every change, who made it, and when.

The previous approach used `supersedes` fields and `status: "withdrawn"` to create an on-disk audit trail. This was necessary before decisions were git-tracked, but now that they live in `.claude/decisions/` committed to the repo, it's redundant. The supersedes/withdrawn ceremony added complexity (auto-withdraw regex rewriting, status filtering in FTS5, withdrawn file clutter) for no benefit over what git already provides.

The plugin now nudges consolidation instead: when a new decision overlaps with existing ones (shared tags or affects paths), it suggests editing the existing decision or merging them into one file.
