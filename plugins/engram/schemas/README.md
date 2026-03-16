# Signal Schemas

Canonical schema for engram decision signals. This is the source of truth — skills, docs, and tests reference this file.

## Signal Type

| Type | File | Question answered |
|---|---|---|
| [decision](decision.md) | `decision-{slug}.md` | Why we chose X |

## Frontmatter

All decision signals support these fields:

| Field | Required | Format | Description |
|---|---|---|---|
| `date` | yes | `YYYY-MM-DD` | When the signal was created |
| `tags` | no | `[tag1, tag2]` | Categorization tags; first tag = primary tag |
| `source` | no | `git:<hash>` or `plan:<file>` | Auto-set by hooks during ingestion |
| `supersedes` | no | `decision-{slug}` | File stem of the decision this replaces |
| `links` | no | `[rel:stem, rel:stem]` | Relationships to other decisions |

## Link Types

| Type | Meaning | Effect |
|---|---|---|
| `supersedes` | This decision replaces the target | Target hidden from brief |
| `related` | Informational connection | None (queryable) |

## Privacy

| Directory | Git | Brief | Queryable |
|---|---|---|---|
| `.engram/signals/` | tracked | included | yes |
| `.engram/_private/` | ignored | excluded | yes |

The directory path determines privacy. Schema is identical in both directories.

## Filename Convention

`decision-{slug}.md` where slug is lowercase, hyphen-separated, max 50 chars.

The filename stem (without `.md`) is the stable ID used in `supersedes:` and `links:` fields.
