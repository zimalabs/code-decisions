---
name: "bash-dispatch-fast-paths"
description: "dispatch.sh avoids spawning Python for no-op hook events via fast-paths"
date: "2026-03-24"
tags:
  - "architecture"
  - "performance"
  - "hooks"
affects:
  - "src/hooks/dispatch.sh"
  - "src/decision/utils/constants.py"
---

# Bash dispatch fast-paths

`dispatch.sh` is the hook entry point and avoids spawning Python when the event will produce `{}`. Two fast-paths:

1. **UserPromptSubmit**: Skip unless input contains `/decision` or exceeds 60 bytes
2. **PostToolUse**: Skip when file path matches test/config/doc patterns

Skip patterns in `dispatch.sh` must stay in sync with `SKIP_FILE_PATTERNS` in `utils/constants.py`. Python startup (~100ms) on every hook event would make the plugin feel sluggish.
