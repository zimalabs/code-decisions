---
type: decision
date: 2026-03-16
tags: [skill, visualization, dashboard]
---

# Add @engram:visualize skill for HTML dashboard generation

Users had no way to see signals visually — all output was text-based SQL. Added a skill that generates a self-contained HTML dashboard with timeline, type distribution doughnut, tag frequency bars, SVG link graph, and a searchable/filterable signal table.

Single new file: `plugins/engram/skills/visualize/SKILL.md`. No changes to lib.sh, hooks, schema, or any other files. Uses Chart.js via CDN for charts, pure SVG for link graph, vanilla JS for table interactivity. Dark theme with CSS custom properties.
