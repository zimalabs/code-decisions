---
name: "dispatch-errors-never-break-claude"
description: "dispatch.sh traps ERR and exits 0 — plugin errors must never break Claude Code"
date: "2026-03-24"
tags:
  - "architecture"
  - "reliability"
  - "hooks"
affects:
  - "src/hooks/dispatch.sh"
---

# Dispatch errors never break Claude Code

`dispatch.sh` traps ERR and always exits 0, logging errors to `~/.claude/logs/decision.log`. A plugin bug must never prevent Claude Code from functioning — the worst case is a missing nudge or context injection, not a broken session.

This is a hard requirement for any Claude Code hook. A non-zero exit or malformed JSON from a hook can block tool use or crash the session.
