#!/usr/bin/env bash
# Thin dispatcher — pipes stdin to the Python policy engine.
# Usage: bash dispatch.sh <event>
set -euo pipefail
trap 'printf "{}\n"; exit 0' ERR
export PYTHONPATH="${CLAUDE_PLUGIN_ROOT}"
input=$(cat)
printf '%s' "$input" | python3 -m engram policy "$@"
