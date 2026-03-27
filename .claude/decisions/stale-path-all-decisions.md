---
name: "stale-path-all-decisions"
description: "Stale affects-path warnings fire for all decision writes, not just new ones"
date: "2026-03-26"
tags:
  - "affects"
  - "ux"
affects:
  - "src/decision/policy/content_validation.py"
---

# Stale-path check on all decision writes

The `_check_affects()` function in `content_validation.py` warns about stale `affects:` paths on both new and existing decisions. Previously this only fired for new files, but stale paths silently degrade proximity matching over time as files are renamed or deleted. Since the plugin is advisory-only, the warning is low-cost and catches drift early.
