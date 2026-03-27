"""LIFECYCLE policy — initialize decision store and print banner."""

from __future__ import annotations

import sys
from typing import Any

from .engine import PolicyResult, SessionState


def _session_init_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Initialize decision store and print banner at session start."""
    store = state.get_store()
    store.ensure_dir()

    # Opportunistically clean up stale session dirs from /tmp
    SessionState.cleanup_stale(max_age_seconds=14400)  # 4 hours

    count = store.decision_count()

    if count == 0:
        # First-run: inviting banner with a concrete nudge to try it
        lines = [
            "",
            "  ◆ decision plugin ready",
            "  └─ Try it: tell Claude to use a specific approach and why — it captures automatically.",
            "",
        ]
    else:
        header = "  ◆ decision active"
        lines = ["", header, f"  └─ {count} decisions"]

        # Warn if FTS5 is unavailable — search will fall back to keyword matching
        if not store._index.available:
            lines.append(
                "  ⚠ FTS5 unavailable — search uses keyword fallback (install sqlite3 with FTS5 for better results)"
            )

        lines.append("")

    print("\n".join(lines), file=sys.stderr)

    return PolicyResult(matched=True)
