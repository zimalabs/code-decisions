"""Tests for search result formatting — relevance indicators and tag grouping."""

from decision.store.query import (
    _format_grouped,
    _format_result_line,
    _group_by_primary_tag,
    _relevance_label,
)
from conftest import make_decision, make_store


# ── Relevance label ───────────────────────────────────────────────


def test_relevance_label_fts_high():
    assert _relevance_label(-6.0, is_fts=True) == "●●●"


def test_relevance_label_fts_medium():
    assert _relevance_label(-3.0, is_fts=True) == "●●"


def test_relevance_label_fts_low():
    assert _relevance_label(-1.0, is_fts=True) == "●"


def test_relevance_label_keyword_high():
    assert _relevance_label(5, is_fts=False) == "●●●"


def test_relevance_label_keyword_medium():
    assert _relevance_label(3, is_fts=False) == "●●"


def test_relevance_label_keyword_low():
    assert _relevance_label(1, is_fts=False) == "●"


# ── Group by primary tag ──────────────────────────────────────────


def _item(date, title, tags, excerpt=""):
    """Helper to create a result tuple."""
    rel = "●●"
    tag_str = f"({', '.join(tags)})" if tags else ""
    return (date, title, rel, tags, excerpt, tag_str)


def test_group_by_primary_tag_basic():
    items = [
        _item("2026-03-20", "Decision A", ["auth", "security"]),
        _item("2026-03-19", "Decision B", ["auth"]),
        _item("2026-03-18", "Decision C", ["caching"]),
    ]
    groups = _group_by_primary_tag(items)
    assert list(groups.keys()) == ["auth", "caching"]
    assert len(groups["auth"]) == 2
    assert len(groups["caching"]) == 1


def test_group_by_primary_tag_untagged():
    items = [
        _item("2026-03-20", "Tagged", ["api"]),
        _item("2026-03-19", "Untagged", []),
    ]
    groups = _group_by_primary_tag(items)
    assert "(untagged)" in groups
    assert len(groups["(untagged)"]) == 1


# ── Format result line ────────────────────────────────────────────


def test_format_result_line_with_excerpt():
    line = _format_result_line("2026-03-20", "Use Redis", "●●●", "(caching)", "Fast lookups")
    assert "●●●" in line
    assert "Use Redis" in line
    assert "Fast lookups" in line
    assert "(caching)" in line
    # Excerpt should be on its own indented line
    assert "\n  Fast lookups" in line


def test_format_result_line_without_excerpt():
    line = _format_result_line("2026-03-20", "Use Redis", "●●", "", "")
    assert "●●" in line
    assert "Use Redis" in line
    assert "\n" not in line


# ── Grouped formatting ────────────────────────────────────────────


def test_format_grouped_produces_tag_headers():
    items = [
        _item("2026-03-20", "Auth Decision", ["auth"]),
        _item("2026-03-19", "Cache Decision", ["caching"]),
        _item("2026-03-18", "Auth Decision 2", ["auth"]),
        _item("2026-03-17", "Billing Decision", ["billing"]),
    ]
    result = _format_grouped(items)
    assert "**auth** (2):" in result
    assert "**caching** (1):" in result
    assert "**billing** (1):" in result


# ── query_relevant integration ────────────────────────────────────


def test_query_relevant_flat_with_relevance(tmp_path):
    """query_relevant with <=3 results includes relevance indicators."""
    from decision.store.query import query_relevant

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-cache", tags=["caching"])

    result = query_relevant(store, "redis", limit=3)
    # Should contain relevance dots
    assert "●" in result


def test_query_relevant_flat_with_many_results(tmp_path):
    """query_relevant with >3 results uses same flat format as fewer results."""
    from decision.store.query import query_relevant

    decisions_dir, store = make_store(tmp_path)
    # Create decisions with overlapping keyword "test" in title
    for i in range(5):
        tag = "auth" if i < 3 else "billing"
        make_decision(decisions_dir, f"test-decision-{i}", tags=[tag])

    result = query_relevant(store, "test", limit=5)
    if result:
        # Flat format: relevance dots, no tag group headers
        assert "●" in result
        assert "**auth**" not in result
