"""Commit classification and path-to-keywords helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ._constants import (
    _DECISION_FILES,
    _DECISION_PATTERNS,
    _DECISION_PREFIXES,
    _NOISE_WORDS,
    _SKIP_PATTERNS,
    _SKIP_PREFIXES,
)


def _is_decision_commit(subject: str, commit_hash: str) -> bool:
    """Check if a commit represents a decision worth capturing."""
    lower = subject.lower()

    # Skip: conventional commit prefixes that aren't decisions
    if _SKIP_PREFIXES.match(lower):
        return False

    # Skip: merge commits, version bumps, trivial messages
    if _SKIP_PATTERNS.match(lower):
        return False

    # Match: conventional commit prefixes that are decisions
    if _DECISION_PREFIXES.match(lower):
        return True

    # Match: keyword patterns in the message
    if _DECISION_PATTERNS.search(lower):
        return True

    # Match: significant file changes (schema, deps, CI, infra)
    # Require 2+ changed files — touching a single config file alone isn't a decision
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            capture_output=True,
            text=True,
            errors="replace",
        )
        files = [f for f in result.stdout.strip().splitlines() if f.strip()]
        if len(files) >= 2 and _DECISION_FILES.search(result.stdout):
            return True
    except (OSError, subprocess.SubprocessError):
        pass

    return False


def engram_path_to_keywords(filepath: str) -> str:
    """Extract search keywords from a file path."""
    if not filepath:
        return ""
    # Strip extension
    base = Path(filepath).with_suffix("").as_posix()
    # Split on / - _ .
    words = re.split(r"[/\-_.]", base)
    words = [w.lower() for w in words if w]

    seen = set()
    result = []
    for word in words:
        if word in _NOISE_WORDS:
            continue
        if word in seen:
            continue
        seen.add(word)
        result.append(word)

    return " ".join(result)
