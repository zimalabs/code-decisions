+++
date = 2026-03-17
tags = ["architecture", "dx", "repo-structure"]
+++

# Flatten repo structure and add dev tooling

Renamed `plugins/engram/` → `plugin/` with `src/` layout. Moved tests to repo root. Added pytest, ruff, and mypy via uv as dev-only dependencies.

## Rationale

The `plugins/engram/` nesting was unnecessary — there's only one plugin. The `src/` layout prevents accidental imports of the package from the repo root. Dev tooling (pytest, ruff, mypy) improves DX without affecting the shipped plugin, which remains stdlib-only. Tests at repo root means they're excluded from plugin installs automatically.

## Alternatives

- Keep flat `plugin/engram/` without `src/`: simpler but allows accidental sibling imports
- Keep tests inside plugin dir: simpler move but they'd ship with the plugin
- Skip dev tooling: lower complexity but hand-rolled test runner and no linting/typing
