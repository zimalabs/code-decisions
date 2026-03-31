---
name: decision
description: "Single entry point for all decision operations: capture, search, manage. Routes based on natural language intent."
---

# /decision

Parse `$ARGUMENTS` to determine intent and route to the appropriate action.

## CLI Usage

The SessionStart hook injects a `Decision CLI: ...` line into conversation context with the correct `PYTHONPATH` prefix. **Always use that exact prefix** when running CLI commands. For brevity, this document writes `python3 -m decision <command>` — prepend the injected `PYTHONPATH="..."` when executing.

## Intent Detection

**Explicit subcommands take priority** — `/decision search <query>` and `/decision capture <statement>` bypass intent detection entirely.

**Search** (default): questions, keywords, lookups, `--tags`, `--stats`, `--coverage`, or anything ambiguous.
**Capture**: declarative statement with both a **choice** and a **reason** ("chose X because Y", "going with X instead of Y"). Without a reason, prefer search — the user may be looking up an existing decision.
**Manage**: admin verbs — edit, undo, dismiss, debug, review, enrich, tree, tour, history, help.
**No arguments**: show brief status with `python3 -m decision stats --json` and suggest quick actions.

## Search

1. **Check pre-seeded results first** — a hook runs FTS5 search automatically when `/decision <keywords>` is invoked. If results exist in conversation context, present them directly.
2. **If pre-seeded results are empty or insufficient**: use `Grep` to search `.claude/decisions/` files for keywords, then `Read` matching files to present results. This avoids permission prompts. Only fall back to `python3 -m decision search <keywords>` via CLI if native tools fail.
3. **Flags**: `--tags` → `python3 -m decision tags`, `--stats` → `python3 -m decision stats`, `--coverage` → `python3 -m decision coverage`

## Capture

1. **Search existing decisions first** — if one covers the same topic, edit it in place instead of creating a new file.
2. **Write directly** to `.claude/decisions/{slug}.md` following the decision template (injected at session start). The content-validation hook will reject and guide you if anything is wrong.
3. **Confirm** briefly:

   **Captured:** {title}
   **File:** `.claude/decisions/{slug}.md`
   **Tags:** {tags} | **Affects:** {affects paths}

   To undo: `/decision undo`

   Then continue with whatever the user asked.

## Manage

| Command | Action |
|---------|--------|
| `undo [slug]` | `python3 -m decision undo [slug]` |
| `dismiss` | `python3 -m decision dismiss` |
| `debug` | `python3 -m decision policy --trace` |
| `review` | `python3 -m decision validate`, then read files to check health |
| `enrich <slug>` | `python3 -m decision enrich <slug> --json`, then offer to fix findings |
| `tree` | `python3 -m decision tree` |
| `edit <slug>` | Read `.claude/decisions/{slug}.md`, apply changes, write back |
| `history <slug>` | `git log --follow -p -- .claude/decisions/{slug}.md` |
| `tour` | Walk through: show an example decision, explain affects/auto-surface, demo search, explain auto-capture |
| `help` | Show available commands and quick actions |

## Examples

- `/decision redis` → search
- `/decision search redis` → explicit search
- `/decision why did we choose PostgreSQL?` → search
- `/decision we decided to go with JWT because...` → capture
- `/decision capture use Tailwind over CSS modules` → explicit capture
- `/decision --tags` → browse by topic
- `/decision --stats` → health check
- `/decision edit inline-refund` → manage
- `/decision undo` → manage
- `/decision dismiss` → manage
