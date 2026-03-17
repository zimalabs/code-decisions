+++
date = 2026-03-17
tags = ["architecture", "migration"]
links = ["related:convert-engram-py-to-package", "related:migrate-signal-frontmatter-from-yaml-to-toml"]
source = "git:a21a150c3a895c01b9734ee12a1b073bf9fff5ef"
+++

# Migrate engram core library from bash to Python

Replace lib.sh (854 LOC) with engram.py (~560 LOC) using stdlib only.
Eliminates 12 SQL injection risks via parameterized queries, replaces
two 80+ LOC frontmatter state machines with shared _parse_frontmatter(),
and removes fragile IFS-based git log parsing.

Hooks stay bash but call `python3 engram.py <command>` instead of
`source lib.sh`. All 183 tests ported to Python and passing.

.../decisions/migrate-core-lib-bash-to-python.md   |   25 +
 CLAUDE.md                                          |   19 +-
 Makefile                                           |    6 +-
 plugins/engram/engram.py                           | 1124 ++++++++
 plugins/engram/hooks/post-tool-use.sh              |    6 +-
 plugins/engram/hooks/pre-compact.sh                |    6 +-
 plugins/engram/hooks/pre-tool-use.sh               |   48 +-
 plugins/engram/hooks/session-end.sh                |    4 +-
 plugins/engram/hooks/session-start.sh              |   10 +-
 plugins/engram/lib.sh                              |  854 ------
 plugins/engram/skills/backfill/SKILL.md            |    4 +-
 plugins/engram/skills/brief/SKILL.md               |    3 +-
 plugins/engram/skills/query/SKILL.md               |    2 +-
 plugins/engram/skills/resync/SKILL.md              |    3 +-
 plugins/engram/tests/test_engram.py                | 2041 ++++++++++++++
 plugins/engram/tests/test_engram.sh                | 2778 --------------------
 16 files changed, 3226 insertions(+), 3707 deletions(-)

## Rationale

12 manual SQL escaping calls via `sed "s/'/''/g"` were injection risks. Parameterized queries in Python's sqlite3 module eliminate this entire class of vulnerability. The bash frontmatter state machines and IFS-based git log parsing were also fragile.

## Alternatives

- Stay with bash and add escaping helpers — still fragile, doesn't address state machine complexity
- Use an external SQL library — unnecessary, stdlib sqlite3 is sufficient
