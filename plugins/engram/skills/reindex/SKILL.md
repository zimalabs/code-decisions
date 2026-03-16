---
name: engram:reindex
description: "Rebuild the engram index from signal files. Run after editing signals to refresh index.db without waiting for next session start."
---

# @engram:reindex

Rebuild the engram index and brief from signal files.

## Execution

Run the full refresh pipeline via a single Bash call:

```bash
source "${CLAUDE_PLUGIN_ROOT}/lib.sh" && \
ENGRAM_DIR=".engram" && \
engram_ingest_commits "$ENGRAM_DIR" && \
engram_ingest_plans "$ENGRAM_DIR" && \
engram_reindex "$ENGRAM_DIR" && \
engram_brief "$ENGRAM_DIR" && \
if [ -f "$ENGRAM_DIR/index.db" ]; then
  decisions=$(sqlite3 "$ENGRAM_DIR/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision';" 2>/dev/null || echo "0")
  echo "Reindexed: $decisions decisions"
else
  echo "Error: index.db was not created"
  exit 1
fi
```

## Output

Report the decision count to the user after reindexing completes.
