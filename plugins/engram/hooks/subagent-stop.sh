#!/usr/bin/env bash
# SubagentStop command hook: inject decision context into subagent results.
# Subagents don't get SessionStart, so they're blind to past decisions.
# This injects the brief so the parent agent has context when processing results.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

ENGRAM_DIR=".engram"

# Only act if engram is active
[ -d "$ENGRAM_DIR" ] || { printf '{}\n'; exit 0; }

# Build message parts
msg=""

# Inject brief if available
if [ -f "$ENGRAM_DIR/brief.md" ]; then
  brief=$(cat "$ENGRAM_DIR/brief.md")
  if [ -n "$brief" ]; then
    msg="$brief"
  fi
fi

# Nudge about capture (once per session)
session_file="/tmp/engram-subagent-nudge-${CLAUDE_SESSION_ID:-$$}"
if [ ! -f "$session_file" ]; then
  touch "$session_file"
  if [ -n "$msg" ]; then
    msg="$msg\n\nIf this subagent made architectural decisions, capture them with @engram:capture."
  else
    msg="If this subagent made architectural decisions, consider @engram:capture."
  fi
fi

[ -z "$msg" ] && { printf '{}\n'; exit 0; }

# JSON-escape and output
json_msg=$(printf '%s' "$msg" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' | awk '{ if (NR > 1) printf "\\n"; printf "%s", $0 }')
printf '{"systemMessage":"%s"}\n' "$json_msg"
