#!/usr/bin/env bash
# Stop command hook: check if decisions directory has recent signals.
# Uses filesystem checks only — no LLM-dependent JSON generation.
set -euo pipefail

# Always output valid JSON, even on unexpected errors
trap 'printf "{}\n"; exit 0' ERR

ENGRAM_DIR=".engram"

# No .engram directory — nothing to check
[ -d "$ENGRAM_DIR/decisions" ] || { printf '{"ok": true}\n'; exit 0; }

# Count decision files modified in the last 10 minutes (proxy for "this session")
recent=$(find "$ENGRAM_DIR/decisions" -name '*.md' -newer "$ENGRAM_DIR/index.db" 2>/dev/null | wc -l | tr -d ' ')

# If there are recent signals, the agent is recording decisions — all good
if [ "$recent" -gt 0 ]; then
  printf '{"ok": true}\n'
  exit 0
fi

# Check if index.db was recently updated (session was active)
if [ ! -f "$ENGRAM_DIR/index.db" ]; then
  printf '{"ok": true}\n'
  exit 0
fi

# No recent decision files — nudge (advisory, always ok:true)
printf '{"ok": true, "reason": "No new decision signals this session. If you made significant changes, consider @engram:capture."}\n'
