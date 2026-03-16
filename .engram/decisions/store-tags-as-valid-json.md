---
type: decision
date: 2026-03-16
tags: [schema, sqlite, tags]
---

# Store tags as valid JSON in index.db

Tags were stored as YAML-style `[a, b, c]` (no quotes) which is not valid JSON. Every consumer had fragile workarounds with REPLACE/SUBSTR to parse them. Changed `_index_file()` to normalize tags via `_normalize_tags()` during frontmatter parsing, converting to `["a","b","c"]`. This lets all consumers use `json_each(signals.tags)` directly instead of string manipulation hacks. Simplified `engram_brief` distinct-tag counting and `engram_tag_summary` accordingly.
