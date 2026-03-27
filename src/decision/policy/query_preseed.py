"""NUDGE policy — pre-seed query results when /decision is invoked with search intent."""

from __future__ import annotations

import re
from typing import Any

from ..utils.constants import RELATED_CONTEXT_LIMIT
from ._helpers import _get_prompt
from .engine import PolicyResult, SessionState


def _query_preseed_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Pre-seed query results when the user invokes /decision with search arguments."""
    prompt = _get_prompt(data)
    if not prompt:
        return None

    # Match /decision with search-like arguments (also handles legacy /decision:search)
    match = re.search(r"/decision(?::search)?\s+(.+)", prompt, re.IGNORECASE)
    if not match:
        return None

    # Skip if arguments look like capture/manage intent
    args = match.group(1).strip()
    _MANAGE_WORDS = {"publish", "review", "undo", "dismiss", "debug"}
    _CAPTURE_SIGNALS = {"we chose", "decided to", "going with", "use ", "chose "}
    first_word = args.split()[0].lower() if args.split() else ""
    if first_word in _MANAGE_WORDS:
        return None
    if any(args.lower().startswith(sig) for sig in _CAPTURE_SIGNALS):
        return None

    if not args:
        return None

    store = state.get_store()
    if store.decision_count() == 0:
        return None

    results = store.query(args, RELATED_CONTEXT_LIMIT)
    if not results:
        return None

    return PolicyResult(
        matched=True,
        ok=True,
        reason=(
            f'Pre-scored results for "{args}":\n{results}\n\nUse Glob/Grep/Read to dig deeper into matching files.'
        ),
    )
