---
name: engram:capture
description: "Write a signal file to .engram/. Use when the agent makes a significant decision, discovers something important, or identifies an issue. No CLI — just write a markdown file."
---

# @engram:capture

Write a signal file directly to the `.engram/` directory using the Write tool.

## Signal Types

### Decision — Why we chose X
File: `.engram/signals/decision-{slug}.md`

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

### Finding — Why we now know X
File: `.engram/signals/finding-{slug}.md`

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

### Issue — Why X needs attention
File: `.engram/signals/issue-{slug}.md`

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

## Privacy

Signals have two visibility tiers based on directory path:

- **Public** (default): `.engram/signals/`
  - Git-tracked, included in brief, visible in PRs
- **Private**: `.engram/_private/`
  - Git-ignored, excluded from brief, never auto-sent to Claude API

Use private for:
- Messaging content (Slack conversations, emails)
- CRM data (customer details, deal notes)
- Competitive intelligence
- Personnel decisions (hiring, performance)
- Anything you wouldn't put in a commit message

Moving a file between public and private paths changes its visibility on next reindex. The schemas are identical — only the directory determines privacy.

## Execution Steps

1. **Determine type** from context: decision (chose X), finding (discovered X), issue (X needs attention)
2. **Determine privacy**: sensitive content → `.engram/_private/`, everything else → `.engram/signals/`
3. **Generate filename**: `{type}-{slug}.md`
4. **Write the file** using the Write tool with the appropriate schema above
5. **Confirm** to the user what was captured

## Arguments

Parse `$ARGUMENTS` as: `<type> "<title>"` or infer from conversation context.

If no type given:
- Choices or directions set -> `decision`
- New information discovered -> `finding`
- Problems or blockers -> `issue`

## Linking Signals

Use `supersedes:` to mark a signal as replacing a prior one. The superseded signal is hidden from the brief but remains queryable.

```markdown
supersedes: decision-old-auth    # this decision replaces decision-old-auth
```

Use `links:` to express non-supersession relationships:

```markdown
links: [related:finding-fts5-perf, blocks:issue-ci-timeout]
```

### Link Types
- **supersedes** — this signal replaces the target (target hidden from brief)
- **related** — informational connection
- **blocks** — this signal blocks the target from being resolved
- **blocked-by** — this signal is blocked by the target

### Resolving Issues

Don't edit old issue files. Write a new signal that supersedes the old issue:

```markdown
---
date: 2026-03-16
supersedes: issue-ci-slow
---

# CI pipeline optimized to 8 minutes

Parallelized integration tests across 4 workers.
```

## Content Guidelines

- Be specific — "Use Redis for caching because it's already in our stack" not "Redis is good"
- Include the *why*, not just the *what*
- Reference specific files, PRs, or conversations when relevant
- Keep individual signals focused on one thing
- Tags are optional but help with filtering
- Source field is optional (hooks auto-set `git:<hash>` or `plan:<file>`)
