+++
date = 2026-03-17
tags = ["skills", "conventions"]
links = ["related:formalize-policy-layer"]
+++

# Standardize skill prefix from @ to / (slash command syntax)

Claude Code uses `/` as the standard prefix for slash commands and skills. All engram docs, policy messages, skill headings, and tests used `@engram:` instead.

## Rationale

The `@` prefix was carried over from early development but doesn't match the Claude Code convention. Users type `/engram:query`, not `@engram:query`. Inconsistency confuses both humans and agents.

## Scope

Replaced `@engram:` with `/engram:` across 14 files: docs (CLAUDE.md, README.md, CHANGELOG.md, plugins/engram/README.md), all 7 SKILL.md files, _policy_defs.py, store.py, and test_engram.py. Historical decision files in `.engram/decisions/` left untouched (append-only).

Also fixed `engram:policies` skill — name field was `policies` (missing namespace prefix) and had non-standard `user_invocable: true` field.
