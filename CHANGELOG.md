# Changelog

All notable changes to this project will be documented in this file.

## 1.1.1 — 2026-04-06

### Fixes
- CLI now accepts `--tags`, `--stats`, `--coverage`, `--health`, and `--help` flag aliases alongside subcommands
- Updated Python requirement from 3.11+ to 3.9+ for broader compatibility

## 1.1.0 — 2026-03-27

### Features
- Auto-capture detects decision language and writes `.claude/decisions/` files without prompting
- Rules index (`.claude/rules/decisions.md`) auto-regenerates on capture
- Search skill prefers Grep/Read over CLI to avoid permission prompts

## 1.0.0 — 2026-03-27

First stable release.

### Core
- Decision capture, search, and management via single `/decision` command
- Decisions are markdown files with YAML frontmatter, stored at `.claude/decisions/` in the repo
- **Proximity triggering** — the `affects` field maps decisions to files; editing those files auto-injects the decision into Claude's context
- SQLite FTS5 index with BM25 ranking, incremental sync, and keyword fallback
- Shared via git — committed to the repo, inherited by every team member's Claude

### Policy Engine
- 10 policies across 4 levels: BLOCK, LIFECYCLE, CONTEXT, NUDGE
- 5 hook events: SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop
- Bash fast-paths skip Python for common no-op events (<10ms hook latency)
- Advise-only — nudges coach, never block

### Key Policies
- **Proximity-triggered context** — decisions auto-surface when editing affected files
- **Capture nudge** — detects decision language ("we chose X because Y") and suggests capture
- **Edit checkpoint** — periodic nudge during long editing sessions (auto-dismisses)
- **Stop nudge** — end-of-session reminder for uncaptured decisions
- **Content validation** — structural checks on decision writes

### Developer Experience
- Zero external dependencies (stdlib only, Python 3.11+)
- 600+ tests, 90% coverage threshold, mypy strict, ruff, shellcheck
- `make dev` for one-command local development setup
- Centralized version with `scripts/bump-version.sh`
