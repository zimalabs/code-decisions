"""Scale tests — validate performance with large decision sets.

Ensures FTS5 index rebuild, search, and query remain fast enough
for the 5-second hook timeout even with 100+ decisions.
"""

import time
from pathlib import Path

import decision
from conftest import make_decision, make_store


SCALE_TAGS = ["infra", "auth", "caching", "database", "api", "frontend", "testing", "deploy"]


def _populate_decisions(decisions_dir: Path, count: int) -> None:
    """Create N decision files with varied tags and content."""
    for i in range(count):
        tag_idx = i % len(SCALE_TAGS)
        tags = [SCALE_TAGS[tag_idx], SCALE_TAGS[(tag_idx + 1) % len(SCALE_TAGS)]]
        body = f"Decision {i} covers {SCALE_TAGS[tag_idx]} concerns. "
        if i % 3 == 0:
            body += "Uses Redis for caching layer. "
        if i % 5 == 0:
            body += "Integrates with PostgreSQL database. "
        make_decision(
            decisions_dir,
            f"decision-{i:04d}",
            title=f"Decision {i}: {SCALE_TAGS[tag_idx]} strategy",
            tags=tags,
            body_extra=body + "\n\n",
            affects=[f"src/{SCALE_TAGS[tag_idx]}/module_{i}.py"],
            description=f"Test decision decision-{i:04d}",
        )


# ── Index rebuild performance ────────────────────────────────────


def test_index_rebuild_100_decisions(tmp_path):
    """FTS5 index rebuild with 100 decisions completes under 3 seconds."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 100)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")
    start = time.monotonic()
    idx.ensure_fresh()
    elapsed = time.monotonic() - start

    assert idx.db_path.exists()
    assert elapsed < 3.0, f"Index rebuild took {elapsed:.1f}s — too slow for 5s hook timeout"


def test_index_rebuild_200_decisions(tmp_path):
    """FTS5 index rebuild with 200 decisions completes under 5 seconds."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 200)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")
    start = time.monotonic()
    idx.ensure_fresh()
    elapsed = time.monotonic() - start

    assert idx.db_path.exists()
    assert elapsed < 5.0, f"Index rebuild took {elapsed:.1f}s — exceeds 5s hook timeout"


# ── Search performance ───────────────────────────────────────────


def test_search_100_decisions(tmp_path):
    """FTS5 search across 100 decisions completes under 500ms."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 100)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")
    idx.ensure_fresh()

    start = time.monotonic()
    results = idx.search("redis caching")
    elapsed = time.monotonic() - start

    assert len(results) > 0
    assert elapsed < 0.5, f"Search took {elapsed:.3f}s — too slow"


def test_search_returns_correct_results_at_scale(tmp_path):
    """Search results are correct and ranked with 100+ decisions."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 100)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")
    idx.ensure_fresh()

    # Search for a specific tag
    results = idx.search("auth", limit=5)
    assert len(results) > 0
    assert len(results) <= 5

    # Tag-based search
    by_tag = idx.by_tag("infra")
    assert len(by_tag) > 0


# ── Query (store-level) performance ──────────────────────────────


def test_store_query_100_decisions(tmp_path):
    """DecisionStore.query with 100 decisions completes under 1 second."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 100)

    start = time.monotonic()
    result = store.query("redis")
    elapsed = time.monotonic() - start

    assert result != ""
    assert elapsed < 1.0, f"Store query took {elapsed:.3f}s — too slow"


# ── Tag aggregation at scale ─────────────────────────────────────


def test_all_tags_100_decisions(tmp_path):
    """all_tags with 100 decisions returns correct counts quickly."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 100)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")

    start = time.monotonic()
    tags = idx.all_tags()
    elapsed = time.monotonic() - start

    assert len(tags) == len(SCALE_TAGS)
    total = sum(tags.values())
    assert total == 200  # 100 decisions × 2 tags each
    assert elapsed < 0.5, f"all_tags took {elapsed:.3f}s — too slow"


# ── Incremental sync performance ─────────────────────────────────


def test_incremental_sync_after_one_addition(tmp_path):
    """Adding one decision to a 100-decision index syncs fast."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 100)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")
    idx.ensure_fresh()

    # Add one more
    make_decision(decisions_dir, "new-addition", title="Brand new decision", tags=["infra"])

    idx.invalidate()
    start = time.monotonic()
    idx.ensure_fresh()
    elapsed = time.monotonic() - start

    assert elapsed < 0.5, f"Incremental sync took {elapsed:.3f}s — too slow"
    results = idx.search("brand new")
    assert len(results) == 1


# ── Higher scale tests (Item 12) ─────────────────────────────────


def test_index_rebuild_500_decisions(tmp_path):
    """FTS5 index rebuild with 500 decisions completes under 10 seconds."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 500)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")
    start = time.monotonic()
    idx.ensure_fresh()
    elapsed = time.monotonic() - start

    assert idx.db_path.exists()
    assert elapsed < 10.0, f"Index rebuild took {elapsed:.1f}s — budget 10s"


def test_search_500_decisions(tmp_path):
    """FTS5 search across 500 decisions completes under 1 second."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 500)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")
    idx.ensure_fresh()

    start = time.monotonic()
    results = idx.search("redis caching")
    elapsed = time.monotonic() - start

    assert len(results) > 0
    assert elapsed < 1.0, f"Search took {elapsed:.3f}s — budget 1s"


def test_index_rebuild_1000_decisions(tmp_path):
    """FTS5 index rebuild with 1000 decisions completes under 20 seconds."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 1000)

    idx = decision.DecisionIndex(decisions_dir, db_dir=tmp_path / "db")
    start = time.monotonic()
    idx.ensure_fresh()
    elapsed = time.monotonic() - start

    assert idx.db_path.exists()
    assert elapsed < 20.0, f"Index rebuild took {elapsed:.1f}s — budget 20s"


def test_store_query_1000_decisions(tmp_path):
    """DecisionStore.query with 1000 decisions completes under 2 seconds."""
    decisions_dir, store = make_store(tmp_path)
    _populate_decisions(decisions_dir, 1000)

    start = time.monotonic()
    result = store.query("redis")
    elapsed = time.monotonic() - start

    assert result != ""
    assert elapsed < 2.0, f"Store query took {elapsed:.3f}s — budget 2s"
