"""Contradiction detection — find decisions that give opposing guidance on the same area."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .similarity import _affects_overlap

if TYPE_CHECKING:
    pass

# Verb pairs where one negates the other.  Each tuple is (positive, negative).
OPPOSING_PAIRS: list[tuple[str, str]] = [
    ("use", "avoid"),
    ("always", "never"),
    ("prefer", "reject"),
    ("require", "prohibit"),
    ("enable", "disable"),
    ("add", "remove"),
    ("allow", "disallow"),
    ("allow", "forbid"),
    ("include", "exclude"),
    ("keep", "drop"),
    ("adopt", "abandon"),
]

# Build compiled patterns: capture the subject after each verb (up to 5 tokens).
_SUBJECT_RE: dict[str, re.Pattern[str]] = {}
for _pos, _neg in OPPOSING_PAIRS:
    for _verb in (_pos, _neg):
        if _verb not in _SUBJECT_RE:
            # Match: "use Redis", "avoid the monolith", "always validate input"
            _SUBJECT_RE[_verb] = re.compile(
                rf"\b{_verb}\b[\s]+(.{{1,60}}?)(?:[.,;!?\n]|$)",
                re.IGNORECASE,
            )


def _extract_subjects(text: str, verb: str) -> list[str]:
    """Extract subject phrases following a verb (lowercased, first 4 words)."""
    pat = _SUBJECT_RE.get(verb)
    if not pat:
        return []
    results: list[str] = []
    for m in pat.finditer(text):
        raw = m.group(1).strip().lower()
        # Truncate to first 4 content words to avoid diluting overlap
        words = [w for w in raw.split() if len(w) > 1 or w.isalpha()][:4]
        if words:
            results.append(" ".join(words))
    return results


def _subjects_overlap(subjects_a: list[str], subjects_b: list[str]) -> bool:
    """Check if any subject from A appears in (or contains) any subject from B."""
    for sa in subjects_a:
        sa_words = set(sa.split())
        for sb in subjects_b:
            sb_words = set(sb.split())
            # Exact match or significant word overlap (>50% of shorter phrase)
            if sa == sb:
                return True
            common = sa_words & sb_words
            min_len = min(len(sa_words), len(sb_words))
            if min_len > 0 and len(common) / min_len >= 0.5:
                return True
    return False


def find_contradictions(
    body_a: str,
    body_b: str,
    affects_a: list[str],
    affects_b: list[str],
) -> float:
    """Score how contradictory two decisions are (0.0 = no conflict, 1.0 = strong).

    Gates on affects overlap first — decisions about different areas can't contradict.
    Then scans for opposing verb patterns with overlapping subjects.
    """
    # Gate: no affects overlap → no contradiction possible
    overlap = _affects_overlap(affects_a, affects_b)
    if overlap == 0:
        return 0.0

    # Scan for opposing language with shared subjects
    matches_found = 0

    for pos_verb, neg_verb in OPPOSING_PAIRS:
        pos_subjects_a = _extract_subjects(body_a, pos_verb)
        neg_subjects_a = _extract_subjects(body_a, neg_verb)
        pos_subjects_b = _extract_subjects(body_b, pos_verb)
        neg_subjects_b = _extract_subjects(body_b, neg_verb)

        # A says "use X", B says "avoid X" (or vice versa)
        if pos_subjects_a and neg_subjects_b:
            if _subjects_overlap(pos_subjects_a, neg_subjects_b):
                matches_found += 1
        if neg_subjects_a and pos_subjects_b:
            if _subjects_overlap(neg_subjects_a, pos_subjects_b):
                matches_found += 1

    if matches_found == 0:
        return 0.0

    # Score: affects overlap contributes 0.3, language opposition 0.7
    # A single clear opposition (1 match) should score above the default 0.5 threshold
    affects_component = min(overlap / 2.0, 1.0) * 0.3
    language_component = min(matches_found, 1.0) * 0.7
    return affects_component + language_component


def detect_pairwise(
    decisions: list[tuple[str, str, list[str], list[str]]],
    threshold: float = 0.5,
) -> list[tuple[str, str, float]]:
    """Check all decision pairs for contradictions.

    *decisions* is a list of ``(slug, body, tags, affects)`` tuples.
    Returns ``(slug_a, slug_b, score)`` for pairs above *threshold*.
    Early-outs on no affects overlap to keep practical complexity low.
    """
    results: list[tuple[str, str, float]] = []
    n = len(decisions)
    for i in range(n):
        slug_a, body_a, _tags_a, affects_a = decisions[i]
        for j in range(i + 1, n):
            slug_b, body_b, _tags_b, affects_b = decisions[j]
            score = find_contradictions(body_a, body_b, affects_a, affects_b)
            if score >= threshold:
                results.append((slug_a, slug_b, score))
    results.sort(key=lambda x: x[2], reverse=True)
    return results
