# Team Decisions

## Affects
- [stale-path-all-decisions](.claude/decisions/stale-path-all-decisions.md) — Stale affects-path warnings fire for all decision writes, not just new ones

## Architecture
- [append-only-decisions](.claude/decisions/append-only-decisions.md) — Append-only is enforced by git, not file conventions. Edit in place, delete when obsolete, git log preserves history.
- [bash-dispatch-fast-paths](.claude/decisions/bash-dispatch-fast-paths.md) — dispatch.sh avoids spawning Python for no-op hook events via fast-paths
- [dispatch-errors-never-break-claude](.claude/decisions/dispatch-errors-never-break-claude.md) — dispatch.sh traps ERR and exits 0 — plugin errors must never break Claude Code
- [fts5-search-pipeline](.claude/decisions/fts5-search-pipeline.md) — Search uses FTS5 with BM25 ranking, falling back to weighted keyword matching
- [git-is-the-history-layer](.claude/decisions/git-is-the-history-layer.md) — Edit decisions in place, delete when obsolete. Git tracks the full evolution — no supersedes/withdrawn ceremony needed.
- [markdown-source-of-truth](.claude/decisions/markdown-source-of-truth.md) — Markdown files are the source of truth — FTS5 index is derived and disposable
- [no-capture-confirmation](.claude/decisions/no-capture-confirmation.md) — Agents write decisions automatically without confirmation prompts — /decision undo is the safety net
- [policy-evaluation-order](.claude/decisions/policy-evaluation-order.md) — Policies evaluate BLOCK → LIFECYCLE → CONTEXT → NUDGE with fail-fast on block/reject
- [pure-methods-on-store](.claude/decisions/pure-methods-on-store.md) — No side effects at import time on DecisionStore
- [session-state-in-tmp](.claude/decisions/session-state-in-tmp.md) — Per-session state in /tmp with atomic O_CREAT|O_EXCL marker files for once-per-session policies
- [single-skill-entry-point](.claude/decisions/single-skill-entry-point.md) — One /decision skill handles capture, search, and manage via intent detection
- [skill-hook-cli-boundary](.claude/decisions/skill-hook-cli-boundary.md) — Skill = intent + behavior guidance, hooks = correctness enforcement, CLI = data access + computation
- [stdlib-only-in-src](.claude/decisions/stdlib-only-in-src.md) — Zero external dependencies in src/ — stdlib-only Python 3.11+
- [team-first-decisions](.claude/decisions/team-first-decisions.md) — Decisions write to .claude/decisions/ in repo by default. Memory is fallback for non-repo contexts only.

## Hooks
- [capture-nudge-corroboration-requirement](.claude/decisions/capture-nudge-corroboration-requirement.md) — Capture-nudge requires trigger phrase + technical signal (or 2+ phrases) to reduce false positives

## Plugin Architecture
- [query-preseed-hook-for-skill](.claude/decisions/query-preseed-hook-for-skill.md) — UserPromptSubmit hook pre-seeds Python query results before the query skill runs Glob/Grep
- [stop-hook-nudge-for-decision-capture](.claude/decisions/stop-hook-nudge-for-decision-capture.md) — Stop hook nudges agent to capture decisions before session ends
- [tag-summary-over-per-decision-listing](.claude/decisions/tag-summary-over-per-decision-listing.md) — Session-context injects tag counts and query hint instead of listing individual decisions

## Search
- [incremental-sync-over-full-rebuild](.claude/decisions/incremental-sync-over-full-rebuild.md) — FTS5 index uses incremental sync with per-file mtime instead of full rebuild on every change
- [search-skill-prefer-preseeded](.claude/decisions/search-skill-prefer-preseeded.md) — Search skill presents pre-seeded hook results first, falls back to Glob/Grep only if needed

## Skills
- [merge-tags-stats-into-list](.claude/decisions/merge-tags-stats-into-list.md) — Consolidated /decision:tags and /decision:stats into /decision:list as --tags and --stats flags

## Superpowers
- [superpowers-design-first](.claude/decisions/superpowers-design-first.md) — Always brainstorm and validate design before writing any code
- [superpowers-detailed-plans](.claude/decisions/superpowers-detailed-plans.md) — Implementation plans must be complete with zero placeholders
- [superpowers-git-worktrees](.claude/decisions/superpowers-git-worktrees.md) — Use git worktrees for feature branch isolation with verified baselines
- [superpowers-spec-before-quality](.claude/decisions/superpowers-spec-before-quality.md) — Review spec compliance before code quality — wrong code polished is waste
- [superpowers-subagent-development](.claude/decisions/superpowers-subagent-development.md) — Fresh subagent per task with two-stage review (spec then quality)
- [superpowers-systematic-debugging](.claude/decisions/superpowers-systematic-debugging.md) — Root cause investigation before any fixes — no random changes
- [superpowers-tdd](.claude/decisions/superpowers-tdd.md) — No production code without a failing test first (RED-GREEN-REFACTOR)
- [superpowers-verify-before-complete](.claude/decisions/superpowers-verify-before-complete.md) — No completion claims without fresh verification evidence

## Versioning
- [semver-versioning](.claude/decisions/semver-versioning.md) — Use semantic versioning (semver) for all releases
