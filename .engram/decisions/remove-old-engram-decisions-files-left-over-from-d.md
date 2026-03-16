---
type: decision
date: 2026-03-16
tags: [cleanup, signals]
links: [related:reorganize-repo-to-plugin-marketplace-structure]
source: git:8f257cf81f767446715d55c670c2f316a8794274
---

# Remove old .engram/decisions/ files left over from directory flattening

These were replaced by type-prefixed files in .engram/signals/ in e392b65.

 ...-workflow-security-policy-funding-faq-and-go.md | 22 ----------------------
 ...i-install-homebrew-sqlite-with-fts5-on-macos.md | 12 ------------
 ...-03-16-remove-good-first-issues-md-from-repo.md | 11 -----------
 3 files changed, 45 deletions(-)

## Rationale

Duplicates after migration — these files were superseded by type-prefixed files in `.engram/signals/` (e392b65).

## Alternatives

None — dead files with no reason to keep duplicates after the directory flattening migration.
