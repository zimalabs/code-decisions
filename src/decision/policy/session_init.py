"""LIFECYCLE policy — initialize decision store and print banner."""

from __future__ import annotations

import sys
from typing import Any

from .engine import PolicyResult, SessionState


def _rebuild_index_if_stale(state: SessionState) -> None:
    """Regenerate .claude/rules/decisions.md if any decision file is newer than the index."""
    try:
        store = state.get_store()
        rules_file = store.decisions_dir.parent / "rules" / "decisions.md"

        # If the index doesn't exist, rebuild unconditionally
        if not rules_file.is_file():
            if store.decision_count() == 0:
                return  # nothing to index
            from .index_update import _generate_index

            rules_file.parent.mkdir(parents=True, exist_ok=True)
            rules_file.write_text(_generate_index(store))
            return

        index_mtime = rules_file.stat().st_mtime

        # Check if any decision file is newer than the index
        for f in store.decisions_dir.glob("*.md"):
            try:
                if f.stat().st_mtime > index_mtime:
                    from .index_update import _generate_index

                    new_content = _generate_index(store)
                    if new_content.strip() != rules_file.read_text().strip():
                        rules_file.write_text(new_content)
                    return
            except OSError:
                continue
    except Exception as exc:
        print(f"decision: _rebuild_index_if_stale error: {exc}", file=sys.stderr)


def _session_init_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Initialize decision store and print banner at session start."""
    store = state.get_store()
    store.ensure_dir()

    # Rebuild rules index if decision files changed outside Claude Code
    _rebuild_index_if_stale(state)

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
