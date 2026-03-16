# Issue — Why X needs attention

File: `.engram/signals/issue-{slug}.md`

## Frontmatter

| Field | Required | Description |
|---|---|---|
| `date` | yes | ISO date (YYYY-MM-DD) |
| `tags` | no | Bracket list: `[topic1, topic2]` |
| `source` | no | Origin: `git:<hash>`, `plan:<file>` (auto-set by hooks) |
| `status` | no | `open` (default when absent) or `resolved` |
| `supersedes` | no | File stem of the signal this replaces |
| `links` | no | Bracket list: `[blocks:stem, blocked-by:stem]` |

## Template

```markdown
---
date: YYYY-MM-DD
tags: [topic1, topic2]
status: open                     # optional: open (default) or resolved
supersedes: issue-old-slug       # optional: replaces a prior issue
links: [blocks:issue-y]          # optional: related, blocks, blocked-by
---

# Title of the issue

Description of the problem.

## Impact
How this affects the project, team, or users.

## Next steps
What should be done about it.
```

## Body Sections

- **Lead paragraph** (required): One-line summary of the problem.
- **Impact** (recommended): Who or what is affected and how severely.
- **Next steps** (recommended): What should be done to resolve this.
