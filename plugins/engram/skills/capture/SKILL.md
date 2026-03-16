---
name: engram:capture
description: "Write a decision signal file to .engram/. Use when the agent makes a significant decision. No CLI — just write a markdown file."
---

# @engram:capture

Write a decision signal file directly to the `.engram/` directory using the Write tool.

## Execution Steps

1. **Read the schema**: `${CLAUDE_PLUGIN_ROOT}/schemas/decision.md`
2. **Determine privacy**: sensitive content → `.engram/_private/`, everything else → `.engram/signals/`
3. **Generate filename**: `decision-{slug}.md`
4. **Write the file** using the Write tool, following the template and body sections from the schema
5. **Confirm** to the user what was captured

## Arguments

Parse `$ARGUMENTS` as: `"<title>"` or infer from conversation context.

## Schema File

The canonical template and field definitions live in `${CLAUDE_PLUGIN_ROOT}/schemas/decision.md`.

**Always read the schema file before writing a signal.** The schema defines required/optional frontmatter fields, the template structure, and recommended body sections.

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

Moving a file between public and private paths changes its visibility on next reindex. The schema is identical — only the directory determines privacy.

## Linking Signals

Use `supersedes:` to mark a decision as replacing a prior one. The superseded decision is hidden from the brief but remains queryable.

```markdown
supersedes: decision-old-auth    # this decision replaces decision-old-auth
```

Use `links:` to express non-supersession relationships:

```markdown
links: [related:decision-redis-cluster]
```

### Link Types
- **supersedes** — this decision replaces the target (target hidden from brief)
- **related** — informational connection

## Content Guidelines

- Be specific — "Use Redis for caching because it's already in our stack" not "Redis is good"
- Include the *why*, not just the *what*
- Reference specific files, PRs, or conversations when relevant
- Keep individual signals focused on one thing
- **Tags are required** — at least one tag (not empty `[]`)
- **Lead paragraph is mandatory** — the first non-empty line after `# Title` must explain "why" and be at least 20 characters. Signals without this are marked invalid and excluded from the brief.
- Source field is optional (hooks auto-set `git:<hash>` or `plan:<file>`)
- **Slug matching tip:** Use a slug that matches the commit subject so auto-ingest defers to your manual signal. E.g., if the commit will be "feat: switch to Redis for caching", name the signal `decision-feat-switch-to-redis-for-caching.md`.
