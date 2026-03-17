#!/usr/bin/env bash
# SubagentStop command hook: advisory nudge about capturing subagent recommendations.
# Cannot programmatically detect architectural recommendations, so just output
# a lightweight reminder via systemMessage.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

ENGRAM_DIR=".engram"

# Only nudge if engram is active
[ -d "$ENGRAM_DIR" ] || { printf '{}\n'; exit 0; }

# Dedup: only nudge once per session
session_file="/tmp/engram-subagent-nudge-${CLAUDE_SESSION_ID:-$$}"
if [ -f "$session_file" ]; then
  printf '{}\n'
  exit 0
fi
touch "$session_file"

printf '{"systemMessage":"If this subagent made architectural recommendations, consider @engram:capture."}\n'
