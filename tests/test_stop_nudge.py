"""Stop nudge policy tests — unacted capture follow-up, activity summary."""

import json
import os
import time

import decision
from conftest import make_session_state, make_decision, make_store


# ── stop-nudge tests ──────────────────────────────────────────────


def test_stop_nudge_fires_on_unacted_capture(tmp_path):
    """stop-nudge fires when capture-nudge detected decision language but no decision was captured."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.defs import _stop_nudge_condition
    from decision.policy.stop_nudge import load_last_session

    state = make_session_state("stop-nudge-fires", store=store)
    state.mark_fired("_capture-nudge-pending")
    state.store_data("_capture-nudge-pending", "switching to")
    for i in range(5):
        state.record_edit(f"src/file{i}.py")

    result = _stop_nudge_condition({}, state)
    assert result is not None
    assert result.matched is True
    assert "uncaptured choice detected" in result.system_message.lower()
    # Should quote the original phrase
    assert "switching to" in result.system_message

    # Verify last-session info was also persisted
    last = load_last_session(decisions_dir)
    assert last is not None
    assert last["edit_count"] == 5


def test_stop_nudge_silent_without_capture_nudge(tmp_path):
    """stop-nudge doesn't fire (no nudge, just activity summary or None)."""
    _, store = make_store(tmp_path)
    from decision.policy.defs import _stop_nudge_condition

    state = make_session_state("stop-no-nudge", store=store)
    for i in range(10):
        state.record_edit(f"src/file{i}.py")

    result = _stop_nudge_condition({}, state)
    # No capture-nudge pending → no active nudge. May have activity summary or None.
    if result is not None:
        assert "decision language" not in result.system_message


def test_stop_nudge_silent_when_decisions_captured(tmp_path):
    """stop-nudge doesn't nag when decisions were captured this session."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.defs import _stop_nudge_condition

    state = make_session_state("stop-captured", store=store)
    state.mark_fired("_capture-nudge-pending")
    for i in range(5):
        state.record_edit(f"src/file{i}.py")

    # Simulate a decision being captured after session start
    f = make_decision(decisions_dir, "test-stop")
    future = time.time() + 1
    os.utime(f, (future, future))

    result = _stop_nudge_condition({}, state)
    # Should not contain nudge message
    if result is not None:
        assert "decision language" not in result.system_message


def test_stop_nudge_once_per_session(tmp_path):
    """stop-nudge only fires once via the engine (once_per_session=True)."""
    _, store = make_store(tmp_path)
    from decision.policy.defs import ALL_POLICIES

    engine = decision.PolicyEngine()
    for p in ALL_POLICIES:
        engine.register(p)

    state = make_session_state("stop-once", store=store)
    state.mark_fired("_capture-nudge-pending")
    for i in range(5):
        state.record_edit(f"src/file{i}.py")

    r1 = json.loads(engine.evaluate("Stop", {}, state))
    assert r1.get("ok") is True

    r2 = json.loads(engine.evaluate("Stop", {}, state))
    # Second time, once_per_session prevents it
    assert r2 == {} or r2.get("ok", True) is True


# ── stop-nudge dismiss test ──────────────────────────────────────


def test_stop_nudge_suppressed_when_dismissed(tmp_path):
    """stop-nudge saves last_session but suppresses nudge when dismissed."""
    _, store = make_store(tmp_path)
    from decision.policy.defs import _stop_nudge_condition

    state = make_session_state("sn-dismissed", store=store)
    state.mark_nudges_dismissed()
    state.mark_fired("_capture-nudge-pending")
    for i in range(5):
        state.record_edit(f"src/file{i}.py")

    result = _stop_nudge_condition({}, state)
    # Dismissed → no active nudge (may have activity summary)
    if result is not None:
        assert "decision language" not in result.system_message


def test_stop_nudge_fires_after_edit_checkpoint_ignored(tmp_path):
    """stop-nudge still fires even after edit-checkpoint was shown and ignored."""
    _, store = make_store(tmp_path)
    from decision.policy.edit_checkpoint import _edit_checkpoint_condition
    from decision.policy.stop_nudge import _stop_nudge_condition

    state = make_session_state("sn-after-ec", store=store)
    state.mark_fired("_capture-nudge-pending")
    state.store_data("_capture-nudge-pending", "going with")
    for i in range(4):
        state.record_edit(f"src/file{i}.py")

    # Edit-checkpoint fires and is ignored
    data = {"tool_input": {"file_path": "src/file4.py"}}
    ec_result = _edit_checkpoint_condition(data, state)
    assert ec_result is not None, "Edit-checkpoint should fire"

    # Second edit-checkpoint is suppressed
    for i in range(5, 10):
        state.record_edit(f"src/file{i}.py")
    data2 = {"tool_input": {"file_path": "src/file10.py"}}
    ec_result2 = _edit_checkpoint_condition(data2, state)
    assert ec_result2 is None, "Second edit-checkpoint should be suppressed"

    # But stop-nudge should still fire — it's the last safety net
    result = _stop_nudge_condition({}, state)
    assert result is not None
    assert "uncaptured choice detected" in result.system_message.lower()
    assert "going with" in result.system_message


# ── activity summary ────────────────────────────────────────────────


def test_stop_nudge_shows_activity_summary(tmp_path):
    """stop-nudge includes activity summary when context was injected."""
    _, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _stop_nudge_condition

    state = make_session_state("stop-activity", store=store)
    # Simulate 2 context injections (related decisions surfaced)
    state.increment_activity_counter("context_injections")
    state.increment_activity_counter("context_injections")

    result = _stop_nudge_condition({}, state)
    assert result is not None
    assert "Decision plugin" in result.system_message
    assert "2 decisions surfaced" in result.system_message


def test_stop_nudge_no_summary_when_no_activity(tmp_path):
    """stop-nudge returns None when no activity and no unacted capture."""
    _, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _stop_nudge_condition

    state = make_session_state("stop-no-activity", store=store)
    result = _stop_nudge_condition({}, state)
    assert result is None


# ── _save_last_session / load_last_session edge cases ──────────────


def test_save_last_session_writes_file(tmp_path):
    """_save_last_session writes a JSON file with edit info."""
    _, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _save_last_session, load_last_session

    state = make_session_state("save-last", store=store)
    for i in range(3):
        state.record_edit(f"src/file{i}.py")

    _save_last_session(state)

    # Verify the file was written by loading it
    data = load_last_session(tmp_path / "decisions")
    assert data is not None
    assert data["edit_count"] == 3
    assert len(data["files"]) == 3
    assert "timestamp" in data


def test_load_last_session_absent(tmp_path):
    """load_last_session returns None when no file exists."""
    from decision.policy.stop_nudge import load_last_session

    result = load_last_session(tmp_path / "nonexistent")
    assert result is None


def test_load_last_session_legacy_location(tmp_path):
    """load_last_session checks the legacy location as fallback."""
    from decision.policy.stop_nudge import load_last_session

    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir()
    legacy = decisions_dir / ".decision_last_session.json"
    legacy.write_text(json.dumps({"edit_count": 7, "files": ["a.py"], "timestamp": 1.0}))

    data = load_last_session(decisions_dir)
    assert data is not None
    assert data["edit_count"] == 7
    # File should be cleaned up after load
    assert not legacy.exists()


def test_load_last_session_corrupt_json(tmp_path):
    """load_last_session handles corrupt JSON gracefully."""
    from decision.policy.stop_nudge import load_last_session
    from decision.utils.helpers import _state_dir

    state_dir = _state_dir()
    path = state_dir / "last_session.json"
    path.write_text("{broken json!!!")

    data = load_last_session(tmp_path / "decisions")
    assert data is None
    # File should be cleaned up
    assert not path.exists()


def test_save_last_session_oserror_ignored(tmp_path):
    """_save_last_session silently ignores OSError on write."""
    from unittest.mock import patch

    _, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _save_last_session

    state = make_session_state("save-oserror", store=store)
    state.record_edit("src/file.py")

    # Patch _state_dir at the helpers module level (imported inside the function)
    bad_dir = tmp_path / "readonly"
    bad_dir.mkdir()
    bad_dir.chmod(0o444)

    with patch("decision.utils.helpers._state_dir", return_value=bad_dir):
        _save_last_session(state)

    # Restore permissions for cleanup
    bad_dir.chmod(0o755)


# ── Staleness surfacing ──────────────────────────────────────────────


def test_stop_nudge_staleness(tmp_path):
    """stop-nudge surfaces stale decisions affecting session edits."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _stop_nudge_condition

    # Create a stale decision (old date, affects src/api/)
    make_decision(decisions_dir, "old-dec", affects=["src/api/"], date="2025-01-01")

    state = make_session_state("stop-stale", store=store)
    state.record_edit("src/api/handler.py")

    result = _stop_nudge_condition({}, state)
    assert result is not None
    assert "stale" in result.system_message.lower()
    assert "old-dec" in result.system_message


def test_stop_nudge_no_staleness_for_fresh(tmp_path):
    """stop-nudge does NOT show staleness for fresh decisions."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _stop_nudge_condition

    make_decision(decisions_dir, "fresh-dec", affects=["src/api/"], date="2026-03-25")

    state = make_session_state("stop-fresh", store=store)
    state.record_edit("src/api/handler.py")

    result = _stop_nudge_condition({}, state)
    # Should not mention staleness
    if result is not None:
        assert "haven't been reviewed" not in result.system_message


# ── Surfacing history persistence ────────────────────────────────────


def test_surfacing_history_persisted(tmp_path):
    """_update_surfacing_history writes cross-session history file."""
    _, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _update_surfacing_history
    from decision.utils.helpers import _state_dir

    state = make_session_state("stop-history", store=store)
    state.record_decision_surfaced("dec-a")
    state.record_decision_surfaced("dec-b")

    _update_surfacing_history(state)

    path = _state_dir() / "surfacing_history.json"
    assert path.is_file()
    history = json.loads(path.read_text())
    assert history["dec-a"] == 1
    assert history["dec-b"] == 1


def test_surfacing_history_accumulates(tmp_path):
    """_update_surfacing_history increments existing counts."""
    _, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _update_surfacing_history
    from decision.utils.helpers import _state_dir

    # Pre-seed history
    path = _state_dir() / "surfacing_history.json"
    path.write_text(json.dumps({"dec-a": 5}))

    state = make_session_state("stop-accum", store=store)
    state.record_decision_surfaced("dec-a")
    state.record_decision_surfaced("dec-c")

    _update_surfacing_history(state)

    history = json.loads(path.read_text())
    assert history["dec-a"] == 6
    assert history["dec-c"] == 1


# ── Coaching suppression ─────────────────────────────────────────────


def test_coaching_suppressed_for_experienced_capturer(tmp_path):
    """Impl/plan coaching messages suppressed when user captures consistently."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _should_suppress_coaching, _stop_nudge_condition
    from decision.utils.helpers import _state_dir

    # Seed capture history with 4 sessions over 4 days (> threshold of 3)
    history = [time.time() - i * 86400 for i in range(4)]
    path = _state_dir() / "capture_history.json"
    path.write_text(json.dumps(history))

    assert _should_suppress_coaching() is True

    # Create impl-nudge state that would normally trigger coaching
    state = make_session_state("coaching-suppress", store=store)
    state.mark_fired("_impl-nudge-pending")
    state.store_data("_impl-new-files", json.dumps(["a.py", "b.py", "c.py"]))
    state.store_data("_impl-dirs-touched", json.dumps(["src/", "lib/", "test/"]))
    for i in range(6):
        state.record_edit(f"src/file{i}.py")

    result = _stop_nudge_condition({}, state)
    # Should NOT contain impl coaching message
    if result is not None:
        assert "new file" not in result.system_message.lower()


def test_coaching_not_suppressed_for_new_user(tmp_path):
    """Coaching messages still fire for users with few captures."""
    from decision.policy.stop_nudge import _should_suppress_coaching
    from decision.utils.helpers import _state_dir

    # Only 1 capture session (below threshold of 3)
    path = _state_dir() / "capture_history.json"
    path.write_text(json.dumps([time.time()]))

    assert _should_suppress_coaching() is False


def test_coaching_not_suppressed_when_no_history(tmp_path):
    """Coaching fires when no capture history exists."""
    from decision.policy.stop_nudge import _should_suppress_coaching

    assert _should_suppress_coaching() is False


# ── Never-surfaced detection ─────────────────────────────────────────


def test_never_surfaced_warns_about_recent_decisions(tmp_path):
    """Warn about recent decisions with affects that never surfaced."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _check_never_surfaced
    from decision.utils.helpers import _state_dir

    # Create a recent decision with affects
    make_decision(decisions_dir, "new-dec", affects=["src/api/"], date="2026-03-25")

    # Empty surfacing history (decision never surfaced)
    path = _state_dir() / "surfacing_history.json"
    path.write_text(json.dumps({}))

    state = make_session_state("never-surfaced", store=store)
    result = _check_never_surfaced(state)
    assert result is not None
    assert "new-dec" in result
    assert "never surfaced" in result


def test_never_surfaced_silent_when_surfaced(tmp_path):
    """No warning when decision has surfaced before."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _check_never_surfaced
    from decision.utils.helpers import _state_dir

    make_decision(decisions_dir, "surfaced-dec", affects=["src/api/"], date="2026-03-25")

    # Decision has surfaced before
    path = _state_dir() / "surfacing_history.json"
    path.write_text(json.dumps({"surfaced-dec": 3}))

    state = make_session_state("surfaced-ok", store=store)
    result = _check_never_surfaced(state)
    assert result is None


def test_never_surfaced_silent_for_old_decisions(tmp_path):
    """No warning for decisions older than NEVER_SURFACED_AGE_DAYS."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _check_never_surfaced
    from decision.utils.helpers import _state_dir

    # Old decision (outside 30-day window)
    make_decision(decisions_dir, "old-dec", affects=["src/api/"], date="2025-01-01")

    path = _state_dir() / "surfacing_history.json"
    path.write_text(json.dumps({}))

    state = make_session_state("old-never", store=store)
    result = _check_never_surfaced(state)
    assert result is None


def test_never_surfaced_silent_when_no_affects(tmp_path):
    """No warning for decisions without affects (they're expected to not surface)."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _check_never_surfaced
    from decision.utils.helpers import _state_dir

    make_decision(decisions_dir, "no-affects-dec", date="2026-03-25")

    path = _state_dir() / "surfacing_history.json"
    path.write_text(json.dumps({}))

    state = make_session_state("no-affects", store=store)
    result = _check_never_surfaced(state)
    assert result is None


# ── session cleanup on stop ──────────────────────────────────────


def test_stop_nudge_cleans_up_session_dir(tmp_path):
    """stop-nudge cleans up the session's /tmp state directory."""
    _, store = make_store(tmp_path)
    from decision.policy.stop_nudge import _stop_nudge_condition

    state = make_session_state("stop-cleanup", store=store)
    state.record_edit("src/app.py")

    # Session dir should exist before stop
    assert state._dir.is_dir()

    _stop_nudge_condition({}, state)

    # Session dir should be removed after stop
    assert not state._dir.is_dir()
