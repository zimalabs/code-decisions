---
name: "policy-evaluation-order"
description: "Policies evaluate BLOCK → LIFECYCLE → CONTEXT → NUDGE with fail-fast on block/reject"
date: "2026-03-24"
tags:
  - "architecture"
  - "policy"
affects:
  - "src/decision/policy/engine.py"
  - "src/decision/policy/defs.py"
---

# Policy evaluation order

Policies are evaluated in level order: BLOCK (0) → LIFECYCLE (1) → CONTEXT (2) → NUDGE (3). Within each level, order follows registration in `defs.py` — reordering changes behavior.

A policy returning `decision: "block"` or `decision: "reject"` exits immediately (fail-fast). Otherwise, multiple matched policies merge their `system_message`, `additional_context`, and `reason` fields. The plugin always forces `ok=True` on the merged result (advise-only).
