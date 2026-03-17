+++
date = 2026-03-17
tags = ["dx", "schema"]
links = ["related:enrich-signals-add-make-dev-fix-backfill-links"]
+++

# Skip sections gap for auto-ingested signals in find_incomplete

Auto-ingested signals (source: git:* or plan:*) were flagged as missing Rationale/Alternatives sections by find_incomplete, but they can't have those sections without human input. This made the backfill skill report false positives that it then correctly skipped — noisy and confusing.

## Rationale

The sections gap only makes sense for agent-written signals where the agent had context to write rationale but didn't. Auto-ingested signals are commit diffstats — they structurally lack the context needed for rationale sections.

## Alternatives

- Filter in the backfill skill instead of the query — pushes complexity to every consumer
- Add a separate "auto-ingested incomplete" category — over-engineering for a simple boolean check
