---
type: decision
date: 2026-03-16
tags: [skill, visualization, dashboard]
links: [related:add-reindex-skill]
status: withdrawn
---

# Add @engram:visualize skill for HTML dashboard generation

Users had no way to see signals visually — all output was text-based SQL. Added a skill that generates a self-contained HTML dashboard with timeline, type distribution doughnut, tag frequency bars, SVG link graph, and a searchable/filterable signal table.

Single new file: `plugins/engram/skills/visualize/SKILL.md`. No changes to lib.sh, hooks, schema, or any other files. Uses Chart.js via CDN for charts, pure SVG for link graph, vanilla JS for table interactivity. Dark theme with CSS custom properties.

## Rationale

Text-based SQL output is hard to scan for patterns — a visual dashboard lets users spot trends (clustering of decisions around certain dates/tags, orphaned signals with no links) at a glance. Self-contained HTML means zero deployment overhead.

## Alternatives

- Terminal-based TUI — limited chart rendering, harder to share
- Markdown table output — no interactivity, no charts
- External dashboard tool (Grafana, etc.) — heavy dependency for a plugin
