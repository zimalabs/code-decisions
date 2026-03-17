"""Content validation for pre-tool-use hook."""
from __future__ import annotations

import sys

from ._frontmatter import _split_frontmatter


def _validate_content_stdin() -> str:
    """Validate signal content read from stdin. For pre-tool-use hook."""
    text = sys.stdin.read()
    errors = []

    fm, content_lines = _split_frontmatter(text)
    lines = text.splitlines()

    if not fm and lines[:1] != ["+++"]:
        errors.append("missing opening +++ frontmatter delimiter")
        errors.append("missing closing +++ frontmatter delimiter")
    elif not fm:
        errors.append("invalid TOML frontmatter (missing closing +++ or parse error)")

    if fm:
        # Check date field
        if "date" not in fm or not fm["date"]:
            errors.append("missing or invalid date field (need YYYY-MM-DD)")

        # Check tags field
        tags = fm.get("tags", "")
        if not tags or tags == "[]":
            errors.append("tags field missing or empty, add at least one tag")

    # Check H1 title and lead paragraph
    has_title = False
    lead = ""
    for line in content_lines:
        if not has_title and line.startswith("# "):
            has_title = True
            continue
        if has_title:
            if not line or line.startswith("#"):
                continue
            lead = line
            break

    if not has_title:
        errors.append("missing H1 title (# ...)")
    if not lead or len(lead) < 20:
        errors.append("lead paragraph after title must exist and be >= 20 chars (explains why)")

    if errors:
        return "; ".join(errors) + "; "
    return ""
