#!/usr/bin/env bash
# PreToolUse Bash hook: block deletion of .engram signal files.
# Protects the append-only rule — signals should never be deleted or reverted.
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR

ENGRAM_DIR=".engram"

# No .engram directory — allow everything
[ -d "$ENGRAM_DIR" ] || { printf '{}\n'; exit 0; }

# Read JSON from stdin
input=$(cat)

# Extract the command being run
command=$(printf '%s' "$input" | sed -n 's/.*"command" *: *"\([^"]*\)".*/\1/p')
[ -z "$command" ] && { printf '{}\n'; exit 0; }

# Check for destructive operations targeting .engram/ signal files
case "$command" in
  rm*\.engram/decisions/*|rm*\.engram/_private/decisions/*)
    printf '{"decision": "block", "reason": "Signals are append-only — do not delete .engram/ decision files. Write a new signal with status: withdrawn instead."}\n'
    exit 0
    ;;
  rm*-rf*\.engram*|rm*-r*\.engram*)
    printf '{"decision": "block", "reason": "Do not delete the .engram/ directory or its contents. Signals are append-only."}\n'
    exit 0
    ;;
  git\ checkout*--*\.engram/decisions/*|git\ checkout*--*\.engram/_private/*)
    printf '{"decision": "block", "reason": "Do not revert .engram/ signal files. Signals are append-only — write a new signal with status: withdrawn instead."}\n'
    exit 0
    ;;
  git\ restore*\.engram/decisions/*|git\ restore*\.engram/_private/*)
    printf '{"decision": "block", "reason": "Do not restore/revert .engram/ signal files. Signals are append-only."}\n'
    exit 0
    ;;
esac

printf '{}\n'
