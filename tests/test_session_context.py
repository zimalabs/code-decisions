"""Session context policy tests — injection, workflow, compression."""

import json
import time

import decision
from conftest import make_session_state, make_decision, make_store


# ── session-context tests ───────────────────────────────────────────


def test_session_context_injects_decisions(tmp_path):
    """session-context injects decision summary with auto-capture instructions."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir)

    from decision.policy.defs import _session_context_condition

    state = make_session_state("sc-decisions", store=store)
    result = _session_context_condition({}, state)
    assert result is not None
    ctx = str(result.additional_context)
    assert "◆" in ctx
    assert "Auto-capture" in ctx


def test_session_context_empty_store(tmp_path):
    """session-context provides onboarding when no decisions exist."""
    _, store = make_store(tmp_path)

    from decision.policy.defs import _session_context_condition

    state = make_session_state("sc-empty", store=store)
    result = _session_context_condition({}, state)
    assert result is not None
    ctx = str(result.additional_context)
    assert "no decisions captured yet" in ctx
    assert "/decision" in ctx
    assert "How it works" in ctx or "Try it now" in ctx


# ── session-context workflow instructions ─────────────────────────


def test_session_context_empty_includes_workflow(tmp_path):
    """session-context includes onboarding guidance with no decisions."""
    _, store = make_store(tmp_path)

    from decision.policy.defs import _session_context_condition

    state = make_session_state("sc-empty-workflow", store=store)
    result = _session_context_condition({}, state)
    assert result is not None
    ctx = str(result.additional_context)
    assert "no decisions captured yet" in ctx
    assert "/decision" in ctx
    assert "via git" in ctx.lower() or "try it now" in ctx.lower()


def test_session_context_onboarding_is_concise(tmp_path):
    """Onboarding users (<5 decisions) get concise instructions, not full template."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir)

    from decision.policy.defs import _session_context_condition

    state = make_session_state("sc-affects-guide", store=store)
    result = _session_context_condition({}, state)
    assert result is not None
    ctx = str(result.additional_context)
    # Should mention auto-capture and search
    assert "Auto-capture" in ctx
    assert "/decision" in ctx
    # Should NOT contain the full template (it injects lazily)
    assert "```" not in ctx
    assert "slug-name" not in ctx


# ── _stale_affects_slugs tests ─────────────────────────────────────


def test_stale_affects_slugs_no_stale(tmp_path):
    """_stale_affects_slugs returns 0 when all affects paths exist."""
    import os

    decisions_dir, store = make_store(tmp_path)

    # Create a real file that the decision's affects can point to
    target = tmp_path / "src" / "app.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pass")

    make_decision(decisions_dir, "with-affects", affects=["src/app.py"])

    from decision.policy.session_context import _stale_affects_slugs

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = _stale_affects_slugs(store)
    finally:
        os.chdir(old_cwd)

    assert result == []


def test_stale_affects_slugs_with_stale(tmp_path):
    """_stale_affects_slugs returns slugs of decisions with non-existent affects paths."""
    import os

    decisions_dir, store = make_store(tmp_path)

    # Create a decision pointing to a non-existent file
    make_decision(decisions_dir, "stale-affects", affects=["src/nonexistent.py"])

    from decision.policy.session_context import _stale_affects_slugs

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = _stale_affects_slugs(store)
    finally:
        os.chdir(old_cwd)

    assert result == ["stale-affects"]



def test_stale_affects_slugs_skips_no_affects(tmp_path):
    """_stale_affects_slugs skips decisions without affects."""
    import os

    decisions_dir, store = make_store(tmp_path)

    make_decision(decisions_dir, "no-affects")

    from decision.policy.session_context import _stale_affects_slugs

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = _stale_affects_slugs(store)
    finally:
        os.chdir(old_cwd)

    assert result == []


# ── FTS5 unavailable warning ─────────────────────────────────────


def test_session_context_slim_for_returning_users(tmp_path):
    """Returning users (>=RETURNING_USER_THRESHOLD decisions) get slim context without template."""
    from decision.utils.constants import RETURNING_USER_THRESHOLD

    decisions_dir, store = make_store(tmp_path)
    for i in range(RETURNING_USER_THRESHOLD):
        make_decision(decisions_dir, f"decision-{i}", tags=[f"topic-{i}"])

    from decision.policy.defs import _session_context_condition

    state = make_session_state("sc-returning", store=store)
    result = _session_context_condition({}, state)
    assert result is not None
    ctx = str(result.additional_context)
    # Should have summary line
    assert "◆" in ctx
    assert f"{RETURNING_USER_THRESHOLD} decisions" in ctx
    # Should NOT have the full template
    assert "```" not in ctx
    assert "slug-name" not in ctx
    # Should have brief reminders
    assert "Auto-capture" in ctx
    assert "memories" in ctx


def test_session_context_fts5_unavailable_warning(tmp_path):
    """session-context shows FTS5 unavailable warning when index is not available."""
    from unittest.mock import PropertyMock, patch

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "test-dec")

    from decision.policy.session_context import _session_context_condition

    # Mock the index's available property to return False
    with patch.object(type(store._index), "available", new_callable=PropertyMock, return_value=False):
        state = make_session_state("sc-fts5-warn", store=store)
        result = _session_context_condition({}, state)

    assert result is not None
    assert "FTS5 unavailable" in result.additional_context


# ── Session-start banner (systemMessage) ──────────────────────────────


def test_session_context_banner_for_existing_decisions(tmp_path):
    """Session context includes a human-visible banner with decision count."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "dec-a", tags=["auth"])
    make_decision(decisions_dir, "dec-b", tags=["billing"])

    from decision.policy.defs import _session_context_condition

    state = make_session_state("sc-banner", store=store)
    result = _session_context_condition({}, state)
    assert result is not None
    assert result.system_message is not None
    assert "2 decisions" in result.system_message
    assert "2 topics" in result.system_message


def test_session_context_banner_includes_stale_count(tmp_path):
    """Banner shows stale count when decisions have stale affects."""
    import os

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "stale-dec", affects=["src/nonexistent.py"])

    from decision.policy.session_context import _session_context_condition

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        state = make_session_state("sc-banner-stale", store=store)
        result = _session_context_condition({}, state)
    finally:
        os.chdir(old_cwd)

    assert result is not None
    assert result.system_message is not None
    assert "stale" in result.system_message


def test_session_context_no_banner_for_empty_store(tmp_path):
    """No banner when no decisions exist (onboarding only)."""
    _, store = make_store(tmp_path)

    from decision.policy.defs import _session_context_condition

    state = make_session_state("sc-no-banner", store=store)
    result = _session_context_condition({}, state)
    assert result is not None
    assert not result.system_message  # empty string or None
