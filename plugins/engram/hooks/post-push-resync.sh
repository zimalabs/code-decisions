#!/usr/bin/env bash
# PostToolUse Bash hook: auto-resync after git push to keep index current.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT}"
ENGRAM_DIR=".engram"

# No .engram directory — nothing to do
[ -d "$ENGRAM_DIR" ] || { printf '{}\n'; exit 0; }

# Read JSON from stdin
input=$(cat)

# Extract the command that was run
command=$(printf '%s' "$input" | sed -n 's/.*"command" *: *"\([^"]*\)".*/\1/p')
[ -z "$command" ] && { printf '{}\n'; exit 0; }

# Only act on git push
case "$command" in
  git\ push*) ;;
  *) printf '{}\n'; exit 0 ;;
esac

# Resync to pick up any changes
python3 -m engram resync "$ENGRAM_DIR" 2>/dev/null

printf '{"systemMessage":"engram resynced after push."}\n'
