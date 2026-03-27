---
name: "no-capture-confirmation"
description: "Agents write decisions automatically without confirmation prompts — /decision undo is the safety net"
date: "2026-03-24"
tags:
  - "architecture"
  - "capture"
affects:
  - "src/decision/policy/content_validation.py"
  - "src/skills/decision/SKILL.md"
---

# No confirmation prompts on capture

Agents must write decision files directly without asking "should I capture this?" or showing a preview for approval. Low friction is the priority — if the agent detects decision language, it writes the file immediately.

`/decision undo` exists as the safety net for bad captures. Interactive confirmation would kill the auto-capture workflow that makes this plugin valuable.
