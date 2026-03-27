---
name: "stop-hook-nudge-for-decision-capture"
description: "Stop hook nudges agent to capture decisions before session ends"
date: "2026-03-19"
tags:
  - "plugin-architecture"
  - "hooks"
  - "nudge"
affects:
  - "src/decision/policy/stop_nudge.py"
  - "src/decision/policy/engine.py"
---

# Stop hook nudge for decision capture

The `capture-nudge` policy only watches `UserPromptSubmit`, so it detects decision language in user messages but misses decisions the agent makes silently while writing code. A `Stop` hook nudges the agent before it finishes its response to either capture decisions or explicitly acknowledge none were made.

## Alternatives
- PostToolUse nudge after N edits — fires mid-conversation, however the agent hasn't finished its work yet and doesn't know if it made decisions. Premature nudges would be noisy and ignored.
- SessionEnd hook — fires after the session is over, but the agent can't act on it. The context is gone and no capture is possible.

## Rationale
The `Stop` event fires when the agent is about to finish responding — the ideal moment because all implementation choices have been made and the agent still has full context. `SessionState.edit_count()` and `has_recent_decisions()` already track the data needed. The `once_per_session=True` flag ensures the nudge only fires once — after the agent acknowledges or captures, subsequent stops proceed normally. The `EDIT_THRESHOLD` constant (3 edits) prevents nudging on trivial sessions.

## Trade-offs
Adds one nudge per session when the agent has done significant work — roughly ~2s delay while the Stop hook evaluates. The agent can dismiss the nudge by acknowledging "no decisions were made," so false positives don't permanently stall. If `list_decisions()` is slow with many files, the `has_recent_decisions()` check could approach the 5s hook timeout.
