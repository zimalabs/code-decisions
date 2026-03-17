+++
date = 2026-03-16
tags = ["repo-structure", "plugin"]
links = ["related:remove-old-engram-decisions-files-left-over-from-d"]
source = "git:52326197eeb7f2eb5a4393e831b41ee59a60ce29"
+++

# Reorganize repo to plugin marketplace structure

Move plugin code (lib.sh, schema.sql, hooks/, skills/, tests/) into
plugins/engram/ so the repo root serves as the marketplace and the
plugin lives in a subdirectory. Update marketplace.json source path,
Makefile, and CLAUDE.md to match.

 .claude-plugin/marketplace.json                    |  2 +-
 .shellcheckrc                                      |  1 +
 CLAUDE.md                                          | 33 ++++++++++++----------
 Makefile                                           |  4 +--
 .../engram/.claude-plugin}/plugin.json             |  0
 {hooks => plugins/engram/hooks}/hooks.json         |  0
 {hooks => plugins/engram/hooks}/session-end.sh     |  0
 {hooks => plugins/engram/hooks}/session-start.sh   |  0
 lib.sh => plugins/engram/lib.sh                    |  0
 schema.sql => plugins/engram/schema.sql            |  0
 {skills => plugins/engram/skills}/capture/SKILL.md |  0
 {skills => plugins/engram/skills}/query/SKILL.md   |  0
 {tests => plugins/engram/tests}/run_tests.sh       |  0
 {tests => plugins/engram/tests}/test_engram.sh     |  0
 14 files changed, 22 insertions(+), 18 deletions(-)

## Rationale

Marketplace architecture — repo root serves as the marketplace while the plugin lives in a subdirectory, enabling multi-plugin support in the future.

## Alternatives

Flat structure — keep everything at root. Simpler today but doesn't scale for multiple plugins.
