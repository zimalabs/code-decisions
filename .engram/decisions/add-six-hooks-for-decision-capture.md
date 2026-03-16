---
type: decision
date: 2026-03-16
tags: [hooks, decision-capture, plugin-api]
---

# Add 6 new hooks for in-the-moment decision capture

Added PostToolUse, PreToolUse, SubagentStop, PreCompact, UserPromptSubmit, and Notification hooks to complement the existing SessionStart/SessionEnd/Stop trio.

## Why

The Stop hook catches missing decisions at session end, but by then context may be lost. These hooks capture decisions **as they happen**: after code changes (PostToolUse), before context compaction (PreCompact), when users state decisions verbally (UserPromptSubmit), and when subagents make recommendations (SubagentStop).

## Trade-offs

- **Only PreToolUse blocks** — it validates signal file format before writes to .engram/signals/ or .engram/_private/. All other new hooks are advisory-only systemMessages.
- **Once-per-session nudging** — PostToolUse and UserPromptSubmit nudge at most once to avoid noise.
- **Notification is passive** — only surfaces open issues older than 7 days, count-based.
- **PostToolUse skips .engram/, tests, formatting, docs** — avoids false positives on non-decision changes.
