---
name: "search-skill-prefer-preseeded"
description: "Search skill presents pre-seeded hook results first, falls back to Glob/Grep only if needed"
date: "2026-03-20"
tags:
  - "search"
  - "skills"
affects:
  - "src/skills/decision/SKILL.md"
---

# Search skill prefers pre-seeded results over native tool search

The search SKILL.md now explicitly instructs the agent to present results from the `query-preseed` hook directly, only falling back to Glob/Grep if the hook didn't fire or returned no results. This avoids redundant searches and ensures the hook's curated results take priority.
