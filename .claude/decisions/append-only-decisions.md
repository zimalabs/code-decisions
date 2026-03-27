---
name: "append-only-decisions"
description: "Append-only is enforced by git, not file conventions. Edit in place, delete when obsolete, git log preserves history."
date: "2026-03-25"
tags:
  - "architecture"
  - "governance"
affects:
  - ".claude/decisions/"
---

# Append-only decisions — enforced by git

Decision history is append-only because git commits are immutable. Edit decision files in place when they evolve, delete them when they're obsolete. `git log -p` preserves the full chain of reasoning.

There's no need for `supersedes` fields or `withdrawn` statuses — those were file-level conventions from before decisions were git-tracked. Git provides the same immutability guarantee with less ceremony.
