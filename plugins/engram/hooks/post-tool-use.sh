#!/usr/bin/env bash
# PostToolUse command hook: nudge about decision capture + inject related context.
# Merges the capture-nudge (was prompt hook) with context injection into one script.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

source "${CLAUDE_PLUGIN_ROOT}/lib.sh"
ENGRAM_DIR=".engram"

# Read JSON from stdin
input=$(cat)

# Extract file path from tool_input
file_path=$(printf '%s' "$input" | sed -n 's/.*"file_path" *: *"\([^"]*\)".*/\1/p')
[ -z "$file_path" ] && { printf '{}\n'; exit 0; }

# ── Capture nudge (once per session) ──────────────────────────────

session_nudge="/tmp/engram-nudge-${CLAUDE_SESSION_ID:-$$}"
session_context="/tmp/engram-injected-${CLAUDE_SESSION_ID:-$$}"

# Skip .engram/ paths, tests, docs, config files for nudge logic
skip_nudge=0
case "$file_path" in
  *.engram/*) skip_nudge=1 ;;
  *_test.*|*.test.*|*/tests/*|*/test/*|*/spec/*|tests/*|test/*|spec/*) skip_nudge=1 ;;
  *.md|*/docs/*|*/doc/*) skip_nudge=1 ;;
  *.json|*.yaml|*.yml|*.toml|*.lock) skip_nudge=1 ;;
esac

nudge_msg=""
if [ "$skip_nudge" -eq 0 ] && [ ! -f "$session_nudge" ]; then
  # Check if any .engram/decisions/ file was written this session
  # (Proxy: any decision file newer than index.db)
  if [ -d "$ENGRAM_DIR/decisions" ]; then
    recent=$(find "$ENGRAM_DIR/decisions" -name '*.md' -newer "$ENGRAM_DIR/index.db" 2>/dev/null | wc -l | tr -d ' ')
  else
    recent=0
  fi
  if [ "$recent" -eq 0 ]; then
    nudge_msg="Consider recording this decision with @engram:capture."
    touch "$session_nudge"
  fi
fi

# ── Context injection ─────────────────────────────────────────────

# Must have an index to query
context_msg=""
if [ -f "$ENGRAM_DIR/index.db" ] && [ "$skip_nudge" -ne 1 ]; then
  keywords=$(engram_path_to_keywords "$file_path")
  if [ -n "$keywords" ]; then
    # Dedup: skip if already injected for these keywords
    if [ ! -f "$session_context" ] || ! grep -qF "$keywords" "$session_context" 2>/dev/null; then
      results=$(engram_query_relevant "$ENGRAM_DIR" "$keywords" 3)
      if [ -n "$results" ]; then
        echo "$keywords" >> "$session_context"
        context_msg="Related past decisions:\\n$results"
      fi
    fi
  fi
fi

# ── Output ────────────────────────────────────────────────────────

if [ -n "$nudge_msg" ] && [ -n "$context_msg" ]; then
  msg="$context_msg\\n\\n$nudge_msg"
elif [ -n "$context_msg" ]; then
  msg="$context_msg"
elif [ -n "$nudge_msg" ]; then
  msg="$nudge_msg"
else
  printf '{}\n'
  exit 0
fi

json_msg=$(printf '%s' "$msg" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' | awk '{ if (NR > 1) printf "\\n"; printf "%s", $0 }')
printf '{"systemMessage":"%s"}\n' "$json_msg"
