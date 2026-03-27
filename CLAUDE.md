# CLAUDE.md

## What This Is

Decision memory for Claude Code — captures why choices were made so future sessions inherit context instead of repeating debates. Decisions are markdown files in `.claude/decisions/` (committed to the repo, shared via git). Hooks and skills handle everything automatically.

## Commands

```sh
uv sync                        # install dev deps (first time only)
make check                     # ruff + mypy + shellcheck + pytest
make dev                       # symlink plugin into Claude Code cache
```

## Key Concepts

- **Decisions** extend Claude Code's memory schema with: `name`, `description`, `date`, `tags`, `affects`
- **YAML frontmatter** with `---` delimiters (not TOML) for decision files. Block scalars (`|`, `>`) are rejected.
- **All decisions are lightweight** — frontmatter, title, and lead paragraph. No weight distinction.
- **DecisionStore** = file-based store with FTS5 derived search index. Progressive loading: index stores summaries, full files read on demand.
- **Zero-config, advise-only.** No strictness settings, no config file. The plugin just nudges — it never blocks or enforces.

## Storage

Decisions live at `.claude/decisions/{slug}.md` in the repo — committed to git and shared with the team. The FTS5 index lives at `~/.claude/projects/{project-key}/.decision/`.

## Architecture Rules

Architecture lives in decision files under `.claude/decisions/` — see `.claude/rules/decisions.md` for the full index.

1. **Markdown is source of truth.** SQLite FTS5 is a derived index. Delete it and everything rebuilds.
2. **Git is the history layer.** Edit decisions in place, delete when obsolete. Git tracks the evolution.
3. **Skill = intent + behavior, hooks = correctness, CLI = data access.** `/decision` skill routes intent. Hooks enforce validation and inject context. CLI provides search, stats, and git operations.
4. **Pure methods on DecisionStore.** No side effects at import time.
5. **Plugin is stdlib only.** Zero external dependencies in `src/`.
6. **No confirmation prompts on capture.** Write decisions directly — agents must capture without human approval gates. `/decision undo` is the safety net.

## Using the Decision Plugin (Agent Workflow)

This section is for you, the agent. Use judgment — not every task involves decisions.

### Before starting work
When the user asks you to do something **that involves choosing between approaches** (architecture, framework selection, API design, migration strategy):
1. **Search first**: `/decision <topic>` to check if past decisions constrain your approach
2. If related decisions exist, acknowledge them before proposing your approach

**Skip this step** for bug fixes, typo corrections, simple feature additions, test writing, and other tasks where there's an obvious single approach.

### Capturing decisions (automatic — like memories)
When the user states a decision, preference, or trade-off — **capture it automatically** by writing a decision file. Do not ask for confirmation, do not suggest `/decision capture`. Just write it, exactly like you auto-save memories.

**Trigger on statements like:**
- "we should use X because Y"
- "let's go with X — Y is too Z"
- "don't paginate this — only 50 tenants"
- "handle errors inline, webhooks are too slow"
- Any statement that explains *why* something should be done a certain way

**How to capture:**
1. Write a decision file to `.claude/decisions/{slug}.md` following the decision template (injected at session start). The content-validation hook will reject and guide you if anything is wrong.
2. Always populate `affects` — auto-infer from files edited this session (deduplicate to directory prefixes when 3+ files share a dir). Never leave empty.
3. Confirm briefly: "Captured: {title}" with the affects paths

**Then continue with the user's request.** If they asked you to implement something, capture the decision AND do the implementation. Don't stop at capture.

### During work
When you (the agent) choose between alternatives (framework, pattern, architecture, API design):
1. **Capture immediately** by writing a decision file while the reasoning is fresh
2. Don't batch captures — the best time is right after the choice is made
3. Include affected files so future `related-context` matching is precise

If you're not choosing between alternatives, there's nothing to capture.

### After work
When committing changes that involved non-trivial decisions, include the decision rationale directly in the commit message body — the *why*, alternatives considered, and trade-offs. Make `git log` self-documenting.

### Browsing and monitoring
- `/decision --tags` to browse what topics have been captured and drill into specific tags
- `/decision --stats` to check decision coverage health (counts, activity, gaps)
- `/decision debug` to see which policies fired, thresholds, and session state

### What to capture vs skip
- **Capture**: choices between alternatives, non-obvious trade-offs, constraints a future agent needs
- **Skip**: implementation details that are obvious from the code, one-line fixes, style choices

### Decisions vs Memories
- **Decision** = a technical choice between alternatives, shared with the team via git. It has `affects` paths so it auto-surfaces when teammates edit related code.
- **Memory** = personal context (user preferences, workflow style, role info). Lives in MEMORY.md, not shared via git.

Rule of thumb: if it should travel with the repo and surface for other developers, it's a decision. If it's about how *this user* prefers to work, it's a memory.
