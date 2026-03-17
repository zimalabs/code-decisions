+++
date = 2026-03-17
tags = ["schema", "architecture", "hooks"]
+++

# Reduce signal bloat: fewer + higher-quality decisions + compaction

Agents wrote thin signals to satisfy the commit-gate block, not because they had genuine decisions to record. Signals accumulated without lifecycle management. Three changes address this: (1) downgrade commit-gate from BLOCK to NUDGE, (2) tighten auto-ingest filter and validation depth, (3) add signal compaction.

## Rationale

The commit-gate created adversarial compliance — agents learned to write perfunctory signals just to unblock `git commit`. Moving enforcement to a reflection nudge at Stop time produces more thoughtful signals because the agent can look back on completed work. Auto-ingest captured ~50% of commits; tightening skip prefixes and requiring 2+ file changes for dependency-file matches drops this to ~15-20%. Empty section bodies (heading with no content) now fail validation. Compaction archives signals older than 90 days that aren't referenced or pinned.

## Alternatives

- Keep block gate with stricter content checks — still adversarial, agents would just write longer boilerplate
- Remove commit-gate entirely — loses the prompt for agents to consider decisions at all
- TTL-based deletion instead of archival — destroys history, archived signals remain searchable via FTS
- Manual-only archival — doesn't scale, signals accumulate indefinitely

## Trade-offs

- Agents may write fewer signals overall (acceptable — quality over quantity)
- Compaction adds filesystem moves during resync (cheap, ~10ms for typical stores)
- `pin = true` is a new frontmatter field that must be documented
