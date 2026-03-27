"""BLOCK policy — warn if Edit/MultiEdit corrupts a decision file."""

from __future__ import annotations

from typing import Any

from ._helpers import _extract_file_path, _is_decision_path
from .engine import PolicyResult, SessionState


def _edit_validation_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Warn if an Edit/MultiEdit leaves a decision file in a malformed state."""
    fp = _extract_file_path(data)
    if not fp or not _is_decision_path(fp):
        return None

    from pathlib import Path

    path = Path(fp)
    if not path.is_file():
        return None

    try:
        content = path.read_text()
    except OSError:
        return None

    from ..core.decision import Decision

    dec = Decision.from_text(content)
    errors = dec.validate()
    if errors:
        error_list = "\n".join(f"  - {e}" for e in errors)
        msg = (
            f"Warning: decision file may be malformed after edit:\n{error_list}\n"
            "Re-read the file with the Read tool, fix the YAML frontmatter errors, then save again."
        )
        return PolicyResult(matched=True, system_message=msg)

    return None
