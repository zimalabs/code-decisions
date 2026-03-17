"""Constants used across the engram package."""

from __future__ import annotations

import re
from pathlib import Path

# Conventional commit prefixes that represent decisions
_DECISION_PREFIXES = re.compile(r"^(feat|feat!|breaking|refactor|perf)[:(]")

# Prefixes that are never decisions
_SKIP_PREFIXES = re.compile(
    r"^(fix|docs|test|tests|chore|ci|style|build|typo|wip"
    r"|merge|remove|delete|clean|rename|move|bump|update)[:(]"
)

# Commit message patterns that indicate architectural/dependency decisions
_DECISION_PATTERNS = re.compile(
    r"(migrate|switch to|replace|add support|adopt|introduce|deprecate|rewrite)",
    re.IGNORECASE,
)

# Files whose presence in a commit's diff indicates a decision
_DECISION_FILES = re.compile(
    r"(Gemfile|package\.json|Cargo\.toml|go\.mod|requirements\.txt|Pipfile|pyproject\.toml"
    r"|schema\.rb|structure\.sql|docker-compose|Dockerfile|\.github/workflows|\.circleci|Makefile)"
)

# Merge/trivial commit patterns
_SKIP_PATTERNS = re.compile(r"^(merge branch|merge pull|bump version|wip$|wip:|fixup!|squash!)")

# Noise words for path_to_keywords
_NOISE_WORDS = frozenset(
    [
        "src",
        "lib",
        "app",
        "index",
        "test",
        "spec",
        "the",
        "and",
        "is",
        "of",
        "to",
        "in",
        "for",
        "a",
        "an",
    ]
)

# ── Type aliases ─────────────────────────────────────────────────────

StrPath = str | Path
