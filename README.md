# engram

**The why database.** Your agents remember why things are the way they are.

Install the plugin. Signals auto-accumulate from git commits, are git-tracked as markdown, and injected into every agent session. No CLI. No commands to learn. No manual steps.

## Install

```sh
claude plugin install zimalabs/engram
```

That's it. No `engram init`. No configuration.

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

| | ADRs | Claude auto-memory | Plans | engram |
|---|---|---|---|---|
| Structured | Yes | No | Partial | Yes |
| Automatic | No (manual) | Yes | Yes | Yes |
| Permanent | Yes | Yes | No (ephemeral) | Yes |
| Git-tracked | Yes | No | No | Yes |
| Queryable | No | No | No | Yes (FTS5) |
| In PRs | Sometimes | Never | Never | Always |
| Brownfield | No | No | No | Yes (git history) |

## Contributing

```sh
git clone https://github.com/zimalabs/engram.git
cd engram
make check   # shellcheck + tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
