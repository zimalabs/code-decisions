[![CI](https://github.com/zimalabs/engram/actions/workflows/ci.yml/badge.svg)](https://github.com/zimalabs/engram/actions/workflows/ci.yml)

# engram

**Decision memory for AI agents.** Git-tracked, zero-config, no vendor lock-in.

A Claude Code plugin that gives your agents persistent memory of decisions, findings, and issues. Signals auto-accumulate from git commits, are stored as markdown, and injected into every session. No CLI. No commands to learn. No manual steps.

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
1. Creates `.engram/{decisions,findings,issues}/` if missing
2. Ingests last 50 git commits as decision signals (brownfield bootstrap)
3. Ingests any Claude plan files with `## Context` sections
4. Builds `index.db` (derived SQLite index, git-ignored)
5. Generates `brief.md`
6. Injects brief + behavioral instructions into agent context

### During session

The agent works normally. When it makes a significant decision, it writes a signal file using the Write tool:

```markdown
# .engram/decisions/2026-03-14-use-redis-for-caching.md
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

No CLI. No skill invocation. Just write a file.

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

## Signal Types

Three types, each answering a different "why" question.

### Decision — Why we chose X

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

### Finding — Why we now know X

```markdown
---
date: 2026-03-11
tags: [sqlite, search]
---

# FTS5 requires explicit sync triggers

SQLite FTS5 content= tables don't auto-update.

## Trigger
Index was returning stale results after inserts.

## Implications
Every table with FTS needs explicit triggers in the schema.
```

### Issue — Why X needs attention

```markdown
---
date: 2026-03-11
tags: [ci, testing]
---

# CI pipeline takes 45 minutes

Integration tests run serially against a shared test database.

## Impact
Developers avoid running full test suite locally.

## Next steps
Investigate per-worker test databases.
```

## In a PR

```diff
+ .engram/decisions/2026-03-14-use-redis-for-caching.md
+ .engram/decisions/2026-03-14-jwt-over-sessions.md
  src/auth/middleware.py
  src/cache/redis_client.py
```

Reviewers see **why** alongside **what**. Decision reasoning is part of the code review.

## Private Signals

For sensitive content that shouldn't be git-tracked or auto-sent to the Claude API, write to the `private/` subdirectory:

```
.engram/private/decisions/2026-03-14-competitor-deal.md
.engram/private/findings/2026-03-14-customer-churn-data.md
.engram/private/issues/2026-03-14-personnel-concern.md
```

Private signals are:
- **Git-ignored** — never committed or pushed
- **Excluded from brief** — never auto-injected into agent context
- **Indexed and queryable** — available on-demand via `@engram:query`
- **Same schema** — identical format to public signals

The directory path IS the privacy boundary. No config, no encryption. Move a file between `decisions/` and `private/decisions/` to change its visibility.

Use private for: messaging content, CRM data, competitive intel, personnel decisions — anything you wouldn't put in a commit message.

## Architecture

```
.engram/
├── decisions/                    # git-tracked
│   ├── 2026-03-10-use-fastapi.md
│   └── 2026-03-12-jwt-auth.md
├── findings/                     # git-tracked
│   └── 2026-03-11-fts5-triggers.md
├── issues/                       # git-tracked
│   └── 2026-03-11-ci-too-slow.md
├── private/                      # git-IGNORED
│   ├── decisions/
│   ├── findings/
│   └── issues/
├── brief.md                      # git-tracked
└── index.db                      # git-IGNORED (derived)
```

Markdown files are the source of truth. `index.db` is derived — delete it anytime, rebuilt from files on next session.

## Comparison

| | engram | claude-mem | supermemory |
|---|---|---|---|
| **What it stores** | Decisions, findings, issues | Key-value facts | Conversations, bookmarks, documents |
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

CLAUDE.md doesn't grow. Engram does. After 50 sessions, your CLAUDE.md is the same 30 lines. Your `.engram/decisions/` has 50+ signals that prevent the agent from re-debating settled architecture choices.

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
