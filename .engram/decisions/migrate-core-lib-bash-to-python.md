+++
date = 2026-03-17
tags = ["architecture", "migration"]
+++

# Migrate engram core library from bash to Python

The bash implementation of lib.sh had fragility clusters: 184 LOC for frontmatter state machines, 12 manual SQL escaping calls (injection risk via `sed "s/'/''/g"`), IFS-based splitting for git log parsing. Python handles all of these natively.

## Rationale

Single-file `engram.py` (~550 LOC) replaces `lib.sh` (854 LOC). Key wins:
- **Parameterized SQL queries** eliminate all injection risk (12 `sed` escaping calls removed)
- **Shared `_parse_frontmatter()`** replaces two 80+ LOC state machines
- **`subprocess.run()`** replaces fragile IFS pipe splitting for git integration
- **stdlib only** — `sqlite3`, `json`, `re`, `subprocess`, `pathlib`. No PyYAML, no external deps.

Hooks remain bash but call `python3 engram.py <command>` instead of `source lib.sh`.

## Alternatives

- Stay with bash — accepted the fragility and injection risk
- Rewrite hooks in Python too — unnecessary complexity, hooks are thin wrappers
- Use PyYAML for frontmatter — adds a dependency for a problem solved in 30 LOC
