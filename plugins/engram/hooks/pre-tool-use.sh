#!/usr/bin/env bash
# PreToolUse command hook: validate signal files written to .engram/.
# Deterministic frontmatter validation — no LLM dependency.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT}"

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

# ── Edit tool: block content deletion from signal files ──
# Edit has old_string + new_string. Block if new_string is empty (content removal).
old_string=$(printf '%s' "$input" | sed -n 's/.*"old_string" *: *"\([^"]*\)".*/\1/p')
if [ -n "$old_string" ]; then
  new_string=$(printf '%s' "$input" | sed -n 's/.*"new_string" *: *"\([^"]*\)".*/\1/p')
  if [ -z "$new_string" ]; then
    printf '{"decision": "block", "reason": "Signals are append-only — do not delete content from .engram/ decision files. To retract a decision, set status: withdrawn in frontmatter."}\n'
    exit 0
  fi
  # Allow other edits (adding tags, fixing typos, appending sections)
  printf '{}\n'
  exit 0
fi

# ── Write tool: validate full content ──
content=$(printf '%s' "$input" | sed -n 's/.*"content" *: *"\(.*\)"/\1/p')
[ -z "$content" ] && { printf '{}\n'; exit 0; }

# Unescape JSON string (basic: \n → newline, \" → ", \\ → \)
decoded=$(printf '%s' "$content" | sed -e 's/\\n/\n/g' -e 's/\\"/"/g' -e 's/\\\\/\\/g')

# Validate via Python
errors=$(printf '%s' "$decoded" | python3 -m engram validate-content 2>&1 || true)

if [ -n "$errors" ]; then
  # Escape for JSON
  esc_errors=$(printf '%s' "$errors" | sed -e 's/"/\\"/g')
  printf '{"ok": false, "reason": "%s"}\n' "$esc_errors"
else
  printf '{}\n'
fi
