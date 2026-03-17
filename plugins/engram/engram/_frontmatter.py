"""Frontmatter parsing shared across signal and validation modules."""
from __future__ import annotations

from ._helpers import _normalize_tags


# Field name -> transform function for frontmatter parsing
_FM_FIELDS: dict[str, callable] = {
    "type": str.strip,
    "date": str.strip,
    "tags": _normalize_tags,
    "source": str.strip,
    "supersedes": str.strip,
    "links": str.strip,
    "status": str.strip,
}


def _split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    """Split markdown into (frontmatter_lines, content_lines).

    Returns raw line lists — frontmatter lines exclude the --- delimiters.
    If no valid frontmatter, returns ([], all_lines).
    """
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return [], lines

    for i, line in enumerate(lines[1:], 1):
        if line == "---":
            return lines[1:i], lines[i + 1:]

    return [], lines
