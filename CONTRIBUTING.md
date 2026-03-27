# Contributing

Structured decision memory for Claude Code. Captures *why* decisions were made as markdown files with SQLite FTS5 search — stdlib only, no external dependencies.

## Development Setup

```sh
git clone https://github.com/zimalabs/code-decisions.git
cd code-decisions
uv sync        # install dev deps
make check     # ruff + mypy + shellcheck + pytest
```

**Requirements:** Python 3.11+, [uv](https://docs.astral.sh/uv/)

To test the plugin end-to-end in Claude Code:

```sh
make dev         # symlink into Claude Code's plugin cache
```

Restart Claude Code (or run `/reload-plugins`) to load the plugin.

## Making Changes

1. Fork the repo and create a branch: `git checkout -b feat/my-feature`
2. Make your changes
3. Run `make check` (must pass)
4. Commit with a clear message
5. Open a PR

## Code Style

- **Linting:** ruff (format + lint), mypy for type checking, shellcheck for bash
- **Plugin is stdlib only** — no external dependencies in `src/`
- Dev tooling (pytest, ruff, mypy) lives in `pyproject.toml` at the repo root
- Functions prefixed with `_` are private helpers
- YAML frontmatter with `---` delimiters

## Architecture

Decisions are markdown files in `.claude/decisions/` in the repo. SQLite FTS5 provides a derived search index — delete it and everything rebuilds from markdown.

```
src/
  decision/               # Core library (stdlib only)
    utils/                # Pure helpers and constants
    core/                 # Decision dataclass and quality scoring
    store/                # File-based storage, FTS5 index, keyword search
    policy/               # 14 policies for capture, validation, context, review
  hooks/                  # Shell dispatcher + hook registration
  skills/                 # /decision — single skill, intent-routed (see SKILL.md)
tests/                    # pytest with tmp_path fixtures, no mocks
```

`dispatch.sh` short-circuits common cases (observe mode, short messages, skip-pattern files) in bash before spawning Python, keeping hook latency low.

## Testing

Tests use pytest with `tmp_path` fixtures. Each test creates its own decisions dir in a temp dir. No mocks.

```sh
make test      # pytest only
make check     # full suite (ruff + mypy + shellcheck + pytest)
```

## Adding a New Function

1. Add the function to the appropriate subpackage (`utils/`, `core/`, `store/`, or `policy/`)
2. Add tests to the relevant test file
3. Wire into hooks via a new policy in `policy/defs.py` if needed
4. Run `make check`

## Adding a New Policy

1. Write a condition function in a new file under `src/decision/policy/` (e.g. `my_policy.py`)
2. Import the condition in `src/decision/policy/defs.py`
3. Add a `Policy(...)` instance to `ALL_POLICIES` with name, level, events, matchers
4. Add tests to `tests/test_policy.py`
5. Run `make check` — no `hooks.json` changes needed

## Architecture Decisions

This project uses its own plugin to track decisions. When you make a non-trivial choice (architecture, API design, trade-off), capture it with `/decision`. Future contributors inherit that context automatically.

## Reporting Issues

Use GitHub issues for bugs and feature requests. See the issue templates for bug reports and feature requests.
