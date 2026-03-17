+++
date = 2026-03-17
tags = ["skills", "conventions"]
links = ["related:standardize-skill-prefix-to-slash"]
source = "git:0680e0c32569a18c56e816645fdfc98252db2215"
+++

# Fix skill prefix: replace @engram: with /engram: (standard slash command syntax)

Also fix engram:policies skill name (was missing engram: prefix) and remove non-standard user_invocable field.

.../decisions/standardize-skill-prefix-to-slash.md | 18 ++++++++++
 CHANGELOG.md                                       |  2 +-
 CLAUDE.md                                          |  4 +--
 README.md                                          | 16 ++++-----
 plugins/engram/README.md                           | 42 +++++++++++-----------
 plugins/engram/engram/_policy_defs.py              | 18 +++++-----
 plugins/engram/engram/store.py                     |  2 +-
 plugins/engram/skills/backfill/SKILL.md            |  2 +-
 plugins/engram/skills/brief/SKILL.md               |  2 +-
 plugins/engram/skills/capture/SKILL.md             |  4 +--
 plugins/engram/skills/introspect/SKILL.md          |  4 +--
 plugins/engram/skills/policies/SKILL.md            |  7 ++--
 plugins/engram/skills/query/SKILL.md               |  2 +-
 plugins/engram/skills/resync/SKILL.md              |  2 +-
 plugins/engram/tests/test_engram.py                |  4 +--
 15 files changed, 73 insertions(+), 56 deletions(-)

## Rationale

Claude Code uses `/` as the standard prefix for slash commands and skills. The `@` prefix was non-standard and confused both users and agents about how to invoke engram skills.

## Alternatives

- Keep `@` prefix — diverges from platform convention, causes invocation failures
