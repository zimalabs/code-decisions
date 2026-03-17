#!/usr/bin/env bash
# PreToolUse command hook: validate signal files written to .engram/.
# Deterministic frontmatter validation — no LLM dependency.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

# Read JSON from stdin
input=$(cat)

# Extract file path
file_path=$(printf '%s' "$input" | sed -n 's/.*"file_path" *: *"\([^"]*\)".*/\1/p')
[ -z "$file_path" ] && { printf '{}\n'; exit 0; }

# Only validate .engram/decisions/ and .engram/_private/ files
case "$file_path" in
  *.engram/decisions/*.md|*.engram/_private/*.md) ;;
  *) printf '{}\n'; exit 0 ;;
esac

# Extract file content from tool_input
# For Write: "content" field. For Edit: we can't validate partial edits, skip.
content=$(printf '%s' "$input" | sed -n 's/.*"content" *: *"\(.*\)"/\1/p')
[ -z "$content" ] && { printf '{}\n'; exit 0; }

# Unescape JSON string (basic: \n → newline, \" → ", \\ → \)
decoded=$(printf '%s' "$content" | sed -e 's/\\n/\n/g' -e 's/\\"/"/g' -e 's/\\\\/\\/g')

# Validate frontmatter
errors=""

# Check frontmatter delimiters
if ! printf '%s\n' "$decoded" | head -1 | grep -q '^---$'; then
  errors="${errors}missing opening --- frontmatter delimiter; "
fi

if [ "$(printf '%s\n' "$decoded" | grep -c '^---$')" -lt 2 ]; then
  errors="${errors}missing closing --- frontmatter delimiter; "
fi

# Check date field
if ! printf '%s\n' "$decoded" | grep -qE '^date: *[0-9]{4}-[0-9]{2}-[0-9]{2}'; then
  errors="${errors}missing or invalid date: field (need YYYY-MM-DD); "
fi

# Check tags field (must exist and not be empty [])
tags_line=$(printf '%s\n' "$decoded" | grep -m1 '^tags:' || echo "")
if [ -z "$tags_line" ]; then
  errors="${errors}missing tags: field; "
else
  case "$tags_line" in
    *'[]'*) errors="${errors}tags: is empty, add at least one tag; " ;;
  esac
fi

# Check H1 title after frontmatter
if ! printf '%s\n' "$decoded" | grep -q '^# '; then
  errors="${errors}missing H1 title (# ...); "
fi

# Check lead paragraph (first non-empty non-heading line after title, >= 20 chars)
lead=$(printf '%s\n' "$decoded" | awk '
  /^---$/ { fm++; next }
  fm < 2 { next }
  /^# / { found_title=1; next }
  found_title && /^$/ { next }
  found_title && /^#/ { next }
  found_title { print; exit }
')
if [ -z "$lead" ] || [ "${#lead}" -lt 20 ]; then
  errors="${errors}lead paragraph after title must exist and be >= 20 chars (explains why); "
fi

if [ -n "$errors" ]; then
  # Escape for JSON
  esc_errors=$(printf '%s' "$errors" | sed -e 's/"/\\"/g')
  printf '{"ok": false, "reason": "%s"}\n' "$esc_errors"
else
  printf '{}\n'
fi
