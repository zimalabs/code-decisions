+++
date = 2026-03-16
tags = ["schema", "cleanup"]
links = ["related:remove-visualize-skill-bloat-without-core-value"]
source = "git:43a5b07bd4ce4dbbcdfe471e1fd5a837fb2d11e5"
+++

# Simplify engram to decisions-only: remove finding and issue signal types

100% of generated signals are decisions. Auto-ingest only creates decisions,
and nothing triggers finding/issue creation automatically. Dropping unused
types simplifies the codebase, sharpens positioning as "decision memory",
and removes dead code paths.

- Delete finding.md and issue.md schema files
- schema.sql: CHECK constraint now decision-only, remove status column
- lib.sh: remove finding/issue type detection, status parsing, brief sections
- session-start.sh: simplify banner and context injection to decisions-only
- hooks.json: update PreToolUse validation, replace open-issues notification
- Skills: simplify capture, query, introspect, reindex to decisions-only
- Tests: remove test_write_finding, test_write_issue, test_issue_status;
  convert remaining finding/issue signals to decisions
- CLAUDE.md + README.md: update all references

CLAUDE.md                                 | 17 +++---
 plugins/engram/hooks/hooks.json           |  4 +-
 plugins/engram/hooks/session-start.sh     | 18 ++----
 plugins/engram/lib.sh                     |  8 +--
 plugins/engram/schema.sql                 |  3 +-
 plugins/engram/schemas/README.md          | 28 +++------
 plugins/engram/schemas/finding.md         | 40 -------------
 plugins/engram/schemas/issue.md           | 42 -------------
 plugins/engram/skills/capture/SKILL.md    | 59 +++++-------------
 plugins/engram/skills/introspect/SKILL.md | 99 +++++++++----------------------
 plugins/engram/skills/query/SKILL.md      | 55 +++++++----------
 plugins/engram/skills/reindex/SKILL.md    |  6 +-
 12 files changed, 90 insertions(+), 289 deletions(-)

## Rationale

100% of generated signals were decisions. Auto-ingest only creates decisions, and nothing triggers finding/issue creation automatically. The unused types were dead code that diluted engram's focus as a decision memory system.

## Alternatives

- Keep types as future extensibility — YAGNI; can re-add if a real use case emerges
- Archive types in docs only — still leaves dead code paths in the implementation
