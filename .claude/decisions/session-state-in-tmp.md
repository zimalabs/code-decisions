---
name: "session-state-in-tmp"
description: "Per-session state in /tmp with atomic O_CREAT|O_EXCL marker files for once-per-session policies"
date: "2026-03-24"
tags:
  - "architecture"
  - "policy"
  - "state"
affects:
  - "src/decision/policy/engine.py"
---

# Session state in /tmp

Per-session state lives at `/tmp/decision-policy-{session_id}/` with marker files for once-per-session policy tracking. Marker files are created atomically via `O_CREAT|O_EXCL` to avoid TOCTOU races between concurrent hook invocations.

Session ID comes from `CLAUDE_SESSION_ID` env var (set by Claude Code), falling back to PID if unset. Stale directories (>24h) are cleaned up at SessionStart.
