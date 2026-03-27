"""Similarity utilities — detect near-duplicate tags and overlapping decisions using stdlib only."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .constants import TAG_SIMILARITY_THRESHOLD

if TYPE_CHECKING:
    from ..core.decision import Decision
    from ..store.store import DecisionStore


def _levenshtein(a: str, b: str, max_dist: int = -1) -> int:
    """Compute Levenshtein edit distance between two strings.

    If *max_dist* >= 0, returns early with max_dist + 1 when the distance
    is guaranteed to exceed the threshold (saves work for dissimilar strings).
    """
    if len(a) < len(b):
        return _levenshtein(b, a, max_dist)
    if not b:
        return len(a)

    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        if max_dist >= 0 and min(curr) > max_dist:
            return max_dist + 1
        prev = curr
    return prev[-1]


def similar_tags(
    new_tags: list[str], existing_tags: list[str], threshold: float = TAG_SIMILARITY_THRESHOLD
) -> list[tuple[str, str]]:
    """Find similar tags between new and existing tag sets.

    Returns list of (new_tag, existing_tag) pairs that look like near-duplicates.
    Checks: prefix/suffix containment, plurals, edit distance ratio.
    """
    matches: list[tuple[str, str]] = []
    existing_lower = {t: t.lower() for t in existing_tags}

    for new in new_tags:
        nl = new.lower()
        for ext, el in existing_lower.items():
            if nl == el:
                continue  # exact match is fine

            # Plural check: one is the other + "s"
            if nl + "s" == el or el + "s" == nl:
                matches.append((new, ext))
                continue

            # Prefix/suffix containment (one tag contains the other)
            if len(nl) >= 3 and len(el) >= 3:
                if nl in el or el in nl:
                    matches.append((new, ext))
                    continue

            # Hyphen normalization: "pre-commit" vs "precommit"
            if nl.replace("-", "") == el.replace("-", ""):
                matches.append((new, ext))
                continue

            # Edit distance ratio
            max_len = max(len(nl), len(el))
            if max_len > 0:
                max_dist = math.ceil(max_len * (1.0 - threshold))
                dist = _levenshtein(nl, el, max_dist)
                ratio = 1.0 - (dist / max_len)
                if ratio >= threshold:
                    matches.append((new, ext))

    return matches


def suggest_tags_from_overlaps(dec: Decision, store: DecisionStore, max_results: int = 5) -> list[str]:
    """Suggest existing tags from decisions that overlap with this one.

    Uses ``find_overlapping_decisions`` (lower threshold) to find related decisions,
    then collects their tags, excluding tags already on ``dec``.
    Returns up to *max_results* suggestions sorted by frequency.
    """
    overlaps = find_overlapping_decisions(dec, store, threshold=2.0, max_results=5)
    if not overlaps:
        return []

    existing = set(dec.tags)
    suggested: dict[str, int] = {}

    all_decisions = store.list_decisions()
    slug_map = {d.slug: d for d in all_decisions}

    for slug, _title, _score in overlaps:
        d = slug_map.get(slug)
        if not d:
            continue
        for t in d.tags:
            if t not in existing:
                suggested[t] = suggested.get(t, 0) + 1

    if not suggested:
        return []

    return sorted(suggested, key=lambda t: (-suggested[t], t))[:max_results]


def _affects_overlap(a_paths: list[str], b_paths: list[str]) -> int:
    """Count overlapping affects entries between two decisions.

    Handles exact matches and directory containment (``src/auth/`` contains ``src/auth/handler.py``).
    """
    if not a_paths or not b_paths:
        return 0

    a_set = set(a_paths)
    b_set = set(b_paths)
    count = len(a_set & b_set)

    # Directory containment: "src/auth/" contains "src/auth/handler.py"
    a_dirs = [p for p in a_set if p.endswith("/")]
    b_dirs = [p for p in b_set if p.endswith("/")]
    for a_dir in a_dirs:
        for bp in b_set:
            if bp != a_dir and bp.startswith(a_dir):
                count += 1
    for b_dir in b_dirs:
        for ap in a_set:
            if ap != b_dir and ap.startswith(b_dir):
                count += 1

    return count


def find_overlapping_decisions(
    dec: Decision,
    store: DecisionStore,
    *,
    threshold: float = 4.0,
    max_results: int = 3,
) -> list[tuple[str, str, float]]:
    """Find existing decisions that overlap with a new one.

    Scores each existing decision: +2 per shared tag, +3 per overlapping affects path.
    Returns ``(slug, title, score)`` tuples above *threshold*, highest score first.
    Excludes the decision's own slug.
    """
    try:
        summaries = store.list_summaries()
        affects_data = {slug: aff for slug, _t, _d, _tags, aff in store.decisions_with_affects()}
    except Exception:
        return []

    new_tags = set(dec.tags)
    results: list[tuple[str, str, float]] = []

    for s in summaries:
        if s.slug == dec.name:
            continue  # don't match self

        score = 0.0

        # Tag overlap: +2 per shared tag
        shared_tags = new_tags & set(s.tags)
        score += len(shared_tags) * 2.0

        # Affects overlap: +3 per overlapping path
        existing_affects = affects_data.get(s.slug, [])
        score += _affects_overlap(dec.affects, existing_affects) * 3.0

        if score >= threshold:
            results.append((s.slug, s.title, score))

    results.sort(key=lambda x: x[2], reverse=True)
    return results[:max_results]
