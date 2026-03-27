"""Pure helper functions used across the decision package."""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .constants import (
    NOISE_WORDS,
    PATH_KEYWORD_LIMIT,
    PATH_MIN_SEGMENT_LEN,
)

_PATH_SEGMENT_RE = re.compile(rf"[a-zA-Z]{{{PATH_MIN_SEGMENT_LEN},}}")


def _parse_list_field(raw: Any) -> list[str]:
    """Parse a YAML frontmatter list field (tags, affects) into a list of strings.

    Handles list, JSON string, plain string, and empty/None inputs.
    """
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
        return [raw] if raw else []
    return []


def _log(msg: str) -> None:
    """Print a decision-prefixed message to stderr."""
    print(f"decision: {msg}", file=sys.stderr)


def _project_key(cwd: str | Path | None = None) -> str:
    """Derive the Claude Code project key from the working directory."""
    project_root = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    return str(project_root).replace("/", "-")


def _state_dir(cwd: str | Path | None = None) -> Path:
    """Return the plugin state directory (~/.claude/projects/{key}/.decision/).

    Creates the directory if it doesn't exist.
    """
    d = Path.home() / ".claude" / "projects" / _project_key(cwd) / ".decision"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _discover_decisions_dir(cwd: str | Path | None = None) -> Path:
    """Return the decisions directory (.claude/decisions/ under git root or CWD)."""
    from .git import get_repo_root

    root = get_repo_root()
    if root is None:
        root = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    return root / ".claude" / "decisions"


@contextmanager
def _file_lock(lock_path: Path) -> Generator[None, None, None]:
    """Acquire an exclusive file lock, cross-platform (fcntl on Unix, msvcrt on Windows)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as fd:
        if os.name == "nt":
            import msvcrt  # type: ignore[import-not-found]

            msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
            try:
                yield
            finally:
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)


def _path_to_keywords(path: str) -> str:
    """Extract searchable words from a file path."""
    parts = Path(path).parts
    words: list[str] = []
    for part in parts:
        for seg in _PATH_SEGMENT_RE.findall(part):
            lower = seg.lower()
            if lower not in NOISE_WORDS:
                words.append(lower)
    return " ".join(words[:PATH_KEYWORD_LIMIT])
