[![CI](https://github.com/zimalabs/engram/actions/workflows/ci.yml/badge.svg)](https://github.com/zimalabs/engram/actions/workflows/ci.yml)

# engram

**Structured decision memory for AI agents.** Decisions are markdown files — auto-captured, full-text searchable, and injected into every session.

## What it does

- **Records decisions as markdown files** — the "why" behind code changes, not just the "what"
- **Auto-captures from git commits** — decision-worthy commits become decisions automatically (opt-in)
- **Full-text search via SQLite FTS5** — query past decisions in natural language or raw SQL
- **Context injection** — relevant decisions surface automatically via session hooks
- **Policy engine** — configurable policies enforce discipline and inject context

## Install

```sh
claude plugin marketplace add zimalabs/engram
claude plugin install engram@zimalabs
```

> **Requires:** SQLite 3.35+ with FTS5 (ships with macOS 10.14+, most Linux distros).

## How it works

1. You make code changes and commit as normal
2. The policy engine detects decisions and prompts the agent to capture them
3. Decisions accumulate as markdown files in `.engram/decisions/`
4. Past decisions are injected into future sessions automatically

Query anytime:

```
/engram:query what decisions about caching?
```

## Skills

| Skill | Purpose |
|---|---|
| `/engram:capture` | Guided decision creation with schema validation |
| `/engram:query` | Query past decisions (natural language or SQL) |
| `/engram:resync` | Full sync: ingest, reindex, regenerate brief |
| `/engram:brief` | Regenerate the context brief on demand |
| `/engram:backfill` | Autonomously enrich incomplete decisions |
| `/engram:introspect` | Interactive gap-filling for existing decisions |
| `/engram:policies` | List active policies and their levels |

Most skills run automatically via the policy engine — capture is enforced before commits, resync runs at session boundaries and after pushes, and the brief regenerates before context compaction. Skills can also be invoked manually when needed.

## Development

```sh
claude plugin marketplace add ./. --scope user
claude plugin install engram@zimalabs --scope project
```

## Links

- [Full documentation](plugins/engram/README.md) — decisions, linking, querying, policy engine, git integration, architecture
- [Contributing](CONTRIBUTING.md)

## License

MIT
