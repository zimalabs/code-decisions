---
name: "team-first-decisions"
description: "Decisions write to .claude/decisions/ in repo by default. Memory is fallback for non-repo contexts only."
date: "2026-03-23"
tags:
  - "architecture"
  - "storage"
affects:
  - "src/decision/store/"
  - "src/decision/policy/"
  - "src/skills/decision/SKILL.md"
---

# Team-first decisions: write to repo, not memory



Decisions write directly to `.claude/decisions/{slug}.md` with `.claude/rules/decisions.md` as the index. Memory path (`~/.claude/projects/*/memory/`) is only used when there's no git repo.

**Why:** The memory→publish flow was complex and buggy (publish timing, transform, staging, fast-path conflicts). During demo testing, writing directly to the repo worked perfectly — zero bugs, zero concepts to learn, zero "unpublished" nudges. The simplicity wins.

**Implications:**
- No publish flow (removed entirely)
- No two-layer model (single source of truth)
- No slug collision logic (one location)
- Decisions appear in PRs alongside code (feature, not bug)
- Index auto-regenerated from files
