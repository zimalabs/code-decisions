[![CI](https://github.com/zimalabs/engram/actions/workflows/ci.yml/badge.svg)](https://github.com/zimalabs/engram/actions/workflows/ci.yml)

# engram

**Structured decision memory for AI agents.** Decisions are markdown files — auto-captured, full-text searchable, and injected into every session.

## What it does

- **Records decisions as markdown files** — the "why" behind code changes, not just the "what"
- **Auto-captures from git commits** — brownfield bootstrap from your existing history
- **Full-text search via SQLite FTS5** — query past decisions in natural language or raw SQL
- **Context injection** — relevant decisions surface automatically via session hooks

## Install

```sh
claude plugin install zimalabs/engram
```

No `engram init`. No configuration. Just install and go.

### Local development

```sh
claude plugin marketplace add ./. --scope project
claude plugin install engram@zimalabs --scope project
```

> **Requires:** SQLite 3.35+ with FTS5 (ships with macOS 10.14+, most Linux distros).

## Quick example

Write a decision — just a markdown file:

```markdown
# .engram/decisions/use-redis-for-caching.md
+++
date = 2026-03-14
tags = ["infrastructure", "caching"]
+++

Redis supports pub/sub which we'll need for the notification system.
Memcached is faster for simple k/v but doesn't support pub/sub.
```

Query it later:

```
@engram:query what decisions about caching?
```

Decisions show up in PRs alongside the code they describe.

## Skills

| Skill | Purpose |
|---|---|
| `@engram:capture` | Guided decision creation with schema validation |
| `@engram:query` | Query past decisions (natural language or SQL) |
| `@engram:resync` | Full sync: ingest, reindex, regenerate brief |
| `@engram:brief` | Regenerate the context brief on demand |
| `@engram:backfill` | Autonomously enrich incomplete decisions |
| `@engram:introspect` | Interactive gap-filling for existing decisions |
| `@engram:policies` | List active policies and their levels |

## Links

- [Full documentation](plugins/engram/README.md) — decisions, linking, querying, policy engine, git integration, architecture
- [Contributing](CONTRIBUTING.md)

## License

MIT
