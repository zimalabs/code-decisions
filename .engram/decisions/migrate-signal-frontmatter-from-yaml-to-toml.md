+++
date = 2026-03-17
tags = ["schema", "migration", "signals"]
links = ["related:migrate-engram-core-library-from-bash-to-python"]
source = "git:2f3f0d366d63dd937cafb98a3212dbb707069e46"
+++

# Migrate signal frontmatter from YAML to TOML

Replace custom YAML-like line parser with stdlib tomllib (Python 3.11+).
Signals now use +++ delimiters and native TOML types: dates parse as
datetime.date, tags/links parse as arrays. Drop the `type` field (always
"decision", implied by path). Remove _normalize_tags() and _FM_FIELDS.

Migrate all 21 existing .engram/decisions/ files in-place.

.../decisions/add-automatic-context-injection.md   |   9 +-
 ...-workflow-security-policy-funding-faq-and-go.md |  13 +-
 .engram/decisions/add-reindex-skill.md             |   9 +-
 .../add-six-hooks-for-decision-capture.md          |   9 +-
 .engram/decisions/add-status-field.md              |  11 +-
 .engram/decisions/add-stop-hook-enforce-signals.md |   9 +-
 .engram/decisions/add-visualize-skill.md           |  13 +-
 .engram/decisions/convert-engram-py-to-package.md  |   9 +-
 ...nforce-decision-structure-with-mandatory-why.md |  11 +-
 .../decisions/enforce-signal-integrity-hooks.md    |  11 +-
 ...i-install-homebrew-sqlite-with-fts5-on-macos.md |  13 +-
 .engram/decisions/formalize-policy-layer.md        |   9 +-
 .engram/decisions/git-opt-in.md                    |  11 +-
 .../decisions/migrate-core-lib-bash-to-python.md   |   9 +-
 .engram/decisions/polish-schema-for-release.md     |   9 +-
 .engram/decisions/pre-commit-gate-hook.md          |  11 +-
 .../remove-good-first-issues-md-from-repo.md       |  13 +-
 ...-old-engram-decisions-files-left-over-from-d.md |  13 +-
 ...rganize-repo-to-plugin-marketplace-structure.md |  13 +-
 .../decisions/resolve-commit-signal-redundancy.md  |  11 +-
 .engram/decisions/store-tags-as-valid-json.md      |  11 +-
 CLAUDE.md                                          |  15 +-
 plugins/engram/engram/_frontmatter.py              |  75 ++++++---
 plugins/engram/engram/_helpers.py                  |  34 ++---
 plugins/engram/engram/_validate.py                 |  41 +++--
 plugins/engram/engram/signal.py                    |  39 ++---
 plugins/engram/engram/store.py                     |  23 ++-
 plugins/engram/schemas/README.md                   |  10 +-
 plugins/engram/schemas/decision.md                 |  26 ++--
 plugins/engram/skills/capture/SKILL.md             |  14 +-
 plugins/engram/tests/test_engram.py                | 168 ++++++++++-----------
 plugins/engram/tests/test_policy.py                |  11 +-
 32 files changed, 338 insertions(+), 345 deletions(-)

## Rationale

The custom YAML-like line parser had edge cases with quoting, arrays, and date types. Stdlib `tomllib` (Python 3.11+) handles all of these natively and correctly — dates parse as `datetime.date`, tags/links parse as real arrays.

## Alternatives

- Fix YAML parser edge cases — more code to maintain for a solved problem
- Use PyYAML — adds an external dependency for something stdlib handles
