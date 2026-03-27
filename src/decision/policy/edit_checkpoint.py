"""NUDGE policy — follow up on unacted capture nudges mid-session."""

from __future__ import annotations

from typing import Any

from ..utils.constants import FOLLOWUP_EDIT_DELAY, SKIP_FILE_PATTERNS
from ._helpers import _extract_file_path
from .engine import PolicyResult, SessionState


def _edit_checkpoint_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Follow up when capture-nudge detected decision language but no decision was written.

    Only fires when:
    1. A capture-nudge previously fired (decision language detected)
    2. No decision file was written since
    3. At least FOLLOWUP_EDIT_DELAY edits have passed (don't nag immediately)

    Fires once. Stop-nudge remains active as the last safety net.
    """
    if state.nudges_dismissed():
        return None

    fp = _extract_file_path(data)
    if not fp:
        return None

    # Don't count memory/decision/test/config files
    if any(pat in fp for pat in SKIP_FILE_PATTERNS):
        return None

    # Only follow up if capture-nudge detected decision language
    if not state.has_fired("_capture-nudge-pending"):
        return None

    # Don't double-nag if impl-nudge already told the user to capture
    if state.has_fired("_impl-nudge-pending"):
        return None

    store = state.get_store()
    if state.has_recent_decisions(store.decisions_dir):
        return None  # Decision was captured — pending is resolved

    # Wait for a few edits after the nudge before following up
    if state.edit_invocations() < FOLLOWUP_EDIT_DELAY:
        return None

    # Fire once — suppress further edit-checkpoint follow-ups but preserve stop-nudge
    if state.has_fired("_unacted-capture-shown"):
        return None
    state.mark_fired("_unacted-capture-shown")

    phrase = state.load_data("_capture-nudge-pending")
    quote = f' ("{phrase}")' if phrase else ""

    return PolicyResult(
        matched=True,
        system_message=(f"Uncaptured choice detected{quote} — `/decision capture` if a decision was made."),
    )
