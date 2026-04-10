"""NUDGE policy — actively nudge at session end when edits lack decisions."""

from __future__ import annotations

import json
import sys
from typing import Any

from .engine import PolicyResult, SessionState


def _should_suppress_coaching() -> bool:
    """Check if coaching nudges should be suppressed for experienced capturers.

    Reads capture_history.json and surfacing_history.json. If captures occurred
    in >= COACHING_SUPPRESS_THRESHOLD of the last COACHING_WINDOW sessions,
    suppress impl/plan coaching messages at session end.
    """
    from ..utils.constants import COACHING_SUPPRESS_THRESHOLD, COACHING_WINDOW
    from ..utils.helpers import _state_dir

    path = _state_dir() / "capture_history.json"
    if not path.is_file():
        return False

    try:
        history: list[float] = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return False

    if not history:
        return False

    # Count distinct sessions with captures (group by 4-hour windows)
    SESSION_GAP = 4 * 3600
    sessions: list[float] = []
    for ts in sorted(history):
        if not sessions or ts - sessions[-1] > SESSION_GAP:
            sessions.append(ts)

    recent = sessions[-COACHING_WINDOW:]
    return len(recent) >= COACHING_SUPPRESS_THRESHOLD


def _save_last_session(state: SessionState) -> None:
    """Persist uncaptured-edit info so the next session can reflect on it."""
    import time

    from ..utils.helpers import _state_dir

    info = {
        "edit_count": state.edit_count(),
        "files": state.files_edited()[:10],
        "timestamp": time.time(),
    }
    path = _state_dir() / "last_session.json"
    try:
        path.write_text(json.dumps(info))
    except OSError:
        pass


def load_last_session(decisions_dir: Any) -> dict[str, Any] | None:
    """Load and remove the last-session info file. Returns None if absent."""
    from pathlib import Path

    from ..utils.helpers import _state_dir

    path = _state_dir() / "last_session.json"
    # Also check legacy location
    if not path.is_file():
        legacy = Path(decisions_dir) / ".decision_last_session.json"
        if legacy.is_file():
            path = legacy
    if not path.is_file():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text())
        path.unlink(missing_ok=True)
        return data
    except (json.JSONDecodeError, OSError):
        path.unlink(missing_ok=True)
        return None


def _session_activity_summary(state: SessionState) -> str:
    """Build a 1-line session activity summary for ambient visibility."""
    ctx = state.get_activity_counter("context_injections")
    nudges = state.nudge_count()
    parts = []
    if ctx:
        parts.append(f"{ctx} decision{'s' if ctx != 1 else ''} surfaced")
    if nudges:
        parts.append(f"{nudges} nudge{'s' if nudges != 1 else ''} fired")
    if not parts:
        return ""
    return "◆ Decision plugin: " + " · ".join(parts)


def _check_staleness(state: SessionState) -> str | None:
    """Check if session edits touch files covered by stale decisions."""
    edited = state.files_edited()
    if not edited:
        return None

    try:
        from datetime import datetime, timedelta, timezone

        from ..utils.constants import STALENESS_AGE_DAYS
        from .related_context import _affects_match

        store = state.get_store()
        cutoff = datetime.now(timezone.utc).date() - timedelta(days=STALENESS_AGE_DAYS)
        cutoff_str = cutoff.isoformat()

        stale_slugs: dict[str, str] = {}  # slug -> date
        for slug, _title, date, _tags, affects in store.decisions_with_affects():
            if date >= cutoff_str:
                continue  # fresh enough
            for fp in edited:
                if _affects_match(affects, fp):
                    stale_slugs[slug] = date
                    break
            if len(stale_slugs) >= 5:
                break  # cap for performance

        if not stale_slugs:
            return None

        n = len(stale_slugs)
        slug_list = ", ".join(f"`{s}`" for s in list(stale_slugs)[:3])
        return f"{n} stale decision{'s' if n != 1 else ''} touched today: {slug_list} — worth a glance?"
    except Exception as exc:
        print(f"decision: _check_staleness error: {exc}", file=sys.stderr)
        return None  # Never break Claude Code


def _update_surfacing_history(state: SessionState) -> None:
    """Persist per-decision surfacing counts across sessions."""
    surfaced = state.decisions_surfaced()
    if not surfaced:
        return

    try:
        from ..utils.helpers import _state_dir

        path = _state_dir() / "surfacing_history.json"
        history: dict[str, int] = {}
        if path.is_file():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        for slug in surfaced:
            history[slug] = history.get(slug, 0) + 1

        # Cap at 500 entries — prune least-surfaced
        if len(history) > 500:
            sorted_items = sorted(history.items(), key=lambda x: x[1], reverse=True)
            history = dict(sorted_items[:500])

        path.write_text(json.dumps(history))
    except OSError:
        pass


def _check_never_surfaced(state: SessionState) -> str | None:
    """Warn about recent decisions with affects that have never surfaced in any session."""
    try:
        from datetime import datetime, timedelta, timezone

        from ..utils.constants import NEVER_SURFACED_AGE_DAYS
        from ..utils.helpers import _state_dir

        # Load surfacing history (accumulated across sessions)
        history_path = _state_dir() / "surfacing_history.json"
        surfaced_slugs: set[str] = set()
        if history_path.is_file():
            try:
                surfaced_slugs = set(json.loads(history_path.read_text()).keys())
            except (json.JSONDecodeError, OSError):
                pass

        store = state.get_store()
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=NEVER_SURFACED_AGE_DAYS)).isoformat()

        never_surfaced: list[str] = []
        for slug, _title, date, _tags, affects in store.decisions_with_affects():
            if date < cutoff:
                continue  # too old
            if not affects:
                continue  # no affects = expected to not surface
            if slug in surfaced_slugs:
                continue  # has surfaced before
            never_surfaced.append(slug)
            if len(never_surfaced) >= 3:
                break

        if not never_surfaced:
            return None

        n = len(never_surfaced)
        slug_list = ", ".join(f"`{s}`" for s in never_surfaced)
        return f"{n} decision{'s' if n != 1 else ''} never surfaced: {slug_list} — `/decision enrich` to check"
    except Exception as exc:
        print(f"decision: _check_never_surfaced error: {exc}", file=sys.stderr)
        return None  # Never break Claude Code


def _scan_assistant_decisions(state: SessionState) -> list[str]:
    """Scan the session transcript for decision language in assistant messages.

    Reads the tail of the JSONL transcript, parses assistant text blocks, and
    applies the same corroboration requirements as capture_nudge. Returns a list
    of matched decision phrases (max 3).
    """
    from ..utils.constants import TRANSCRIPT_MAX_BLOCKS, TRANSCRIPT_TAIL_BYTES
    from ..utils.helpers import _discover_transcript
    from .capture_nudge import (
        _DECISION_PHRASE,
        _REASONING_SIGNAL,
        _has_nearby_technical,
        _is_false_positive,
    )

    try:
        path = _discover_transcript()
        if path is None:
            return []

        # Read the tail of the file to bound scan time
        file_size = path.stat().st_size
        with open(path, encoding="utf-8", errors="replace") as f:
            if file_size > TRANSCRIPT_TAIL_BYTES:
                f.seek(file_size - TRANSCRIPT_TAIL_BYTES)
                f.readline()  # discard partial first line
            lines = f.readlines()

        # Extract text blocks from assistant messages
        texts: list[str] = []
        for line in reversed(lines):
            if len(texts) >= TRANSCRIPT_MAX_BLOCKS:
                break
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if obj.get("type") != "assistant":
                continue
            content = obj.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        texts.append(text)

        if not texts:
            return []

        # Deduplicate against phrases already detected by capture_nudge
        already_detected = state.load_data("_capture-nudge-pending").lower()

        phrases: list[str] = []
        seen: set[str] = set()
        for text in texts:
            text_lower = text.lower()
            match_iter = list(_DECISION_PHRASE.finditer(text_lower))
            if not match_iter:
                continue

            real_matches = [m for m in match_iter if not _is_false_positive(text_lower, m.end())]
            if not real_matches:
                continue

            # Corroboration: same bar as capture_nudge neutral context
            has_nearby_tech = any(_has_nearby_technical(text, m.start(), m.end()) for m in real_matches)
            has_reasoning = bool(_REASONING_SIGNAL.search(text_lower))
            has_multiple = len(set(m.group(0) for m in real_matches)) >= 2

            if not (has_nearby_tech or has_reasoning or has_multiple):
                continue

            for m in real_matches:
                phrase = m.group(0)
                if phrase in seen:
                    continue
                # Skip if capture_nudge already detected this phrase from user input
                if already_detected and phrase in already_detected:
                    continue
                seen.add(phrase)
                phrases.append(phrase)
                if len(phrases) >= 3:
                    return phrases

        return phrases
    except Exception as exc:
        print(f"decision: _scan_assistant_decisions error: {exc}", file=sys.stderr)
        return []


def _assistant_decision_summary(state: SessionState) -> str | None:
    """Check for decision language in assistant messages via transcript scanning."""
    if state.nudges_dismissed():
        return None

    store = state.get_store()
    if state.has_recent_decisions(store.decisions_dir):
        return None

    phrases = _scan_assistant_decisions(state)
    if not phrases:
        return None

    if len(phrases) == 1:
        return f'Assistant stated a choice ("{phrases[0]}") — write to `.claude/decisions/` to preserve context'
    return f"Assistant stated {len(phrases)} uncaptured choices — write to `.claude/decisions/` to preserve context"


def _stop_nudge_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Show a compact one-line summary at session end. Never a wall of text."""
    # Persist surfacing analytics before building summary
    _update_surfacing_history(state)

    activity_summary = _session_activity_summary(state)

    # Check if there's an unacted capture to nag about
    has_unacted = state.has_fired("_capture-nudge-pending") and not state.nudges_dismissed()

    if has_unacted:
        store = state.get_store()
        if state.has_recent_decisions(store.decisions_dir):
            has_unacted = False  # Decision was captured — resolved
        else:
            # Save for next session
            _save_last_session(state)

    if has_unacted:
        phrase = state.load_data("_capture-nudge-pending")
        quote = f' ("{phrase}")' if phrase else ""
        nudge_msg = (
            f"Uncaptured choice detected{quote} — write to `.claude/decisions/` next time. No confirmation needed."
        )
        if activity_summary:
            nudge_msg = activity_summary + " · " + nudge_msg
        return PolicyResult(matched=True, system_message=nudge_msg)

    # Suppress coaching nudges for experienced capturers
    suppress_coaching = _should_suppress_coaching()

    # Pick the single highest-priority secondary hint (one sentence max).
    # Priority: assistant scan > impl session > plan session > staleness > never-surfaced.
    secondary_msg: str | None = None
    secondary_msg = _assistant_decision_summary(state)
    if secondary_msg is None and not suppress_coaching:
        secondary_msg = _impl_session_summary(state)
    if secondary_msg is None and not suppress_coaching:
        secondary_msg = _plan_session_summary(state)
    if secondary_msg is None:
        secondary_msg = _check_staleness(state)
    if secondary_msg is None:
        secondary_msg = _check_never_surfaced(state)

    # Combine activity summary + at most one compact secondary hint
    combined = activity_summary
    if secondary_msg:
        combined = (combined + " · " + secondary_msg).strip() if combined else secondary_msg

    # Clean up this session's /tmp state dir — all data persisted above
    state.cleanup()

    if combined:
        return PolicyResult(matched=True, system_message=combined)

    return None


def _impl_session_summary(state: SessionState) -> str | None:
    """Detect implementation sessions and summarize uncaptured decisions."""
    if state.nudges_dismissed():
        return None

    try:
        from .impl_nudge import _load_json_list

        new_files = _load_json_list(state, "_impl-new-files")
    except Exception as exc:
        print(f"decision: _impl_session_summary error: {exc}", file=sys.stderr)
        return None

    if not new_files:
        return None

    # Check if decisions were already captured
    store = state.get_store()
    if state.has_recent_decisions(store.decisions_dir):
        return None

    # impl-nudge-pending means threshold was met mid-session
    # Otherwise, check heuristic: 2+ new files and 5+ total edits
    has_pending = state.has_fired("_impl-nudge-pending")
    is_impl_session = len(new_files) >= 2 and state.edit_count() >= 5

    if not has_pending and not is_impl_session:
        return None

    n_files = len(new_files)

    return (
        f"{n_files} new file{'s' if n_files != 1 else ''} created, no decisions captured"
        " — write decisions to `.claude/decisions/` if choices were made"
    )


def _plan_session_summary(state: SessionState) -> str | None:
    """Check for uncaptured plan candidates at session end."""
    if state.nudges_dismissed():
        return None

    if not state.has_fired("_plan-candidates-ready"):
        return None

    # If decisions were captured, nothing to report
    store = state.get_store()
    if state.has_recent_decisions(store.decisions_dir):
        return None

    try:
        from .plan_nudge import _load_candidates

        candidates = _load_candidates(state)
    except Exception as exc:
        print(f"decision: _plan_session_summary error: {exc}", file=sys.stderr)
        return None

    if not candidates:
        return None

    n = len(candidates)

    return f"{n} plan choice{'s' if n != 1 else ''} uncaptured — write to `.claude/decisions/` while reasoning is fresh"
