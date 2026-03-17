# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-03-14

### Added
- Markdown signal files as source of truth (git-tracked, reviewable in PRs)
- 3 signal types with defined schemas: decision, finding, issue
- Private signals tier — `.engram/private/` directory (git-ignored, excluded from brief, never auto-sent to API)
- Auto-capture from git commits (brownfield bootstrap: last 50 commits)
- Auto-capture from Claude plan files with `## Context` sections
- Incremental ingestion (session-start catches commits from any source)
- `lib.sh` core library (sourced by hooks and tests)
- `brief.md` generated from index as decision context summary
- `file` column in index for source traceability
- `private` column in index for privacy tier
- `meta` table for tracking ingestion cursors
- 21 test groups covering all features including private signals

### Changed
- SQLite is now a derived index (git-ignored), not the source of truth
- Reduced from 5 note types to 3 signal types
- Renamed "notes" to "signals" throughout
- Hooks auto-init on first session (no manual `engram init`)
- Capture via Write tool (write markdown files directly)
- Query via `/engram:query` skill (SQL against index.db)
- Hook timeout increased to 15s for brownfield ingestion

### Removed
- `engram.sh` CLI (replaced by hooks + Write tool + skills)
- AES-256 encryption (signals have same sensitivity as commit messages)
- OS keychain integration
- `entities` and `brief` tables (replaced by markdown files)
- `learning` and `observation` note types

## [0.1.0] - 2026-03-13

### Added
- Initial release: 3 tables (notes, entities, brief) with FTS5 full-text search
- CLI with 6 commands: init, capture, query, search, brief, status
- AES-256-CBC encryption with OS keychain key storage
- SessionStart hook injects living brief + behavioral instructions
- SessionEnd hook auto-regenerates brief when new notes exist
- Capture skill for structured note-taking
- Query skill for natural language and SQL retrieval
- Bash test suite with 9 test groups
