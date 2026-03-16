# Decision — Why we chose X

File: `.engram/signals/decision-{slug}.md`

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
supersedes: decision-old-slug    # optional: replaces a prior decision
links: [related:finding-x]       # optional: related, blocks, blocked-by
---

# Title of the decision

Why this choice was made.

## Alternatives
- Option A — why not
- Option B — why not

## Rationale
The reasoning behind the choice.

## Trade-offs
What we gave up or risk by choosing this.
```

## Body Sections

- **Lead paragraph** (required): One-line summary of what was decided and why.
- **Alternatives** (recommended): What else was considered and why it was rejected.
- **Rationale** (recommended): The reasoning and constraints that led to this choice.
- **Trade-offs** (optional): What was given up or risked.
