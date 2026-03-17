#!/usr/bin/env bash
# Ingest new commits, reindex, regenerate brief at session end.
set -euo pipefail

# Always output valid JSON, even on unexpected errors
trap 'printf "{}\n"; exit 0' ERR

source "${CLAUDE_PLUGIN_ROOT}/lib.sh"
ENGRAM_DIR=".engram"
[ -d "$ENGRAM_DIR" ] || { printf '{}\n'; exit 0; }

engram_resync "$ENGRAM_DIR"

# SessionEnd hooks only support universal fields (continue, stopReason, suppressOutput, systemMessage).
# Context injection (additionalContext) is only valid for SessionStart hooks.
printf '{}\n'
