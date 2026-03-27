"""NUDGE policy — detect implementation-time decisions from agent behavior.

Fires on PostToolUse for Write/Edit/MultiEdit.  Tracks new file creations,
directory breadth, and decision language in code comments to detect when the
agent is making architectural choices without capturing decisions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..utils.constants import (
    IMPL_BREADTH_DIR_THRESHOLD,
    IMPL_BREADTH_FILE_THRESHOLD,
    IMPL_NEW_FILE_THRESHOLD,
    IMPL_NUDGE_COOLDOWN,
    IMPL_NUDGE_MIN_EDITS,
    SKIP_FILE_PATTERNS,
)
from ._helpers import _extract_file_path
from .engine import PolicyResult, SessionState

# Decision language in code comments (subset of capture-nudge patterns).
_COMMENT_DECISION_RE = re.compile(
    r"(?:#|//|/\*|\*)\s*"
    r"(chose\b.+?(?:over|instead|because)|"
    r"trade.?off\b.{5,60}|"
    r"opted for\b.{3,60}|"
    r"instead of\b.{3,60}|"
    r"alternative\b.{3,60}|"
    r"decision:\s*.{3,80}|"
    r"we use\b.+?because)",
    re.IGNORECASE,
)

# ── State keys ───────────────────────────────────────────────────────
_KEY_NEW_FILES = "_impl-new-files"
_KEY_DIRS = "_impl-dirs-touched"
_KEY_COMMENTS = "_impl-decision-comments"
_KEY_LAST_NUDGE_AT = "_impl-last-nudge-at"


def _load_json_list(state: SessionState, key: str) -> list[str]:
    raw = state.load_data(key)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _save_json_list(state: SessionState, key: str, items: list[str]) -> None:
    state.store_data(key, json.dumps(items))


def _dir_prefix(fp: str) -> str:
    """Extract top-level directory prefix from a file path."""
    from pathlib import PurePosixPath

    parts = PurePosixPath(fp.lstrip("./")).parts
    if len(parts) >= 2:
        return parts[0] + "/" + parts[1] + "/"
    if parts:
        return parts[0] + "/"
    return ""


def _extract_decision_comments(data: dict[str, Any]) -> list[str]:
    """Scan Write/Edit content for decision language in comments."""
    ti = data.get("tool_input", {})
    if not isinstance(ti, dict):
        return []
    text = ti.get("content", "") or ti.get("new_string", "")
    if not text:
        return []
    # Cap scan size
    text = text[:10_000]
    results: list[str] = []
    for m in _COMMENT_DECISION_RE.finditer(text):
        snippet = m.group(1).strip()[:80]
        if snippet:
            results.append(snippet)
    return results[:3]  # cap at 3 snippets


def _impl_nudge_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Detect implementation decisions from agent behavior (new files, structural changes)."""
    if state.nudges_dismissed():
        return None

    # Don't double-nudge if capture-nudge already detected user decision language
    if state.has_fired("_capture-nudge-pending"):
        return None

    fp = _extract_file_path(data)
    if not fp:
        return None

    if any(pat in fp for pat in SKIP_FILE_PATTERNS):
        return None

    tool_name = data.get("tool_name", "")

    # ── Accumulate signals ───────────────────────────────────────────
    new_files = _load_json_list(state, _KEY_NEW_FILES)
    dirs = _load_json_list(state, _KEY_DIRS)
    comments = _load_json_list(state, _KEY_COMMENTS)

    changed = False

    # Track new file creations (Write to a path not yet in our list)
    if tool_name == "Write" and fp not in new_files:
        new_files.append(fp)
        changed = True

    # Track directory breadth
    d = _dir_prefix(fp)
    if d and d not in dirs:
        dirs.append(d)
        changed = True

    # Check for decision comments in code
    new_comments = _extract_decision_comments(data)
    for c in new_comments:
        if c not in comments:
            comments.append(c)
            changed = True

    if changed:
        _save_json_list(state, _KEY_NEW_FILES, new_files)
        _save_json_list(state, _KEY_DIRS, dirs)
        if new_comments:
            _save_json_list(state, _KEY_COMMENTS, comments)

    # ── Evaluate threshold ───────────────────────────────────────────
    n_new = len(new_files)
    n_dirs = len(dirs)

    # Primary: 3+ new files, OR breadth condition (2+ files, 3+ dirs)
    threshold_met = n_new >= IMPL_NEW_FILE_THRESHOLD or (
        n_new >= IMPL_BREADTH_FILE_THRESHOLD and n_dirs >= IMPL_BREADTH_DIR_THRESHOLD
    )
    if not threshold_met:
        return None

    # Mark pending for stop-nudge even if we can't fire right now
    state.mark_fired("_impl-nudge-pending")

    # Min edits before firing
    invocations = state.edit_invocations()
    if invocations < IMPL_NUDGE_MIN_EDITS:
        return None

    # Cooldown: don't fire again too soon
    last_at_raw = state.load_data(_KEY_LAST_NUDGE_AT)
    if last_at_raw:
        try:
            last_at = int(last_at_raw)
            if invocations - last_at < IMPL_NUDGE_COOLDOWN:
                return None
        except ValueError:
            pass

    # Don't fire if decisions were already captured this session
    store = state.get_store()
    if state.has_recent_decisions(store.decisions_dir):
        return None

    # Record this nudge for cooldown tracking
    state.store_data(_KEY_LAST_NUDGE_AT, str(invocations))

    # ── Build message ────────────────────────────────────────────────
    short_files = [fp.split("/")[-1] if "/" in fp else fp for fp in new_files[:5]]
    files_str = ", ".join(short_files)
    more = f" (+{n_new - 5} more)" if n_new > 5 else ""

    msg = (
        f"This session created {n_new} new file{'s' if n_new != 1 else ''}"
        f" ({files_str}{more}) across {n_dirs} area{'s' if n_dirs != 1 else ''}"
        " — no decisions captured yet.\n"
        "New modules often embody choices worth preserving "
        "(pattern, naming, data structure, trade-offs).\n"
        "Capture now while reasoning is fresh: "
        "`/decision we chose X because Y`"
    )

    if comments:
        hint = comments[0]
        msg += f'\n\nCode comment hint: "{hint}"'

    return PolicyResult(matched=True, ok=True, system_message=msg)
