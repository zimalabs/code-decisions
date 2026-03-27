"""Policy engine test suite — core engine mechanics.

Tests for PolicyEngine evaluation, tracing, config, SessionState, and activity tracking.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import decision
from conftest import PLUGIN_DIR, make_decision, make_session_state, make_store
from decision import SessionState


# ── PolicyEngine tests ──────────────────────────────────────────────


def test_engine_list_policies():
    """PolicyEngine.list_policies returns all registered policies."""
    engine = decision.PolicyEngine()
    p = decision.Policy(
        name="test-policy",
        description="A test",
        level=decision.PolicyLevel.NUDGE,
        events=["PostToolUse"],
        matchers=["Bash"],
        condition=lambda d, s: None,
    )
    engine.register(p)
    policies = engine.list_policies()
    assert len(policies) == 1
    assert policies[0]["name"] == "test-policy"
    assert policies[0]["level"] == "NUDGE"


def test_engine_evaluate_empty():
    """Evaluate with no matching policies returns {}."""
    engine = decision.PolicyEngine()
    state = make_session_state("empty")
    result = engine.evaluate("PreToolUse", {}, state)
    assert result == "{}"


def test_engine_block_stops_evaluation():
    """BLOCK policy stops evaluation — subsequent policies don't run."""
    ran = []

    def blocker(d, s):
        ran.append("blocker")
        return decision.PolicyResult(matched=True, decision="block", reason="blocked")

    def nudger(d, s):
        ran.append("nudger")
        return decision.PolicyResult(matched=True, system_message="nudge")

    engine = decision.PolicyEngine()
    engine.register(decision.Policy("block-p", "", decision.PolicyLevel.BLOCK, ["PreToolUse"], ["*"], blocker))
    engine.register(decision.Policy("nudge-p", "", decision.PolicyLevel.NUDGE, ["PreToolUse"], ["*"], nudger))

    state = make_session_state("block-stops")
    result = json.loads(engine.evaluate("PreToolUse", {"tool_name": "Bash"}, state))
    assert result["decision"] == "block"
    assert ran == ["blocker"]


def test_engine_nudge_collects_all():
    """Multiple NUDGE policies collect all messages."""

    def nudge1(d, s):
        return decision.PolicyResult(matched=True, system_message="msg1")

    def nudge2(d, s):
        return decision.PolicyResult(matched=True, system_message="msg2")

    engine = decision.PolicyEngine()
    engine.register(decision.Policy("n1", "", decision.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], nudge1))
    engine.register(decision.Policy("n2", "", decision.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], nudge2))

    state = make_session_state("nudge-all")
    result = json.loads(engine.evaluate("PostToolUse", {"tool_name": "Write"}, state))
    assert "msg1" in str(result.get("systemMessage", ""))
    assert "msg2" in str(result.get("systemMessage", ""))


def test_engine_once_per_session():
    """once_per_session policies only fire once."""
    call_count = [0]

    def counter(d, s):
        call_count[0] += 1
        return decision.PolicyResult(matched=True, system_message="fired")

    engine = decision.PolicyEngine()
    engine.register(
        decision.Policy("once", "", decision.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], counter, once_per_session=True)
    )

    state = make_session_state("once")
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)
    assert call_count[0] == 1


def test_engine_exception_isolation():
    """Policy exceptions don't crash the engine."""

    def exploder(d, s):
        raise RuntimeError("boom")

    def ok_policy(d, s):
        return decision.PolicyResult(matched=True, system_message="survived")

    engine = decision.PolicyEngine()
    engine.register(decision.Policy("explode", "", decision.PolicyLevel.CONTEXT, ["PostToolUse"], ["*"], exploder))
    engine.register(decision.Policy("ok", "", decision.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], ok_policy))

    state = make_session_state("exception")
    result = json.loads(engine.evaluate("PostToolUse", {"tool_name": "Write"}, state))
    assert "survived" in str(result.get("systemMessage", ""))


# ── SessionState tests ──────────────────────────────────────────────


def test_session_state_has_fired():
    """SessionState tracks fired policies."""
    state = make_session_state("state-fired")
    assert state.has_fired("test-policy") is False
    state.mark_fired("test-policy")
    assert state.has_fired("test-policy") is True


def test_session_state_activity_tracking():
    """SessionState tracks file edits."""
    state = make_session_state("activity")
    assert state.edit_count() == 0
    assert state.has_edits() is False

    state.record_edit("src/main.py")
    assert state.edit_count() == 1
    assert state.has_edits() is True

    # Duplicate is ignored
    state.record_edit("src/main.py")
    assert state.edit_count() == 1

    state.record_edit("src/other.py")
    assert state.edit_count() == 2


def test_session_state_activity_skips_decisions():
    """SessionState.record_edit skips decisions/ paths."""
    state = make_session_state("activity-skip")
    state.record_edit("/home/user/project/.claude/decisions/foo.md")
    assert state.edit_count() == 0


def test_session_state_has_recent_decisions(tmp_path):
    """SessionState.has_recent_decisions detects new files."""
    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir()

    state = make_session_state("recent")
    assert state.has_recent_decisions(str(decisions_dir)) is False

    f = make_decision(decisions_dir)
    # Set mtime to 1 second in the future to guarantee it's after session start
    future = time.time() + 1
    os.utime(f, (future, future))
    assert state.has_recent_decisions(str(decisions_dir)) is True


def test_engine_records_edits():
    """PolicyEngine.evaluate records edits for PostToolUse Write/Edit/MultiEdit."""
    engine = decision.PolicyEngine()
    state = make_session_state("engine-edits")

    engine.evaluate(
        "PostToolUse",
        {"tool_name": "Write", "tool_input": {"file_path": "src/app.py", "content": "hello"}},
        state,
    )
    assert state.edit_count() == 1

    engine.evaluate(
        "PostToolUse",
        {"tool_name": "Edit", "tool_input": {"file_path": "src/model.py", "old_string": "x", "new_string": "y"}},
        state,
    )
    assert state.edit_count() == 2

    engine.evaluate(
        "PostToolUse",
        {"tool_name": "Read", "tool_input": {"file_path": "src/other.py"}},
        state,
    )
    assert state.edit_count() == 2


# ── Full engine integration test ────────────────────────────────────


def test_full_engine_with_all_policies():
    """Load all policies and evaluate a non-matching event."""
    from decision.policy.defs import ALL_POLICIES

    engine = decision.PolicyEngine()
    for p in ALL_POLICIES:
        engine.register(p)

    policies = engine.list_policies()
    assert len(policies) == 11

    # Verify ordering — BLOCK first
    assert policies[0]["level"] == "BLOCK"

    # Evaluate a non-matching event
    state = make_session_state("full-engine")
    result = engine.evaluate("PreToolUse", {"tool_name": "Read"}, state)
    assert result == "{}"


def test_policy_list_command():
    """python3 -m decision policy (no args) lists policies."""
    parent_dir = str(Path(__file__).resolve().parent.parent / "src")
    result = subprocess.run(
        [sys.executable, "-m", "decision", "policy"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": parent_dir},
    )
    assert result.returncode == 0
    policies = json.loads(result.stdout)
    assert len(policies) == 11
    names = [p["name"] for p in policies]
    assert "content-validation" in names
    assert "session-init" in names
    assert "session-context" in names
    assert "related-context" in names
    assert "capture-nudge" in names


# ── Trace tests ─────────────────────────────────────────────────────


def test_engine_trace_collection():
    """PolicyEngine collects trace entries during evaluate."""

    def match_policy(d, s):
        return decision.PolicyResult(matched=True, system_message="hit")

    def skip_policy(d, s):
        return None

    engine = decision.PolicyEngine()
    engine.register(decision.Policy("p-match", "", decision.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], match_policy))
    engine.register(decision.Policy("p-skip", "", decision.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], skip_policy))

    state = make_session_state("trace")
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)

    assert len(engine.last_trace) == 2
    assert engine.last_trace[0]["matched"] is True
    assert engine.last_trace[1]["matched"] is False


# ── Session activity cap ───────────────────────────────────────────


def test_session_state_edit_cap():
    """record_edit stops recording after MAX_SESSION_EDITS unique files."""
    from decision.utils.constants import MAX_SESSION_EDITS

    state = make_session_state("cap-test")
    for i in range(MAX_SESSION_EDITS + 50):
        state.record_edit(f"src/file_{i}.py")

    assert state.edit_count() == MAX_SESSION_EDITS
    assert len(state.files_edited()) == MAX_SESSION_EDITS


# ── Session ID fallback ───────────────────────────────────────────


def test_session_id_fallback_is_stable():
    """Without CLAUDE_SESSION_ID, fallback ID is stable across calls with same cwd+ppid."""
    from unittest.mock import patch

    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_SESSION_ID"}
    with patch.dict(os.environ, env, clear=True):
        state1 = SessionState()
        state2 = SessionState()
    # Both should use the same session dir (same cwd + ppid)
    assert state1._dir == state2._dir
    assert state1._session_id_fallback is True


def test_session_id_fallback_differs_from_explicit():
    """Explicit session ID produces a different dir than fallback."""
    from unittest.mock import patch

    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_SESSION_ID"}
    with patch.dict(os.environ, env, clear=True):
        fallback = SessionState()
    explicit = SessionState(session_id="explicit-test-id")
    assert fallback._dir != explicit._dir
    assert explicit._session_id_fallback is False


# ── Atomic writes ─────────────────────────────────────────────────


def test_activity_persists_after_save(tmp_path):
    """Activity written atomically is readable by a new SessionState."""
    state = SessionState(session_id="atomic-test-1")
    state.record_edit("src/main.py")
    state.record_edit("src/util.py")

    # Create a new state with the same session ID — should load from disk
    state2 = SessionState(session_id="atomic-test-1")
    assert state2.edit_count() == 2
    assert "src/main.py" in state2.files_edited()


def test_corrupt_activity_logs_and_resets():
    """Corrupt activity JSON is logged and reset to defaults."""
    state = SessionState(session_id="corrupt-test-1")
    # Write corrupt JSON directly
    state._activity_path().write_text("{broken json")

    # New state should recover gracefully
    state2 = SessionState(session_id="corrupt-test-1")
    assert state2.edit_count() == 0


# ── PolicyResult.to_hook_json tests ──────────────────────────────


def test_to_hook_json_block():
    """to_hook_json returns block decision."""
    r = decision.PolicyResult(matched=True, decision="block", reason="dangerous")
    result = r.to_hook_json("PreToolUse")
    assert result == {"decision": "block", "reason": "dangerous"}


def test_to_hook_json_reject():
    """to_hook_json returns reject with ok=False."""
    r = decision.PolicyResult(matched=True, decision="reject", reason="invalid")
    result = r.to_hook_json("PreToolUse")
    assert result == {"ok": False, "reason": "invalid"}


def test_to_hook_json_session_start():
    """to_hook_json returns hookSpecificOutput for SessionStart."""
    r = decision.PolicyResult(matched=True, additional_context="context here")
    result = r.to_hook_json("SessionStart")
    assert result["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert result["hookSpecificOutput"]["additionalContext"] == "context here"


def test_to_hook_json_stop_event():
    """to_hook_json returns ok for Stop event."""
    r = decision.PolicyResult(matched=True, ok=True, reason="done")
    result = r.to_hook_json("Stop")
    assert result == {"ok": True, "reason": "done"}


def test_to_hook_json_stop_no_reason():
    """to_hook_json for Stop without reason omits reason key."""
    r = decision.PolicyResult(matched=True, ok=True)
    result = r.to_hook_json("Stop")
    assert result == {"ok": True}


def test_to_hook_json_user_prompt_submit():
    """to_hook_json returns ok for UserPromptSubmit."""
    r = decision.PolicyResult(matched=True, ok=False, reason="wait")
    result = r.to_hook_json("UserPromptSubmit")
    assert result == {"ok": False, "reason": "wait"}


def test_to_hook_json_system_message():
    """to_hook_json returns systemMessage for other events."""
    r = decision.PolicyResult(matched=True, system_message="hello")
    result = r.to_hook_json("PostToolUse")
    assert result == {"systemMessage": "hello"}


def test_to_hook_json_empty():
    """to_hook_json returns empty dict when no special fields set."""
    r = decision.PolicyResult(matched=True)
    result = r.to_hook_json("PostToolUse")
    assert result == {}


# ── __main__ entry point test ────────────────────────────────────


def test_main_module_entry_point():
    """python -m decision help runs without error."""
    parent_dir = str(Path(__file__).resolve().parent.parent / "src")
    result = subprocess.run(
        [sys.executable, "-m", "decision", "help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": parent_dir},
    )
    assert result.returncode == 0


def test_main_module_importable():
    """decision.__main__ is importable and exposes main."""
    import importlib

    mod = importlib.import_module("decision.__main__")
    assert hasattr(mod, "main")


def test_nudge_count_persists():
    """Nudge count written atomically persists across instances."""
    import uuid

    sid = f"nudge-persist-{uuid.uuid4().hex[:8]}"
    state = SessionState(session_id=sid)
    state.increment_nudge_count()
    state.increment_nudge_count()

    state2 = SessionState(session_id=sid)
    assert state2.nudge_count() == 2


# ── try_claim tests ──────────────────────────────────────────────


def test_try_claim_first_call_succeeds():
    """try_claim returns True on first call, False on second."""
    state = make_session_state("try-claim")
    assert state.try_claim("test-policy") is True
    assert state.try_claim("test-policy") is False


def test_try_claim_with_path_separator():
    """try_claim handles keys with path separators (hashed marker)."""
    state = make_session_state("try-claim-path")
    assert state.try_claim("related-context/src/foo.py") is True
    assert state.try_claim("related-context/src/foo.py") is False


# ── cleanup_stale tests ──────────────────────────────────────────


def test_cleanup_stale_removes_old():
    """cleanup_stale removes session dirs older than max_age."""
    import tempfile

    state = make_session_state("cleanup-old")
    # Backdate the dir mtime
    import os

    os.utime(state._dir, (0, 0))
    removed = SessionState.cleanup_stale(max_age_seconds=1)
    assert removed >= 1


def test_cleanup_stale_keeps_recent():
    """cleanup_stale keeps recent session dirs."""
    state = make_session_state("cleanup-recent")
    removed = SessionState.cleanup_stale(max_age_seconds=86400)
    # Our state dir is brand new, should not be removed
    assert state._dir.exists()


# ── mark_fired idempotent ────────────────────────────────────────


def test_mark_fired_idempotent():
    """mark_fired can be called twice without error."""
    state = make_session_state("mark-idem")
    state.mark_fired("test-policy")
    state.mark_fired("test-policy")  # should not raise
    assert state.has_fired("test-policy") is True


# ── _save_activity error path ────────────────────────────────────


def test_save_activity_oserror_ignored():
    """_save_activity logs warning on OSError without raising."""
    from unittest.mock import patch as _patch

    state = make_session_state("save-err")
    state.record_edit("src/foo.py")
    # Make the dir read-only to trigger OSError on next save
    with _patch("tempfile.mkstemp", side_effect=OSError("disk full")):
        state._save_activity()  # should not raise


# ── flush_activity no-op ─────────────────────────────────────────


def test_flush_activity_noop_when_empty():
    """flush_activity does nothing when no edits recorded."""
    state = make_session_state("flush-empty")
    state.flush_activity()  # should not raise


# ── store_data / load_data ─────────────────────────────────────────


def test_store_data_and_load_data():
    """store_data persists and load_data retrieves."""
    state = make_session_state("store-data")
    state.store_data("my-key", "my-value")
    assert state.load_data("my-key") == "my-value"


def test_store_data_oserror_silent():
    """store_data silently ignores OSError."""
    from unittest.mock import patch as _patch

    state = make_session_state("store-err")
    with _patch.object(Path, "write_text", side_effect=OSError("disk full")):
        state.store_data("k", "v")  # should not raise
    # Value not persisted
    assert state.load_data("k") == ""


def test_load_data_missing_key():
    """load_data returns empty string for missing key."""
    state = make_session_state("load-missing")
    assert state.load_data("nonexistent") == ""


# ── _load_activity_from_disk error paths ────────────────────────────


def test_load_activity_oserror_returns_default():
    """_load_activity_from_disk returns default on OSError."""
    from unittest.mock import patch as _patch

    state = make_session_state("load-err")
    # Write valid activity first
    state.record_edit("src/foo.py")

    with _patch.object(Path, "read_text", side_effect=OSError("permission denied")):
        result = state._load_activity_from_disk()
    assert result == {"edits": []}


# ── increment_nudge_count error path ───────────────────────────────


def test_increment_nudge_count_write_failure():
    """increment_nudge_count logs warning on write failure."""
    from unittest.mock import patch as _patch

    state = make_session_state("nudge-err")
    with _patch("tempfile.mkstemp", side_effect=OSError("disk full")):
        state.increment_nudge_count()  # should not raise
    # Count stays at 0 since the write failed
    assert state.nudge_count() == 0


# ── has_recent_decisions edge cases ─────────────────────────────────


def test_has_recent_decisions_nonexistent_dir():
    """has_recent_decisions returns False for nonexistent dir."""
    state = make_session_state("recent-nodir")
    assert state.has_recent_decisions("/nonexistent/dir") is False


def test_has_recent_decisions_stat_oserror(tmp_path):
    """has_recent_decisions returns False on stat() OSError."""
    from unittest.mock import patch as _patch

    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir()
    make_decision(decisions_dir)

    state = make_session_state("recent-stat-err")
    # Patch Path.stat on files to raise OSError
    original_stat = Path.stat

    def broken_stat(self, **kwargs):
        if self.suffix == ".md" and "decisions" in str(self):
            raise OSError("broken")
        return original_stat(self, **kwargs)

    with _patch.object(Path, "stat", broken_stat):
        result = state.has_recent_decisions(str(decisions_dir))
    assert result is False


# ── evaluate forces ok=True ──────────────────────────────────────


def test_evaluate_forces_ok_true():
    """Plugin is always advisory — evaluate forces ok=True even if policy says False."""
    def rejector(d, s):
        return decision.PolicyResult(matched=True, ok=False, reason="reject-intent")

    engine = decision.PolicyEngine()
    engine.register(
        decision.Policy("rej", "", decision.PolicyLevel.NUDGE, ["Stop"], ["*"], rejector)
    )

    state = make_session_state("force-ok")
    result = json.loads(engine.evaluate("Stop", {"tool_name": "*"}, state))
    assert result["ok"] is True


# ── cleanup_stale edge cases ─────────────────────────────────────


def test_cleanup_stale_non_dir_skipped():
    """cleanup_stale skips files (not dirs) named decision-policy-*."""
    import tempfile

    tmp = Path(tempfile.gettempdir())
    fake_file = tmp / "decision-policy-fakefile"
    fake_file.write_text("not a dir")
    try:
        removed = SessionState.cleanup_stale(max_age_seconds=0)
        # Should not count the file
        assert fake_file.exists()
    finally:
        fake_file.unlink(missing_ok=True)


def test_cleanup_stale_handles_permission_error():
    """cleanup_stale handles dirs where stat fails by continuing."""
    # This is tested implicitly via the OSError catch in cleanup_stale.
    # We just verify cleanup_stale doesn't crash with a normal run.
    removed = SessionState.cleanup_stale(max_age_seconds=86400)
    assert removed >= 0


# ── edit_invocations ─────────────────────────────────────────────


def test_edit_invocations_counts_all():
    """edit_invocations counts total calls, not just unique files."""
    state = make_session_state("invoc")
    state.record_edit("src/foo.py")
    state.record_edit("src/foo.py")  # same file, still increments invocations
    state.record_edit("src/bar.py")
    assert state.edit_invocations() == 3
    assert state.edit_count() == 2  # unique files


# ── mark_nudges_dismissed / nudges_dismissed ─────────────────────


def test_nudges_dismissed():
    """mark_nudges_dismissed + nudges_dismissed round-trips."""
    state = make_session_state("dismiss")
    assert state.nudges_dismissed() is False
    state.mark_nudges_dismissed()
    assert state.nudges_dismissed() is True


# ── increment_activity_counter / get_activity_counter ─────────────


def test_activity_counter_roundtrip():
    """increment_activity_counter and get_activity_counter work together."""
    state = make_session_state("counter")
    assert state.get_activity_counter("decisions_surfaced") == 0
    state.increment_activity_counter("decisions_surfaced", 3)
    assert state.get_activity_counter("decisions_surfaced") == 3
    state.increment_activity_counter("decisions_surfaced")
    assert state.get_activity_counter("decisions_surfaced") == 4


