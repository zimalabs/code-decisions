# CLAUDE.md

## What This Is

Claude Code plugin that gives agents persistent decision memory. Signals (decisions, findings, issues) are git-tracked markdown files in `.engram/`. A derived SQLite index provides FTS5 search. No CLI — hooks handle everything automatically.

## Commands

```sh
make check    # shellcheck + tests (run before every push)
make lint     # shellcheck only
make test     # test suite only
```

## File Layout

```
.claude-plugin/
  marketplace.json        # Marketplace manifest (points to plugins/engram)
plugins/engram/
  .claude-plugin/
    plugin.json           # Plugin manifest
  lib.sh                  # Core library — all functions live here
  schema.sql              # SQLite schema (signals table + FTS5 + triggers)
  hooks/
    session-start.sh      # Ingest, reindex, brief, inject context
    session-end.sh        # Ingest, reindex, brief (no injection)
    hooks.json            # Hook registration (SessionStart + SessionEnd)
  skills/
    capture/SKILL.md      # Write signal files via Write tool
    query/SKILL.md        # SQL queries against index.db
  tests/
    test_engram.sh        # 31 test groups
    run_tests.sh          # Test runner wrapper
```

## Key Concepts

- **Signals** = markdown files in `.engram/signals/` (prefixed by type: `decision-`, `finding-`, `issue-`)
- **Private signals** = same format, in `.engram/_private/` (git-ignored, excluded from brief)
- **index.db** = derived SQLite database, rebuilt from files every session. Safe to delete.
- **brief.md** = generated summary injected into agent context. Public signals only.

## How the Index Stays Fresh

No background jobs. Hooks run the full pipeline at session start and end:

```
engram_ingest_commits → engram_ingest_plans → engram_reindex → engram_brief
```

`engram_reindex()` does a destructive rebuild — drops `index.db`, recreates from `schema.sql`, re-indexes every `.md` file. The `meta` table (ingestion cursors) is preserved across rebuilds.

## Architecture Rules

1. **Markdown is source of truth.** `index.db` is derived. Never store data only in SQLite.
2. **Append-only signals.** Don't delete or overwrite signal files. Write new ones.
3. **Directory = privacy.** `_private/` path means git-ignored + excluded from brief. No config flags.
4. **No CLI.** Capture via Write tool, query via `@engram:query` skill, everything else via hooks.
5. **Pure functions in lib.sh.** No side effects at source time. Every function takes `dir` as first arg.

## Schema

```sql
signals: id, type, title, content, tags, source, date, file, private, excerpt, status, supersedes, file_stem, created_at
signals_fts: FTS5 virtual table (title, content, tags) synced via triggers
links: source_file, target_file, rel_type  (signal-to-signal relationships)
meta: key, value  (stores ingestion cursors like last_commit)
```

Types: `decision`, `finding`, `issue`
Privacy: `private=0` (public), `private=1` (private)
Status: `''` (default/open), `'resolved'`
Link rel_types: `supersedes`, `related`, `blocks`, `blocked-by`

## Adding a New Function

1. Add the function to `plugins/engram/lib.sh`
2. Add tests to `plugins/engram/tests/test_engram.sh`
3. Wire into hooks if it should run at session start/end
4. Run `make check`

## Testing

Tests use temp directories and real SQLite — no mocks. Each test function creates its own `.engram/` in `$TEST_DIR`. Git-related tests create throwaway repos via `_create_test_repo()`.

Test helpers: `assert_eq`, `assert_contains`, `assert_not_contains`, `assert_file_exists`, `assert_dir_exists`, `assert_file_count`.

## Dogfooding: Record Your Decisions

This project is a decision memory system — use it. **Before committing any significant change**, write a signal file to `.engram/signals/`:

```
.engram/signals/decision-{slug}.md
```

With frontmatter:

```markdown
---
type: decision
date: YYYY-MM-DD
tags: [relevant, tags]
---

Body explaining what was decided and why.
```

What counts as significant: architecture changes, new features, refactors, dependency changes, non-trivial bug fixes. Routine typo fixes or formatting do not need signals.

## Conventions

- Table/FTS names: `signals`, `signals_fts` (not `notes`)
- SQL escaping: use `sed "s/'/''/g"`, not bash string replacement
- Frontmatter parsing: manual line-by-line (no YAML parser dependency)
- Hook timeout: 15 seconds (set in `hooks.json`)
- Filenames: `{type}-{slug}.md`, slug via `_slugify()`
