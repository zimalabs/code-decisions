"""Frontmatter parsing shared across signal and validation modules."""

from __future__ import annotations

import json
import tomllib
from datetime import date


def _split_frontmatter(text: str) -> tuple[dict, list[str]]:
    """Split markdown with TOML frontmatter into (fields_dict, content_lines).

    Returns parsed and normalized dict + content lines.
    Normalization: datetime.date → ISO string, list → json.dumps().
    If no valid frontmatter, returns ({}, all_lines).
    """
    lines = text.splitlines()
    if not lines or lines[0] != "+++":
        return {}, lines

    end = None
    for i, line in enumerate(lines[1:], 1):
        if line == "+++":
            end = i
            break

    if end is None:
        return {}, lines

    toml_block = "\n".join(lines[1:end])
    try:
        fields = tomllib.loads(toml_block)
    except tomllib.TOMLDecodeError:
        return {}, lines

    # Normalize values for downstream consumers
    normalized: dict[str, str] = {}
    for key, val in fields.items():
        if isinstance(val, date):
            normalized[key] = val.isoformat()
        elif isinstance(val, list):
            normalized[key] = json.dumps(val)
        else:
            normalized[key] = str(val)

    return normalized, lines[end + 1 :]


def _format_toml_frontmatter(fields: dict) -> str:
    """Format a dict as TOML frontmatter block (+++...+++).

    Handles date (bare), lists (TOML array), strings (quoted).
    """
    lines = ["+++"]
    for key, val in fields.items():
        if isinstance(val, list):
            items = ", ".join(f'"{v}"' for v in val)
            lines.append(f"{key} = [{items}]")
        elif key == "date":
            # Bare TOML date (no quotes)
            lines.append(f"{key} = {val}")
        else:
            lines.append(f'{key} = "{val}"')
    lines.append("+++")
    return "\n".join(lines)
