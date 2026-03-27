# Team Decisions

## Core Architecture
- [markdown-source-of-truth](.claude/decisions/markdown-source-of-truth.md) — Markdown files are source of truth. FTS5 index is derived — delete it and it rebuilds.
- [append-only-decisions](.claude/decisions/append-only-decisions.md) — Append-only is enforced by git. Edit in place, delete when obsolete, git log preserves history.
- [git-is-the-history-layer](.claude/decisions/git-is-the-history-layer.md) — Edit decisions in place, delete when obsolete. Git tracks evolution — no supersedes/withdrawn needed.
- [stdlib-only-in-src](.claude/decisions/stdlib-only-in-src.md) — Zero external dependencies in src/. Stdlib-only Python 3.11+.
- [pure-methods-on-store](.claude/decisions/pure-methods-on-store.md) — No side effects at import time on DecisionStore.
- [team-first-decisions](.claude/decisions/team-first-decisions.md) — Decisions write to .claude/decisions/ in repo. Memory is fallback for non-repo contexts only.

## Policy Engine
- [policy-evaluation-order](.claude/decisions/policy-evaluation-order.md) — BLOCK → LIFECYCLE → CONTEXT → NUDGE. Block/reject fail-fast. Plugin always forces ok=True (advisory).
- [session-state-in-tmp](.claude/decisions/session-state-in-tmp.md) — Per-session state in /tmp with atomic O_CREAT|O_EXCL marker files.

## Hook Dispatch
- [bash-dispatch-fast-paths](.claude/decisions/bash-dispatch-fast-paths.md) — dispatch.sh avoids spawning Python for no-op events via fast-paths.
- [dispatch-errors-never-break-claude](.claude/decisions/dispatch-errors-never-break-claude.md) — dispatch.sh traps ERR and exits 0. Plugin errors must never break Claude Code.

## Search & Storage
- [fts5-search-pipeline](.claude/decisions/fts5-search-pipeline.md) — FTS5 MATCH with BM25, fallback to weighted keyword matching.
- [incremental-sync-over-full-rebuild](.claude/decisions/incremental-sync-over-full-rebuild.md) — FTS5 index uses incremental sync with per-file mtime, not full rebuild.
- [tag-summary-over-per-decision-listing](.claude/decisions/tag-summary-over-per-decision-listing.md) — Session-context injects tag counts and query hint instead of listing individual decisions.

## Skills & UX
- [single-skill-entry-point](.claude/decisions/single-skill-entry-point.md) — One /decision skill handles capture, search, and manage via intent detection.
- [no-capture-confirmation](.claude/decisions/no-capture-confirmation.md) — Agents write decisions without confirmation. /decision undo is the safety net.
- [merge-tags-stats-into-list](.claude/decisions/merge-tags-stats-into-list.md) — Consolidated /decision:tags and /decision:stats into /decision:list as --tags and --stats flags.
- [search-skill-prefer-preseeded](.claude/decisions/search-skill-prefer-preseeded.md) — Search skill presents pre-seeded hook results first, falls back to Glob/Grep only if needed.

## Nudges
- [capture-nudge-corroboration-requirement](.claude/decisions/capture-nudge-corroboration-requirement.md) — Capture-nudge requires trigger phrase + technical signal (or 2+ phrases) to reduce false positives.
- [query-preseed-hook-for-skill](.claude/decisions/query-preseed-hook-for-skill.md) — UserPromptSubmit hook pre-seeds Python query results before the skill runs Glob/Grep.
- [stop-hook-nudge-for-decision-capture](.claude/decisions/stop-hook-nudge-for-decision-capture.md) — Stop hook nudges agent to capture decisions before session ends.

- [stale-path-all-decisions](.claude/decisions/stale-path-all-decisions.md) — Stale affects-path warnings fire for all decision writes, not just new ones.

