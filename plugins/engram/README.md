# engram — Full Documentation

**Structured decision memory for AI agents.** Auto-capture, search, and evolution tracking. Privacy first.

A Claude Code plugin that gives your agents persistent memory of decisions. Decisions are stored as markdown files, indexed for full-text search, and injected into every session. No CLI. No commands to learn. No manual steps.

## Install

```sh
claude plugin marketplace add zimalabs/engram
claude plugin install engram@zimalabs
```

> **Requires:** SQLite 3.35+ with FTS5 (ships with macOS 10.14+, most Linux distros).

## How It Works

### First session (greenfield or brownfield)

SessionStart hook fires:
1. Creates `.engram/decisions/` and `.engram/_private/decisions/` if missing
2. Ingests any Claude plan files with `## Context` sections
3. If git tracking is enabled: ingests last 50 git commits as decisions (brownfield bootstrap)
4. Builds `index.db` (derived SQLite index)
5. Generates `brief.md`
6. Injects brief + behavioral instructions into agent context

### During session

The agent works normally. When it makes a significant decision, it writes a decision file using the Write tool:

```markdown
# .engram/decisions/use-redis-for-caching.md
+++
date = 2026-03-14
tags = ["infrastructure", "caching"]
+++

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

No CLI needed. Just write a file — or use `/engram:capture` for guided decision creation with schema validation.

If you write a decision manually with the same slug as a commit subject (e.g., `use-redis-for-caching`), auto-ingest skips that commit. Manual decisions are the primary record; auto-ingest is a safety net for decisions that weren't explicitly captured.

When the agent needs past decisions:

```
/engram:query what decisions about caching?
```

### Session ends

SessionEnd hook fires:
1. Ingests modified Claude plan files
2. If git tracking is enabled: ingests new git commits since last ingest
3. Rebuilds `index.db`
4. Regenerates `brief.md`

## Decision Format

File: `.engram/decisions/{slug}.md`

```markdown
+++
date = 2026-03-10
tags = ["api", "framework"]
+++

# Use FastAPI over Django

Async-first, lighter weight, team has more experience.

## Alternatives
- Django REST Framework — mature but synchronous by default

## Rationale
Team has 2 years of FastAPI experience. Async support is critical.

## Trade-offs
Smaller ecosystem than Django. No built-in admin.
```

## Linking Decisions

Decisions can reference each other via frontmatter. This enables supersession tracking (replacing outdated decisions) and relationship graphs.

### Superseding a decision

When a decision replaces an older one, use `supersedes:`:

```markdown
# .engram/decisions/use-jwt.md
+++
date = 2026-03-15
tags = ["auth"]
supersedes = "use-sessions"
+++

# Use JWT authentication

Mobile clients need token-based auth. Sessions don't work across native apps.
```

The superseded decision (`use-sessions`) is hidden from the brief but remains queryable. The brief shows the new decision with a `(supersedes: use-sessions)` annotation.

### Linking related decisions

Use `links:` for non-supersession relationships:

```markdown
+++
date = 2026-03-15
tags = ["infrastructure"]
links = ["related:redis-latency"]
+++

# Switch to Redis Cluster

Single-node Redis can't handle our pub/sub volume.
```

Link types: `supersedes`, `related`.

## Querying

Ask questions in natural language — Claude converts them to SQL automatically.

### Natural language

```
/engram:query what decisions have we made about authentication?
/engram:query what did we decide about caching last week?
```

### Full-text search

Search across all decisions by keyword:

```
/engram:query anything mentioning Redis?
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
/engram:query what did use-jwt replace?
/engram:query show me the full auth decision chain
```

Example chain: `use-sessions` → `use-jwt` → `use-oauth2`

### Relationship traversal

Follow links between decisions:

```
/engram:query what's related to the Redis decision?
```

### Direct SQL

Power users can pass raw SQL queries:

```
/engram:query SELECT COUNT(*) as count FROM signals
/engram:query SELECT title, date FROM signals WHERE date >= '2026-03-01' ORDER BY date DESC
```

## Skills

| Skill | Purpose |
|---|---|
| `/engram:capture` | Guided decision creation — reads schema, validates frontmatter, writes the file |
| `/engram:query` | Query past decisions in natural language or raw SQL (see [Querying](#querying)) |
| `/engram:brief` | Regenerate and display the brief on demand — see updated context without restarting the session |
| `/engram:resync` | Full sync: ingest commits + plans, rebuild index, regenerate brief |
| `/engram:introspect` | Interactive gap-filling loop — adds missing tags, links, and body sections to existing decisions |
| `/engram:backfill` | Autonomously enrich incomplete decisions — adds missing tags, rationale, alternatives, and links |
| `/engram:policies` | List all active policies with their levels, events, and descriptions |

## Policy Engine

Engram enforces behavior through a configurable policy engine. A single thin dispatcher (`dispatch.sh`) routes all hook events to `python3 -m engram policy <event>`, which evaluates 15 registered policies in priority order.

### Policy levels

| Level | Behavior | Example |
|---|---|---|
| **BLOCK** | Prevents the action | `commit-gate` blocks `git commit` without a decision recorded |
| **LIFECYCLE** | Side effects (init, resync) | `session-init` sets up `.engram/` and rebuilds the index |
| **CONTEXT** | Injects information | `session-context` adds the brief to agent context |
| **NUDGE** | Advisory suggestion | `capture-nudge` suggests recording a decision after 3+ edits |

### Active policies

| Policy | Level | Event | What it does |
|---|---|---|---|
| `commit-gate` | BLOCK | PreToolUse | Blocks `git commit` if no decision written this session |
| `delete-guard` | BLOCK | PreToolUse | Blocks deletion of `.engram/` decision files (append-only) |
| `edit-guard` | BLOCK | PreToolUse | Blocks content removal from decision files via Edit tool |
| `content-validation` | BLOCK | PreToolUse | Validates frontmatter and structure on Write to `.engram/decisions/` |
| `session-init` | LIFECYCLE | SessionStart | Creates dirs, resyncs index, prints banner |
| `session-cleanup` | LIFECYCLE | SessionEnd | Resyncs index at session end |
| `push-resync` | LIFECYCLE | PostToolUse | Auto-resyncs after `git push` |
| `session-context` | CONTEXT | SessionStart | Injects brief + behavioral instructions |
| `related-context` | CONTEXT | PostToolUse | Injects related past decisions when editing code (path + content keywords) |
| `subagent-context` | CONTEXT | SubagentStop | Injects brief into subagent results |
| `compact-context` | CONTEXT | PreCompact | Regenerates brief before context compaction |
| `capture-nudge` | NUDGE | PostToolUse | Suggests `/engram:capture` after 3+ code edits (once/session) |
| `stop-nudge` | NUDGE | Stop | Nudges if no decisions written this session (skips read-only sessions) |
| `decision-language` | NUDGE | UserPromptSubmit | Detects "let's go with…" and suggests capture (per-phrase dedup) |
| `incomplete-nudge` | NUDGE | Notification | Suggests `/engram:backfill` for incomplete decisions |

List active policies anytime with `/engram:policies`.

### Configuring policies

Disable any policy by setting it to `"off"` in `.engram/config.toml`:

```toml
[policies]
commit-gate = "off"
capture-nudge = "off"
```

Disabled policies are skipped during evaluation — no code changes needed.

### Evaluation trace

Enable tracing to see which policies fire and why:

```toml
trace = true
```

With tracing on, each evaluation prints a one-line summary to stderr:

```
engram trace: PostToolUse -> related-context, capture-nudge
```

For detailed debugging, use the `--trace` flag:

```sh
echo '{"tool_name": "Write"}' | python3 -m engram policy --trace PostToolUse
```

This outputs `{"result": {...}, "trace": [...]}` with per-policy timing, match status, and skip reasons.

### Smart nudge behavior

Nudge policies avoid noise through activity-aware thresholds:

- **capture-nudge** only fires after 3+ qualifying code edits (not on the first edit)
- **stop-nudge** stays silent for read-only sessions (no code edits)
- **decision-language** deduplicates by matched phrase — "let's go with X" early in a session doesn't suppress "we decided Y" later

### Content-aware context

The `related-context` policy searches for relevant past decisions using both the file path **and** the edit content. Editing `auth/middleware.py` to add `authenticate_user()` searches for both "auth middleware" and "authenticate" — finding decisions about authentication that a path-only search would miss.

### Adding a policy

Write a condition function in `_policy_defs.py`, add a `Policy(...)` to `ALL_POLICIES`, add tests. No `hooks.json` changes needed — the dispatcher routes all events automatically.

## In a PR

```diff
+ .engram/decisions/use-redis-for-caching.md
+ .engram/decisions/jwt-over-sessions.md
  src/auth/middleware.py
  src/cache/redis_client.py
```

Reviewers see **why** alongside **what**. Decision reasoning is part of the code review.

## Git Integration (Optional)

By default, engram works standalone — no git required. To enable git commit ingestion and `.gitignore` management, set `git_tracking = true` in `.engram/config.toml`:

```toml
git_tracking = true
```

With git tracking enabled:
- Commits matching decision patterns (`feat:`, `refactor:`, dependency changes) are auto-ingested as decisions
- `.engram/.gitignore` is created/maintained to ignore `index.db`, `brief.md`, `_private/`, and `config.toml`
- Uncommitted decisions are reported in the session banner
- Decisions show up in PRs alongside the code they describe

| Source | How engram catches it | When |
|---|---|---|
| VS Code / terminal commits | `git log` at session-start | Next session |
| CI auto-commits | `git log` at session-start | Next session |
| Other developer's commits | `git log` after `git pull` | Next session after pull |
| Manual decision files | Developer writes `.engram/` file | Next reindex |

## Private Decisions

For sensitive content that should be excluded from brief and context, write to `.engram/_private/decisions/`:

```
.engram/_private/decisions/competitor-deal.md
.engram/_private/decisions/customer-churn-data.md
.engram/_private/decisions/personnel-concern.md
```

Private decisions are:
- **Excluded from brief and context** — never auto-injected into agent context
- **Indexed and queryable** — available on-demand via `/engram:query`
- **Same format** — identical to public decisions

The directory path IS the privacy boundary. No config, no encryption. Move a file between `decisions/` and `_private/` to change its visibility.

Use private for: messaging content, CRM data, competitive intel, personnel decisions — anything you wouldn't include in shared context.

## Architecture

```
.engram/
├── decisions/                          # decision files
│   ├── use-fastapi.md
│   ├── jwt-auth.md
│   └── redis-cluster.md
├── _private/                         # excluded from brief
│   └── decisions/
│       └── competitor-deal.md
├── config.toml                        # settings (git_tracking, trace, policies)
├── brief.md                          # derived
└── index.db                          # derived
```

The filename stem (without `.md`) serves as a stable ID for linking between decisions.

Markdown files are the source of truth. `index.db` is derived — delete it anytime, rebuilt from files on next session.

### Hook architecture

All hook events flow through a single dispatcher:

```
hooks.json → dispatch.sh <event> → python3 -m engram policy <event> → JSON response
```

The policy engine evaluates all registered policies for that event in priority order (BLOCK → LIFECYCLE → CONTEXT → NUDGE), with per-policy exception isolation, once-per-session dedup, and activity tracking. Session state — including fired policies and edit counts — is unified in a single `/tmp/engram-policy-{session_id}/` directory. Configuration (disabled policies, tracing) is read from `.engram/config.toml`.

## Comparison

| | engram | claude-mem | supermemory |
|---|---|---|---|
| **What it stores** | Decisions | Key-value facts | Conversations, bookmarks, documents |
| **Source of truth** | Markdown files (local) | JSON in `~/.claude/` | Cloud database |
| **Search** | FTS5 (local SQLite) | Keyword match | Vector similarity (cloud) |
| **Context injection** | Auto (session hooks) | Auto (system prompt) | Manual / API |
| **Capture model** | Write tool + auto-capture | CLI commands | Browser extension / API |
| **Runtime deps** | SQLite (ships with OS) | Node.js | Docker + cloud services |
| **Privacy** | Local-only, git-ignored private tier | Local files | Cloud-hosted |
| **Git integration** | Optional (opt-in) | None | None |
| **Cost** | Free | Free | Free tier + paid plans |
| **Overhead** | Zero config, no commands | `mem add` / `mem search` | Setup + API keys |
| **Self-hostable** | Yes (it's just files) | Yes | Yes (Docker) |

### Key differentiators

**engram** is purpose-built for decision memory — the "why" behind code changes. Decisions are plain markdown files that survive across tools, editors, and team members. With optional git tracking, they show up in PRs alongside code. Zero runtime dependencies beyond SQLite.

**claude-mem** is a general-purpose key-value memory for Claude Code. Good for remembering user preferences and short facts. Lightweight, but memories are local to one machine and invisible to code review.

**supermemory** is a cloud-native knowledge base for teams. Strong at ingesting diverse sources (bookmarks, conversations, documents) and semantic search. Best when you need cross-tool memory with a managed service. Requires cloud infrastructure.

## FAQ

### How is this different from Claude's auto-memory?

Claude's built-in memory stores general facts and preferences — "user prefers TypeScript", "project uses PostgreSQL". It's great for personalizing the assistant. Engram captures structured *decisions* — the why, alternatives considered, and trade-offs.

They're complementary:
- **Auto-memory** → "This project uses Redis for caching"
- **engram** → "Chose Redis over Memcached because we need pub/sub for notifications. Trade-off: higher memory usage. (2026-03-14)"

Auto-memory is invisible — stored in `~/.claude/`, never in your repo. Engram decisions are markdown files in git, visible in PRs alongside the code they explain. After 50 sessions, auto-memory has a flat list of facts. Engram has 50+ linked decisions with supersession chains that prevent the agent from re-debating settled architecture.

### Does engram send my data anywhere?

No. Everything is local. Decisions are markdown files on disk. The index is a local SQLite database. There are no network calls, no cloud services, no telemetry. Private decisions are git-ignored and never injected into agent context.

### Can I use engram with other AI tools?

The decisions are plain markdown files in git. Any tool that can read files can read your decision history. The Claude Code plugin (hooks, skills, context injection) is Claude-specific, but the decision format is universal.

### What happens if I delete index.db?

Nothing bad. It's rebuilt from the markdown files on the next session start. The markdown files are the source of truth — the database is derived.

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md).

## License

MIT
