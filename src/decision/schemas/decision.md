# Decision — Why we chose X

File: `.claude/decisions/{slug}.md`

## Storage

Decisions live at `.claude/decisions/{slug}.md` in the repo — committed to git and shared with the team. No `decision_` prefix; filenames are just `{slug}.md`.

## Schema

| Field | Required | Description |
|---|---|---|
| `name` | yes | Slug identifier (matches filename stem) |
| `description` | yes | One-line summary of the decision |
| `date` | yes | ISO date (YYYY-MM-DD) |
| `tags` | yes | List with at least one tag |
| `affects` | **recommended** | List of file paths, directories, or glob patterns this decision relates to. **This is the plugin's most valuable field** — it enables proximity-triggered context injection. When someone edits an affected file, this decision automatically surfaces. Without `affects`, the decision only appears via manual search. Entries ending with `/` match all files under that directory (e.g., `"src/auth/"`). Entries with `*`/`?` use glob matching (e.g., `"src/auth/*.py"`). |

## Template

```markdown
---
name: "slug-name"
description: "One-line summary"
date: "YYYY-MM-DD"
tags:
  - "topic"
affects:
  - "src/affected_file.py"
---

# Title of the decision

Why this choice was made. At least 20 characters.
```

## Body

- **Lead paragraph** (required): One-line summary of what was decided and why. Must be at least 20 characters.

Additional sections (Rationale, Alternatives, Trade-offs) are encouraged but not enforced. The lead paragraph is the minimum — write more when the reasoning is non-obvious.

## Validation Rules

1. **Frontmatter** — must open and close with `---`
2. **date** — required, ISO format (YYYY-MM-DD)
3. **tags** — required, at least one tag
4. **H1 title** — required (`# ...` after frontmatter)
5. **Lead paragraph** — required, first non-empty non-heading line, minimum 20 characters

## Qualification Gate

Before writing a decision, evaluate:

1. Is this a **choice between alternatives**? (not just "we did X")
2. Would a future agent benefit from knowing **why** this choice was made?
3. Are there **non-obvious trade-offs** or constraints?
4. Could this decision be **reversed**, and would someone need the original reasoning?

> Yes to any? Write the decision. No to all? Commit message is enough.

## Decision Evolution

Decisions are **edit-in-place** — update the existing file when a decision evolves. Git tracks the full history.

1. **Update**: Edit the decision file directly. `git log -p` shows what changed and when.
2. **Consolidate**: When multiple decisions cover the same topic, merge them into one file and delete the others.
3. **Remove**: Delete a decision file when it's no longer relevant. Git preserves the history.

The plugin detects overlapping decisions at capture time (shared tags or affects paths) and nudges consolidation.

## Integrity

Git provides content-addressable storage (SHA-256), tamper detection, and cryptographic signing. The plugin does not add its own integrity layer — it leverages git:

- `git config commit.gpgsign true` enables cryptographic non-repudiation (recommended for compliance)
- Git's immutable commit history preserves the full evolution of every decision
