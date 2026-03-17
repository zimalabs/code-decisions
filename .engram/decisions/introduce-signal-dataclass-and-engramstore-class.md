+++
date = 2026-03-17
tags = ["architecture", "schema"]
links = ["related:convert-engram-py-to-package", "related:migrate-core-lib-bash-to-python"]
source = "git:1311e747f14fd551dc6619493e973d4d0025aaba"
+++

# Introduce Signal dataclass and EngramStore class

Replace flat engram_* functions with EngramStore methods and SignalMeta
TypedDict with Signal dataclass. Eliminates ~15 redundant Path(dir_path)
computations, ~7 inline meta table read/write blocks, and consolidates
parsing/validation into Signal.from_text() and Signal.validate().

CLAUDE.md                           |   10 +-
 plugins/engram/engram.py            | 1629 +++++++++++++++++------------------
 plugins/engram/tests/test_engram.py |  364 ++++----
 3 files changed, 983 insertions(+), 1020 deletions(-)

## Rationale

Flat `engram_*` functions scattered ~15 redundant `Path(dir_path)` computations and ~7 inline meta table read/write blocks. Consolidating into `EngramStore` methods and `Signal` dataclass with `from_text()` / `validate()` eliminates this duplication.

## Alternatives

- Keep flat functions with shared helpers — still requires passing dir_path everywhere
- Multiple store classes (one per concern) — over-abstraction for current scope
