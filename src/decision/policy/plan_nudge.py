"""NUDGE policy — extract decision candidates from Claude Code plan files.

Two-phase behavior:
  Phase 1 (plan file Write): Scan content, extract candidates, store in state.
  Phase 2 (first non-plan PostToolUse): Nudge with candidate list.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..utils.constants import PLAN_AFFECTS_MAX, PLAN_CANDIDATE_MAX, SKIP_FILE_PATTERNS
from ._helpers import _extract_file_path
from .engine import PolicyResult, SessionState

# Decision language in plan markdown — broader than code-comment patterns
# because plans are prose-heavy with explicit reasoning.
_PLAN_DECISION_RE = re.compile(
    r"(?:chose|decided|instead of|trade.?off|rather than|opted for|going with|over \w[\w\s]{1,40}\w because)"
    r".{3,120}",
    re.IGNORECASE,
)

# File paths in "Files to Change" sections
_PLAN_FILE_PATH_RE = re.compile(
    r"(?:New|Modify|Change|Update|Create):\s*`?("
    r"(?:src|lib|app|tests?|pkg|internal|cmd)/[^\s`]+"
    r")`?",
    re.IGNORECASE,
)

# ── State keys ───────────────────────────────────────────────────────
_KEY_CANDIDATES = "_plan-candidates"
_KEY_AFFECTS = "_plan-affects"
_KEY_PLAN_PATH = "_plan-file-path"


def _is_plan_file(file_path: str) -> bool:
    """Return True if file_path is a Claude Code plan file."""
    return ".claude/plans/" in file_path and file_path.endswith(".md")


def _extract_decision_candidates(content: str) -> list[dict[str, str]]:
    """Scan plan markdown for decision signals.

    Returns list of {"title": ..., "reasoning": ...} dicts.
    """
    content = content[:20_000]  # cap scan size
    candidates: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    for m in _PLAN_DECISION_RE.finditer(content):
        snippet = m.group(0).strip()
        # Derive a short title from the first ~60 chars
        title = snippet[:60].rstrip(".,;:!? ")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        candidates.append({"title": title, "reasoning": snippet[:120]})
        if len(candidates) >= PLAN_CANDIDATE_MAX:
            break

    return candidates


def _extract_plan_affects(content: str) -> list[str]:
    """Extract file paths from plan's 'Files to Change' section."""
    content = content[:20_000]
    paths: list[str] = []
    seen: set[str] = set()

    for m in _PLAN_FILE_PATH_RE.finditer(content):
        p = m.group(1).strip().rstrip("`")
        if p and p not in seen:
            seen.add(p)
            paths.append(p)
            if len(paths) >= PLAN_AFFECTS_MAX:
                break

    return paths


def _load_candidates(state: SessionState) -> list[dict[str, str]]:
    raw = state.load_data(_KEY_CANDIDATES)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _plan_nudge_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Detect plan file writes and nudge on first implementation edit."""
    if state.nudges_dismissed():
        return None

    if state.has_fired("_plan-nudge-delivered"):
        return None

    fp = _extract_file_path(data)
    if not fp:
        return None

    tool_name = data.get("tool_name", "")

    # ── Phase 1: Plan file detection ─────────────────────────────────
    if _is_plan_file(fp):
        # Only Write provides full content; Edit has partial patches
        if tool_name != "Write":
            return None

        content = (data.get("tool_input") or {}).get("content", "")
        if not content:
            return None

        candidates = _extract_decision_candidates(content)
        if not candidates:
            return None

        affects = _extract_plan_affects(content)

        state.store_data(_KEY_CANDIDATES, json.dumps(candidates))
        state.store_data(_KEY_AFFECTS, json.dumps(affects))
        state.store_data(_KEY_PLAN_PATH, fp)
        state.mark_fired("_plan-candidates-ready")
        return None  # Never nudge during plan mode

    # ── Phase 2: First implementation edit ───────────────────────────
    if not state.has_fired("_plan-candidates-ready"):
        return None

    # Skip non-code files
    if any(pat in fp for pat in SKIP_FILE_PATTERNS):
        return None

    candidates = _load_candidates(state)
    if not candidates:
        return None

    # Don't fire if decisions already captured
    store = state.get_store()
    if state.has_recent_decisions(store.decisions_dir):
        return None

    state.mark_fired("_plan-nudge-delivered")

    # Build nudge message
    n = len(candidates)
    titles = [c["title"] for c in candidates[:3]]
    titles_str = "\n".join(f"  - {t}" for t in titles)
    more = f"\n  - ...and {n - 3} more" if n > 3 else ""

    affects_raw = state.load_data(_KEY_AFFECTS)
    plan_affects: list[str] = []
    if affects_raw:
        try:
            plan_affects = json.loads(affects_raw)
        except (json.JSONDecodeError, TypeError):
            pass
    affects_hint = f"\nAffects: {', '.join(plan_affects[:5])}" if plan_affects else ""

    msg = (
        f"The implementation plan contains {n} decision-worthy choice{'s' if n != 1 else ''}:\n"
        f"{titles_str}{more}\n"
        "Capture these as you implement — reasoning is freshest now:\n"
        f"`/decision we chose X because Y`{affects_hint}"
    )

    return PolicyResult(matched=True, ok=True, system_message=msg)
