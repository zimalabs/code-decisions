"""FTS5 search index test suite — pytest style.

Each test creates its own decisions dir via tmp_path.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

import decision
from conftest import make_decision, make_store


@pytest.fixture(autouse=True)
def _isolate_state_dir(tmp_path):
    """Isolate the index db per test by patching _state_dir."""
    state = tmp_path / ".state"
    state.mkdir()
    with patch("decision.utils.helpers._state_dir", return_value=state):
        yield


# ── Index creation and rebuild ───────────────────────────────────


def test_index_creation(tmp_path):
    """DecisionIndex creates a db file on first ensure_fresh."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir)

    idx = store._index
    assert idx.available
    idx.ensure_fresh()
    assert idx.db_path.exists()


def test_sync_adds_new_file(tmp_path):
    """New decision file is picked up by incremental sync."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "first", title="First", tags=["infra"])

    idx = store._index
    idx.ensure_fresh()
    assert len(idx.search("first")) == 1
    assert len(idx.search("second")) == 0

    make_decision(decisions_dir, "second", title="Second", tags=["infra"])
    idx.invalidate()
    idx.ensure_fresh()
    assert len(idx.search("second")) == 1


def test_sync_removes_deleted_file(tmp_path):
    """Deleted decision file is removed from index."""
    decisions_dir, store = make_store(tmp_path)
    f = make_decision(decisions_dir, "ephemeral", title="Ephemeral decision", tags=["testing"])

    idx = store._index
    idx.ensure_fresh()
    assert len(idx.search("ephemeral")) == 1

    f.unlink()
    idx.invalidate()
    idx.ensure_fresh()
    assert len(idx.search("ephemeral")) == 0


def test_sync_updates_modified_file(tmp_path):
    """Modified decision file is re-indexed."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "evolving", title="Original title", tags=["infra"])

    idx = store._index
    idx.ensure_fresh()
    results = idx.search("original")
    assert len(results) == 1
    assert results[0].title == "Original title"

    # Overwrite with new title — bump mtime to ensure sync detects the change
    make_decision(decisions_dir, "evolving", title="Updated title", tags=["infra"])
    f = decisions_dir / "evolving.md"
    future = f.stat().st_mtime + 1
    os.utime(f, (future, future))

    idx.invalidate()
    idx.ensure_fresh()
    assert len(idx.search("updated")) == 1
    assert len(idx.search("original")) == 0


def test_sync_delete_removes_from_tags(tmp_path):
    """Deleting a file removes its tags from all_tags counts."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "d1", title="D1", tags=["infra", "caching"])
    f2 = make_decision(decisions_dir, "d2", title="D2", tags=["infra"])

    idx = store._index
    tags = idx.all_tags()
    assert tags["infra"] == 2

    f2.unlink()
    idx.invalidate()
    idx.ensure_fresh()
    tags = idx.all_tags()
    assert tags["infra"] == 1


def test_sync_no_change_is_noop(tmp_path):
    """If no files changed, sync doesn't modify the db."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "stable", title="Stable", tags=["infra"])

    idx = store._index
    idx.ensure_fresh()
    mtime1 = idx.db_path.stat().st_mtime

    # ensure_fresh again with no changes — db mtime should not change
    idx.ensure_fresh()
    mtime2 = idx.db_path.stat().st_mtime
    assert mtime1 == mtime2


# ── FTS5 search ──────────────────────────────────────────────────


def test_search_basic(tmp_path):
    """Basic keyword search returns matching decisions."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "use-redis", title="Use Redis for caching", tags=["infra", "caching"])
    make_decision(decisions_dir, "use-postgres", title="Use Postgres for storage", tags=["infra", "database"],
                  body="Postgres provides storage.\n")

    idx = store._index
    results = idx.search("redis")
    assert len(results) == 1
    assert results[0].slug == "use-redis"


def test_search_stemming(tmp_path):
    """Porter stemming: 'cache' matches 'caching'."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "caching-strategy", title="Caching strategy with Redis",
                  tags=["caching"], body_extra="We use caching extensively.\n\n")

    idx = store._index
    results = idx.search("cache")
    assert len(results) == 1
    assert results[0].slug == "caching-strategy"


def test_search_prefix_wildcard(tmp_path):
    """Short terms get * suffix: 'auth' matches 'authentication'."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "auth-flow", title="Authentication flow design",
                  tags=["authentication"], body_extra="The authentication system uses OAuth.\n\n")

    idx = store._index
    results = idx.search("auth")
    assert len(results) == 1
    assert results[0].slug == "auth-flow"


def test_search_ranking(tmp_path):
    """More relevant results rank higher."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-cache", title="Redis caching layer",
                  tags=["caching", "redis"], body_extra="Redis is our caching solution for Redis.\n\n")
    make_decision(decisions_dir, "postgres-setup", title="Postgres setup",
                  tags=["database"], body="We also considered Redis briefly.\n")

    idx = store._index
    results = idx.search("redis", limit=2)
    assert len(results) == 2
    # The one with more redis mentions should rank first
    assert results[0].slug == "redis-cache"


def test_search_empty_query(tmp_path):
    """Empty query returns nothing."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir)

    idx = store._index
    results = idx.search("")
    assert results == []


def test_search_no_results(tmp_path):
    """Query with no matches returns empty list."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir)

    idx = store._index
    results = idx.search("xyznonexistent")
    assert results == []


def test_search_limit(tmp_path):
    """Limit constrains result count."""
    decisions_dir, store = make_store(tmp_path)
    for i in range(5):
        make_decision(decisions_dir, f"decision-{i}", title=f"Decision {i} about testing",
                      tags=["testing"])

    idx = store._index
    results = idx.search("testing", limit=2)
    assert len(results) == 2



# ── Tag operations ───────────────────────────────────────────────


def test_all_tags(tmp_path):
    """all_tags returns correct counts."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "d1", title="D1", tags=["infra", "caching"])
    make_decision(decisions_dir, "d2", title="D2", tags=["infra", "auth"])
    make_decision(decisions_dir, "d3", title="D3", tags=["caching"])

    idx = store._index
    tags = idx.all_tags()
    assert tags["infra"] == 2
    assert tags["caching"] == 2
    assert tags["auth"] == 1



def test_by_tag(tmp_path):
    """by_tag filters by exact tag match."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "d1", title="D1", tags=["infra", "caching"])
    make_decision(decisions_dir, "d2", title="D2", tags=["auth"])

    idx = store._index
    results = idx.by_tag("infra")
    assert len(results) == 1
    assert results[0].slug == "d1"



# ── Corrupt db recovery ─────────────────────────────────────────


def test_corrupt_db_recovery(tmp_path):
    """Corrupt db is deleted and rebuilt on next access."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir)

    idx = store._index
    idx.ensure_fresh()

    # Corrupt the db
    idx.db_path.write_bytes(b"not a database")

    # Search should handle it gracefully (rebuild or return empty)
    results = idx.search("test")
    # After recovery, a fresh search should work
    idx2 = store._index
    results2 = idx2.search("test")
    assert isinstance(results2, list)


# ── Integration: query_relevant uses FTS5 ────────────────────────


def test_query_relevant_uses_fts5(tmp_path):
    """store.query() uses FTS5 path when available."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "caching-strategy", title="Caching strategy",
                  tags=["caching"], body_extra="We use caching for performance.\n\n")

    # Porter stemming: "cache" should match "caching"
    result = store.query("cache")
    assert "Caching strategy" in result


# ── Store methods delegate to index ──────────────────────────────


def test_store_search(tmp_path):
    """DecisionStore.search() delegates to index."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis", title="Use Redis", tags=["infra"])

    results = store.search("redis")
    assert len(results) == 1
    assert results[0].slug == "redis"


def test_store_by_tag(tmp_path):
    """DecisionStore.by_tag() delegates to index."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "d1", title="D1", tags=["infra"])
    make_decision(decisions_dir, "d2", title="D2", tags=["auth"])

    results = store.by_tag("infra")
    assert len(results) == 1


def test_store_all_tags(tmp_path):
    """DecisionStore.all_tags() delegates to index."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "d1", title="D1", tags=["infra", "caching"])

    tags = store.all_tags()
    assert "infra" in tags
    assert "caching" in tags


# ── Sanitize query ───────────────────────────────────────────────


def test_sanitize_short_terms():
    """Short terms get * suffix; multi-token queries use AND."""
    assert decision.DecisionIndex._sanitize_query("auth") == "auth*"
    assert decision.DecisionIndex._sanitize_query("auth cache") == "auth* AND cache*"


def test_sanitize_long_terms():
    """Long terms don't get * suffix."""
    assert decision.DecisionIndex._sanitize_query("authentication") == "authentication"


def test_sanitize_strips_special_chars():
    """Special characters are stripped."""
    assert decision.DecisionIndex._sanitize_query("auth!") == "auth*"
    assert decision.DecisionIndex._sanitize_query("") == ""


def test_sanitize_splits_underscores():
    """Underscores are treated as word separators, joined with AND."""
    assert decision.DecisionIndex._sanitize_query("stripe_client") == "stripe* AND client*"


# ── Concurrent rebuild ─────────────────────────────────────────────


# ── _parse_json_list edge cases ────────────────────────────────────


def test_parse_json_list_empty_string():
    """Empty string returns empty list."""
    from decision.store.index import _parse_json_list

    assert _parse_json_list("") == []


def test_parse_json_list_legacy_comma():
    """Comma-separated fallback for legacy data."""
    from decision.store.index import _parse_json_list

    assert _parse_json_list("auth, caching") == ["auth", "caching"]


def test_parse_json_list_single_bare_value():
    """Plain string without commas returns single-element list."""
    from decision.store.index import _parse_json_list

    assert _parse_json_list("auth") == ["auth"]


def test_parse_json_list_malformed_json_bracket():
    """Malformed JSON starting with [ logs warning and falls back."""
    from decision.store.index import _parse_json_list

    result = _parse_json_list("[broken")
    # Falls through to comma-split; "[broken" has no commas → single element
    assert isinstance(result, list)
    assert len(result) >= 1


def test_parse_json_list_valid_json():
    """Valid JSON array is parsed correctly."""
    from decision.store.index import _parse_json_list

    assert _parse_json_list('["auth", "caching"]') == ["auth", "caching"]


# ── DatabaseError recovery paths ──────────────────────────────────


def test_ensure_fresh_database_error_rebuilds(tmp_path):
    """ensure_fresh triggers rebuild on DatabaseError from _sync."""
    import sqlite3

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "rebuild-test")

    idx = store._index
    idx.ensure_fresh()
    assert len(idx.search("rebuild")) == 1

    # Patch _sync to raise DatabaseError — should trigger _delete_and_rebuild
    with patch.object(idx, "_sync", side_effect=sqlite3.DatabaseError("corrupt")):
        idx.db_path.write_bytes(b"x")  # Force db_path.exists() to be True
        idx.invalidate()
        idx.ensure_fresh()  # Should not raise

    # After rebuild, search should still work
    results = idx.search("rebuild")
    assert len(results) == 1


def test_search_database_error_rebuilds_and_returns_empty(tmp_path):
    """search handles DatabaseError by rebuilding (returns results or empty gracefully)."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "optest")

    idx = store._index
    idx.ensure_fresh()

    # Corrupt the db — search will catch DatabaseError and call _delete_and_rebuild
    idx.db_path.write_bytes(b"corrupt data here")
    # This should not raise — it either returns [] or rebuilds and returns results
    results = idx.search("optest")
    assert isinstance(results, list)


def test_by_tag_database_error_recovers(tmp_path):
    """by_tag recovers gracefully from DatabaseError (rebuild or empty)."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "tagtest", tags=["infra"])

    idx = store._index
    idx.ensure_fresh()

    # Corrupt db — triggers _delete_and_rebuild which recovers
    idx.db_path.write_bytes(b"corrupt")
    results = idx.by_tag("infra")
    assert isinstance(results, list)


def test_decisions_with_affects_database_error_recovers(tmp_path):
    """decisions_with_affects recovers from DatabaseError."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "afftest", affects=["src/app.py"])

    idx = store._index
    idx.ensure_fresh()

    idx.db_path.write_bytes(b"corrupt")
    results = idx.decisions_with_affects()
    assert isinstance(results, list)


def test_all_tags_database_error_recovers(tmp_path):
    """all_tags recovers from DatabaseError."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "tagtest2", tags=["infra"])

    idx = store._index
    idx.ensure_fresh()

    idx.db_path.write_bytes(b"corrupt")
    result = idx.all_tags()
    assert isinstance(result, dict)


def test_list_summaries_database_error_recovers(tmp_path):
    """list_summaries recovers from DatabaseError."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "sumtest")

    idx = store._index
    idx.ensure_fresh()

    idx.db_path.write_bytes(b"corrupt")
    result = idx.list_summaries()
    assert isinstance(result, list)


def test_sanitize_query_all_special_chars():
    """Query with only special characters returns empty string."""
    assert decision.DecisionIndex._sanitize_query("!@#$%^") == ""


def test_sanitize_query_hyphens():
    """Hyphens are treated as separators."""
    result = decision.DecisionIndex._sanitize_query("use-redis")
    assert "AND" in result  # multi-token, should use AND
    assert "use*" in result
    assert "redis*" in result


# ── FTS5 unavailable paths ────────────────────────────────────────


def test_search_fts5_unavailable_returns_empty(tmp_path):
    """search returns empty when FTS5 is not available."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "fts-test")

    idx = store._index
    idx._available = False
    assert idx.search("test") == []


def test_by_tag_fts5_unavailable_returns_empty(tmp_path):
    """by_tag returns empty when FTS5 is not available."""
    decisions_dir, store = make_store(tmp_path)
    idx = store._index
    idx._available = False
    assert idx.by_tag("test") == []


def test_decisions_with_affects_fts5_unavailable(tmp_path):
    """decisions_with_affects returns empty when FTS5 unavailable."""
    decisions_dir, store = make_store(tmp_path)
    idx = store._index
    idx._available = False
    assert idx.decisions_with_affects() == []


def test_all_tags_fts5_unavailable(tmp_path):
    """all_tags returns empty when FTS5 unavailable."""
    decisions_dir, store = make_store(tmp_path)
    idx = store._index
    idx._available = False
    assert idx.all_tags() == {}


def test_list_summaries_fts5_unavailable(tmp_path):
    """list_summaries returns empty when FTS5 unavailable."""
    decisions_dir, store = make_store(tmp_path)
    idx = store._index
    idx._available = False
    assert idx.list_summaries() == []


def test_ensure_fresh_fts5_unavailable_noop(tmp_path):
    """ensure_fresh is a no-op when FTS5 is not available."""
    decisions_dir, store = make_store(tmp_path)
    idx = store._index
    idx._available = False
    idx.ensure_fresh()  # Should not raise or create db
    assert not idx.db_path.exists()


# ── Concurrent rebuild ────────────────────────────────────────────


def test_concurrent_rebuild_does_not_corrupt(tmp_path):
    """Two threads calling _delete_and_rebuild don't corrupt the index."""
    import threading

    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir()
    db_dir = tmp_path / "db"
    db_dir.mkdir()

    # Create some decision files
    for i in range(5):
        make_decision(decisions_dir, f"concurrent-{i}", tags=["test"])

    errors = []

    def rebuild_worker():
        try:
            idx = decision.DecisionIndex(str(decisions_dir), db_dir=str(db_dir))
            idx._delete_and_rebuild()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=rebuild_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"Concurrent rebuild produced errors: {errors}"

    # Verify index is usable after concurrent rebuilds
    idx = decision.DecisionIndex(str(decisions_dir), db_dir=str(db_dir))
    summaries = idx.list_summaries()
    assert len(summaries) == 5
