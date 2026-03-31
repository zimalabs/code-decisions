"""CONTEXT policy — auto-regenerate .claude/rules/decisions.md after decision writes."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

from ._helpers import _extract_file_path, _is_decision_path
from .engine import PolicyResult, SessionState

if TYPE_CHECKING:
    from ..store import DecisionStore


def _generate_index(store: DecisionStore) -> str:
    """Generate the rules/decisions.md content grouped by primary tag."""
    decisions = store.list_decisions()
    if not decisions:
        return "# Team Decisions\n\nNo decisions captured yet.\n"

    # Group by primary tag (first tag), fallback to "Other"
    groups: dict[str, list[tuple[str, str, str]]] = {}  # tag -> [(slug, path, description)]
    for d in decisions:
        tag = d.tags[0] if d.tags else "other"
        rel_path = f".claude/decisions/{d.name}.md"
        entry = (d.name, rel_path, d.description or d.title or d.name)
        groups.setdefault(tag, []).append(entry)

    # Sort groups alphabetically, but put "other" last
    sorted_tags = sorted(groups.keys(), key=lambda t: (t == "other", t))

    lines = ["# Team Decisions", ""]
    for tag in sorted_tags:
        # Title-case the tag for section heading
        heading = tag.replace("-", " ").replace("_", " ").title()
        lines.append(f"## {heading}")
        for slug, path, desc in sorted(groups[tag], key=lambda x: x[0]):
            lines.append(f"- [{slug}]({path}) — {desc}")
        lines.append("")

    return "\n".join(lines)


def _index_update_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Regenerate .claude/rules/decisions.md after a decision file is written."""
    fp = _extract_file_path(data)
    if not fp or not _is_decision_path(fp):
        return None

    try:
        store = state.get_store()
        new_content = _generate_index(store)

        # Locate the rules directory relative to decisions_dir
        rules_dir = store.decisions_dir.parent / "rules"
        rules_file = rules_dir / "decisions.md"

        # Only write if content changed
        if rules_file.is_file():
            existing = rules_file.read_text()
            if existing.strip() == new_content.strip():
                return None

        rules_dir.mkdir(parents=True, exist_ok=True)
        rules_file.write_text(new_content)

        return PolicyResult(
            matched=True,
            system_message=f"Updated `.claude/rules/decisions.md` — {store.decision_count()} decisions indexed.",
        )
    except Exception as exc:
        print(f"decision: index_update error: {exc}", file=sys.stderr)
        return None  # Never break Claude Code
