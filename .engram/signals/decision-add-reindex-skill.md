---
type: decision
date: 2026-03-16
tags: [skill, dx]
---

Add `@engram:reindex` skill so users can rebuild the index after editing signals without waiting for next session start. Runs the same pipeline as session-start hook: ingest_commits → ingest_plans → reindex → brief.
