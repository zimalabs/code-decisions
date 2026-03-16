---
type: decision
date: 2026-03-16
tags: [hooks, context-injection, read-path]
---

# Add automatic decision context injection to hooks

Engram's hook system was write-heavy, read-light — 6 capture hooks but context injection only at SessionStart. Past decisions didn't resurface mid-session unless manually queried.

Added 3 new lib.sh functions (`engram_path_to_keywords`, `engram_query_relevant`, `engram_tag_summary`) and 2 new command hooks:

- **PostToolUse command hook** (`post-tool-context.sh`): after Write/Edit, extracts file path keywords and queries FTS5 for related past decisions. Deduplicates per session.
- **PreCompact command hook** (`pre-compact.sh`): regenerates and re-injects the brief before context is lost to compaction.
- **Enhanced prompts**: UserPromptSubmit detects query intent ("why did we", "what was decided"); SubagentStop suggests checking for related decisions.
- **Tag summary**: session-start appends top topics when signal count > 30.

Command hooks run in parallel with existing prompt hooks. Context injection is advisory — no blocking.
