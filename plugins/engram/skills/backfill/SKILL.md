---
name: engram:backfill
description: "Autonomously enrich incomplete signals — adds missing tags, rationale, alternatives, and links without user interaction."
---

# @engram:backfill

Autonomously enrich incomplete decision signals. No user interaction — infer missing metadata from conversation context and signal content.

## Execution Steps

### Phase 1: Find Incomplete Signals

Run to discover gaps:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/engram.py" find-incomplete .engram 5
```

Output is pipe-delimited: `file_stem|title|gap_types` where gap_types is a comma-separated list of: `tags`, `sections`, `links`.

If no output, respond: "All signals are complete." and stop.

### Phase 2: Classify and Enrich

For each incomplete signal:

1. **Read the signal file** from `.engram/decisions/{file_stem}.md` or `.engram/_private/decisions/{file_stem}.md`
2. **Check the `source:` field** in frontmatter to classify:
   - **No source field** (agent-written): full enrichment — tags, `## Rationale`, `## Alternatives`, links
   - **`source: git:*`** or **`source: plan:*`** (auto-ingested): tags and links only — do NOT add rationale or alternatives (agent has no special context for these)

### Phase 3: Apply Edits

Use the **Edit tool** for surgical changes. Do not rewrite files.

#### Missing Tags

If `tags: []` or no `tags:` line, infer 1-3 tags from the title and body content. Use existing tags from the index as a reference:

```bash
sqlite3 .engram/index.db "SELECT DISTINCT j.value FROM signals, json_each(signals.tags) j WHERE signals.tags != '[]' ORDER BY j.value;"
```

Edit the frontmatter to add tags:
- If `tags: []` exists, replace with `tags: [inferred, tags]`
- If no `tags:` line, insert `tags: [inferred, tags]` after the `date:` line

#### Missing Sections (agent-written signals only)

If the body has neither `## Rationale` nor `## Alternatives`:

1. Infer the rationale from the signal's title, lead paragraph, and your conversation context
2. Append to end of file:

```markdown

## Rationale

<inferred rationale — 1-3 sentences explaining why>

## Alternatives

- <alternative 1>
- <alternative 2>
```

Use Edit tool: match the last line of the file and append the new sections.

#### Missing Links

Check other signals for related decisions:

```bash
sqlite3 -separator '|' .engram/index.db "SELECT file_stem, title FROM signals WHERE file_stem != '{current_stem}' ORDER BY date DESC LIMIT 20;"
```

If a clear relationship exists (same topic, one supersedes another), add a `links:` field:
- If `links:` exists, append to the bracket list
- If no `links:` line, insert after `tags:` (or `date:` if no tags)

Only add links when the relationship is obvious from content. When in doubt, skip.

### Phase 4: Resync

After all edits, rebuild the index:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/engram.py" resync .engram
```

### Phase 5: Report

Summarize what was done:

```
Backfill complete.
  Tags added:     N signals
  Sections added: N signals
  Links added:    N signals
```

## Constraints

- **Process up to 5 signals per run** — keeps the skill fast and focused
- **No AskUserQuestion** — this is fully autonomous
- **Edit, not rewrite** — use Edit tool for surgical changes to preserve file content
- **Prioritize agent-written signals** — signals without `source:` field get full enrichment
- **Auto-ingested signals get limited enrichment** — tags and links only, no rationale/alternatives
- **Respect existing content** — never overwrite existing tags, sections, or links
