"""Tests for concurrent session state operations.

Validates that try_claim, record_edit, and _save_activity are safe
under concurrent access from multiple threads (simulating concurrent
hook invocations within the same session).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from conftest import make_session_state


def _claim_worker(session_dir: str, policy_name: str) -> bool:
    """Worker that creates a fresh SessionState (like a new hook invocation) and tries to claim."""
    import decision

    ss = decision.SessionState(session_id=session_dir)
    return ss.try_claim(policy_name)


def test_try_claim_exactly_one_winner():
    """Only one concurrent try_claim should succeed for the same policy."""
    ss = make_session_state("concurrent-claim")
    session_id = str(ss._dir).split("decision-policy-")[-1]

    results = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_claim_worker, session_id, "test-policy") for _ in range(10)]
        results = [f.result() for f in futures]

    assert results.count(True) == 1, f"Expected exactly 1 winner, got {results.count(True)}"
    assert results.count(False) == 9


def test_concurrent_record_edit_no_data_loss(tmp_path):
    """Concurrent record_edit calls should not lose edits."""
    import decision

    sid = "test-concurrent-edits"

    def _edit_worker(file_path: str) -> None:
        ss = decision.SessionState(session_id=sid)
        ss.record_edit(file_path)

    files = [f"src/file_{i}.py" for i in range(20)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_edit_worker, files))

    # Final state should contain all edits
    final = decision.SessionState(session_id=sid)
    recorded = final._activity.get("edits", [])
    for f in files:
        assert f in recorded, f"Missing edit: {f}"


def test_concurrent_mark_fired_idempotent():
    """Multiple mark_fired calls for same policy should not raise."""
    ss = make_session_state("concurrent-mark")
    session_id = str(ss._dir).split("decision-policy-")[-1]

    import decision

    def _mark_worker(_: int) -> None:
        s = decision.SessionState(session_id=session_id)
        s.mark_fired("some-policy")

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(_mark_worker, range(10)))

    # Should be marked exactly once
    check = decision.SessionState(session_id=session_id)
    assert check.has_fired("some-policy")
