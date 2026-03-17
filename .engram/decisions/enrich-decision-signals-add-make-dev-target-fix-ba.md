+++
date = 2026-03-17
source = "git:a04bdec08b89bf2946a332a923fc0a5bfd05df00"
+++

# Enrich decision signals, add make dev target, fix backfill skill link format

Backfill and introspect all 34 decision signals: add tags (7), rationale/alternatives
sections (13), and cross-reference links (10+) to auto-ingested commit signals and
agent-written signals. Fix backfill SKILL.md to document the "rel:slug" link format
and use the correct `slug` column name. Add `make dev` target that symlinks the plugin
cache to source for fast local development.

.../decisions/add-automatic-context-injection.md   |  1 +
 .../add-six-hooks-for-decision-capture.md          |  1 +
 .engram/decisions/add-stop-hook-enforce-signals.md | 10 ++++
 ...convert-engram-py-monolith-to-python-package.md | 44 ++++++++++++++++
 ...rich-signals-add-make-dev-fix-backfill-links.md | 19 +++++++
 ...ggy-prompt-hooks-enforce-json-format-remove-.md | 26 ++++++++++
 ...-replace-macos-only-sed-i-with-portable-temp.md | 20 ++++++++
 ...ill-prefix-replace-engram-with-engram-standa.md | 35 +++++++++++++
 ...ize-policy-layer-replace-12-shell-hooks-with.md | 54 ++++++++++++++++++++
 ...oduce-signal-dataclass-and-engramstore-class.md | 27 ++++++++++
 .../decisions/migrate-core-lib-bash-to-python.md   |  1 +
 ...rate-engram-core-library-from-bash-to-python.md | 43 ++++++++++++++++
 ...migrate-signal-frontmatter-from-yaml-to-toml.md | 58 ++++++++++++++++++++++
 ...-schema-for-release-merge-valid-status-remov.md | 38 ++++++++++++++
 .engram/decisions/polish-schema-for-release.md     |  1 +
 ...ove-visualize-skill-bloat-without-core-value.md | 28 +++++++++++
 ...fy-engram-to-decisions-only-remove-finding-a.md | 46 +++++++++++++++++
 .../decisions/standardize-skill-prefix-to-slash.md |  1 +
 ...-readme-remove-stale-visualize-skill-fix-hoo.md | 19 +++++++
 Makefile                                           | 12 ++++-
 plugins/engram/skills/backfill/SKILL.md            |  8 ++-
 21 files changed, 490 insertions(+), 2 deletions(-)
