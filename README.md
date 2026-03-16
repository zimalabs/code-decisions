[![CI](https://github.com/zimalabs/engram/actions/workflows/ci.yml/badge.svg)](https://github.com/zimalabs/engram/actions/workflows/ci.yml)

# engram

**Decision memory for AI agents.** Git-tracked, zero-config, no vendor lock-in.

A Claude Code plugin that gives your agents persistent memory of decisions. Signals auto-accumulate from git commits, are stored as markdown, and injected into every session. No CLI. No commands to learn. No manual steps.

## Install

```sh
claude plugin install zimalabs/engram
```

That's it. No `engram init`. No configuration.

### Install from local source

For development or dogfooding from a local clone:

```sh
claude plugin marketplace add . --scope project
claude plugin install engram@zimalabs --scope project
```

> **Requires:** SQLite 3.35+ with FTS5 (ships with macOS 10.14+, most Linux distros).
> If you see "no such module: fts5", run `brew install sqlite` (macOS) or `sudo apt-get install libsqlite3-0` (Ubuntu).

## How It Works

### First session (greenfield or brownfield)

SessionStart hook fires:
1. Creates `.engram/decisions/` and `.engram/_private/` if missing
2. Ingests last 50 git commits as decision signals (brownfield bootstrap)
3. Ingests any Claude plan files with `## Context` sections
4. Builds `index.db` (derived SQLite index, git-ignored)
5. Generates `brief.md`
6. Injects brief + behavioral instructions into agent context

### During session

The agent works normally. When it makes a significant decision, it writes a signal file using the Write tool:

```markdown
# .engram/decisions/use-redis-for-caching.md
---
date: 2026-03-14
tags: [infrastructure, caching]
---

# Use Redis for caching

Already in our stack for session storage.

## Alternatives
- Memcached — faster for simple k/v but no pub/sub
- In-process cache — no sharing between pods

## Rationale
Redis supports pub/sub which we'll need for the notification system.

## Trade-offs
Higher memory usage than Memcached for pure cache workloads.
```

No CLI needed. Just write a file — or use `@engram:capture` for guided signal creation with schema validation.

If you write a signal manually with the same slug as a commit subject (e.g., `use-redis-for-caching`), auto-ingest skips that commit. Manual signals are the primary record; auto-ingest is a safety net for decisions that weren't explicitly captured.

When the agent needs past decisions:

```
@engram:query what decisions about caching?
```

### Session ends

SessionEnd hook fires:
1. Ingests new git commits since last ingest
2. Ingests modified Claude plan files
3. Rebuilds `index.db`
4. Regenerates `brief.md`

### Next session starts

SessionStart hook catches ALL changes — commits from VS Code, terminal, CI, other developers — via `git log`. The agent never has stale context.

| Source | How engram catches it | When |
|---|---|---|
| VS Code / terminal commits | `git log` at session-start | Next session |
| CI auto-commits | `git log` at session-start | Next session |
| Other developer's commits | `git log` after `git pull` | Next session after pull |
| Manual signal files | Developer writes `.engram/` file + commits | Next session after commit |

## Decision Signals

File: `.engram/decisions/{slug}.md`

```markdown
---
date: 2026-03-10
tags: [api, framework]
source: git:a3f2b1c
---

# Use FastAPI over Django

Async-first, lighter weight, team has more experience.

## Alternatives
- Django REST Framework — mature but synchronous by default

## Rationale
Team has 2 years of FastAPI experience. Async support is critical.

## Trade-offs
Smaller ecosystem than Django. No built-in admin.
```

## Linking Signals

Signals can reference each other via frontmatter. This enables supersession tracking (replacing outdated decisions) and relationship graphs.

### Superseding a decision

When a decision replaces an older one, use `supersedes:`:

```markdown
# .engram/decisions/use-jwt.md
---
date: 2026-03-15
tags: [auth]
supersedes: use-sessions
---

# Use JWT authentication

Mobile clients need token-based auth. Sessions don't work across native apps.
```

The superseded signal (`use-sessions`) is hidden from the brief but remains queryable. The brief shows the new decision with a `(supersedes: use-sessions)` annotation.

### Linking related signals

Use `links:` for non-supersession relationships:

```markdown
---
date: 2026-03-15
tags: [infrastructure]
links: [related:redis-latency]
---

# Switch to Redis Cluster

Single-node Redis can't handle our pub/sub volume.
```

Link types: `supersedes`, `related`.

## Querying

Ask questions in natural language — Claude converts them to SQL automatically.

### Natural language

```
@engram:query what decisions have we made about authentication?
@engram:query what did we decide about caching last week?
```

### Full-text search

Search across all decisions by keyword:

```
@engram:query anything mentioning Redis?
```

Behind the scenes:

```sql
SELECT s.type, s.title, s.date FROM signals_fts fts
JOIN signals s ON s.id = fts.rowid
WHERE signals_fts MATCH 'Redis' ORDER BY rank
```

### Decision history

Walk the supersession chain to see how a decision evolved:

```
@engram:query what did use-jwt replace?
@engram:query show me the full auth decision chain
```

Example chain: `use-sessions` → `use-jwt` → `use-oauth2`

### Relationship traversal

Follow links between decisions:

```
@engram:query what's related to the Redis decision?
```

### Direct SQL

Power users can pass raw SQL queries:

```
@engram:query SELECT COUNT(*) as count FROM signals
@engram:query SELECT title, date FROM signals WHERE date >= '2026-03-01' ORDER BY date DESC
```

## Skills

| Skill | Purpose |
|---|---|
| `@engram:capture` | Guided signal creation — reads schema, validates frontmatter, writes the file |
| `@engram:query` | Query past decisions in natural language or raw SQL (see [Querying](#querying)) |
| `@engram:visualize` | Generate an interactive HTML dashboard — timeline, charts, link graph, searchable table |
| `@engram:brief` | Regenerate and display the brief on demand — see updated context without restarting the session |
| `@engram:reindex` | Rebuild `index.db` on demand after manual signal edits (no need to wait for next session) |
| `@engram:introspect` | Interactive gap-filling loop — adds missing tags, links, and body sections to existing decisions |

## Automation

Engram hooks run automatically — no configuration needed. Here's what happens behind the scenes:

| Hook | Event | Behavior |
|---|---|---|
| **Stop enforcement** | Session end | Blocks if significant code changes lack a decision signal |
| **PostToolUse nudge** | After Write/Edit | Advisory "consider recording this decision" (once per session) |
| **Context injection** | After Write/Edit | Auto-injects related past decisions when editing code files |
| **Signal validation** | Before Write/Edit | Validates frontmatter format on writes to `.engram/decisions/` |
| **Decision detection** | User prompt | Detects decision language ("let's go with…") and suggests capture |
| **Compaction safety** | Before compaction | Warns about unrecorded decisions before context is compacted |

All hooks are advisory or self-correcting — they guide the agent without interrupting your workflow.

## In a PR

```diff
+ .engram/decisions/use-redis-for-caching.md
+ .engram/decisions/jwt-over-sessions.md
  src/auth/middleware.py
  src/cache/redis_client.py
```

Reviewers see **why** alongside **what**. Decision reasoning is part of the code review.

## Private Signals

For sensitive content that shouldn't be git-tracked or auto-sent to the Claude API, write to `.engram/_private/`:

```
.engram/_private/competitor-deal.md
.engram/_private/customer-churn-data.md
.engram/_private/personnel-concern.md
```

Private signals are:
- **Git-ignored** — never committed or pushed
- **Excluded from brief** — never auto-injected into agent context
- **Indexed and queryable** — available on-demand via `@engram:query`
- **Same schema** — identical format to public signals

The directory path IS the privacy boundary. No config, no encryption. Move a file between `decisions/` and `_private/` to change its visibility.

Use private for: messaging content, CRM data, competitive intel, personnel decisions — anything you wouldn't put in a commit message.

## Architecture

```
.engram/
├── decisions/                          # git-tracked
│   ├── use-fastapi.md
│   ├── jwt-auth.md
│   └── redis-cluster.md
├── _private/                         # git-IGNORED
│   └── competitor-deal.md
├── brief.md                          # git-IGNORED (derived)
└── index.db                          # git-IGNORED (derived)
```

The filename stem (without `.md`) serves as a stable ID for linking between signals.

Markdown files are the source of truth. `index.db` is derived — delete it anytime, rebuilt from files on next session.

## Comparison

| | engram | claude-mem | supermemory |
|---|---|---|---|
| **What it stores** | Decisions | Key-value facts | Conversations, bookmarks, documents |
| **Source of truth** | Markdown files in git | JSON in `~/.claude/` | Cloud database |
| **Search** | FTS5 (local SQLite) | Keyword match | Vector similarity (cloud) |
| **Context injection** | Auto (session hooks) | Auto (system prompt) | Manual / API |
| **Capture model** | Write tool + git ingest | CLI commands | Browser extension / API |
| **Runtime deps** | SQLite (ships with OS) | Node.js | Docker + cloud services |
| **Privacy** | Local-only, git-ignored private tier | Local files | Cloud-hosted |
| **Git integration** | Native (signals in PRs) | None | None |
| **Cost** | Free | Free | Free tier + paid plans |
| **Overhead** | Zero config, no commands | `mem add` / `mem search` | Setup + API keys |
| **Self-hostable** | Yes (it's just files) | Yes | Yes (Docker) |

### Key differentiators

**engram** is purpose-built for decision memory — the "why" behind code changes. Signals live in git alongside the code they describe, show up in PRs and diffs, and survive across tools, editors, and team members. Zero runtime dependencies beyond SQLite.

**claude-mem** is a general-purpose key-value memory for Claude Code. Good for remembering user preferences and short facts. Lightweight, but memories are local to one machine and invisible to code review.

**supermemory** is a cloud-native knowledge base for teams. Strong at ingesting diverse sources (bookmarks, conversations, documents) and semantic search. Best when you need cross-tool memory with a managed service. Requires cloud infrastructure.

## FAQ

### How is this different from CLAUDE.md?

`CLAUDE.md` is static instructions — you write it once and update it manually. It tells the agent *how* to behave. Engram is dynamic decision accumulation — signals are created automatically as the agent works, capturing *why* decisions were made.

They're complementary:
- **CLAUDE.md** → "Use pytest for testing, prefer composition over inheritance"
- **engram** → "Chose Redis over Memcached because we need pub/sub for notifications (2026-03-14)"

CLAUDE.md doesn't grow. Engram does. After 50 sessions, your CLAUDE.md is the same 30 lines. Your `.engram/decisions/` has 50+ decisions that prevent the agent from re-debating settled architecture choices.

### Does engram send my data anywhere?

No. Everything is local. Signals are markdown files on disk. The index is a local SQLite database. There are no network calls, no cloud services, no telemetry. Private signals are git-ignored and never injected into agent context.

### Can I use engram with other AI tools?

The signals are plain markdown files in git. Any tool that can read files can read your decision history. The Claude Code plugin (hooks, skills, context injection) is Claude-specific, but the signal format is universal.

### What happens if I delete index.db?

Nothing bad. It's rebuilt from the markdown files on the next session start. The markdown files are the source of truth — the database is derived.

## Contributing

```sh
git clone https://github.com/zimalabs/engram.git
cd engram
make check   # shellcheck + tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
