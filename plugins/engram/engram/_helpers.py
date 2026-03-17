"""Pure helper functions used across the engram package."""
from __future__ import annotations

import contextlib
import json
import re
import sqlite3
import sys
from pathlib import Path

from ._constants import StrPath


@contextlib.contextmanager
def _connect(db_path: StrPath):
    """Context manager for SQLite connections."""
    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()


def _check_fts5() -> bool:
    """Verify SQLite FTS5 module is available."""
    try:
        with _connect(":memory:") as conn:
            conn.execute("CREATE VIRTUAL TABLE _fts5_test USING fts5(x);")
    except sqlite3.OperationalError:
        print("engram: SQLite FTS5 module not available.", file=sys.stderr)
        print("engram: Install SQLite with FTS5 support:", file=sys.stderr)
        print('engram:   macOS:  brew install sqlite && export PATH="$(brew --prefix sqlite)/bin:$PATH"', file=sys.stderr)
        print("engram:   Ubuntu: sudo apt-get install -y libsqlite3-0", file=sys.stderr)
        print("engram:   Alpine: apk add sqlite", file=sys.stderr)
        return False
    return True


def _slugify(text: str) -> str:
    """Lowercase, replace non-alphanum with hyphens, collapse, trim, truncate to 50."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s[:50]


def _slug(filepath: StrPath) -> str:
    """Extract slug from filepath (basename without .md)."""
    return Path(filepath).stem


def _parse_links(s: str) -> list[tuple[str, str]]:
    """Parse links field into list of (rel, target).

    Input is a JSON array string like '["related:foo", "supersedes:bar"]'.
    """
    s = s.strip()
    if not s or s == "[]":
        return []
    try:
        items = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        # Fallback for plain comma-separated strings
        items = [p.strip() for p in s.lstrip("[").rstrip("]").split(",")]
    result = []
    for item in items:
        item = str(item).strip()
        if ":" in item:
            rel, target = item.split(":", 1)
            rel, target = rel.strip(), target.strip()
            if rel and target:
                result.append((rel, target))
    return result
