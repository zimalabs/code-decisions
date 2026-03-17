+++
date = 2026-03-17
tags = ["architecture", "config", "git"]
links = ["related:resolve-commit-signal-redundancy"]
+++

# Make git integration opt-in via .engram/config

Engram's identity was coupled to git — .gitignore creation, commit ingestion, and uncommitted signal reporting were all on by default. This made engram less accessible to users who don't use git or don't want signals in version control.

## What changed

- New `_git_tracking_enabled()` function reads `.engram/config` for `git_tracking=true`
- `engram_init()` only creates/manages `.gitignore` when git tracking is enabled
- `engram_ingest_commits()` and `engram_uncommitted_summary()` are no-ops without the config
- Migration: existing `.gitignore` without config auto-creates `config` with `git_tracking=true` (zero breakage for existing users)
- Documentation repositioned around structured decision memory, not git

## Alternatives

- Environment variable — less discoverable, doesn't persist
- Auto-detect git repo — still couples identity to git, confusing for users who have git but don't want tracking
- Config in plugin.json — not per-project

## Rationale

The real value is structured decision memory with auto-capture, search, and evolution tracking. Git is a power feature, not the core identity. Making it opt-in broadens the audience and simplifies the default experience.

## Trade-offs

Existing users need migration (handled automatically). New users who want git tracking need one extra step (`echo 'git_tracking=true' > .engram/config`).
