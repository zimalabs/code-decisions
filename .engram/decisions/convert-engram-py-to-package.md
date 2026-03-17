---
type: decision
date: 2026-03-17
tags: [architecture, repo-structure]
---

# Convert engram.py monolith to Python package

The 1068-line engram.py was becoming hard to navigate — constants, helpers, dataclass, store, validation, and CLI all in one file. Splitting into a package (`engram/`) with focused modules improves maintainability without changing the public API.

## Rationale

Single-file worked early on but grew past the point where quick navigation was easy. A package with `__init__.py` re-exports preserves `import engram` / `engram.EngramStore` / `engram.ENGRAM_SCHEMA_FILE` — zero test changes needed. Hooks switch from `python3 "$ENGRAM_PY"` to `python3 -m engram` via PYTHONPATH.

## Alternatives

- **Keep single file** — simpler but increasingly unwieldy as features are added.
- **Split into separate top-level .py files** — breaks `import engram` semantics and requires more test changes.
