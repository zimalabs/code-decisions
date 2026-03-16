#!/usr/bin/env bash
# Ingest new commits, reindex, regenerate brief at session end.
# Inject context reminder about uncommitted signals.
set -euo pipefail

source "${CLAUDE_PLUGIN_ROOT}/lib.sh"
ENGRAM_DIR=".engram"
[ -d "$ENGRAM_DIR" ] || exit 0

engram_ingest_commits "$ENGRAM_DIR"
engram_ingest_plans "$ENGRAM_DIR"
engram_reindex "$ENGRAM_DIR"
engram_brief "$ENGRAM_DIR"

# Check for uncommitted signals and inject context
uncommitted_msg=$(engram_uncommitted_summary "$ENGRAM_DIR")

if [ -n "$uncommitted_msg" ]; then
  note="You have $uncommitted_msg — stage and commit them before ending: git add .engram/ && git commit -m 'engram: update signals'"
else
  note="No new signals were captured this session. If you made decisions, discovered issues, or found unexpected behavior, consider writing signals before ending."
fi

json_note=$(printf '%s' "$note" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' | awk '{ if (NR > 1) printf "\\n"; printf "%s", $0 }')
printf '{"hookSpecificOutput":{"hookEventName":"SessionEnd","additionalContext":"%s"}}\n' "$json_note"
