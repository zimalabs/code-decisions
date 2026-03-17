# Signal Schemas

Canonical schema for engram decision signals. This is the source of truth — skills, docs, and tests reference this file.

## Signal Type

| Type | File | Question answered |
|---|---|---|
| [decision](decision.md) | `{slug}.md` | Why we chose X |

## Frontmatter

All decision signals support these fields:

| Field | Required | Format | Description |
|---|---|---|---|
| `date` | yes | `YYYY-MM-DD` | When the signal was created |
| `tags` | no | `["tag1", "tag2"]` | TOML array; first tag = primary tag |
| `source` | no | `"git:<hash>"` or `"plan:<file>"` | Auto-set by hooks during ingestion |
| `supersedes` | no | `"slug"` | File stem of the decision this replaces |
| `links` | no | `["rel:stem"]` | TOML array of relationships |
| `created_at` | no | ISO datetime | Set once at creation; fallback to file birthtime at index |

## Link Types

| Type | Meaning | Effect |
|---|---|---|
| `supersedes` | This decision replaces the target | Target hidden from brief |
| `related` | Informational connection | None (queryable) |

## Privacy

| Directory | Git | Brief | Queryable |
|---|---|---|---|
| `.engram/decisions/` | tracked | included | yes |
| `.engram/_private/decisions/` | ignored | excluded | yes |

The directory path determines privacy. Schema is identical in both directories.

## Filename Convention

`{slug}.md` where slug is lowercase, hyphen-separated, max 50 chars.

The filename stem (without `.md`) is the stable ID used in `supersedes` and `links` fields.
