# Contributing to engram

## Development Setup

```sh
git clone https://github.com/zimalabs/engram.git
cd engram
make check   # Run shellcheck + tests
```

Requirements: `bash 4+`, `sqlite3 3.35+`, `shellcheck` (for linting).

## Making Changes

1. Fork the repo and create a branch: `git checkout -b feat/my-feature`
2. Make your changes
3. Run `make check` (must pass)
4. Commit with a clear message
5. Open a PR

## Code Style

- All bash scripts use `set -euo pipefail`
- Functions prefixed with `_` are private helpers
- Public functions in `lib.sh` are prefixed with `engram_`
- Quote all variables: `"$var"` not `$var`
- Use `local` for function-scoped variables

## Architecture

- `lib.sh` — Core functions (sourced by hooks and tests, no side effects at source time)
- `hooks/` — SessionStart and SessionEnd hooks that call `lib.sh` functions
- `skills/` — Capture convention docs and query skill
- `schema.sql` — SQLite index schema (FTS5)

## Testing

Add tests in `tests/test_engram.sh`. Each test function should:
- Print its name with `echo "test_name:"`
- Source `lib.sh` and call functions directly
- Use `assert_*` helpers for validation
- Clean up any state it creates

## Reporting Issues

Use the GitHub issue templates for bugs and feature requests.
