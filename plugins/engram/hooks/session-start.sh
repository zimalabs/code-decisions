#!/usr/bin/env bash
# Auto-init, ingest, index, brief, inject context at session start.
set -euo pipefail

source "${CLAUDE_PLUGIN_ROOT}/lib.sh"
ENGRAM_DIR=".engram"

# Always init — idempotent, ensures new dirs exist on old installs
engram_init "$ENGRAM_DIR"

# ALWAYS re-ingest — catches commits from any source (VS Code, terminal, CI, other devs)
engram_ingest_commits "$ENGRAM_DIR"
engram_ingest_plans "$ENGRAM_DIR"
engram_reindex "$ENGRAM_DIR"
engram_brief "$ENGRAM_DIR"

# Gather stats for intro banner
if [ -f "$ENGRAM_DIR/index.db" ]; then
  decisions=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision';" 2>/dev/null || echo "0")
  private=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE private=1;" 2>/dev/null || echo "0")
else
  decisions=0; private=0
fi

# Print intro banner to stderr (visible to user)
{
  echo ""
  echo "  ◆ engram active"
  echo "  ├─ $decisions decisions"
  uncommitted_msg=$(engram_uncommitted_summary "$ENGRAM_DIR")
  if [ -n "$uncommitted_msg" ]; then
    echo "  ├─ $uncommitted_msg"
  fi
  if [ "$private" -gt 0 ]; then
    echo "  ├─ $private private signals"
  fi
  echo "  └─ $decisions signals indexed"
  echo ""
} >&2

# Read brief and inject with behavioral instructions
[ -f "$ENGRAM_DIR/brief.md" ] || exit 0
brief=$(cat "$ENGRAM_DIR/brief.md")

instructions="$brief"

# For large signal stores, append tag summary to help the agent know which domains have coverage
if [ "$decisions" -gt 30 ]; then
  tag_line=$(engram_tag_summary "$ENGRAM_DIR")
  if [ -n "$tag_line" ]; then
    instructions="$instructions
$tag_line"
  fi
fi

instructions="$instructions

---
You have a persistent decision store via engram (.engram/ directory).
When you make a significant decision, write a signal file:
  Write .engram/signals/decision-{slug}.md  (use the decision schema)

For PRIVATE signals (sensitive, never git-tracked or auto-sent to API):
  Write .engram/_private/decision-{slug}.md

To query past signals:
  @engram:query <question>"

# JSON-escape and output
json_ctx=$(printf '%s' "$instructions" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' | awk '{ if (NR > 1) printf "\\n"; printf "%s", $0 }')
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$json_ctx"
