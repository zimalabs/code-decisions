+++
date = 2026-03-17
tags = ["dx", "signals", "cleanup"]
links = ["related:standardize-skill-prefix-to-slash"]
+++

# Enrich decision signals, add make dev target, fix backfill link format

Three changes in one session: (1) backfill and introspect all 34 decision signals — added tags to 7, rationale/alternatives to 13, and cross-reference links to 10+; (2) added `make dev` target that symlinks the plugin cache to source for instant local iteration; (3) fixed backfill SKILL.md to document the `"rel:slug"` link format and use the correct `slug` column name instead of `file_stem`.

## Rationale

Auto-ingested commit signals were bare — just diffstats and no metadata. Enriching them makes the decision graph navigable and the brief more useful. The `make dev` symlink eliminates the remove-reinstall cycle during plugin development. The backfill skill was generating TOML inline table syntax for links (`{target = "...", rel = "..."}`) instead of the string format (`"related:slug"`) that the parser expects.

## Alternatives

- Leave auto-ingested signals bare — loses the "why" context that makes decisions queryable
- Manual cache management instead of `make dev` — error-prone and version-dependent
- Fix backfill skill only in docs, not in code — agents would keep generating wrong format
