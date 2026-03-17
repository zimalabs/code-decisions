+++
date = 2026-03-17
tags = ["schema", "cleanup", "release"]
links = ["related:polish-schema-for-release"]
source = "git:82e323c5a5858d597e2de1bb858eadb1941dafda"
+++

# Polish schema for release: merge valid+status, remove supersedes column, rename file_stem→slug

Simplify the data schema ahead of release:
- Merge `valid` (int) + `status` (text) into unified `status` with CHECK('active','withdrawn','invalid')
- Remove denormalized `supersedes` column — links table is the single source of truth
- Rename `file_stem` → `slug` to match terminology everywhere (CLAUDE.md, _slugify(), filenames)
- Drop unused `created_at` column
- Simplify link types to supersedes + related (remove dead-code blocks/blocked-by)

No migration needed — index.db is rebuilt from scratch every session.

## Rationale

Dual valid/status state confused query patterns (`WHERE valid=1 AND status='active'`). `file_stem` didn't match the "slug" terminology used in CLAUDE.md, schemas, `_slugify()`, and filenames. Unifying before release avoids baking inconsistency into the public API.

## Alternatives

- Keep both valid and status — every query already combines them, so dual state is pointless
- Keep file_stem naming — diverges from all documentation and function names

.engram/decisions/polish-schema-for-release.md | 22 ++++++++
 CLAUDE.md                                      |  5 +-
 plugins/engram/hooks/notification.sh           |  4 +-
 plugins/engram/hooks/stop.sh                   |  4 +-
 plugins/engram/lib.sh                          | 66 +++++++++++------------
 plugins/engram/schema.sql                      |  9 ++--
 plugins/engram/schemas/decision.md             |  6 +--
 plugins/engram/skills/capture/SKILL.md         |  2 +
 plugins/engram/skills/query/SKILL.md           | 25 +++++----
 plugins/engram/tests/test_engram.sh            | 74 ++++++++++++--------------
 10 files changed, 119 insertions(+), 98 deletions(-)
