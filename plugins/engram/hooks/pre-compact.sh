#!/usr/bin/env bash
# PreCompact command hook: regenerate and re-inject brief before context is lost.
set -euo pipefail

# Always output valid JSON, even on unexpected errors
trap 'printf "{}\n"; exit 0' ERR

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT}"
ENGRAM_DIR=".engram"

# Must have .engram/ directory
[ -d "$ENGRAM_DIR" ] || { printf '{}\n'; exit 0; }

# Reindex to capture any mid-session signal writes, then regenerate brief
python3 -m engram reindex "$ENGRAM_DIR"
python3 -m engram brief "$ENGRAM_DIR"

# Read brief and inject as systemMessage
[ -f "$ENGRAM_DIR/brief.md" ] || { printf '{}\n'; exit 0; }

brief=$(cat "$ENGRAM_DIR/brief.md")
[ -z "$brief" ] && { printf '{}\n'; exit 0; }

# JSON-escape the brief content
json_brief=$(printf '%s' "$brief" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' | awk '{ if (NR > 1) printf "\\n"; printf "%s", $0 }')
printf '{"systemMessage":"%s"}\n' "$json_brief"
