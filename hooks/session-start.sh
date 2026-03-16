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

# Gather stats for intro banner
if [ -f "$ENGRAM_DIR/index.db" ]; then
  decisions=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision';" 2>/dev/null || echo "0")
  findings=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE type='finding';" 2>/dev/null || echo "0")
  issues=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE type='issue';" 2>/dev/null || echo "0")
  private=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE private=1;" 2>/dev/null || echo "0")
else
  decisions=0; findings=0; issues=0; private=0
fi

total=$((decisions + findings + issues))

# Print intro banner to stderr (visible to user)
{
  echo ""
  echo "  ◆ engram active"
  echo "  ├─ $decisions decisions · $findings findings · $issues issues"
  uncommitted_msg=$(engram_uncommitted_summary "$ENGRAM_DIR")
  if [ -n "$uncommitted_msg" ]; then
    echo "  ├─ $uncommitted_msg"
  fi
  if [ "$private" -gt 0 ]; then
    echo "  ├─ $private private signals"
  fi
  echo "  └─ $total signals indexed"
  echo ""
} >&2

# Read brief and inject with behavioral instructions
[ -f "$ENGRAM_DIR/brief.md" ] || exit 0
brief=$(cat "$ENGRAM_DIR/brief.md")

instructions="$brief

---
You have a persistent decision store via engram (.engram/ directory).

IMPORTANT: You MUST capture signals during this session. After completing
any of these actions, immediately write a signal file:

  Decision signals (.engram/decisions/{date}-{slug}.md):
  - Chose one approach over alternatives
  - Added, removed, or changed a dependency
  - Changed architecture, schema, or API design
  - Set up CI, deployment, or infrastructure

  Finding signals (.engram/findings/{date}-{slug}.md):
  - Discovered a bug, limitation, or undocumented behavior
  - Found that a library/tool works differently than expected
  - Identified a performance bottleneck or security concern

  Issue signals (.engram/issues/{date}-{slug}.md):
  - Found something broken that wasn't fixed this session
  - Identified tech debt or a missing test
  - Noted a blocker for future work

For PRIVATE signals (sensitive, never git-tracked):
  Use .engram/private/{decisions,findings,issues}/ instead

To query past signals:
  @engram:query <question>

Signal files are git-tracked. Before ending your session, if you created
any signals, stage and commit them:
  git add .engram/ && git commit -m \"engram: update signals\""

# JSON-escape and output
json_ctx=$(printf '%s' "$instructions" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' | awk '{ if (NR > 1) printf "\\n"; printf "%s", $0 }')
printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$json_ctx"
