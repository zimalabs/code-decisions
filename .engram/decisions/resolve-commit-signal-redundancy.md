+++
date = 2026-03-16
tags = ["dedup", "ingest", "hooks"]
links = ["related:git-opt-in", "related:enforce-decision-structure-with-mandatory-why"]
+++

# Resolve commit message vs decision signal redundancy

Manual signals are the primary record (the "why"). Auto-ingest is a safety net for uncaptured decisions.

When `engram_ingest_commits()` generates a slug from a commit subject and finds an existing `decision-{slug}.md` in either `signals/` or `_private/`, it now skips (continues) instead of creating a hash-suffixed duplicate. The `source: git:<hash>` dedup also checks `_private/`.

Considered adding a `commit: <hash>` frontmatter field but rejected it — slug matching handles >95% of cases with zero workflow friction, and the signal is written before the commit hash exists.

## Rationale

Duplicate signals dilute the brief and waste context tokens. Manual signals carry the "why" that auto-ingested commit messages lack, so they should always win. Slug-based dedup is simple and covers the common case without requiring any workflow changes.

## Alternatives

- Hash-suffixed duplicates (status quo) — clutters the signal directory, confusing
- `commit: <hash>` frontmatter linking — requires knowing the hash before commit, breaks the write-then-commit flow
- Disable auto-ingest entirely — loses the safety net for uncaptured decisions
