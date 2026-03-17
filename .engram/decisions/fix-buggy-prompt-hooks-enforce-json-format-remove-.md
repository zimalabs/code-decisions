+++
date = 2026-03-16
tags = ["hooks", "quality"]
links = ["related:add-six-hooks-for-decision-capture"]
source = "git:474fc0f5bf231d4c6204ff6f89f86eab8644fa95"
+++

# Fix buggy prompt hooks: enforce JSON format, remove systemMessage refs

All 7 prompt hooks had broken output format — they used informal language
("return 'block'") and referenced systemMessage (command-hook only).
Rewrites every prompt to require valid JSON {"ok": true/false, "reason": "..."}
and explicitly marks SKILL.md as functional code, not documentation.
Adds test_hooks_json_prompts with 11 assertions guarding these invariants.

plugins/engram/hooks/hooks.json     | 14 ++++-----
 plugins/engram/tests/test_engram.sh | 62 +++++++++++++++++++++++++++++++++++++
 2 files changed, 69 insertions(+), 7 deletions(-)

## Rationale

All 7 prompt hooks used informal language ("return 'block'") and referenced the non-existent `systemMessage` API (command-hook only). The incorrect output format caused hooks to silently fail instead of blocking or advising as intended.

## Alternatives

- Fix hooks individually — risk of inconsistency; batch rewrite with shared test assertions is more reliable
