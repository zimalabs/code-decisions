#!/usr/bin/env bash
# UserPromptSubmit command hook: detect decision language in user messages.
# Reads user prompt from stdin JSON, checks for decision keywords.
set -euo pipefail

# Always output valid JSON, even on unexpected errors
trap 'printf "{}\n"; exit 0' ERR

# Read JSON from stdin
input=$(cat)

# Extract user prompt text (best-effort from JSON)
prompt=$(printf '%s' "$input" | sed -n 's/.*"content" *: *"\([^"]*\)".*/\1/p' | tr '[:upper:]' '[:lower:]')
[ -z "$prompt" ] && { printf '{}\n'; exit 0; }

# Dedup: only nudge once per session
session_file="/tmp/engram-prompt-nudge-${CLAUDE_SESSION_ID:-$$}"

# Check for decision language
if printf '%s' "$prompt" | grep -qE "(let.?s go with|we decided|switching to|going with|the decision is|we.?ll use|agreed on|settled on)"; then
  if [ ! -f "$session_file" ]; then
    touch "$session_file"
    printf '{"ok": true, "reason": "That sounds like a decision — consider @engram:capture."}\n'
    exit 0
  fi
fi

# Check for past-decision queries
if printf '%s' "$prompt" | grep -qE "(why did we|what was decided|what did we decide|remind me)"; then
  printf '{"ok": true, "reason": "Past signals may exist — consider @engram:query."}\n'
  exit 0
fi

printf '{}\n'
