"""Query functions — FTS5 search with keyword fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .index import SearchResult
    from .store import DecisionStore


# ── Relevance helpers ─────────────────────────────────────────────


def _relevance_label(rank: float, *, is_fts: bool = True) -> str:
    """Convert a search rank to a relevance indicator.

    FTS5 BM25 ranks are negative (more negative = more relevant).
    Keyword scores are positive (higher = more relevant).
    """
    if is_fts:
        if rank <= -5.0:
            return "●●●"
        if rank <= -2.0:
            return "●●"
        return "●"
    # keyword score (positive)
    if rank >= 5:
        return "●●●"
    if rank >= 3:
        return "●●"
    return "●"


def _group_by_primary_tag(
    results: list[tuple[str, str, str, list[str], str, str]],
) -> dict[str, list[tuple[str, str, str, list[str], str, str]]]:
    """Group formatted result tuples by their primary (first) tag.

    Each tuple is (date, title, relevance, tags, excerpt, tag_str).
    Returns an ordered dict preserving first-seen tag order.
    """
    groups: dict[str, list[tuple[str, str, str, list[str], str, str]]] = {}
    for item in results:
        tags = item[3]
        primary = tags[0] if tags else "(untagged)"
        groups.setdefault(primary, []).append(item)
    return groups


def _format_result_line(date: str, title: str, relevance: str, tag_str: str, excerpt: str) -> str:
    """Format a single search result as a markdown bullet with excerpt on next line."""
    header = f"- [{date}] {title} {relevance}"
    if tag_str:
        header += f" {tag_str}"
    if excerpt:
        header += f"\n  {excerpt}"
    return header


# ── Main query functions ──────────────────────────────────────────


def query_relevant(
    store: DecisionStore,
    search_terms: str,
    limit: int = 3,
    exclude_slugs: set[str] | None = None,
) -> str:
    """Search for decisions matching keywords. Returns formatted string.

    Tries FTS5 index first (stemming + BM25 ranking), falls back to
    plain keyword matching if FTS5 is unavailable.

    Results are always flat (one per line) with relevance indicators.
    """
    if not search_terms:
        return ""

    # Try FTS5 path
    index = store._index
    if index.available:
        # Request extra results to account for exclusions
        extra = len(exclude_slugs) if exclude_slugs else 0
        results = index.search(search_terms, limit + extra)
        if exclude_slugs:
            results = [r for r in results if r.slug not in exclude_slugs]
        results = results[:limit]
        if results:
            return _format_fts_results(results)

    # Fallback: plain keyword matching (FTS5 unavailable or returned nothing)
    fallback_result = _keyword_search(store, search_terms, limit, exclude_slugs=exclude_slugs)
    if fallback_result and not index.available:
        fallback_result += "\n_(FTS5 unavailable — results from keyword matching, quality may vary)_"
    return fallback_result


def query_titles(
    store: DecisionStore,
    search_terms: str,
    limit: int = 3,
    exclude_slugs: set[str] | None = None,
) -> list[str]:
    """Search for decisions matching keywords. Returns list of titles.

    Tries FTS5 index first, falls back to keyword matching.
    """
    if not search_terms:
        return []

    index = store._index
    if index.available:
        extra = len(exclude_slugs) if exclude_slugs else 0
        results = index.search(search_terms, limit + extra)
        if exclude_slugs:
            results = [r for r in results if r.slug not in exclude_slugs]
        results = results[:limit]
        if results:
            return [r.title for r in results]

    # Fallback: plain keyword matching
    from ..utils.constants import KEYWORD_WEIGHT_BODY, KEYWORD_WEIGHT_TAGS, KEYWORD_WEIGHT_TITLE

    decisions = store.list_decisions()
    if not decisions:
        return []

    raw_terms = search_terms.lower().split()
    if not raw_terms:
        return []

    term_variants = [(t, _naive_stem(t)) for t in raw_terms]
    scored: list[tuple[float, str]] = []
    for dec in decisions:
        if exclude_slugs and dec.slug in exclude_slugs:
            continue
        title_lower = dec.title.lower()
        tags_lower = " ".join(dec.tags).lower()
        desc_lower = dec.description.lower()
        body_lower = dec.body.lower()
        score: float = 0
        for original, stemmed in term_variants:
            if original in title_lower:
                score += KEYWORD_WEIGHT_TITLE
            elif stemmed in title_lower or _fuzzy_match(original, title_lower):
                score += KEYWORD_WEIGHT_TITLE * 0.6
            if original in tags_lower or original in desc_lower:
                score += KEYWORD_WEIGHT_TAGS
            elif stemmed in tags_lower or stemmed in desc_lower:
                score += KEYWORD_WEIGHT_TAGS * 0.6
            if original in body_lower:
                score += KEYWORD_WEIGHT_BODY
            elif stemmed in body_lower or _fuzzy_match(original, body_lower):
                score += KEYWORD_WEIGHT_BODY * 0.6
        if score > 0:
            scored.append((score, dec.title))
    scored.sort(key=lambda x: -x[0])
    return [title for _, title in scored[:limit]]


def _format_fts_results(results: list[SearchResult]) -> str:
    """Format FTS5 search results with relevance indicators."""
    lines = []
    for r in results:
        relevance = _relevance_label(r.rank, is_fts=True)
        tag_str = f"({', '.join(r.tags)})" if r.tags else ""
        lines.append(_format_result_line(r.date, r.title, relevance, tag_str, r.excerpt))
    return "\n".join(lines)


def _format_grouped(
    items: list[tuple[str, str, str, list[str], str, str]],
) -> str:
    """Format results grouped by primary tag."""
    groups = _group_by_primary_tag(items)
    parts: list[str] = []
    for tag, group_items in groups.items():
        count = len(group_items)
        parts.append(f"**{tag}** ({count}):")
        for date, title, rel, _tags, excerpt, tag_str in group_items:
            parts.append(_format_result_line(date, title, rel, tag_str, excerpt))
    return "\n".join(parts)


def _naive_stem(word: str) -> str:
    """Simple suffix-stripping stemmer for keyword fallback (no external deps).

    Handles common English suffixes to improve recall when FTS5 porter
    stemmer is unavailable.
    """
    if len(word) <= 4:
        return word
    for suffix in (
        "ation",
        "tion",
        "ness",
        "ment",
        "ings",
        "able",
        "ible",
        "ally",
        "ious",
        "ing",
        "ies",
        "ion",
        "ful",
        "ous",
        "ive",
        "ity",
        "ize",
        "ise",
        "ely",
        "ist",
        "ant",
        "ent",
        "ess",
        "ure",
        "age",
        "ate",
        "ed",
        "er",
        "ly",
        "es",
        "al",
    ):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def _fuzzy_match(term: str, text: str) -> bool:
    """Check if term approximately matches any word in text (Levenshtein distance ≤ 1)."""
    if term in text:
        return True
    # Only try fuzzy for terms ≥ 4 chars (short terms produce too many false positives)
    if len(term) < 4:
        return False
    from ..utils.similarity import _levenshtein

    for word in text.split():
        # Strip punctuation for cleaner matching
        word = word.strip(".,;:!?()[]{}\"'`")
        if not word:
            continue
        if abs(len(word) - len(term)) > 1:
            continue  # skip words too different in length
        if _levenshtein(term, word, max_dist=1) <= 1:
            return True
    return False


def _keyword_search(
    store: DecisionStore,
    search_terms: str,
    limit: int,
    exclude_slugs: set[str] | None = None,
) -> str:
    """Keyword-match search with weighted scoring, fuzzy matching, and basic stemming.

    Uses naive suffix-stripping stemmer and Levenshtein fuzzy matching to
    improve recall when FTS5 is unavailable.
    """
    from ..utils.constants import KEYWORD_WEIGHT_BODY, KEYWORD_WEIGHT_TAGS, KEYWORD_WEIGHT_TITLE

    decisions = store.list_decisions()
    if not decisions:
        return ""

    raw_terms = search_terms.lower().split()
    if not raw_terms:
        return ""

    # Build term variants: original + stemmed form
    term_variants: list[tuple[str, str]] = []  # (original, stemmed)
    for t in raw_terms:
        term_variants.append((t, _naive_stem(t)))

    from ..core.decision import Decision

    scored: list[tuple[float, Decision]] = []
    for dec in decisions:
        slug = dec.slug
        if exclude_slugs and slug in exclude_slugs:
            continue

        title_lower = dec.title.lower()
        tags_lower = " ".join(dec.tags).lower()
        desc_lower = dec.description.lower()
        body_lower = dec.body.lower()

        score: float = 0
        for original, stemmed in term_variants:
            # Exact match (full weight)
            if original in title_lower:
                score += KEYWORD_WEIGHT_TITLE
            elif stemmed in title_lower or _fuzzy_match(original, title_lower):
                score += KEYWORD_WEIGHT_TITLE * 0.6

            if original in tags_lower or original in desc_lower:
                score += KEYWORD_WEIGHT_TAGS
            elif stemmed in tags_lower or stemmed in desc_lower:
                score += KEYWORD_WEIGHT_TAGS * 0.6

            if original in body_lower:
                score += KEYWORD_WEIGHT_BODY
            elif stemmed in body_lower or _fuzzy_match(original, body_lower):
                score += KEYWORD_WEIGHT_BODY * 0.6

        if score > 0:
            scored.append((score, dec))

    scored.sort(key=lambda x: -x[0])
    results = scored[:limit]

    if not results:
        return ""

    lines = []
    for kw_score, dec in results:
        relevance = _relevance_label(kw_score, is_fts=False)
        tag_str = f"({', '.join(dec.tags)})" if dec.tags else ""
        lines.append(_format_result_line(dec.date, dec.title, relevance, tag_str, dec.reasoning_excerpt))

    return "\n".join(lines)
