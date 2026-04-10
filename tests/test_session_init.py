"""Session init policy tests — index rebuild on stale rules file."""

import time

from conftest import make_decision, make_session_state, make_store


# ── Index rebuild at session start ─────────────────────────────────


def test_rebuild_index_when_no_rules_file(tmp_path):
    """Index is created when decisions exist but rules/decisions.md is missing."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.session_init import _rebuild_index_if_stale

    make_decision(decisions_dir, "test-dec", tags=["testing"])

    state = make_session_state("rebuild-missing", store=store)
    rules_file = decisions_dir.parent / "rules" / "decisions.md"
    assert not rules_file.exists()

    _rebuild_index_if_stale(state)

    assert rules_file.is_file()
    content = rules_file.read_text()
    assert "test-dec" in content


def test_rebuild_index_when_decision_newer(tmp_path):
    """Index is regenerated when a decision file is newer than the rules file."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.session_init import _rebuild_index_if_stale

    make_decision(decisions_dir, "old-dec", tags=["testing"])

    # Create an initial rules file
    rules_dir = decisions_dir.parent / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "decisions.md"
    rules_file.write_text("# Team Decisions\n\nStale index.\n")

    # Backdate the rules file so the decision is newer
    past = time.time() - 100
    import os
    os.utime(rules_file, (past, past))

    state = make_session_state("rebuild-stale", store=store)
    _rebuild_index_if_stale(state)

    content = rules_file.read_text()
    assert "old-dec" in content
    assert "Stale index" not in content


def test_no_rebuild_when_index_fresh(tmp_path):
    """Index is not rewritten when it's already up to date."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.session_init import _rebuild_index_if_stale
    from decision.policy.index_update import _generate_index

    make_decision(decisions_dir, "fresh-dec", tags=["testing"])

    # Create an up-to-date rules file
    rules_dir = decisions_dir.parent / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "decisions.md"
    rules_file.write_text(_generate_index(store))

    # Make the rules file newer than all decisions
    import os
    future = time.time() + 100
    os.utime(rules_file, (future, future))

    original_mtime = rules_file.stat().st_mtime

    state = make_session_state("rebuild-fresh", store=store)
    _rebuild_index_if_stale(state)

    # File should not have been rewritten
    assert rules_file.stat().st_mtime == original_mtime


def test_no_rebuild_when_no_decisions(tmp_path):
    """No index created when there are no decisions at all."""
    _, store = make_store(tmp_path)
    from decision.policy.session_init import _rebuild_index_if_stale

    state = make_session_state("rebuild-empty", store=store)
    rules_file = store.decisions_dir.parent / "rules" / "decisions.md"

    _rebuild_index_if_stale(state)

    assert not rules_file.exists()


def test_rebuild_index_error_is_silent(tmp_path):
    """Errors in _rebuild_index_if_stale don't propagate."""
    from unittest.mock import patch
    from decision.policy.session_init import _rebuild_index_if_stale

    _, store = make_store(tmp_path)
    state = make_session_state("rebuild-error", store=store)

    # Force an error by making decisions_dir a file instead of directory
    with patch.object(store, "decision_count", side_effect=RuntimeError("boom")):
        _rebuild_index_if_stale(state)  # should not raise
