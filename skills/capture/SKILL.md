---
name: engram:capture
description: "Write a signal file to .engram/. Use when the agent makes a significant decision, discovers something important, or identifies an issue. No CLI — just write a markdown file."
---

# @engram:capture

Write a signal file directly to the `.engram/` directory using the Write tool.

## Signal Types

### Decision — Why we chose X
Directory: `.engram/decisions/`

```markdown
---
date: YYYY-MM-DD
tags: [topic1, topic2]
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
Directory: `.engram/findings/`

```markdown
---
date: YYYY-MM-DD
tags: [topic1, topic2]
---

# Title of the finding

What was discovered.

## Trigger
What led to discovering this.

## Implications
What this means for the project going forward.
```

### Issue — Why X needs attention
Directory: `.engram/issues/`

```markdown
---
date: YYYY-MM-DD
tags: [topic1, topic2]
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

- **Public** (default): `.engram/decisions/`, `.engram/findings/`, `.engram/issues/`
  - Git-tracked, included in brief, visible in PRs
- **Private**: `.engram/private/decisions/`, `.engram/private/findings/`, `.engram/private/issues/`
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
2. **Determine privacy**: sensitive content → `.engram/private/{type}s/`, everything else → `.engram/{type}s/`
3. **Generate filename**: `{YYYY-MM-DD}-{slug}.md`
4. **Write the file** using the Write tool with the appropriate schema above
5. **Confirm** to the user what was captured

## Arguments

Parse `$ARGUMENTS` as: `<type> "<title>"` or infer from conversation context.

If no type given:
- Choices or directions set -> `decision`
- New information discovered -> `finding`
- Problems or blockers -> `issue`

## Content Guidelines

- Be specific — "Use Redis for caching because it's already in our stack" not "Redis is good"
- Include the *why*, not just the *what*
- Reference specific files, PRs, or conversations when relevant
- Keep individual signals focused on one thing
- Tags are optional but help with filtering
- Source field is optional (hooks auto-set `git:<hash>` or `plan:<file>`)
