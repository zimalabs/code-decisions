"""Query preseed policy tests — slash command detection, result injection."""

from conftest import make_session_state, make_decision, make_store


# ── query-preseed tests ───────────────────────────────────────────


def test_query_preseed_injects_results(tmp_path):
    """query-preseed injects scored results when /decision:search is used."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    from decision.policy.defs import _query_preseed_condition

    state = make_session_state("qp-inject", store=store)
    data = {"tool_input": {"content": "/decision:search redis"}}
    result = _query_preseed_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "redis" in str(result.reason).lower()


def test_query_preseed_silent_without_slash_command(tmp_path):
    """query-preseed ignores prompts without /decision:search."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    from decision.policy.defs import _query_preseed_condition

    state = make_session_state("qp-no-slash", store=store)
    data = {"tool_input": {"content": "Tell me about redis decisions"}}
    result = _query_preseed_condition(data, state)
    assert result is None


def test_query_preseed_silent_no_args(tmp_path):
    """query-preseed ignores /decision:search without arguments."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    from decision.policy.defs import _query_preseed_condition

    state = make_session_state("qp-no-args", store=store)
    data = {"tool_input": {"content": "/decision:search"}}
    result = _query_preseed_condition(data, state)
    assert result is None


def test_query_preseed_fires_with_prompt_field(tmp_path):
    """query-preseed works with Claude Code's actual data shape: {"prompt": "..."}."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    from decision.policy.defs import _query_preseed_condition

    state = make_session_state("qp-prompt-field", store=store)
    data = {"prompt": "/decision redis"}
    result = _query_preseed_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "redis" in str(result.reason).lower()


def test_query_preseed_silent_empty_store(tmp_path):
    """query-preseed returns None when no decisions exist."""
    _, store = make_store(tmp_path)
    from decision.policy.defs import _query_preseed_condition

    state = make_session_state("qp-empty", store=store)
    data = {"tool_input": {"content": "/decision:search auth"}}
    result = _query_preseed_condition(data, state)
    assert result is None


def test_query_preseed_skips_manage_words(tmp_path):
    """query-preseed skips manage intent words like 'review', 'undo'."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "test-dec")
    from decision.policy.query_preseed import _query_preseed_condition

    state = make_session_state("qp-manage", store=store)
    for word in ["review", "undo", "dismiss", "debug", "publish"]:
        data = {"prompt": f"/decision {word}"}
        result = _query_preseed_condition(data, state)
        assert result is None, f"Should skip manage word: {word}"


def test_query_preseed_skips_capture_signals(tmp_path):
    """query-preseed skips capture intent phrases."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "test-dec")
    from decision.policy.query_preseed import _query_preseed_condition

    state = make_session_state("qp-capture", store=store)
    for phrase in ["we chose Redis", "decided to use X", "going with Y", "use Redis because", "chose MongoDB"]:
        data = {"prompt": f"/decision {phrase}"}
        result = _query_preseed_condition(data, state)
        assert result is None, f"Should skip capture signal: {phrase}"


def test_query_preseed_no_prompt(tmp_path):
    """query-preseed returns None when no prompt is present."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "test-dec")
    from decision.policy.query_preseed import _query_preseed_condition

    state = make_session_state("qp-noprompt", store=store)
    result = _query_preseed_condition({}, state)
    assert result is None


def test_query_preseed_no_matching_results(tmp_path):
    """query-preseed returns None when query finds no matches."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    from decision.policy.query_preseed import _query_preseed_condition

    state = make_session_state("qp-nomatch", store=store)
    data = {"prompt": "/decision zzzblimp_nonexistent_topic"}
    result = _query_preseed_condition(data, state)
    assert result is None
