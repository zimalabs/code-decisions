#!/usr/bin/env bash
# PostToolUse command hook: inject related past decisions when editing files.
# Reads tool_input JSON from stdin, extracts file path, queries index.db.
set -euo pipefail

source "${CLAUDE_PLUGIN_ROOT}/lib.sh"
ENGRAM_DIR=".engram"

# Must have an index to query
[ -f "$ENGRAM_DIR/index.db" ] || { printf '{}\n'; exit 0; }

# Read JSON from stdin
input=$(cat)

# Extract file path from tool_input (Write uses file_path, Edit uses file_path too)
file_path=$(printf '%s' "$input" | sed -n 's/.*"file_path" *: *"\([^"]*\)".*/\1/p')
[ -z "$file_path" ] && { printf '{}\n'; exit 0; }

# Skip .engram/ paths (avoid self-referential noise)
case "$file_path" in
  *.engram/*) printf '{}\n'; exit 0 ;;
esac

# Skip test-only, docs-only, config-only files
case "$file_path" in
  *_test.*|*.test.*|*/tests/*|*/test/*|*/spec/*|tests/*|test/*|spec/*) printf '{}\n'; exit 0 ;;
  *.md|*/docs/*|*/doc/*) printf '{}\n'; exit 0 ;;
  *.json|*.yaml|*.yml|*.toml|*.lock) printf '{}\n'; exit 0 ;;
esac

# Dedup: track injected file stems per session to avoid repeats
session_file="/tmp/engram-injected-${CLAUDE_SESSION_ID:-$$}"
keywords=$(engram_path_to_keywords "$file_path")
[ -z "$keywords" ] && { printf '{}\n'; exit 0; }

# Check if we already injected for these keywords
if [ -f "$session_file" ] && grep -qF "$keywords" "$session_file" 2>/dev/null; then
  printf '{}\n'; exit 0
fi

# Query for related signals
results=$(engram_query_relevant "$ENGRAM_DIR" "$keywords" 3)
[ -z "$results" ] && { printf '{}\n'; exit 0; }

# Record that we injected for these keywords
echo "$keywords" >> "$session_file"

# JSON-escape the message
message="Related past decisions:\n$results"
json_msg=$(printf '%s' "$message" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' | awk '{ if (NR > 1) printf "\\n"; printf "%s", $0 }')
printf '{"systemMessage":"%s"}\n' "$json_msg"
