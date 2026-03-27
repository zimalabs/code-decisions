"""Capture nudge policy tests — detection, dedup, trigger phrases, dismiss."""

import pytest

import decision
from conftest import make_session_state, make_decision, make_store


# ── capture-nudge tests ────────────────────────────────────────────


def test_capture_nudge_detects_decision_language():
    """capture-nudge detects decision phrases."""
    from decision.policy.defs import _capture_nudge_condition

    state = make_session_state("cn-detect")
    data = {"tool_input": {"content": "Let's go with PostgreSQL for the database"}}
    result = _capture_nudge_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "capture" in str(result.reason)


def test_capture_nudge_fires_at_advise():
    """capture-nudge fires (plugin is always advise)."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state("cn-advise")
    data = {"tool_input": {"content": "Let's go with `PostgreSQL` for the DataStore"}}
    result = _capture_nudge_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "Capture this?" in result.reason


def test_capture_nudge_detects_query(tmp_path):
    """capture-nudge detects past-decision queries and pre-seeds results."""
    from decision.policy.defs import _capture_nudge_condition

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    state = make_session_state("cn-query", store=store)
    data = {"tool_input": {"content": "Why did we choose Redis?"}}
    result = _capture_nudge_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "decision" in str(result.reason).lower() or "decision" in str(result.system_message).lower()


def test_capture_nudge_ignores_normal():
    """capture-nudge ignores normal prompts."""
    from decision.policy.defs import _capture_nudge_condition

    state = make_session_state("cn-normal")
    data = {"tool_input": {"content": "Add a new endpoint for users"}}
    result = _capture_nudge_condition(data, state)
    assert result is None


def test_capture_nudge_per_phrase_dedup():
    """capture-nudge deduplicates by matched phrase."""
    from decision.policy.defs import _capture_nudge_condition

    state = make_session_state("cn-dedup")

    # Include technical signals (CamelCase/backtick) to pass the corroboration bar
    data1 = {"tool_input": {"content": "Let's go with `PostgreSQL` for the DataStore"}}
    r1 = _capture_nudge_condition(data1, state)
    assert r1 is not None
    assert r1.matched is True

    # Same phrase again — suppressed
    data2 = {"tool_input": {"content": "Let's go with `MySQL` instead"}}
    r2 = _capture_nudge_condition(data2, state)
    assert r2 is None

    # Different phrase — fires
    data3 = {"tool_input": {"content": "We decided on `Redis` for caching"}}
    r3 = _capture_nudge_condition(data3, state)
    assert r3 is not None
    assert r3.matched is True


@pytest.mark.parametrize("phrase", [
    "I chose `PostgreSQL` because of its JSON support",
    "After weighing the options, we picked `React` for the UserDashboard",
    "The trade-off is worth it for better performance on `api_server.py`",
    "Opting for `Redis` over `Memcached` in src/cache",
    "We went with the simpler approach and ruling out the complex one",  # two phrases
])
def test_capture_nudge_detects_expanded_phrases(phrase):
    """capture-nudge detects expanded decision phrases with technical signals."""
    from decision.policy.defs import _capture_nudge_condition

    state = make_session_state(f"cn-expanded-{hash(phrase)}")
    data = {"tool_input": {"content": phrase}}
    result = _capture_nudge_condition(data, state)
    assert result is not None, f"Failed to detect: {phrase}"
    assert result.matched is True


def test_capture_nudge_ignores_casual_conversation():
    """capture-nudge does NOT fire for casual phrases without technical signals."""
    from decision.policy.defs import _capture_nudge_condition

    state = make_session_state("cn-casual")
    # Trigger phrase but no technical signal and only one phrase
    data = {"tool_input": {"content": "Let's go with the simpler approach"}}
    result = _capture_nudge_condition(data, state)
    assert result is None, "Should not fire without technical signal or multiple phrases"


# ── Capture-nudge trigger phrase tests ────────────────────────────────


def test_capture_nudge_terse_message():
    """capture-nudge uses terse message without echoing the trigger phrase."""
    from decision.policy.defs import _capture_nudge_condition

    state = make_session_state("cn-terse")
    data = {"tool_input": {"content": "Let's go with PostgreSQL for the database"}}
    result = _capture_nudge_condition(data, state)
    assert result is not None
    assert result.reason == "Capture this? `/decision capture <title>`"


def test_capture_nudge_returns_ok_true():
    """capture-nudge returns ok=True (advisory, not blocking)."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state("capture-ok")
    data = {"tool_input": {"content": "let's go with PostgreSQL for the database"}}
    result = _capture_nudge_condition(data, state)
    assert result is not None
    assert result.ok is True
    assert "Capture this?" in result.reason


# ── Capture-nudge dismiss test ──────────────────────────────────────


def test_capture_nudge_fires_with_prompt_field():
    """capture-nudge works with Claude Code's actual data shape: {"prompt": "..."}."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state("cn-prompt-field")
    data = {"prompt": "Let's go with `PostgreSQL` for the DataStore"}
    result = _capture_nudge_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "Capture this?" in result.reason


def test_capture_nudge_query_with_prompt_field(tmp_path):
    """capture-nudge detects queries with Claude Code's {"prompt": "..."} shape."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    state = make_session_state("cn-query-prompt", store=store)
    data = {"prompt": "Why did we choose Redis?"}
    result = _capture_nudge_condition(data, state)
    assert result is not None
    assert result.matched is True


def test_capture_nudge_suppressed_when_dismissed():
    """capture-nudge returns None when nudges are dismissed."""
    from decision.policy.defs import _capture_nudge_condition

    state = make_session_state("cn-dismissed")
    state.mark_nudges_dismissed()
    data = {"tool_input": {"content": "Let's go with `PostgreSQL` for the database"}}
    result = _capture_nudge_condition(data, state)
    assert result is None


# ── False-positive filtering ───────────────────────────────────


@pytest.mark.parametrize("phrase", [
    "Let's go with your suggestion",
    "Let's go with that approach",
    "Switching to the test file to check coverage",
    "Going with the flow on this one",
    "Committing to the branch now",
    "I'm going with the default for now",
    "Let's go with this for now",
    "Going with it as-is",
    "Switching to the next task",
    "Let's use them both",
])
def test_capture_nudge_rejects_false_positives(phrase):
    """capture-nudge does NOT fire for conversational false positives."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state(f"cn-fp-{hash(phrase)}")
    data = {"tool_input": {"content": phrase}}
    result = _capture_nudge_condition(data, state)
    assert result is None, f"Should not fire for: {phrase!r}"


# ── Reasoning signal corroboration ──────────────────────────────


@pytest.mark.parametrize("phrase", [
    "Switching to Redis because Memcached doesn't support pub/sub",
    "Going with event sourcing instead of CRUD",
    "Let's go with token bucket rather than sliding window",
    "Opting for polling — the trade-off is worth it for simplicity",
])
def test_capture_nudge_fires_with_reasoning_signal(phrase):
    """capture-nudge fires when reasoning language corroborates the decision phrase."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state(f"cn-reasoning-{hash(phrase)}")
    data = {"tool_input": {"content": phrase}}
    result = _capture_nudge_condition(data, state)
    assert result is not None, f"Should fire for: {phrase!r}"
    assert result.matched is True


# ── Proximity-scoped technical signal ───────────────────────────


def test_capture_nudge_rejects_distant_technical_signal():
    """capture-nudge ignores technical signals far from the decision phrase."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    # Decision phrase at start, technical signal 200+ chars away
    prompt = (
        "Let's go with the simpler approach for now. "
        + "x" * 200
        + " Also fix the `UserModel` validation."
    )
    state = make_session_state("cn-distant")
    data = {"tool_input": {"content": prompt}}
    result = _capture_nudge_condition(data, state)
    assert result is None, "Technical signal too far from phrase should not corroborate"


def test_capture_nudge_accepts_nearby_technical_signal():
    """capture-nudge fires when technical signal is near the decision phrase."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state("cn-nearby")
    data = {"tool_input": {"content": "Let's go with `PostgreSQL` for the user_store"}}
    result = _capture_nudge_condition(data, state)
    assert result is not None, "Nearby technical signal should corroborate"
    assert result.matched is True


# ── False-positive window tests ──────────────────────────────────


def test_false_positive_catches_longer_phrases():
    """False-positive check catches phrases beyond old 30-char window."""
    from decision.policy.capture_nudge import _is_false_positive

    # "your recommended approach for auth" is 35 chars — old window would miss "your"
    prompt = "let's go with your recommended approach for authentication"
    # "let's go with" ends at index 13; check from there
    assert _is_false_positive(prompt.lower(), 13) is True


def test_false_positive_does_not_block_real_decisions():
    """Real decision phrases are not caught by false-positive check."""
    from decision.policy.capture_nudge import _is_false_positive

    prompt = "let's go with redis for caching because it supports pub/sub"
    assert _is_false_positive(prompt.lower(), 13) is False


# ── Context-aware nudge suppression ──────────────────────────────


def test_context_debug_suppresses_nudge():
    """capture-nudge is suppressed when debugging signals dominate."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state("cn-debug-suppress")
    # Decision phrase with technical signal, but heavy debug context
    data = {"prompt": "The bug is that `UserModel` crashes with an error. Let's go with `PostgreSQL` instead"}
    result = _capture_nudge_condition(data, state)
    assert result is None, "Should suppress nudge in debug context"


def test_context_debug_from_test_edits():
    """capture-nudge is suppressed when session has many test file edits."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state("cn-debug-edits")
    state.record_edit("tests/test_auth.py")
    state.record_edit("tests/test_handler.py")
    # "fix" + "error" in prompt + 2 test edits = debug context
    data = {"prompt": "After this fix for the error, let's go with `Redis` for caching"}
    result = _capture_nudge_condition(data, state)
    assert result is None, "Should suppress nudge when debugging with test edits"


def test_context_architecture_relaxes_corroboration():
    """capture-nudge fires without full corroboration in architecture context."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state("cn-arch-relax")
    # Architecture signal + decision phrase, but NO technical signal or reasoning
    data = {"prompt": "For the system design of our architecture, let's go with REST over GraphQL"}
    result = _capture_nudge_condition(data, state)
    assert result is not None, "Architecture context should relax corroboration"
    assert result.matched is True


def test_context_neutral_still_requires_corroboration():
    """In neutral context, original corroboration rules still apply."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    state = make_session_state("cn-neutral")
    # Decision phrase without any corroboration — should NOT fire
    data = {"prompt": "Let's go with the simpler approach"}
    result = _capture_nudge_condition(data, state)
    assert result is None, "Neutral context still requires corroboration"


def test_context_classifier_directly():
    """Test _conversation_context classification."""
    from decision.policy.capture_nudge import _conversation_context

    state = make_session_state("cn-ctx-test")

    assert _conversation_context("fix this bug, the error is unexpected", state) == "debug"
    assert _conversation_context("let's discuss the API design and the system design trade-offs", state) == "architecture"
    assert _conversation_context("add a new endpoint for users", state) == "neutral"


def test_debug_query_still_works(tmp_path):
    """Decision queries still work even in debug context (queries bypass nudge gating)."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    state = make_session_state("cn-debug-query", store=store)
    # Debug context but it's a query — queries bypass the context gate
    data = {"prompt": "Why did we choose Redis? The bug might be related to the error in caching"}
    result = _capture_nudge_condition(data, state)
    # Query should still return results even though debug signals are present
    assert result is not None, "Decision queries should bypass debug suppression"
    assert result.matched is True
