#!/usr/bin/env bash
# Auto-init, ingest, index, brief, inject context at session start.
set -euo pipefail

source "${CLAUDE_PLUGIN_ROOT}/lib.sh"
ENGRAM_DIR=".engram"

# Auto-init on first run
[ -d "$ENGRAM_DIR" ] || engram_init "$ENGRAM_DIR"

# ALWAYS re-ingest — catches commits from any source (VS Code, terminal, CI, other devs)
engram_ingest_commits "$ENGRAM_DIR"
engram_ingest_plans "$ENGRAM_DIR"
engram_reindex "$ENGRAM_DIR"
engram_brief "$ENGRAM_DIR"

# Read brief and inject with behavioral instructions
[ -f "$ENGRAM_DIR/brief.md" ] || exit 0
brief=$(cat "$ENGRAM_DIR/brief.md")

instructions="$brief

---
You have a persistent decision store via engram (.engram/ directory).
When you make a significant decision, write a signal file:
  Write .engram/decisions/{date}-{slug}.md  (use the decision schema)
When you discover something important:
  Write .engram/findings/{date}-{slug}.md   (use the finding schema)
When you identify an issue:
  Write .engram/issues/{date}-{slug}.md     (use the issue schema)

For PRIVATE signals (sensitive, never git-tracked or auto-sent to API):
  Write .engram/private/decisions/{date}-{slug}.md
  Write .engram/private/findings/{date}-{slug}.md
  Write .engram/private/issues/{date}-{slug}.md

To query past signals:
  @engram:query <question>"

# JSON-escape and output
json_ctx=$(printf '%s' "$instructions" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' | awk '{ if (NR > 1) printf "\\n"; printf "%s", $0 }')
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$json_ctx"
