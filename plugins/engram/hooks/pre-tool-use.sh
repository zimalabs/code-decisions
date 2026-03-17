#!/usr/bin/env bash
# PreToolUse command hook: validate signal files written to .engram/.
# Deterministic frontmatter validation — no LLM dependency.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

ENGRAM_PY="${CLAUDE_PLUGIN_ROOT}/engram.py"

# Read JSON from stdin
input=$(cat)

# Extract file path
file_path=$(printf '%s' "$input" | sed -n 's/.*"file_path" *: *"\([^"]*\)".*/\1/p')
[ -z "$file_path" ] && { printf '{}\n'; exit 0; }

# Only validate .engram/decisions/ and .engram/_private/ files
case "$file_path" in
  *.engram/decisions/*.md|*.engram/_private/decisions/*.md) ;;
  *) printf '{}\n'; exit 0 ;;
esac

# Extract file content from tool_input
# For Write: "content" field. For Edit: we can't validate partial edits, skip.
content=$(printf '%s' "$input" | sed -n 's/.*"content" *: *"\(.*\)"/\1/p')
[ -z "$content" ] && { printf '{}\n'; exit 0; }

# Unescape JSON string (basic: \n → newline, \" → ", \\ → \)
decoded=$(printf '%s' "$content" | sed -e 's/\\n/\n/g' -e 's/\\"/"/g' -e 's/\\\\/\\/g')

# Validate via Python
errors=$(printf '%s' "$decoded" | python3 "$ENGRAM_PY" validate-content 2>&1 || true)

if [ -n "$errors" ]; then
  # Escape for JSON
  esc_errors=$(printf '%s' "$errors" | sed -e 's/"/\\"/g')
  printf '{"ok": false, "reason": "%s"}\n' "$esc_errors"
else
  printf '{}\n'
fi
