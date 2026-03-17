+++
date = 2026-03-17
tags = ["hooks", "architecture", "policy-engine"]
links = ["related:formalize-policy-layer", "related:enforce-signal-integrity-hooks"]
source = "git:b1fceb01aa9f2072aa6d577ee6dbba12eef7de88"
+++

# Formalize policy layer: replace 12 shell hooks with Python policy engine

Turn the ad-hoc collection of hook scripts into a principled policy engine.
Every hook is now a thin dispatcher (dispatch.sh) that pipes stdin to
`python3 -m engram policy <event>`, which evaluates 15 registered policies
in priority order: BLOCK → LIFECYCLE → CONTEXT → NUDGE.

- Add policy.py (engine framework) and _policy_defs.py (15 policies)
- Add dispatch.sh (8-line universal dispatcher)
- Add test_policy.py (52 tests) and policies skill for introspection
- Delete 12 old shell scripts, unify session state to single /tmp dir
- Update all existing tests to use dispatch.sh

.engram/decisions/formalize-policy-layer.md |  29 ++
 CLAUDE.md                                   |  22 +-
 Makefile                                    |   2 +
 plugins/engram/engram/__init__.py           |   6 +-
 plugins/engram/engram/__main__.py           |  33 ++
 plugins/engram/engram/_policy_defs.py       | 634 +++++++++++++++++++++++++
 plugins/engram/engram/policy.py             | 222 +++++++++
 plugins/engram/hooks/dispatch.sh            |   8 +
 plugins/engram/hooks/hooks.json             |  29 +-
 plugins/engram/hooks/notification.sh        |  25 -
 plugins/engram/hooks/post-push-resync.sh    |  28 --
 plugins/engram/hooks/post-tool-use.sh       |  78 ---
 plugins/engram/hooks/pre-commit-gate.sh     |  40 --
 plugins/engram/hooks/pre-compact.sh         |  26 -
 plugins/engram/hooks/pre-delete-guard.sh    |  39 --
 plugins/engram/hooks/pre-tool-use.sh        |  52 --
 plugins/engram/hooks/session-end.sh         |  16 -
 plugins/engram/hooks/session-start.sh       |  71 ---
 plugins/engram/hooks/stop.sh                |  42 --
 plugins/engram/hooks/subagent-stop.sh       |  39 --
 plugins/engram/hooks/user-prompt-submit.sh  |  34 --
 plugins/engram/skills/policies/SKILL.md     |  25 +
 plugins/engram/tests/test_engram.py         | 186 ++++----
 plugins/engram/tests/test_policy.py         | 708 ++++++++++++++++++++++++++++
 24 files changed, 1791 insertions(+), 603 deletions(-)

## Rationale

12 independent shell scripts with duplicated logic were hard to maintain and extend. A centralized Python policy engine with priority ordering (BLOCK → LIFECYCLE → CONTEXT → NUDGE) makes adding new policies a one-function change.

## Alternatives

- Keep shell scripts with shared helpers — still fragile, harder to test
- YAML/JSON config for policies — less expressive than Python condition functions
