# Changelog

All notable changes to this project will be documented in this file.

## 1.4.0 — 2026-04-21

### Removed
- **Superpowers autoseeding** — the SessionStart hook no longer creates 8 `superpowers-*.md` decision files when the Superpowers plugin is detected. Manufactured decisions conflict with the zero-config, user-authored philosophy. Spec/plan extraction from `docs/superpowers/` files is unchanged.

## 1.3.0 — 2026-04-13

### Features
- **Superpowers integration** — auto-detects the [Superpowers](https://github.com/obra/superpowers) plugin and seeds 8 methodology decisions (TDD, design-first, systematic debugging, subagent-driven development, git worktrees, verification-before-completion, detailed plans, spec-before-quality)
- **Decision extraction from specs/plans** — scans Superpowers spec and plan files (`docs/superpowers/specs/`, `docs/superpowers/plans/`) for trade-offs and approach choices, nudges the agent to capture them as decisions on first implementation edit
- General `SeedRegistry` pattern for plugin-aware decision seeding, extensible to other plugins

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
