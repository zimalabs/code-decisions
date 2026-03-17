---
name: engram:brief
description: "Regenerate and display the engram brief on demand. Run after capturing new signals or reindexing to see the updated summary without starting a new session."
---

# @engram:brief

Regenerate and display the current engram brief.

## Execution

Run the brief pipeline via a single Bash call:

```bash
ENGRAM_DIR=".engram" && \
python3 "${CLAUDE_PLUGIN_ROOT}/engram.py" brief "$ENGRAM_DIR" && \
echo "Brief regenerated."
```

## Output

After the Bash call completes, read `.engram/brief.md` with the Read tool and display its full contents to the user.
