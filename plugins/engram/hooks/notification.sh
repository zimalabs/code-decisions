#!/usr/bin/env bash
# Notification command hook: suggest enrichment for incomplete signals.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

ENGRAM_DIR=".engram"

[ -f "$ENGRAM_DIR/index.db" ] || { printf '{}\n'; exit 0; }

# Dedup: only nudge once per session
session_file="/tmp/engram-enrich-nudge-${CLAUDE_SESSION_ID:-$$}"
if [ -f "$session_file" ]; then
  printf '{}\n'
  exit 0
fi

# Check for incomplete signals (valid=0)
invalid_count=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE valid=0;" 2>/dev/null || echo "0")

if [ "$invalid_count" -gt 0 ]; then
  touch "$session_file"
  printf '{"systemMessage":"%d incomplete decision(s) — consider @engram:introspect to fill gaps."}\n' "$invalid_count"
else
  printf '{}\n'
fi
