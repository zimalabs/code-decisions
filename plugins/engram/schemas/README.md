# Signal Schemas

Canonical schemas for engram signal types. These are the source of truth — skills, docs, and tests reference these files.

## Signal Types

| Type | File | Question answered |
|---|---|---|
| [decision](decision.md) | `decision-{slug}.md` | Why we chose X |
| [finding](finding.md) | `finding-{slug}.md` | Why we now know X |
| [issue](issue.md) | `issue-{slug}.md` | Why X needs attention |

## Shared Frontmatter

All signal types support these fields:

| Field | Required | Format | Description |
|---|---|---|---|
| `date` | yes | `YYYY-MM-DD` | When the signal was created |
| `tags` | no | `[tag1, tag2]` | Categorization tags; first tag = primary tag |
| `source` | no | `git:<hash>` or `plan:<file>` | Auto-set by hooks during ingestion |
| `supersedes` | no | `{type}-{slug}` | File stem of the signal this replaces |
| `links` | no | `[rel:stem, rel:stem]` | Relationships to other signals |

Issue-only fields:

| Field | Required | Format | Description |
|---|---|---|---|
| `status` | no | `open` or `resolved` | Default: `open` (when absent) |

## Link Types

| Type | Meaning | Effect |
|---|---|---|
| `supersedes` | This signal replaces the target | Target hidden from brief |
| `related` | Informational connection | None (queryable) |
| `blocks` | This signal blocks the target | Shown in issue queries |
| `blocked-by` | This signal is blocked by the target | Shown in issue queries |

## Privacy

| Directory | Git | Brief | Queryable |
|---|---|---|---|
| `.engram/signals/` | tracked | included | yes |
| `.engram/_private/` | ignored | excluded | yes |

The directory path determines privacy. Schemas are identical in both directories.

## Filename Convention

`{type}-{slug}.md` where slug is lowercase, hyphen-separated, max 50 chars.

The filename stem (without `.md`) is the stable ID used in `supersedes:` and `links:` fields.
