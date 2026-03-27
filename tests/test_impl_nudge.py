"""Implementation nudge policy tests — detect agent-side decisions."""

from conftest import make_decision, make_session_state, make_store


def _write_data(fp, content=""):
    """Build PostToolUse data for a Write tool call."""
    return {"tool_name": "Write", "tool_input": {"file_path": fp, "content": content}}


def _edit_data(fp, new_string=""):
    """Build PostToolUse data for an Edit tool call."""
    return {"tool_name": "Edit", "tool_input": {"file_path": fp, "new_string": new_string}}


# ── Threshold: fires after 3+ new files + 6+ edits ──────────────────


def test_fires_after_threshold(tmp_path):
    """Fires when 3 new files are created and edit count is sufficient."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-fires", store=store)

    # Accumulate 3 new files via Write
    for i in range(3):
        state.record_edit(f"src/area{i}/file{i}.py")
        _impl_nudge_condition(_write_data(f"src/area{i}/file{i}.py"), state)

    # Need 6+ edit invocations before firing
    for i in range(3, 6):
        state.record_edit(f"src/area0/extra{i}.py")

    result = _impl_nudge_condition(_write_data("src/area0/extra6.py"), state)
    assert result is not None
    assert result.matched is True
    assert "new file" in result.system_message
    assert "no decisions captured" in result.system_message


def test_silent_below_threshold(tmp_path):
    """Does NOT fire when below the new-file threshold."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-below", store=store)

    # Only 2 new files in same directory (below threshold of 3, no breadth)
    for i in range(2):
        state.record_edit(f"src/utils/file{i}.py")
        _impl_nudge_condition(_write_data(f"src/utils/file{i}.py"), state)

    # More edits in same directory (no new dirs)
    for i in range(2, 8):
        state.record_edit(f"src/utils/extra{i}.py")
        _impl_nudge_condition(_edit_data(f"src/utils/extra{i}.py"), state)

    result = _impl_nudge_condition(_edit_data("src/utils/extra8.py"), state)
    assert result is None


def test_breadth_condition(tmp_path):
    """Fires with 2 new files + 3 distinct directories."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-breadth", store=store)

    # 2 new files across different dirs
    state.record_edit("src/auth/handler.py")
    _impl_nudge_condition(_write_data("src/auth/handler.py"), state)
    state.record_edit("src/cache/store.py")
    _impl_nudge_condition(_write_data("src/cache/store.py"), state)

    # Touch a 3rd directory via edits — collect results to find when it fires
    fired = None
    for i in range(7):
        state.record_edit(f"src/api/route{i}.py")
        result = _impl_nudge_condition(_edit_data(f"src/api/route{i}.py"), state)
        if result is not None:
            fired = result
            break

    assert fired is not None, "Should fire once breadth threshold met with sufficient edits"
    assert "2 new file" in fired.system_message


# ── Interaction with capture-nudge ───────────────────────────────────


def test_silent_when_capture_nudge_pending(tmp_path):
    """Does NOT fire when capture-nudge already detected user decision language."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-capture", store=store)
    state.mark_fired("_capture-nudge-pending")

    for i in range(7):
        state.record_edit(f"src/dir{i}/file{i}.py")
        _impl_nudge_condition(_write_data(f"src/dir{i}/file{i}.py"), state)

    result = _impl_nudge_condition(_write_data("src/dir7/file7.py"), state)
    assert result is None


# ── Nudge dismissal ──────────────────────────────────────────────────


def test_silent_when_dismissed(tmp_path):
    """Does NOT fire when nudges are dismissed."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-dismissed", store=store)
    state.mark_nudges_dismissed()

    for i in range(7):
        state.record_edit(f"src/dir{i}/file{i}.py")
        _impl_nudge_condition(_write_data(f"src/dir{i}/file{i}.py"), state)

    result = _impl_nudge_condition(_write_data("src/dir7/file7.py"), state)
    assert result is None


# ── Cooldown ─────────────────────────────────────────────────────────


def test_cooldown_between_nudges(tmp_path):
    """Second nudge requires IMPL_NUDGE_COOLDOWN more edits."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-cooldown", store=store)

    # First: create 3 files + 6 edits → fires
    for i in range(3):
        state.record_edit(f"src/area{i}/file{i}.py")
        _impl_nudge_condition(_write_data(f"src/area{i}/file{i}.py"), state)
    for i in range(3, 6):
        state.record_edit(f"src/area0/extra{i}.py")

    result = _impl_nudge_condition(_write_data("src/area0/extra6.py"), state)
    assert result is not None  # first nudge fires

    # Immediately after: should be in cooldown
    state.record_edit("src/area0/extra7.py")
    result2 = _impl_nudge_condition(_write_data("src/area1/new.py"), state)
    assert result2 is None  # cooldown active


# ── Skip patterns ────────────────────────────────────────────────────


def test_skips_test_files(tmp_path):
    """Does NOT count test files toward the threshold."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-skip", store=store)

    for i in range(7):
        state.record_edit(f"tests/test_file{i}.py")
        _impl_nudge_condition(_write_data(f"tests/test_file{i}.py"), state)

    result = _impl_nudge_condition(_write_data("tests/test_file7.py"), state)
    assert result is None


# ── Decision comments ────────────────────────────────────────────────


def test_detects_decision_comments(tmp_path):
    """Includes code comment hints when decision language found in comments."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-comments", store=store)

    content_with_comment = '''
def process():
    # chose pattern matching over NLP because of stdlib-only constraint
    return match(text)
'''
    for i in range(3):
        state.record_edit(f"src/area{i}/file{i}.py")
        _impl_nudge_condition(
            _write_data(f"src/area{i}/file{i}.py", content_with_comment if i == 0 else ""),
            state,
        )
    for i in range(3, 6):
        state.record_edit(f"src/area0/extra{i}.py")

    result = _impl_nudge_condition(_write_data("src/area0/extra6.py"), state)
    assert result is not None
    assert "Code comment hint" in result.system_message
    assert "pattern matching" in result.system_message


# ── Decision captured → silent ───────────────────────────────────────


def test_silent_when_decision_captured(tmp_path):
    """Does NOT fire if decisions were captured this session."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition

    state = make_session_state("impl-captured", store=store)

    for i in range(3):
        state.record_edit(f"src/area{i}/file{i}.py")
        _impl_nudge_condition(_write_data(f"src/area{i}/file{i}.py"), state)
    for i in range(3, 6):
        state.record_edit(f"src/area0/extra{i}.py")

    # Simulate a decision being written
    make_decision(decisions_dir, "test-impl-dec")

    result = _impl_nudge_condition(_write_data("src/area0/extra6.py"), state)
    assert result is None


# ── Stop-nudge integration ───────────────────────────────────────────


def test_stop_nudge_detects_impl_session(tmp_path):
    """Stop-nudge shows implementation session summary."""
    _, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition, _save_json_list
    from decision.policy.stop_nudge import _stop_nudge_condition

    state = make_session_state("impl-stop", store=store)

    # Simulate 3 new files across dirs
    for i in range(3):
        state.record_edit(f"src/area{i}/file{i}.py")
        _impl_nudge_condition(_write_data(f"src/area{i}/file{i}.py"), state)

    # More edits to reach edit_count >= 5
    for i in range(3, 6):
        state.record_edit(f"src/area0/extra{i}.py")

    result = _stop_nudge_condition({}, state)
    assert result is not None
    assert "new file" in result.system_message
    assert "no decisions captured" in result.system_message


def test_stop_nudge_silent_when_decision_captured(tmp_path):
    """Stop-nudge does NOT show impl summary if decisions were captured."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.impl_nudge import _impl_nudge_condition
    from decision.policy.stop_nudge import _stop_nudge_condition

    state = make_session_state("impl-stop-ok", store=store)

    for i in range(5):
        state.record_edit(f"src/area{i}/file{i}.py")
        _impl_nudge_condition(_write_data(f"src/area{i}/file{i}.py"), state)

    # Decision captured
    make_decision(decisions_dir, "test-stop-dec")

    result = _stop_nudge_condition({}, state)
    # Should not mention "no decisions captured"
    if result is not None:
        assert "no decisions captured" not in result.system_message
