---
type: decision
date: 2026-03-16
source: git:e24fce42854a1757f4e753bd21e2d1fb7e4ebc14
---

# Fix CI: install Homebrew SQLite with FTS5 on macOS

macOS runners ship with system SQLite which lacks the FTS5 module.
Install full-featured SQLite via Homebrew and prepend it to PATH.

 .github/workflows/ci.yml | 6 ++++--
 1 file changed, 4 insertions(+), 2 deletions(-)
