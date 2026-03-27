---
name: "query-preseed-hook-for-skill"
description: "UserPromptSubmit hook pre-seeds Python query results before the query skill runs Glob/Grep"
date: "2026-03-19"
tags:
  - "plugin-architecture"
  - "hooks"
  - "query"
affects:
  - "src/decision/policy/defs.py"
---

# Query-preseed hook to combine Python scorer with native tool search



Added a `query-preseed` policy on `UserPromptSubmit` that detects `/decision:query <keywords>` and runs `store.query()` (Python keyword scorer) to inject ranked results before the skill fires. The skill then uses Glob/Grep/Read to dig deeper into matches. This gives the agent the best of both: fast scored ranking from Python + full file access from native tools.

## Alternatives
- Shell out to Python from the skill — the skill could tell the agent to run `python3 -m decision query`. However this violates the "use native tools" principle and the architecture rule of no CLI.
- Keep Python and skill search separate — the Python query only runs in hooks (related-context), the skill only uses Glob/Grep. But this means two search implementations that could diverge, and the skill misses the scoring logic.
- Replace skill search entirely with Python — make the skill just display Python results. But this removes the agent's ability to read full files and grep for additional terms the scorer missed.

## Rationale
The `_query_preseed_condition` in `src/decision/policy/defs.py` fires on `UserPromptSubmit` when it detects `/decision:query <keywords>`. It calls `store.query(keywords, RELATED_CONTEXT_LIMIT)` and injects results as a `reason` string. The skill (`src/skills/decision/SKILL.md`) now tells the agent to start with pre-seeded results and use native tools for deeper exploration.

## Trade-offs
Adds ~50-100ms to `UserPromptSubmit` processing when `/decision:query` is used — `store.query()` parses all decision files. The preseed only fires for explicit `/decision:query` invocations, not natural language queries like "what did we decide about caching." If the keyword scorer returns no matches but Grep would find them via substring, the agent might trust the empty preseed and stop looking.
