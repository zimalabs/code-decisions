---
type: decision
date: 2026-03-16
tags: [ci, sqlite, macos]
links: [related:decision-add-ci-workflow-security-policy-funding-faq-and-go]
source: git:e24fce42854a1757f4e753bd21e2d1fb7e4ebc14
---

# Fix CI: install Homebrew SQLite with FTS5 on macOS

macOS runners ship with system SQLite which lacks the FTS5 module.
Install full-featured SQLite via Homebrew and prepend it to PATH.

 .github/workflows/ci.yml | 6 ++++--
 1 file changed, 4 insertions(+), 2 deletions(-)

## Rationale

FTS5 is required for engram's core search functionality. System SQLite on macOS lacks the FTS5 module, so CI was failing on the macOS matrix.

## Alternatives

Compile SQLite from source with the FTS5 flag — but Homebrew is simpler and well-maintained on GitHub Actions runners.
