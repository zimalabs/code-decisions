#!/usr/bin/env bash
# Ingest new commits, reindex, regenerate brief at session end.
set -euo pipefail

source "${CLAUDE_PLUGIN_ROOT}/lib.sh"
ENGRAM_DIR=".engram"
[ -d "$ENGRAM_DIR" ] || exit 0

engram_ingest_commits "$ENGRAM_DIR"
engram_ingest_plans "$ENGRAM_DIR"
engram_reindex "$ENGRAM_DIR"
engram_brief "$ENGRAM_DIR"

# SessionEnd hooks only support universal fields (continue, stopReason, suppressOutput, systemMessage).
# Context injection (additionalContext) is only valid for SessionStart hooks.
printf '{}\n'
