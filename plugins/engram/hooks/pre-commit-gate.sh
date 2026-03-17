#!/usr/bin/env bash
# PreToolUse Bash hook: block git commit if no decision signal was written this session.
# Only fires on Bash tool calls whose command starts with "git commit".
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

ENGRAM_DIR=".engram"

# No .engram directory — not an engram project, allow everything
[ -d "$ENGRAM_DIR/decisions" ] || { printf '{}\n'; exit 0; }

# Read JSON from stdin
input=$(cat)

# Extract the command being run
command=$(printf '%s' "$input" | sed -n 's/.*"command" *: *"\([^"]*\)".*/\1/p')

# Only gate on git commit (not amend, not other git commands)
case "$command" in
  git\ commit*--amend*) printf '{}\n'; exit 0 ;;  # amend is fine — signal already exists
  git\ commit*) ;;                                  # gate this
  *) printf '{}\n'; exit 0 ;;                       # not a commit, allow
esac

# Check if any decision file is newer than index.db (proxy for "written this session")
if [ -f "$ENGRAM_DIR/index.db" ]; then
  recent=$(find "$ENGRAM_DIR/decisions" "$ENGRAM_DIR/_private/decisions" -name '*.md' -newer "$ENGRAM_DIR/index.db" 2>/dev/null | wc -l | tr -d ' ')
else
  # No index.db means fresh session — check if any decision files exist at all
  recent=$(find "$ENGRAM_DIR/decisions" "$ENGRAM_DIR/_private/decisions" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
fi

if [ "$recent" -gt 0 ]; then
  # Decision(s) written this session — allow commit
  printf '{}\n'
  exit 0
fi

# No decision signals written — block the commit
printf '{"decision": "block", "reason": "No decision signal written this session. Write a signal to .engram/decisions/{slug}.md before committing (use @engram:capture). If this change is trivial (typo, formatting), amend with --amend to bypass."}\n'
