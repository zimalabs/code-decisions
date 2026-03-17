+++
date = 2026-03-17
tags = ["schema", "cleanup", "release"]
links = ["related:polish-schema-for-release-merge-valid-status-remov", "related:add-status-field"]
+++

# Polish engram data schema for release

Simplified the schema by merging `valid` (integer) + `status` (text) into a unified `status` column with three values: active, withdrawn, invalid. Removed the denormalized `supersedes` column (links table is the single source), renamed `file_stem` → `slug` to match terminology used everywhere else, dropped unused `created_at` column, and simplified link types to just supersedes + related (removed dead-code blocks/blocked-by). Since index.db is rebuilt from scratch every session, no migration was needed.

## Rationale

The dual valid/status state created confusing query patterns (`WHERE valid=1 AND status='active'`). The supersedes column duplicated data already in the links table. file_stem didn't match the "slug" terminology in CLAUDE.md, schemas, _slugify(), and filenames. created_at was never queried. blocks/blocked-by had zero real usage.

## Alternatives

- Keep both valid and status — rejected because every query already combines them
- Keep supersedes column as a convenience — rejected because it creates two sources of truth

## Trade-offs

Existing @engram:query SQL examples using old column names will break (updated in SKILL.md). Hooks that referenced valid=0 needed updating.
