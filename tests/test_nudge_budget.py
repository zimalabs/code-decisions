"""Tests for per-session nudge budget."""

import decision
from conftest import make_session_state, make_store, make_decision
from decision.policy.engine import Policy, PolicyEngine, PolicyLevel, PolicyResult, SessionState
from decision.utils.constants import NUDGE_BUDGET


def _dummy_nudge(name: str, matched: bool = True):
    """Create a NUDGE policy that always matches (or not)."""

    def condition(data, state):
        if matched:
            return PolicyResult(matched=True, reason=f"{name} fired")
        return None

    return Policy(
        name=name,
        description=f"test nudge {name}",
        level=PolicyLevel.NUDGE,
        events=["UserPromptSubmit"],
        matchers=["*"],
        condition=condition,
    )


def _dummy_context(name: str):
    """Create a CONTEXT policy that always matches."""

    def condition(data, state):
        return PolicyResult(matched=True, system_message=f"{name} context")

    return Policy(
        name=name,
        description=f"test context {name}",
        level=PolicyLevel.CONTEXT,
        events=["UserPromptSubmit"],
        matchers=["*"],
        condition=condition,
    )


# ── SessionState nudge counter ────────────────────────────────────


def test_nudge_count_starts_at_zero():
    state = make_session_state("budget-zero")
    assert state.nudge_count() == 0


def test_nudge_count_increments_and_persists():
    state = make_session_state("budget-inc")
    state.increment_nudge_count()
    state.increment_nudge_count()
    assert state.nudge_count() == 2

    # Simulate a new hook invocation loading from disk
    state2 = SessionState(session_id=state._dir.name.replace("decision-policy-", ""))
    assert state2.nudge_count() == 2


def test_nudge_budget_remaining():
    state = make_session_state("budget-remaining")
    assert state.nudge_budget_remaining(NUDGE_BUDGET) is True
    state.increment_nudge_count()
    state.increment_nudge_count()
    state.increment_nudge_count()
    assert state.nudge_budget_remaining(NUDGE_BUDGET) is False


# ── Engine budget enforcement ─────────────────────────────────────


def test_engine_skips_nudges_when_budget_exhausted():
    """Engine should skip NUDGE policies once the budget is spent."""
    engine = PolicyEngine()
    engine.register(_dummy_nudge("nudge-a"))
    engine.register(_dummy_nudge("nudge-b"))
    engine.register(_dummy_nudge("nudge-c"))
    engine.register(_dummy_nudge("nudge-d"))

    state = make_session_state("budget-engine")

    import json

    result = json.loads(engine.evaluate("UserPromptSubmit", {}, state))
    reasons = result.get("reason", "")

    # Only 2 nudges should fire (budget=2)
    assert "nudge-a fired" in reasons
    assert "nudge-b fired" in reasons
    assert "nudge-c fired" not in reasons
    assert "nudge-d fired" not in reasons

    # Trace should show nudge-c and nudge-d skipped
    skipped = [t for t in engine.last_trace if t["skipped"] == "nudge_budget_exhausted"]
    assert len(skipped) == 2
    assert skipped[0]["policy"] == "nudge-c"
    assert skipped[1]["policy"] == "nudge-d"


def test_context_policies_unaffected_by_nudge_budget():
    """CONTEXT-level policies should not be limited by the nudge budget."""
    engine = PolicyEngine()
    engine.register(_dummy_context("ctx-a"))
    engine.register(_dummy_context("ctx-b"))
    engine.register(_dummy_nudge("nudge-a"))

    state = make_session_state("budget-context")
    # Exhaust the nudge budget manually
    for _ in range(5):
        state.increment_nudge_count()

    import json

    result = json.loads(engine.evaluate("UserPromptSubmit", {}, state))

    # Context policies should fire even with exhausted nudge budget
    ctx_fired = [t for t in engine.last_trace if t["matched"] and "ctx-" in t["policy"]]
    assert len(ctx_fired) == 2

    # Nudge should be skipped
    nudge_skipped = [t for t in engine.last_trace if t["skipped"] == "nudge_budget_exhausted"]
    assert len(nudge_skipped) == 1


def test_nudge_dismissed_independent_of_budget():
    """nudges_dismissed() kill switch works independently of budget."""
    engine = PolicyEngine()
    engine.register(_dummy_nudge("nudge-with-dismiss"))

    state = make_session_state("budget-dismiss")
    # Budget has room but nudges are dismissed — the individual policy
    # should check nudges_dismissed() itself (not the engine).
    # The engine only enforces budget, not dismissal.
    assert state.nudge_budget_remaining(NUDGE_BUDGET) is True

    # Verify nudge counter and dismiss are separate mechanisms
    state.mark_nudges_dismissed()
    assert state.nudges_dismissed() is True
    assert state.nudge_budget_remaining(NUDGE_BUDGET) is True  # budget still has room


def _dummy_stop_nudge(name: str):
    """Create a NUDGE policy for Stop events that always matches."""

    def condition(data, state):
        return PolicyResult(matched=True, reason=f"{name} fired")

    return Policy(
        name=name,
        description=f"test stop nudge {name}",
        level=PolicyLevel.NUDGE,
        events=["Stop"],
        matchers=["*"],
        condition=condition,
    )


def test_stop_event_nudges_respect_budget():
    """Stop-event nudges are now subject to the nudge budget like all other nudges."""
    engine = PolicyEngine()
    engine.register(_dummy_stop_nudge("stop-summary"))

    state = make_session_state("budget-stop")
    # Exhaust the nudge budget
    for _ in range(NUDGE_BUDGET + 5):
        state.increment_nudge_count()

    import json

    result = json.loads(engine.evaluate("Stop", {}, state))
    # Budget exhausted — stop nudge should NOT fire
    assert result == {}
