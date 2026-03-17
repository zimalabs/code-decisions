---
name: engram:policies
description: "List all active engram policies with their levels, events, and descriptions"
---

# /engram:policies — Active Policy Introspection

Run the policy engine in list mode to display all registered policies.

## Instructions

Run this command to list all active policies:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m engram policy
```

Display the output as a formatted table with columns: Name, Level, Events, Description.

Policy levels (evaluation order):
- **BLOCK** — fail-fast, prevents the action
- **LIFECYCLE** — side effects (init, resync, cleanup)
- **CONTEXT** — injects information into agent context
- **NUDGE** — advisory suggestions, never blocks
