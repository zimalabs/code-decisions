---
name: engram:resync
description: "Run the full engram sync pipeline: ingest commits and plans, rebuild the index, and regenerate the brief. Use after editing signals or when the index feels stale."
---

# @engram:resync

Run the full sync pipeline — ingest, reindex, and regenerate the brief.

## Execution

Run via a single Bash call:

```bash
source "${CLAUDE_PLUGIN_ROOT}/lib.sh" && \
ENGRAM_DIR=".engram" && \
engram_resync "$ENGRAM_DIR" && \
if [ -f "$ENGRAM_DIR/index.db" ]; then
  decisions=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision';" 2>/dev/null || echo "0")
  echo "Resynced: $decisions decisions"
else
  echo "Error: index.db was not created"
  exit 1
fi
```

## Output

Report the decision count to the user after the sync completes.
