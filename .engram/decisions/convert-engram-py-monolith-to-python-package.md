+++
date = 2026-03-17
tags = ["architecture", "migration"]
links = ["related:convert-engram-py-to-package"]
source = "git:841d5737bab3155a3acc39964e46f49d80d90fd5"
status = "withdrawn"
+++

# Convert engram.py monolith to Python package

Split the 1068-line engram.py into a proper package (engram/) with focused
modules: _constants, _helpers, _frontmatter, signal, _commits, store,
_validate, and __main__. Hooks and skills now use `python3 -m engram` via
PYTHONPATH instead of direct script invocation. All 183 tests pass unchanged.

CLAUDE.md                                     |  11 +-
 Makefile                                      |   2 +-
 plugins/engram/engram/__init__.py             |  20 ++
 plugins/engram/engram/__main__.py             |  88 +++++
 plugins/engram/engram/_commits.py             |  72 ++++
 plugins/engram/engram/_constants.py           |  35 ++
 plugins/engram/engram/_frontmatter.py         |  33 ++
 plugins/engram/engram/_helpers.py             |  76 +++++
 plugins/engram/engram/_validate.py            |  58 ++++
 plugins/engram/engram/signal.py               | 125 +++++++
 plugins/engram/{engram.py => engram/store.py} | 475 +-------------------------
 plugins/engram/hooks/post-tool-use.sh         |   6 +-
 plugins/engram/hooks/pre-compact.sh           |   6 +-
 plugins/engram/hooks/pre-tool-use.sh          |   4 +-
 plugins/engram/hooks/session-end.sh           |   4 +-
 plugins/engram/hooks/session-start.sh         |  10 +-
 plugins/engram/skills/backfill/SKILL.md       |   4 +-
 plugins/engram/skills/brief/SKILL.md          |   2 +-
 plugins/engram/skills/query/SKILL.md          |   2 +-
 plugins/engram/skills/resync/SKILL.md         |   2 +-
 20 files changed, 548 insertions(+), 487 deletions(-)

## Rationale

The 1068-line single file was hard to navigate — constants, helpers, dataclass, store, validation, and CLI all in one place. Splitting into focused modules makes it easier to find and reason about each concern.

## Alternatives

- Keep single file with better section headers — doesn't scale as the codebase grows
- Full package with subpackages — over-engineering for the current size
