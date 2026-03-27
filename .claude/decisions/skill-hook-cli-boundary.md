---
name: "skill-hook-cli-boundary"
description: "Skill = intent + behavior guidance, hooks = correctness enforcement, CLI = data access + computation"
date: "2026-03-27"
tags:
  - "architecture"
  - "skill"
  - "hooks"
  - "cli"
affects:
  - "src/skills/decision/"
  - "src/decision/cli.py"
  - "src/decision/policy/"
---

# Skill says what to do, hooks enforce correctness, CLI provides data access

Each layer does what it's uniquely good at instead of duplicating responsibilities:

- **Skill (SKILL.md)**: Intent routing and behavior guidance for the LLM. Kept thin (~60 lines) — says *what* to do, not *how* to validate. Does not contain templates, field-by-field instructions, or search algorithms.
- **Hooks (policy engine)**: Event-driven correctness enforcement. Content-validation rejects bad decision files and guides fixes. Session-context injects templates lazily. Query-preseed is the authoritative search path. Hooks fire independently of the skill.
- **CLI (python3 -m decision)**: Data access and computation — FTS5 queries, git operations, validation, index management. The skill delegates to CLI for anything requiring subprocess work.

Previously the skill was ~200 lines and duplicated hook logic (capture template, affects auto-fill, Glob/Grep search fallback). This caused three code paths for search, overlapping capture validation, and a skill that tried to be a program instead of a behavior guide.
