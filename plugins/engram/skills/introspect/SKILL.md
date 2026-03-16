---
name: engram:introspect
description: "Interactive review loop — fills missing tags, links, and body sections on existing decisions by asking the user targeted questions."
---

# @engram:introspect

Walk through existing decisions and interactively fill gaps: missing tags, body sections, and links. Groups gaps by type so the user stays in one mental mode per pass.

## Execution Steps

### Phase 1: Discover Gaps

Run these queries against `.engram/index.db` to find decisions with missing metadata:

```bash
# Missing tags
sqlite3 -json .engram/index.db "SELECT file_stem, title, date, file FROM signals WHERE tags = '[]' OR tags = '' ORDER BY date DESC"

# Decisions missing body sections
sqlite3 -json .engram/index.db "SELECT file_stem, title, date, file FROM signals WHERE content NOT LIKE '%## Rationale%' AND content NOT LIKE '%## Alternatives%' ORDER BY date DESC"

# Unlinked decisions (no links in or out)
sqlite3 -json .engram/index.db "SELECT s.file_stem, s.title, s.date, s.file FROM signals s LEFT JOIN links l1 ON l1.source_file = s.file_stem LEFT JOIN links l2 ON l2.target_file = s.file_stem WHERE l1.source_file IS NULL AND l2.target_file IS NULL ORDER BY s.date DESC"
```

Run all three queries, then present a summary table:

```
Gap Type          Decisions
─────────────────────────
Missing tags      N
Missing sections  N
Unlinked          N
```

Ask the user: **"Start with tags? Or pick a category: tags / sections / links / all"**

Use AskUserQuestion for this and all subsequent prompts.

### Phase 2: Loop per Gap Type

Process gap types in this priority order (unless user picks a different one): **tags → body sections → links**

For each gap type, present decisions in batches of 3-5. After each batch, ask: **"Continue / skip to next category / stop?"**

---

#### Tags (lowest friction)

For each decision missing tags:

1. Read the signal file
2. Show: `title (date)` and a 1-line excerpt
3. Ask: **"What tags? (comma-separated, or 'skip')"**
4. If tags provided, use the Edit tool to update the frontmatter:
   - If `tags:` line exists, replace it
   - If no `tags:` line, insert `tags: [tag1, tag2]` after the `date:` line

Example edit — inserting tags after date:
```
old_string: "date: 2026-03-16"
new_string: "date: 2026-03-16\ntags: [architecture, repo-structure]"
```

---

#### Body Sections

For each decision missing recommended body sections (Rationale and/or Alternatives):

1. Show the decision title and lead paragraph
2. Ask: **"What was the rationale for this decision?"**
3. If answered, append `## Rationale` section to end of file
4. Ask: **"What alternatives were considered? (or 'skip')"**
5. If answered, append `## Alternatives` section to end of file

Use the Edit tool to append sections. Example:
```
old_string: "<last line of file>"
new_string: "<last line of file>\n\n## Rationale\n\n<user's answer>\n"
```

---

#### Links (most cognitive)

First, fetch all decision titles for reference:

```bash
sqlite3 -json .engram/index.db "SELECT file_stem, title FROM signals ORDER BY date DESC"
```

Present the full list of decisions as a numbered reference. For each unlinked decision:

1. Show: `title (date)`
2. Ask: **"Related to any of these decisions? Enter numbers or 'skip'"**
3. If related, ask: **"Relationship type? related / supersedes"**
4. Use the Edit tool to add or update the `links:` line in frontmatter:
   - If `links:` exists, add to the bracket list
   - If no `links:` line, insert after `tags:` (or `date:` if no tags)

Example edit — inserting links:
```
old_string: "tags: [ci, testing]"
new_string: "tags: [ci, testing]\nlinks: [related:decision-reorganize-repo]"
```

### Phase 3: Summary

After all categories are done (or user stops early), present:

```
Introspection complete.
  Tags added:      N decisions
  Sections added:  N decisions
  Links added:     N decisions

The index will rebuild at next session start to pick up these changes.
To rebuild now: source plugins/engram/lib.sh && engram_reindex .engram
```

## Resumability

No special tracking needed. Decisions that already have tags won't appear in the "missing tags" query. Decisions with body sections won't appear in the "missing sections" query. Running `@engram:introspect` again after partial enrichment picks up only the remaining gaps.

## Notes

- **Editing existing files is OK.** Adding tags, links, and body sections enriches the record without altering what was decided. This is metadata enrichment, not content mutation.
- **The index is derived.** Edits go to the markdown files (source of truth). The index rebuilds from files at next session start/end.
- **Private decisions are included.** The gap queries don't filter by privacy — private decisions benefit from enrichment too.
