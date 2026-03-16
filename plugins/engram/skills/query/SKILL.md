---
name: engram:query
description: "Query past decisions from the engram index. Runs SQL against .engram/index.db via Bash. Use to look up context before starting work."
---

# @engram:query

Query the engram index for past decisions.

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

3. **Use structured SQL** for filtering by date range, tags, etc.:

```bash
sqlite3 -json .engram/index.db "SELECT id, title, date, content FROM signals ORDER BY date DESC LIMIT 10"
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
SELECT id, title, date, excerpt FROM signals ORDER BY date DESC LIMIT 10

-- Search by keyword (FTS)
SELECT s.id, s.title, s.date FROM signals_fts fts JOIN signals s ON s.id = fts.rowid WHERE signals_fts MATCH 'keyword' ORDER BY rank LIMIT 10

-- Decisions from a date range
SELECT id, title, date FROM signals WHERE date BETWEEN '2026-01-01' AND '2026-01-31' ORDER BY date

-- Total decision count
SELECT COUNT(*) as count FROM signals

-- Public decisions only (excludes private)
SELECT id, title, date FROM signals WHERE private=0 ORDER BY date DESC LIMIT 20

-- Private decisions only
SELECT id, title, date FROM signals WHERE private=1 ORDER BY date DESC LIMIT 20
```

## Link-Aware Patterns

```sql
-- What superseded a decision?
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

-- All decisions linked to X (via links table)
SELECT DISTINCT s.file_stem, s.title, l.rel_type
FROM links l JOIN signals s
ON s.file_stem = l.source_file OR s.file_stem = l.target_file
WHERE (l.source_file = 'decision-x' OR l.target_file = 'decision-x')
AND s.file_stem != 'decision-x'
```

## Schema Reference

SQL tables:

```
signals: id, type, title, content, tags (JSON array), source, date, file, private,
         excerpt, supersedes, file_stem, created_at
links: source_file, target_file, rel_type
meta: key, value
```

Type: `decision`
Privacy: `private=0` (public, git-tracked), `private=1` (private, git-ignored)
Link rel_types: `supersedes`, `related`, `blocks`, `blocked-by`

For signal file schema (frontmatter fields, body sections, link types), see `${CLAUDE_PLUGIN_ROOT}/schemas/`.

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
