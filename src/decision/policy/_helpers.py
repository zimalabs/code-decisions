"""Shared helpers for policy condition functions."""

from __future__ import annotations

import re
from typing import Any

from ..utils.constants import (
    CONTENT_KEYWORD_LIMIT,
    CONTENT_MIN_WORD_LEN,
    IMPORTANT_SHORT_TERMS,
    NOISE_WORDS,
)

# Code noise words to filter from content keyword extraction
_CODE_NOISE = frozenset(
    {
        "self",
        "return",
        "import",
        "from",
        "class",
        "def",
        "none",
        "true",
        "false",
        "with",
        "elif",
        "else",
        "pass",
        "raise",
        "yield",
        "async",
        "await",
        "lambda",
        "assert",
        "global",
        "while",
        "break",
        "continue",
        "except",
        "finally",
        "print",
        "super",
        "init",
        "args",
        "kwargs",
        "dict",
        "list",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "type",
        "null",
        "undefined",
        "const",
        "function",
        "this",
        "that",
        "var",
        "void",
        "new",
        "delete",
        "typeof",
        "instanceof",
        "require",
        "module",
        "exports",
        "default",
        "value",
        "name",
        "data",
        "result",
        "error",
        "string",
        "number",
        "object",
        "array",
    }
)


# Pre-computed union of noise word sets (avoids re-creating on every call)
_ALL_NOISE = NOISE_WORDS | _CODE_NOISE


def _extract_content_keywords(data: dict[str, Any], max_words: int = CONTENT_KEYWORD_LIMIT) -> list[str]:
    """Extract meaningful words from edit/write content for search."""
    ti = data.get("tool_input", {})
    if not isinstance(ti, dict):
        return []

    text = ti.get("new_string", "") or ti.get("content", "")
    if not text:
        return []

    # Cap input size to avoid pathological regex on large content
    text = text[:10_000]

    # Match words of minimum length OR important short terms (API, SQL, etc.)
    words = re.findall(rf"[a-zA-Z]{{{CONTENT_MIN_WORD_LEN},}}", text)
    short_matches = re.findall(r"\b[a-zA-Z]{2,3}\b", text)
    words.extend(w for w in short_matches if w.upper() in IMPORTANT_SHORT_TERMS)

    all_noise = _ALL_NOISE
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        lower = w.lower()
        if lower in all_noise or lower in seen:
            continue
        seen.add(lower)
        result.append(lower)
        if len(result) >= max_words:
            break

    return result


def _extract_file_path(data: dict[str, Any]) -> str:
    """Extract file_path from hook input."""
    ti = data.get("tool_input", {})
    if isinstance(ti, dict):
        fp: str = ti.get("file_path", "")
        return fp
    return ""


def _get_prompt(data: dict[str, Any]) -> str:
    """Extract user prompt from UserPromptSubmit hook data.

    Claude Code sends ``{"prompt": "..."}`` for UserPromptSubmit events.
    Legacy/test data may use ``{"tool_input": {"content": "..."}}``.
    """
    prompt: str = data.get("prompt", "")
    if prompt:
        return prompt
    ti = data.get("tool_input", {})
    if isinstance(ti, dict):
        content: str = ti.get("content", "")
        return content
    return ""


def _is_decision_path(path: str) -> bool:
    """Check if path targets a decision file in .claude/decisions/."""
    if not path.endswith(".md"):
        return False
    from pathlib import PurePosixPath

    p = PurePosixPath(path)
    return p.parent.name == "decisions"
