# Good First Issues

Reference for creating GitHub issues. Each is scoped to 30-60 minutes.

---

## 1. Add signal count to session-start output

**Labels:** good first issue, enhancement

Currently the session-start hook silently ingests signals. Add a one-line summary to stderr showing how many signals were indexed.

**Where:** `hooks/session-start.sh` — after `engram_brief`, add an echo like:
`echo "engram: 12 signals indexed (8 decisions, 2 findings, 2 issues)" >&2`

Count query: `SELECT type, COUNT(*) FROM signals WHERE private=0 GROUP BY type`

---

## 2. Validate frontmatter dates

**Labels:** good first issue, bug

Signals with malformed dates (e.g., `date: tomorrow`) are indexed with invalid date values. Add a `_validate_date()` function to `lib.sh` that checks `YYYY-MM-DD` format.

**Where:** `lib.sh` — add validation in `engram_index_file()` before the INSERT.

**Test:** Add a test in `tests/test_engram.sh` that indexes a file with an invalid date and verifies it's either rejected or defaults to today.

---

## 3. Add `engram_stats` function

**Labels:** good first issue, enhancement

Add a function that returns signal counts by type and month. Useful for understanding decision velocity.

```sql
SELECT type, strftime('%Y-%m', date) as month, COUNT(*)
FROM signals GROUP BY type, month ORDER BY month DESC;
```

**Where:** `lib.sh` — new function `engram_stats()`. Add tests.

---

## 4. Support `resolved` field in issue signals

**Labels:** good first issue, enhancement

Issue signals don't currently have a way to mark resolution. Add an optional `resolved: true` frontmatter field.

**Where:**
- `lib.sh` — parse `resolved` in frontmatter, add to INSERT
- `schema.sql` — add `resolved INTEGER DEFAULT 0` column
- `tests/test_engram.sh` — test resolved parsing

---

## 5. Brief shows signal age

**Labels:** good first issue, enhancement

The brief currently lists signal titles. Add relative age (e.g., "2d ago", "3w ago") next to each signal in `brief.md`.

**Where:** `lib.sh` in `engram_brief()` — calculate days between signal date and today using `date` command.

---

## 6. Warn on duplicate signal titles

**Labels:** good first issue, enhancement

If two signal files have the same title, the agent likely created a duplicate decision. Add a warning during `engram_reindex()`.

**Where:** `lib.sh` — after indexing, query for `SELECT title, COUNT(*) FROM signals GROUP BY title HAVING COUNT(*) > 1` and print warnings.

---

## 7. Support `supersedes` field

**Labels:** good first issue, enhancement

When a decision replaces an earlier one, allow `supersedes: 2026-03-10-use-memcached.md` in frontmatter. The brief should show only the latest decision.

**Where:** `lib.sh` + `schema.sql` — new column, parse in frontmatter, filter in brief generation.

---

## 8. Add `make fmt` target for consistent formatting

**Labels:** good first issue, tooling

Add a `make fmt` target that runs `shfmt` on all shell files for consistent formatting.

**Where:** `Makefile` — add `fmt` target. Document in CONTRIBUTING.md.
