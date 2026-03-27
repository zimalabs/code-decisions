---
name: "fts5-search-pipeline"
description: "Search uses FTS5 with BM25 ranking, falling back to weighted keyword matching"
date: "2026-03-24"
tags:
  - "architecture"
  - "search"
  - "store"
affects:
  - "src/decision/store/index.py"
  - "src/decision/store/query.py"
---

# FTS5 search pipeline

Search follows a three-step pipeline: (1) sanitize query — split on whitespace/underscores/hyphens, add `*` suffix to terms ≤7 chars, join with OR; (2) FTS5 MATCH with BM25 ranking, filtered to `status='active'`; (3) if FTS5 is unavailable, fall back to weighted keyword matching (title x3, tags/description x2, body x1).

The fallback ensures search works even if SQLite FTS5 extension isn't available or the index is corrupted.
