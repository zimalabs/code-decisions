# Finding — Why we now know X

File: `.engram/signals/finding-{slug}.md`

## Frontmatter

| Field | Required | Description |
|---|---|---|
| `date` | yes | ISO date (YYYY-MM-DD) |
| `tags` | no | Bracket list: `[topic1, topic2]` |
| `source` | no | Origin: `git:<hash>`, `plan:<file>` (auto-set by hooks) |
| `supersedes` | no | File stem of the signal this replaces |
| `links` | no | Bracket list: `[related:stem, blocks:stem]` |

## Template

```markdown
---
date: YYYY-MM-DD
tags: [topic1, topic2]
supersedes: finding-old-slug     # optional: replaces a prior finding
links: [related:decision-x]     # optional: related, blocks, blocked-by
---

# Title of the finding

What was discovered.

## Trigger
What led to discovering this.

## Implications
What this means for the project going forward.
```

## Body Sections

- **Lead paragraph** (required): One-line summary of what was discovered.
- **Trigger** (recommended): What event or observation led to the discovery.
- **Implications** (recommended): How this affects the project going forward.
