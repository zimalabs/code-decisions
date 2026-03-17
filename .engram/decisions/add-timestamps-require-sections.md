+++
date = 2026-03-17
tags = ["schema", "validation"]
+++

# Add timestamps and require Rationale/Alternatives sections

Signals lacked lifecycle timestamps and body section enforcement. Added `created_at`/`updated_at` tracking and made `## Rationale` and `## Alternatives` required for valid signals.

## Alternatives
- Timestamps only — wouldn't improve signal quality, just tracking
- Sections as recommended (no enforcement) — status quo was producing too many incomplete signals
- Validate Trade-offs too — over-strict, not every decision has meaningful trade-offs

## Rationale
`date` is the decision date (can be backdated), but there was no record of when the file was created or last modified. `created_at` in frontmatter (set once) plus `updated_at` from mtime at index time gives full lifecycle. Required sections ensure every signal captures the "why" — the core value proposition of engram. Withdrawn signals are exempt from validation since they're historical records.

## Trade-offs
- Existing manual signals missing sections will become `status='invalid'` on next reindex — requires backfill pass
- Auto-ingested signals (git/plan source) were already invalid due to missing tags, so no visible change there
