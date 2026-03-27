---
name: "incremental-sync-over-full-rebuild"
description: "FTS5 index uses incremental sync with per-file mtime instead of full rebuild on every change"
date: "2026-03-19"
tags:
  - "search"
  - "performance"
  - "plugin-architecture"
affects:
  - "src/decision/store/index.py"
---

# Incremental sync with per-file mtime over full rebuild for FTS5 index

The FTS5 index originally did a full drop-and-rebuild whenever any decision file was newer than the db. This doesn't scale past ~100 decisions and silently keeps ghost entries for deleted files.

## Alternatives

- **Full rebuild on every change** — simple but O(n) on every query when any file is modified. Doesn't detect deleted files at all — ghost rows persist in the index until an unrelated file triggers a rebuild. This was the original implementation.
- **Directory mtime shortcut** — check if the memory directory's own mtime changed before scanning files. Reduces stat calls when nothing changed, but doesn't solve the delete problem on its own. Could be layered on later as an optimization.
- **File watcher (inotify/fsevents)** — real-time sync without polling. Too complex for a plugin that runs in short-lived hook processes — no long-running daemon to host the watcher.

## Rationale

Incremental sync compares slugs on disk vs slugs in the `decisions` table and per-file mtime vs stored mtime. Only changed files get re-parsed and upserted. Deleted files get `DELETE FROM decisions` which fires the FTS5 delete trigger. This is O(n) on the glob but O(1) on parse/insert for unchanged files — the expensive part (file I/O + parsing) only runs for diffs. The `mtime` column in the decisions table makes staleness detection per-file instead of whole-index.

## Trade-offs

Added complexity: the `_sync()` method is ~25 lines of diff logic vs the old 3-line mtime check. FTS5 now needs UPDATE and DELETE triggers in addition to the INSERT trigger. The schema migration is handled by deleting the old db on first run (no migration needed since the index is derived). If mtime resolution is coarser than edit speed (sub-second edits on some filesystems), a modification could be missed until the next sync — acceptable for a plugin where decisions are written minutes apart.
