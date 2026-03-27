"""YAML frontmatter parsing — stdlib only, handles the subset we need.

Supported YAML subset (all writes go through _format_yaml_frontmatter):
- Scalar string values: ``key: value`` or ``key: "quoted value"``
- Block lists: ``key:\\n  - "item"``
- Inline lists: ``[a, b, c]`` (no commas inside values)
- Comments and blank lines are skipped

Partially supported (auto-collapsed to single-line):
- Multi-line YAML values (folded ``>`` / literal ``|`` blocks)

NOT supported (will raise or mis-parse):
- Nested objects
- Inline list items containing commas (e.g. ``[a, "b, c"]``)
- Values containing unbalanced quotes
"""

from __future__ import annotations

import re

_NEEDS_QUOTING = re.compile(r"""[:\{\}\[\],&\*\?\|>!\%@`#"']|^\s|\s$""")
_YAML_BOOLISH = frozenset({"true", "false", "null", "yes", "no", "on", "off"})


def _needs_quoting(val: str) -> bool:
    """Return True if a YAML scalar value needs double-quoting."""
    return bool(_NEEDS_QUOTING.search(val)) or val.lower() in _YAML_BOOLISH


def _split_inline_list(inner: str) -> list[str]:
    """Split a YAML inline list body on commas, respecting quoted strings.

    Handles ``"a, b", c`` → ``['"a, b"', 'c']`` so commas inside quoted
    values are not treated as separators.
    """
    items: list[str] = []
    current: list[str] = []
    in_quote: str | None = None

    for ch in inner:
        if in_quote:
            current.append(ch)
            if ch == in_quote and (not current or current[-2] != "\\"):
                in_quote = None
        elif ch in ('"', "'"):
            in_quote = ch
            current.append(ch)
        elif ch == ",":
            items.append("".join(current))
            current = []
        else:
            current.append(ch)

    if current:
        items.append("".join(current))

    return items


def _split_yaml_frontmatter(text: str) -> tuple[dict[str, str | list[str]], list[str]]:
    """Split markdown with YAML frontmatter into (fields_dict, content_lines).

    Returns parsed dict + content lines after closing ---.
    If no valid frontmatter, returns ({}, all_lines).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, lines

    end = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end = i
            break

    if end is None:
        return {}, lines

    # Parse simple YAML subset
    fields: dict[str, str | list[str]] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    fm_lines = lines[1:end]
    skip_until = -1  # index-based skip for block scalar continuation lines

    for idx, line in enumerate(fm_lines):
        if idx <= skip_until:
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # List item continuation
        if re.match(r"^\s+-\s+", line) and current_key is not None:
            item = _strip_outer_quotes(re.sub(r"^\s+-\s+", "", line).strip())
            item = _unescape_yaml_string(item)
            if current_list is None:
                current_list = []
            current_list.append(item)
            fields[current_key] = current_list
            continue

        # Key: value pair
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)", stripped)
        if m:
            key = m.group(1)
            value = m.group(2).strip()
            current_key = key
            current_list = None

            # Auto-collapse block scalars (| and >) into single-line values
            if value in ("|", "|-", "|+", ">", ">-", ">+"):
                block_parts: list[str] = []
                for j in range(idx + 1, len(fm_lines)):
                    cont = fm_lines[j]
                    # Block continues while lines are indented (or blank)
                    if cont.strip() == "":
                        continue  # skip blank lines within block
                    if cont[0] in (" ", "\t"):
                        block_parts.append(cont.strip())
                        skip_until = j
                    else:
                        break  # non-indented line = end of block
                fields[key] = " ".join(block_parts)
                continue

            if not value:
                # Bare key — expect list items to follow
                current_list = []
                fields[key] = current_list
                continue

            # Inline list: [a, b, c]
            if value.startswith("[") and value.endswith("]"):
                items = _split_inline_list(value[1:-1])
                fields[key] = [_unescape_yaml_string(_strip_outer_quotes(i.strip())) for i in items if i.strip()]
                continue

            # Quoted string
            if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                fields[key] = _unescape_yaml_string(value[1:-1])
                continue

            # Bare value
            fields[key] = value

    return fields, lines[end + 1 :]


def _strip_outer_quotes(val: str) -> str:
    """Remove exactly one pair of matching outer quotes (single or double).

    Unlike str.strip(), this only removes one character from each end,
    preventing greedy stripping that would eat into escaped sequences.
    """
    if len(val) >= 2:
        if (val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'"):
            return val[1:-1]
    return val


def _unescape_yaml_string(val: str) -> str:
    """Reverse the escaping done by _escape_yaml_string.

    Converts ``\\"`` back to ``"`` and ``\\\\`` back to ``\\``.
    Order matters: unescape quotes first so ``\\\\"`` doesn't double-convert.
    """
    return val.replace('\\"', '"').replace("\\\\", "\\")


def _escape_yaml_string(val: str) -> str:
    """Escape a string for safe double-quoting in YAML.

    Backslash-escapes backslashes and double quotes so the value
    round-trips through YAML parsers correctly.
    """
    return val.replace("\\", "\\\\").replace('"', '\\"')


def _format_yaml_value(val: str) -> str:
    """Format a scalar YAML value, quoting only when necessary."""
    if _needs_quoting(val):
        return f'"{_escape_yaml_string(val)}"'
    return val


def _format_yaml_frontmatter(fields: dict[str, str | list[str] | bool]) -> str:
    """Format a dict as YAML frontmatter block (---...---).

    Handles strings (quoted only when needed), lists (block style), booleans.
    """
    lines = ["---"]
    for key, val in fields.items():
        if isinstance(val, list):
            if not val:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {_format_yaml_value(item)}")
        elif isinstance(val, bool):
            lines.append(f"{key}: {'true' if val else 'false'}")
        else:
            lines.append(f"{key}: {_format_yaml_value(val)}")
    lines.append("---")
    return "\n".join(lines)
