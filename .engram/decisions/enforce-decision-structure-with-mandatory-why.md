---
type: decision
date: 2026-03-16
tags: [schema, validation, quality]
---

# Enforce decision structure with mandatory "why"

Added `_validate_signal()` to lib.sh that checks frontmatter delimiters, ISO date, non-empty tags, H1 title, and a lead paragraph >= 20 chars. Invalid signals get `valid=0` in index.db and are excluded from the brief but remain queryable via FTS. The PreToolUse hook now rejects signals missing tags or rationale at write time. Auto-ingested commits without bodies are indexed as `valid=0` — they serve as placeholders that can be enriched later.

## Alternatives
- JSONL format — rejected because it loses human readability, has merge conflict issues, and the Write tool overwrites rather than appends
- No enforcement — status quo, too many incomplete signals diluting the brief

## Rationale
Decisions without rationale provide no value in context — they're just titles. Markdown's parse fragility is fixable with validation rather than switching formats. Enforcement at both write time (PreToolUse hook) and index time (_validate_signal) catches all paths.

## Trade-offs
Auto-ingested commits are now mostly `valid=0` since they lack tags and often lack sufficient body text. This is intentional — auto-ingest is a safety net, not the primary record.
