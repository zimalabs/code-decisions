"""NUDGE policy — detect decision language in user messages, suggest capture."""

from __future__ import annotations

import re
from typing import Any

from ..utils.constants import FALSE_POSITIVE_WINDOW
from ._helpers import _get_prompt
from .engine import PolicyResult, SessionState

_DECISION_PHRASE = re.compile(
    r"(let.?s go with|let.?s use|we decided|switching to|going with|the decision is|we.?ll use|agreed on|settled on"
    r"|i chose|i.?ll use|i.?m going with|after weighing|the trade.?off is worth|the approach is"
    r"|over \w[\w\s]{1,28}\w because|picked \w[\w\s]{1,28}\w instead of"
    r"|opting for|went with|committing to|ruling out|going to use)",
)

# Technical signals that indicate the message is about code, not casual conversation
_TECHNICAL_SIGNAL = re.compile(
    r"`[^`]+`"  # inline code
    r"|[a-z_]{2,}(_[a-z0-9]+)+"  # snake_case
    r"|[A-Z][a-z]+[A-Z][a-zA-Z]*"  # CamelCase
    r"|[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*"  # dotted.path
    r"|(?:src|lib|app)/\S+"  # file paths
)

# Words/phrases that follow decision phrases in non-decision contexts.
# "let's go with your suggestion", "switching to the test file", etc.
_FALSE_POSITIVE_AFTER = re.compile(
    r"(?:your|that|this|the\s+(?:flow|idea|plan|suggestion|file|branch|tab|dir"
    r"|test|next|default|same|above|below|rest|other|first|second))\b"
)

# Reasoning language — strong signal the user is explaining a choice
_REASONING_SIGNAL = re.compile(
    r"\bbecause\b|\binstead of\b|\brather than\b|\btrade.?off\b"
    r"|\bdownside\b|\balternative\b"
)

# ── Conversation context detection ───────────────────────────────────
# Debugging/bug-fixing signals — suppress nudges when the user is troubleshooting
_DEBUG_SIGNAL = re.compile(
    r"\b(?:bug|fix|error|traceback|exception|stack\s*trace|debug|crash|fail"
    r"|broken|issue|typo|wrong|incorrect|unexpected|undefined|null|nil"
    r"|segfault|panic|assert(?:ion)?|regression|flaky|hang|timeout"
    r"|not working|doesn.?t work|can.?t reproduce)\b",
    re.IGNORECASE,
)

# Architecture/design signals — amplify nudges during design discussions.
# These must be specific enough to avoid matching casual conversation
# ("approach" alone is too generic — it triggers on "the simpler approach").
_ARCHITECTURE_SIGNAL = re.compile(
    r"\b(?:architect(?:ure)?|design(?:ing)?\s+(?:the|a|our)|pattern|strategy"
    r"|framework\s+(?:for|to|choice)|migration\s+(?:plan|strategy|from|to)"
    r"|trade.?off|pro(?:s)?\s+(?:and|&)\s+con|compare\s+\w+\s+(?:with|vs|to|and)"
    r"|evaluate|proposal|RFC|ADR|should we\s+(?:use|go|pick|choose|adopt)"
    r"|long.?term|scalab|maintainab|decouple|monolith|micro.?service"
    r"|api design|schema design|data model|system design)\b",
    re.IGNORECASE,
)


_DECISION_QUERY = re.compile(
    r"(why did we|what was decided|what did we decide|what.?s our decision"
    r"|remind me|did we decide|what did we choose|why do we)",
)


def _conversation_context(prompt: str, state: SessionState) -> str:
    """Classify the conversation context as 'debug', 'architecture', or 'neutral'.

    Uses prompt content and session edit history to determine whether the user
    is debugging (suppress nudges) or designing architecture (amplify nudges).
    """
    prompt_lower = prompt.lower()
    debug_hits = len(_DEBUG_SIGNAL.findall(prompt_lower))
    arch_hits = len(_ARCHITECTURE_SIGNAL.findall(prompt_lower))

    # Session edits boost debug signal — lots of test file edits = debugging
    edits = state.files_edited()
    test_edit_count = sum(1 for f in edits if "_test." in f or "/test" in f or ".test." in f)
    if test_edit_count >= 2:
        debug_hits += 1

    if debug_hits >= 2 and debug_hits > arch_hits:
        return "debug"
    if arch_hits >= 1 and arch_hits >= debug_hits:
        return "architecture"
    return "neutral"


def _is_false_positive(prompt_lower: str, match_end: int) -> bool:
    """Check if text following a decision phrase indicates non-decision context."""
    after = prompt_lower[match_end : match_end + FALSE_POSITIVE_WINDOW].lstrip()
    return bool(_FALSE_POSITIVE_AFTER.match(after))


def _has_nearby_technical(prompt: str, start: int, end: int, window: int = 120) -> bool:
    """Check for technical signal within a window around the decision phrase."""
    lo = max(0, start - window)
    hi = min(len(prompt), end + window)
    return bool(_TECHNICAL_SIGNAL.search(prompt[lo:hi]))


def _capture_nudge_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Detect decision language in user messages, suggest capture.

    Also detects decision *query* language (what did we decide about X?) and
    pre-seeds search results so Claude answers from decisions.
    """
    prompt = _get_prompt(data)
    if not prompt:
        return None

    prompt_lower = prompt.lower()

    # Decision queries — pre-seed search results so Claude answers from decisions.
    if _DECISION_QUERY.search(prompt_lower):
        store = state.get_store()
        if store.decision_count() > 0:
            # Extract keywords after the query phrase for search
            keywords = re.sub(
                r"(why did we|what was decided|what did we decide|what.?s our decision"
                r"|remind me|did we decide|what did we choose|why do we|about|the)\b",
                "",
                prompt_lower,
            ).strip()
            keywords = re.sub(r"[^\w\s]", "", keywords).strip()  # strip punctuation
            if keywords:
                results = store.query(keywords, limit=3)
                if results:
                    return PolicyResult(
                        matched=True,
                        ok=True,
                        system_message=f"Matching decisions:\n{results}",
                        reason="Found related decisions — answer from these.",
                    )

    if state.nudges_dismissed():
        return None

    # Context-aware nudging: suppress during debugging, relax during architecture
    context = _conversation_context(prompt, state)
    if context == "debug":
        return None

    # Check for decision language — require corroborating signal to reduce noise.
    # Use finditer (not findall) to get match positions for proximity checks.
    match_iter = list(_DECISION_PHRASE.finditer(prompt_lower))
    if not match_iter:
        return None

    # Filter out false positives based on what follows the phrase
    real_matches = [m for m in match_iter if not _is_false_positive(prompt_lower, m.end())]
    if not real_matches:
        return None

    # Corroboration: need nearby technical signal, reasoning language, or 2+ phrases.
    # In architecture context, any single corroboration signal is enough.
    has_nearby_tech = any(_has_nearby_technical(prompt, m.start(), m.end()) for m in real_matches)
    has_reasoning = bool(_REASONING_SIGNAL.search(prompt_lower))
    has_multiple_phrases = len(set(m.group(0) for m in real_matches)) >= 2

    if context != "architecture":
        # Neutral context: require full corroboration (original behavior)
        if not (has_nearby_tech or has_reasoning or has_multiple_phrases):
            return None
    # Architecture context: decision phrase + false-positive filter is enough —
    # the user is already in a design discussion, so the bar is lower.

    phrase = real_matches[0].group(0)
    dedup_key = f"capture-nudge-{phrase}"
    if state.has_fired(dedup_key):
        return None
    state.mark_fired(dedup_key)
    state.mark_fired("_capture-nudge-pending")  # signal to edit_checkpoint follow-up
    state.store_data("_capture-nudge-pending", phrase)  # store phrase for quoting
    return PolicyResult(
        matched=True,
        ok=True,
        reason="Decision detected — write to `.claude/decisions/` now. No confirmation needed.",
    )
