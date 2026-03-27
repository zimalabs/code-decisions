# Guide

Everything you need beyond the basics — commands, matching rules, team rollout, and maintenance.

## Commands

`/decision` handles search, capture, and management when you want explicit control:

| You type | What happens |
|----------|-------------|
| `/decision auth` | Searches past decisions about auth |
| `/decision we chose JWT because stateless` | Captures a new decision |
| `/decision show jwt-auth` | Displays a decision with body, tags, and affects |
| `/decision list` | Browse all decisions (filter with `--tag api`) |
| `/decision --tags` | Lists all tags with counts |
| `/decision --stats` | Shows decision health (`--health` for deep analysis) |
| `/decision tree` | Groups decisions by codebase area |
| `/decision coverage` | Shows what % of source files have decisions |
| `/decision enrich jwt-auth` | Audits a decision for quality (see below) |
| `/decision validate` | Checks all decision files for structural errors |
| `/decision undo` | Reverts the last capture (or specify a slug) |
| `/decision dismiss` | Suppresses nudges for the rest of this session |
| `/decision help` | Lists all commands and CLI usage |

### Decision quality audit

`/decision enrich <slug>` runs a quality analysis on any decision:

- **Conflicts** — finds decisions with overlapping scope and opposing guidance
- **Reasoning gaps** — checks for rationale, alternatives considered, trade-offs
- **Stale affects** — flags paths that no longer exist in the codebase
- **Suggestions** — actionable next steps to strengthen the decision

Use it after a quick capture to fill in gaps, or periodically with `/decision validate` to keep the whole set healthy.

## How `affects` matching works

Each decision declares an `affects` list — file paths that it governs. When anyone edits a file, the plugin checks whether it matches any decision's `affects` entries. Three matching modes are checked in order:

**Directory prefix** — entries ending with `/` match all files under that directory:

```yaml
affects: [src/auth/]
# matches: src/auth/oauth.py, src/auth/middleware.py, src/auth/tests/test_login.py
```

**Glob pattern** — entries with `*` or `?` use fnmatch-style matching:

```yaml
affects: [src/jobs/*.py]
# matches: src/jobs/worker.py, src/jobs/scheduler.py
# doesn't match: src/jobs/README.md
```

**Segment matching** — exact path-segment suffix comparison (no false substring matches):

```yaml
affects: [policy/engine.py]
# matches: src/decision/policy/engine.py (suffix match)
# doesn't match: src/policy_engine.py (not a segment boundary)
```

Segment matching also supports stem matching (`affects: [core]` matches `core.py`) and stem-prefix matching (`affects: [src/auth]` matches `src/auth_helpers.py` — but `affects: [log]` does *not* match `login.py`).

You never need to specify exact paths from root. The plugin finds the right files wherever they live.

## Getting your team started

**Week 1 — Seed a few decisions.** One person installs the plugin and captures 3-5 decisions from recent debates: "why Redis over Sidekiq," "why raw SQL for dashboards." Commit them to `.claude/decisions/` and push. These become the seed set.

**Week 2 — Install across the team.** Each teammate runs `/plugin install decisions@zimalabs`. On their next `git pull`, existing decisions auto-load. Auto-capture starts producing new ones from natural conversation.

**Week 3 — Prune and enrich.** Run `/decision validate` to fix structural issues and `/decision enrich <slug>` on thin decisions. Use `/decision coverage` to see which parts of the codebase lack decisions.

**Tips:**
- Decisions commit to git — they show up in PRs and are reviewable like code
- Start with high-debate areas (auth, data model, infrastructure) rather than trying to cover everything
- `/decision undo` if the auto-capture grabs something wrong — it's cheap to fix
- The plugin is always advisory and never blocks — safe to adopt incrementally

## Uninstalling

```
/plugin uninstall decisions@zimalabs
```

Your decisions stay exactly where they are — markdown files in `.claude/decisions/`, committed to git. They're yours. The plugin only writes and reads them; removing it just stops the automatic capture and surfacing.

To also remove the search index (rebuilds automatically if you reinstall):

```sh
rm -rf ~/.claude/projects/*/.decisions/
```
