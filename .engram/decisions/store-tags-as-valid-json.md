---
type: decision
date: 2026-03-16
tags: [schema, sqlite, tags]
links: [related:enforce-decision-structure-with-mandatory-why]
---

# Store tags as valid JSON in index.db

Tags were stored as YAML-style `[a, b, c]` (no quotes) which is not valid JSON. Every consumer had fragile workarounds with REPLACE/SUBSTR to parse them. Changed `_index_file()` to normalize tags via `_normalize_tags()` during frontmatter parsing, converting to `["a","b","c"]`. This lets all consumers use `json_each(signals.tags)` directly instead of string manipulation hacks. Simplified `engram_brief` distinct-tag counting and `engram_tag_summary` accordingly.

## Rationale

SQLite's `json_each()` requires valid JSON arrays. The YAML-style brackets were a leaky abstraction — every new consumer had to reinvent the same string parsing. Normalizing at index time pushes the complexity into one place and gives all downstream queries a clean contract.

## Alternatives

- Normalize at query time — shifts complexity to every consumer, fragile
- Store as comma-separated string without brackets — loses structure, harder to query
- Use a separate `signal_tags` junction table — over-engineered for the current scale
