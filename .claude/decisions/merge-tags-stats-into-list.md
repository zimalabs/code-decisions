---
name: "merge-tags-stats-into-list"
description: "Consolidated /decision:tags and /decision:stats into /decision:list as --tags and --stats flags"
date: "2026-03-20"
tags:
  - "skills"
  - "ux"
  - "plugin-architecture"
affects:
  - "src/skills/decision/SKILL.md"
  - "CLAUDE.md"
  - "README.md"
  - "CONTRIBUTING.md"
---

# Merge tags and stats skills into list



`/decision:list` already browses decisions with filtering. Tags (tag counts + drill-down) and stats (health metrics) are lightweight admin views that fit naturally as flags on list. Consolidating reduces skill surface area from 7 to 5, making the plugin easier to discover and remember.

## Alternatives
- Keep three separate skills — preserves discoverability of each view but fragments a single conceptual operation (browsing decisions) across three entry points. Users must remember which skill does what.
- Merge all five browsing/query skills into one — too much overloading; search and list serve fundamentally different purposes (keyword query vs chronological browse).

## Rationale
Tags and stats are read-only views over the same decision corpus that list already enumerates. Adding `--tags` and `--stats` flags is a natural extension — the underlying data source (glob decision files, read frontmatter) is identical. Fewer skills means less cognitive overhead for the agent and a tighter plugin.json surface. The drill-down behavior of `--tags <tag>` subsumes the existing `--tag <tag>` filter with richer output (lead paragraph excerpts).

## Trade-offs
Users who had muscle memory for `/decision:tags` or `/decision:stats` must learn the new flag syntax. Acceptable because the plugin is pre-1.0 and the old names were only weeks old. The list skill's SKILL.md grows longer, but the argument routing keeps each mode's instructions distinct.
