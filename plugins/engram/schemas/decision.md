# Decision — Why we chose X

File: `.engram/decisions/{slug}.md`

## Frontmatter

| Field | Required | Description |
|---|---|---|
| `date` | yes | ISO date (YYYY-MM-DD) |
| `tags` | yes | Bracket list with at least one tag: `[topic1, topic2]` |
| `source` | no | Origin: `plan:<file>` (auto-set), `git:<hash>` (when git tracking enabled) |
| `supersedes` | no | File stem of the signal this replaces |
| `links` | no | Bracket list: `[related:stem]` |
| `status` | no | Lifecycle status: `active` (default) or `withdrawn` |

## Template

```markdown
---
date: YYYY-MM-DD
tags: [topic1, topic2]
supersedes: old-slug    # optional: replaces a prior decision
links: [related:some-x]          # optional: related
status: active          # optional: active (default) or withdrawn
---

# Title of the decision

Why this choice was made. This lead paragraph is required and must be at least 20 characters — it explains the "why" behind the decision.

## Alternatives
- Option A — why not
- Option B — why not

## Rationale
The reasoning behind the choice.

## Trade-offs
What we gave up or risk by choosing this.
```

## Body Sections

- **Lead paragraph** (required): One-line summary of what was decided and why. Must be at least 20 characters.
- **Alternatives** (recommended): What else was considered and why it was rejected.
- **Rationale** (recommended): The reasoning and constraints that led to this choice.
- **Trade-offs** (optional): What was given up or risked.

## Validation Rules

Signals are validated at index time. Invalid signals are indexed with `status='invalid'` and excluded from the brief.

1. **Frontmatter** — must open and close with `---`
2. **date:** — required, ISO format (YYYY-MM-DD)
3. **tags:** — required, at least one tag (not empty `[]`)
4. **H1 title** — required (`# ...` after frontmatter)
5. **Lead paragraph** — required, first non-empty non-heading line after the title, minimum 20 characters
