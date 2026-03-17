# CLAUDE.md

## What This Is

Claude Code plugin that gives agents persistent decision memory. Decisions are markdown files in `.engram/`. A derived SQLite index provides FTS5 search. No CLI — hooks handle everything automatically. Git integration is opt-in via `.engram/config`.

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
  engram/                 # Core library package
    __init__.py           # ENGRAM_LIB_DIR, ENGRAM_SCHEMA_FILE, re-exports
    __main__.py           # CLI dispatch (python3 -m engram)
    _constants.py         # Regex patterns, NOISE_WORDS, StrPath alias
    _helpers.py           # _connect, _check_fts5, _slugify, _slug, etc.
    _frontmatter.py       # _FM_FIELDS, _split_frontmatter
    _commits.py           # _is_decision_commit, engram_path_to_keywords
    _validate.py          # _validate_content_stdin
    _policy_defs.py       # 15 policy definitions (ALL_POLICIES)
    policy.py             # PolicyEngine, Policy, PolicyLevel, PolicyResult, SessionState
    signal.py             # Signal dataclass
    store.py              # EngramStore class
  schema.sql              # SQLite schema (signals table + FTS5 + triggers)
  schemas/
    README.md             # Schema overview + shared field/link type reference
    decision.md           # Decision signal schema (source of truth)
  hooks/
    dispatch.sh           # Thin dispatcher — pipes stdin to policy engine
    hooks.json            # Hook registration (all events → dispatch.sh)
  skills/
    capture/SKILL.md      # Write signal files via Write tool (reads schemas/)
    query/SKILL.md        # SQL queries against index.db
    resync/SKILL.md       # Full sync: ingest + reindex + brief
    policies/SKILL.md     # List active policies with levels and events
  tests/
    test_engram.py        # Test suite — store, signals, hooks (Python)
    test_policy.py        # Test suite — policy engine + all 15 policies
    run_tests.sh          # Test runner wrapper (legacy)
```

## Key Concepts

- **Signals** = decision markdown files in `.engram/decisions/`
- **Private signals** = same format, in `.engram/_private/decisions/` (excluded from brief and context)
- **index.db** = derived SQLite database, rebuilt from files every session. Safe to delete.
- **brief.md** = generated summary injected into agent context. Public signals only.

## How the Index Stays Fresh

No background jobs. Hooks call `EngramStore.resync()` at session start and end, which runs the full pipeline:

```
resync → ingest_commits → ingest_plans → reindex → brief
```

`reindex()` does a destructive rebuild — drops `index.db`, recreates from `schema.sql`, re-indexes every `.md` file. The `meta` table (ingestion cursors) is preserved across rebuilds. Use `@engram:resync` to trigger this manually.

## Architecture Rules

1. **Markdown is source of truth.** `index.db` is derived. Never store data only in SQLite.
2. **Append-only signals.** Don't delete or overwrite signal files. Write new ones.
3. **Directory = privacy.** `_private/` path means excluded from brief and context injection. No config flags.
4. **No CLI.** Capture via Write tool, query via `@engram:query` skill, everything else via hooks.
5. **Pure methods on EngramStore.** No side effects at import time. Store methods operate on `self.root`; module-level helpers are pure functions.

## Schema

```sql
signals: id, type, title, content, tags, source, date, file, private, excerpt, slug, status
signals_fts: FTS5 virtual table (title, content, tags) synced via triggers
links: source_file, target_file, rel_type  (decision-to-decision relationships)
meta: key, value  (stores ingestion cursors like last_commit)
```

Type: `decision`
Privacy: `private=0` (public), `private=1` (private)
Status: `active` (default), `withdrawn`, `invalid`
Link rel_types: `supersedes`, `related`

## Adding a New Function

1. Add the function to the appropriate module in `plugins/engram/engram/`
2. Add tests to `plugins/engram/tests/test_engram.py`
3. Wire into hooks via a new policy in `_policy_defs.py` if it should run at session events
4. Run `make check`

## Adding a New Policy

1. Write a condition function in `plugins/engram/engram/_policy_defs.py`
2. Add a `Policy(...)` instance to `ALL_POLICIES` with name, level, events, matchers
3. Add tests to `plugins/engram/tests/test_policy.py`
4. Run `make check` — no hooks.json changes needed (dispatch.sh routes all events)

## Testing

Tests use temp directories and real SQLite — no mocks, no pytest. Each test function creates its own `.engram/` in a temp dir. Git-related tests create throwaway repos via `_create_test_repo()`.

Test helpers: `assert_eq`, `assert_contains`, `assert_not_contains`, `assert_file_exists`, `assert_dir_exists`, `assert_file_count`.

## Dogfooding: Record Your Decisions

This project is a decision memory system — use it. **Before committing any significant change**, write a signal file to `.engram/decisions/`:

```
.engram/decisions/{slug}.md
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

**Commit messages** describe *what* changed. **Decision signals** describe *why* the choice was made, alternatives considered, and trade-offs. Auto-ingest catches decisions that weren't manually recorded — if you write a signal with the same slug as the commit subject, auto-ingest will skip it.

## Conventions

- Table/FTS names: `signals`, `signals_fts` (not `notes`)
- SQL: parameterized queries (`?` placeholders), never string interpolation
- Frontmatter parsing: manual line-by-line via `Signal.from_text()` (no YAML parser dependency)
- Hook timeout: 15 seconds (set in `hooks.json`)
- Filenames: `{slug}.md`, slug via `_slugify()`
- Stdlib only: no PyYAML, no pytest, no external dependencies
