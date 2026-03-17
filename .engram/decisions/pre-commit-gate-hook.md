---
type: decision
date: 2026-03-17
tags: [hooks, enforcement]
links: [related:convert-engram-py-to-package]
---

# Add PreToolUse hook to block git commit without decision signal

Agents skip writing decision signals even when CLAUDE.md and SessionStart context tell them to. Nudges (stop hook, post-tool-use) are advisory and easily ignored. A blocking PreToolUse hook on Bash intercepts `git commit` and checks if any `.engram/decisions/*.md` file is newer than `index.db` — if not, the commit is blocked with a message pointing to `@engram:capture`.

## Rationale

Suggestions don't enforce behavior — hooks do. The pre-commit gate makes decision capture a hard requirement rather than a best-effort convention. `--amend` bypasses the gate for trivial changes.

## Alternatives

- **Advisory-only stop hook** — already exists, agents ignore it.
- **Git pre-commit hook** — only works with git tracking enabled, doesn't integrate with Claude's tool permission system.
