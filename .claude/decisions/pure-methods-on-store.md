---
name: "pure-methods-on-store"
description: "No side effects at import time on DecisionStore"
date: "2026-03-24"
tags:
  - "architecture"
  - "store"
affects:
  - "src/decision/store/store.py"
---

# Pure methods on DecisionStore

DecisionStore methods must not produce side effects at import time. The store is instantiated lazily by SessionState and used across multiple policy evaluations per hook invocation. Import-time side effects would cause unpredictable behavior when the module is loaded by different code paths.
