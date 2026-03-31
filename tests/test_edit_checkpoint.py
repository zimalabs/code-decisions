"""Edit checkpoint policy tests — unacted capture follow-up."""

import os
import time

from conftest import make_session_state, make_decision, make_store


# ── unacted capture follow-up ──────────────────────────────────────


def test_checkpoint_fires_after_unacted_capture(tmp_path):
    """Fires when capture-nudge detected decision language but no decision was written."""
    _, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition

    state = make_session_state("ec-unacted", store=store)
    # Simulate capture-nudge firing (decision language detected)
    state.mark_fired("_capture-nudge-pending")
    state.store_data("_capture-nudge-pending", "going with")
    # Enough edits to trigger follow-up
    for i in range(4):
        state.record_edit(f"src/file{i}.py")

    data = {"tool_input": {"file_path": "src/file4.py"}}
    result = _edit_checkpoint_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "Uncaptured choice detected" in result.system_message
    assert ".claude/decisions/" in result.system_message
    # Should quote the original phrase
    assert "going with" in result.system_message


def test_checkpoint_silent_without_capture_nudge(tmp_path):
    """Does NOT fire when no capture-nudge was triggered — no decision language detected."""
    _, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition

    state = make_session_state("ec-no-nudge", store=store)
    # Many edits but no capture-nudge fired
    for i in range(20):
        state.record_edit(f"src/file{i}.py")

    data = {"tool_input": {"file_path": "src/file20.py"}}
    result = _edit_checkpoint_condition(data, state)
    assert result is None, "Should not fire without capture-nudge"


def test_checkpoint_silent_when_decision_captured(tmp_path):
    """Does NOT fire when a decision was captured after the nudge."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition

    state = make_session_state("ec-captured", store=store)
    state.mark_fired("_capture-nudge-pending")
    for i in range(4):
        state.record_edit(f"src/file{i}.py")

    # Simulate a decision being captured
    f = make_decision(decisions_dir, "test-checkpoint")
    future = time.time() + 1
    os.utime(f, (future, future))

    data = {"tool_input": {"file_path": "src/file4.py"}}
    result = _edit_checkpoint_condition(data, state)
    assert result is None, "Should not fire when decision was captured"


def test_checkpoint_waits_for_edit_delay(tmp_path):
    """Does NOT fire immediately after capture nudge — waits for some edits."""
    _, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition

    state = make_session_state("ec-delay", store=store)
    state.mark_fired("_capture-nudge-pending")
    # Only 1 edit — below delay
    state.record_edit("src/file0.py")

    data = {"tool_input": {"file_path": "src/file1.py"}}
    result = _edit_checkpoint_condition(data, state)
    assert result is None, "Should wait for more edits before following up"


def test_checkpoint_fires_once_then_stops(tmp_path):
    """Edit-checkpoint fires once, then stops — but does not dismiss stop-nudge."""
    _, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition

    state = make_session_state("ec-once", store=store)
    state.mark_fired("_capture-nudge-pending")
    for i in range(4):
        state.record_edit(f"src/file{i}.py")

    # First follow-up — fires
    data = {"tool_input": {"file_path": "src/file4.py"}}
    result1 = _edit_checkpoint_condition(data, state)
    assert result1 is not None, "First follow-up should fire"

    # More edits, second attempt — suppressed
    for i in range(5, 10):
        state.record_edit(f"src/file{i}.py")
    data2 = {"tool_input": {"file_path": "src/file10.py"}}
    result2 = _edit_checkpoint_condition(data2, state)
    assert result2 is None, "Second attempt should be suppressed"
    # Stop-nudge should NOT be dismissed — it's the last safety net
    assert not state.nudges_dismissed(), "Stop-nudge should still be active"


def test_checkpoint_skips_non_code_files(tmp_path):
    """Ignores decision, test, and config file edits."""
    _, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition

    state = make_session_state("ec-skip", store=store)
    state.mark_fired("_capture-nudge-pending")
    for i in range(4):
        state.record_edit(f"src/file{i}.py")

    data = {"tool_input": {"file_path": "/decisions/test.md"}}
    result = _edit_checkpoint_condition(data, state)
    assert result is None


def test_checkpoint_suppressed_when_dismissed(tmp_path):
    """Returns None when nudges are dismissed."""
    _, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition

    state = make_session_state("ec-dismissed", store=store)
    state.mark_nudges_dismissed()
    state.mark_fired("_capture-nudge-pending")
    for i in range(10):
        state.record_edit(f"src/file{i}.py")

    data = {"tool_input": {"file_path": "src/file10.py"}}
    result = _edit_checkpoint_condition(data, state)
    assert result is None


def test_checkpoint_no_file_path(tmp_path):
    """Returns None when no file_path in data."""
    _, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition

    state = make_session_state("ec-no-fp", store=store)
    state.mark_fired("_capture-nudge-pending")
    for i in range(5):
        state.record_edit(f"src/file{i}.py")
    data = {"tool_input": {}}
    result = _edit_checkpoint_condition(data, state)
    assert result is None


# ── SessionState dismiss basics ──────────────────────────────────


def test_session_state_dismiss_nudges():
    """SessionState dismiss methods work correctly."""
    state = make_session_state("dismiss-test")
    assert not state.nudges_dismissed()
    state.mark_nudges_dismissed()
    assert state.nudges_dismissed()


def test_session_state_store_and_load_data():
    """SessionState can store and retrieve string data alongside markers."""
    state = make_session_state("data-test")
    assert state.load_data("test-key") == ""
    state.store_data("test-key", "hello world")
    assert state.load_data("test-key") == "hello world"


def test_session_state_load_data_missing():
    """load_data returns empty string for non-existent key."""
    state = make_session_state("data-missing")
    assert state.load_data("nonexistent") == ""
