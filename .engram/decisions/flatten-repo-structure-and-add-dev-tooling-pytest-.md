+++
date = 2026-03-17
source = "git:8dbfa2e19d046ef3f01bd624b52bd6f1881e6a7a"
+++

# Flatten repo structure and add dev tooling (pytest, ruff, mypy)

Rename plugins/engram/ → plugin/ with src/ layout. Move tests to repo
root so they're excluded from plugin installs. Add pytest, ruff, and
mypy via uv as dev-only deps — plugin remains stdlib-only. Convert
hand-rolled test runner to pytest (136 tests). Fix all ruff and mypy
errors. Update CI to install uv.

.claude-plugin/marketplace.json                    |    2 +-
 .engram/decisions/flatten-repo-add-dev-tooling.md  |   18 +
 .github/workflows/ci.yml                           |    3 +
 .gitignore                                         |   19 +
 CLAUDE.md                                          |   62 +-
 Makefile                                           |   15 +-
 .../engram => plugin}/.claude-plugin/plugin.json   |    0
 {plugins/engram => plugin}/LICENSE                 |    0
 {plugins/engram => plugin}/README.md               |    0
 {plugins/engram => plugin}/hooks/dispatch.sh       |    2 +-
 {plugins/engram => plugin}/hooks/hooks.json        |    0
 {plugins/engram => plugin}/schemas/README.md       |    0
 {plugins/engram => plugin}/schemas/decision.md     |    0
 .../engram => plugin}/schemas/default-config.toml  |    0
 {plugins/engram => plugin}/schemas/schema.sql      |    0
 .../engram => plugin}/skills/backfill/SKILL.md     |    0
 {plugins/engram => plugin}/skills/brief/SKILL.md   |    0
 {plugins/engram => plugin}/skills/capture/SKILL.md |    0
 .../engram => plugin}/skills/introspect/SKILL.md   |    0
 .../engram => plugin}/skills/policies/SKILL.md     |    0
 {plugins/engram => plugin}/skills/query/SKILL.md   |    0
 {plugins/engram => plugin}/skills/resync/SKILL.md  |    0
 {plugins/engram => plugin/src}/engram/__init__.py  |    9 +-
 {plugins/engram => plugin/src}/engram/__main__.py  |    3 +-
 {plugins/engram => plugin/src}/engram/_commits.py  |    0
 .../engram => plugin/src}/engram/_constants.py     |   10 +-
 .../engram => plugin/src}/engram/_frontmatter.py   |    0
 {plugins/engram => plugin/src}/engram/_helpers.py  |    5 +-
 .../engram => plugin/src}/engram/_policy_defs.py   |   25 +-
 {plugins/engram => plugin/src}/engram/_validate.py |    0
 {plugins/engram => plugin/src}/engram/policy.py    |    7 +-
 plugin/src/engram/py.typed                         |    0
 {plugins/engram => plugin/src}/engram/signal.py    |    0
 {plugins/engram => plugin/src}/engram/store.py     |   23 +-
 plugins/engram/.gitignore                          |   38 -
 plugins/engram/tests/run_tests.sh                  |    9 -
 plugins/engram/tests/test_policy.py                | 1088 ---------------
 pyproject.toml                                     |   27 +
 {plugins/engram/tests => tests}/test_engram.py     | 1400 ++++++++------------
 tests/test_policy.py                               |  842 ++++++++++++
 uv.lock                                            |  249 ++++
 41 files changed, 1772 insertions(+), 2084 deletions(-)
