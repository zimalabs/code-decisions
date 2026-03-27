---
name: "tag-summary-over-per-decision-listing"
description: "Session-context injects tag counts and query hint instead of listing individual decisions"
date: "2026-03-19"
tags:
  - "plugin-architecture"
  - "context-injection"
  - "session-start"
affects:
  - "src/decision/policy/session_context.py"
---

# Tag-based summary over per-decision listing for session-context



Replaced the session-start context injection that listed the 10 most recent decisions (title, date, excerpt each) with a compact tag-count summary plus a pointer to `/decision:query`. The agent now sees topic coverage at a glance and pulls details on demand.

## Alternatives
- Per-decision listing (previous approach) — injects ~40 lines of context showing individual decisions sorted by date. Consumes context window with decisions that may be irrelevant to the current task. Doesn't scale past 20-30 decisions.
- Count-only banner ("47 decisions available") — too sparse, gives the agent no signal about what topics are covered, so it wouldn't know when to query.
- Full tag + recent listing hybrid — show tags AND the 5 most recent. However this combines the worst of both: still burns context on potentially irrelevant recent decisions.

## Rationale
The `_session_context_condition` function in `src/decision/policy/defs.py` now uses `collections.Counter` to aggregate tags across active decisions and displays them with counts. The agent sees which topics have decision coverage (e.g. "**caching** (4), **auth** (3)") and can `/decision:query caching` to pull relevant context before starting work. Only the single most recent decision title is shown as a temporal anchor.

## Trade-offs
The agent loses the ability to scan recent decision excerpts without an explicit query — an extra tool call is required to get details. This is intentional: context window is expensive and the query skill exists precisely for this purpose. If the project has very few decisions (< 5), the summary is less useful than a full listing would be, but this is the bootstrapping phase where decisions are few enough to not need summarization.
