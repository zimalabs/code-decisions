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
SELECT id, title, date, excerpt FROM signals WHERE type='decision' ORDER BY date DESC LIMIT 10

-- Open issues
SELECT id, title, date, excerpt FROM signals WHERE type='issue' AND status != 'resolved' ORDER BY date DESC

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

## Link-Aware Patterns

```sql
-- What superseded a signal?
SELECT file_stem, title, date FROM signals WHERE supersedes = 'decision-old-slug'

-- Full supersession chain (walk backwards from current)
WITH RECURSIVE chain(stem, depth) AS (
  SELECT file_stem, 0 FROM signals WHERE file_stem = 'decision-current'
  UNION ALL
  SELECT s.supersedes, c.depth + 1
  FROM chain c JOIN signals s ON s.file_stem = c.stem
  WHERE s.supersedes != ''
)
SELECT s.title, s.date, c.depth FROM chain c
JOIN signals s ON s.file_stem = c.stem ORDER BY c.depth

-- All signals linked to X (via links table)
SELECT DISTINCT s.file_stem, s.title, s.type, l.rel_type
FROM links l JOIN signals s
ON s.file_stem = l.source_file OR s.file_stem = l.target_file
WHERE (l.source_file = 'decision-x' OR l.target_file = 'decision-x')
AND s.file_stem != 'decision-x'

-- Open issues with blockers
SELECT s.title, l.target_file as blocks
FROM signals s LEFT JOIN links l ON l.source_file = s.file_stem AND l.rel_type = 'blocks'
WHERE s.type='issue' AND s.status != 'resolved'

-- Resolved issues
SELECT file_stem, title, date FROM signals WHERE type='issue' AND status = 'resolved'
```

## Schema Reference

SQL tables:

```
signals: id, type, title, content, tags (JSON array), source, date, file, private,
         excerpt, status, supersedes, file_stem, created_at
links: source_file, target_file, rel_type
meta: key, value
```

Types: `decision`, `finding`, `issue`
Privacy: `private=0` (public, git-tracked), `private=1` (private, git-ignored)
Status: `''` (default/open), `'resolved'`
Link rel_types: `supersedes`, `related`, `blocks`, `blocked-by`

For signal file schemas (frontmatter fields, body sections, link types), see `${CLAUDE_PLUGIN_ROOT}/schemas/`.

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
