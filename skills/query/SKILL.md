---
name: engram:query
description: "Query past decisions, findings, and issues from the engram index. Runs SQL against .engram/index.db via Bash. Use to look up context before starting work."
---

# @engram:query

Query the engram index for past signals.

## Arguments

Parse `$ARGUMENTS` as either:
- A natural language question (convert to SQL)
- A raw SQL query (if it starts with SELECT)

## Execution Steps

### Natural Language Query

1. **Analyze** the question to determine the best retrieval strategy
2. **Try full-text search first** for keyword-based questions:

```bash
sqlite3 -json .engram/index.db "SELECT s.id, s.type, s.title, s.date, s.content FROM signals_fts fts JOIN signals s ON s.id = fts.rowid WHERE signals_fts MATCH 'keywords' ORDER BY rank LIMIT 10"
```

3. **Use structured SQL** for filtering by type, date range, etc.:

```bash
sqlite3 -json .engram/index.db "SELECT id, type, title, date, content FROM signals WHERE type = 'decision' ORDER BY date DESC LIMIT 10"
```

4. **Combine** if needed — search first, then get full content

### Direct SQL Query

If `$ARGUMENTS` starts with `SELECT`, pass directly:

```bash
sqlite3 -json .engram/index.db "$ARGUMENTS"
```

## Common Patterns

```sql
-- Recent decisions
SELECT id, title, date, content FROM signals WHERE type='decision' ORDER BY date DESC LIMIT 10

-- Open issues
SELECT id, title, date, content FROM signals WHERE type='issue' ORDER BY date DESC

-- Search by keyword (FTS)
SELECT s.id, s.type, s.title, s.date FROM signals_fts fts JOIN signals s ON s.id = fts.rowid WHERE signals_fts MATCH 'keyword' ORDER BY rank LIMIT 10

-- Signals from a date range
SELECT id, type, title, date FROM signals WHERE date BETWEEN '2026-01-01' AND '2026-01-31' ORDER BY date

-- Counts by type
SELECT type, COUNT(*) as count FROM signals GROUP BY type ORDER BY count DESC

-- All recent signals
SELECT id, type, title, date FROM signals ORDER BY date DESC LIMIT 20

-- Public signals only (excludes private)
SELECT id, type, title, date FROM signals WHERE private=0 ORDER BY date DESC LIMIT 20

-- Private signals only
SELECT id, type, title, date FROM signals WHERE private=1 ORDER BY date DESC LIMIT 20
```

## Schema Reference

```
signals: id, type, title, content, tags (JSON array), source, date, file, private, created_at
meta: key, value
```

Types: `decision`, `finding`, `issue`
Privacy: `private=0` (public, git-tracked), `private=1` (private, git-ignored)

## If index.db is missing

Rebuild it first:

```bash
source ${CLAUDE_PLUGIN_ROOT}/lib.sh && engram_reindex .engram
```

## Output

- Parse the JSON array returned by sqlite3
- Present results in a readable format
- Highlight the most relevant results
- If no results, suggest broadening the search
- Only SELECT queries — never modify the index
- Note: query results ARE visible to the LLM (user-initiated, acceptable)
