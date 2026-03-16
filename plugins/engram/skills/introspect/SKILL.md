---
name: engram:introspect
description: "Interactive review loop — fills missing tags, links, body sections, and status on existing signals by asking the user targeted questions."
---

# @engram:introspect

Walk through existing signals and interactively fill gaps: missing tags, body sections, links, and issue status. Groups gaps by type so the user stays in one mental mode per pass.

## Execution Steps

### Phase 1: Discover Gaps

Run these queries against `.engram/index.db` to find signals with missing metadata:

```bash
# Missing tags
sqlite3 -json .engram/index.db "SELECT file_stem, type, title, date, file FROM signals WHERE tags = '[]' OR tags = '' ORDER BY date DESC"

# Decisions missing body sections
sqlite3 -json .engram/index.db "SELECT file_stem, title, date, file FROM signals WHERE type='decision' AND content NOT LIKE '%## Rationale%' AND content NOT LIKE '%## Alternatives%' ORDER BY date DESC"

# Findings missing body sections
sqlite3 -json .engram/index.db "SELECT file_stem, title, date, file FROM signals WHERE type='finding' AND content NOT LIKE '%## Trigger%' AND content NOT LIKE '%## Implications%' ORDER BY date DESC"

# Issues missing body sections
sqlite3 -json .engram/index.db "SELECT file_stem, title, date, file FROM signals WHERE type='issue' AND content NOT LIKE '%## Impact%' AND content NOT LIKE '%## Next steps%' ORDER BY date DESC"

# Issues without status
sqlite3 -json .engram/index.db "SELECT file_stem, title, date, file FROM signals WHERE type='issue' AND status = '' ORDER BY date DESC"

# Unlinked signals (no links in or out)
sqlite3 -json .engram/index.db "SELECT s.file_stem, s.type, s.title, s.date, s.file FROM signals s LEFT JOIN links l1 ON l1.source_file = s.file_stem LEFT JOIN links l2 ON l2.target_file = s.file_stem WHERE l1.source_file IS NULL AND l2.target_file IS NULL ORDER BY s.date DESC"
```

Run all six queries, then present a summary table:

```
Gap Type          Signals
─────────────────────────
Missing tags      N
Missing sections  N  (decisions: N, findings: N, issues: N)
Unlinked          N
Missing status    N  (issues only)
```

Ask the user: **"Start with tags? Or pick a category: tags / sections / links / status / all"**

Use AskUserQuestion for this and all subsequent prompts.

### Phase 2: Loop per Gap Type

Process gap types in this priority order (unless user picks a different one): **tags → body sections → links → issue status**

For each gap type, present signals in batches of 3-5. After each batch, ask: **"Continue / skip to next category / stop?"**

---

#### Tags (lowest friction)

For each signal missing tags:

1. Read the signal file
2. Show: `[type] title (date)` and a 1-line excerpt
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

#### Body Sections (per signal type)

For each signal missing recommended body sections, read the file and ask type-specific questions:

**Decisions** (missing Rationale and/or Alternatives):
1. Show the decision title and lead paragraph
2. Ask: **"What was the rationale for this decision?"**
3. If answered, append `## Rationale` section to end of file
4. Ask: **"What alternatives were considered? (or 'skip')"**
5. If answered, append `## Alternatives` section to end of file

**Findings** (missing Trigger and/or Implications):
1. Show the finding title and lead paragraph
2. Ask: **"What triggered this finding?"**
3. If answered, append `## Trigger` section to end of file
4. Ask: **"What are the implications? (or 'skip')"**
5. If answered, append `## Implications` section to end of file

**Issues** (missing Impact and/or Next steps):
1. Show the issue title and lead paragraph
2. Ask: **"What is the impact of this issue?"**
3. If answered, append `## Impact` section to end of file
4. Ask: **"What are the next steps? (or 'skip')"**
5. If answered, append `## Next steps` section to end of file

Use the Edit tool to append sections. Example:
```
old_string: "<last line of file>"
new_string: "<last line of file>\n\n## Rationale\n\n<user's answer>\n"
```

---

#### Links (most cognitive)

First, fetch all signal titles for reference:

```bash
sqlite3 -json .engram/index.db "SELECT file_stem, type, title FROM signals ORDER BY date DESC"
```

Present the full list of signals as a numbered reference. For each unlinked signal:

1. Show: `[type] title (date)`
2. Ask: **"Related to any of these signals? Enter numbers or 'skip'"**
3. If related, ask: **"Relationship type? related / blocks / blocked-by"**
4. Use the Edit tool to add or update the `links:` line in frontmatter:
   - If `links:` exists, add to the bracket list
   - If no `links:` line, insert after `tags:` (or `date:` if no tags)

Example edit — inserting links:
```
old_string: "tags: [ci, testing]"
new_string: "tags: [ci, testing]\nlinks: [related:decision-reorganize-repo]"
```

---

#### Issue Status

For each issue without a status field:

1. Show: title, date, lead paragraph
2. Ask: **"Still open or resolved?"**
3. If resolved, use the Edit tool to add `status: resolved` to frontmatter:

```
old_string: "date: 2026-03-16"
new_string: "date: 2026-03-16\nstatus: resolved"
```

If open, optionally add `status: open` or leave as-is (absent status = open by convention).

### Phase 3: Summary

After all categories are done (or user stops early), present:

```
Introspection complete.
  Tags added:      N signals
  Sections added:  N signals
  Links added:     N signals
  Status updated:  N signals

The index will rebuild at next session start to pick up these changes.
To rebuild now: source plugins/engram/lib.sh && engram_reindex .engram
```

## Resumability

No special tracking needed. Signals that already have tags won't appear in the "missing tags" query. Signals with body sections won't appear in the "missing sections" query. Running `@engram:introspect` again after partial enrichment picks up only the remaining gaps.

## Notes

- **Editing existing files is OK.** Adding tags, links, and body sections enriches the record without altering what was decided. This is metadata enrichment, not content mutation.
- **The index is derived.** Edits go to the markdown files (source of truth). The index rebuilds from files at next session start/end.
- **Private signals are included.** The gap queries don't filter by privacy — private signals benefit from enrichment too.
