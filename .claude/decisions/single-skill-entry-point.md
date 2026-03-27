---
name: "single-skill-entry-point"
description: "One /decision skill handles capture, search, and manage via intent detection"
date: "2026-03-24"
tags:
  - "architecture"
  - "skills"
affects:
  - "src/skills/decision/SKILL.md"
---

# Single skill entry point

`/decision` is the only user-facing skill. It handles capture, search, list, config, review, undo, and debug via intent detection in `SKILL.md`. No separate `/decision:search`, `/decision:capture`, etc.

This reduces cognitive load (one command to remember) and lets the skill route intelligently based on natural language. Earlier iterations had 7+ separate skills which was confusing and hard to maintain.
