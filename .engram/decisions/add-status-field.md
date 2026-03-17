+++
date = 2026-03-17
tags = ["schema", "lifecycle"]
links = ["related:add-visualize-skill"]
+++

# Add status field for decision lifecycle

Decisions like `add-visualize-skill` recorded features that were never implemented but appeared in the brief as current. The `supersedes` mechanism only handles replacement — there was no way to mark a decision as simply "no longer relevant." Added a `status` frontmatter field (`active`|`withdrawn`) so decisions can be retired by editing their frontmatter without deleting the file.

## Alternatives

- Delete signal files — violates append-only architecture rule
- Add an `archived` directory — adds a third privacy tier, complicates path logic
- Use `supersedes` with a "null" target — semantic abuse, confusing to query

## Rationale

A frontmatter field is the simplest mechanism that preserves decision history while keeping the brief clean. It follows the existing pattern (markdown is source of truth, SQLite is derived) and requires minimal code changes — just filtering queries.
