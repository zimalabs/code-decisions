"""Content validation for pre-tool-use hook."""
from __future__ import annotations

import re
import sys

from ._frontmatter import _split_frontmatter


def _validate_content_stdin() -> str:
    """Validate signal content read from stdin. For pre-tool-use hook."""
    text = sys.stdin.read()
    errors = []

    fm_lines, content_lines = _split_frontmatter(text)

    if not fm_lines and text.splitlines()[:1] != ["---"]:
        errors.append("missing opening --- frontmatter delimiter")
        errors.append("missing closing --- frontmatter delimiter")
    elif not fm_lines:
        errors.append("missing closing --- frontmatter delimiter")

    # Check date field
    has_date = any(
        re.match(r"^ *\d{4}-\d{2}-\d{2}", line.partition(":")[2])
        for line in fm_lines if line.startswith("date:")
    )
    if not has_date:
        errors.append("missing or invalid date: field (need YYYY-MM-DD)")

    # Check tags field
    tags_line = next((l for l in fm_lines if l.startswith("tags:")), None)
    if not tags_line:
        errors.append("missing tags: field")
    elif "[]" in tags_line:
        errors.append("tags: is empty, add at least one tag")

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
