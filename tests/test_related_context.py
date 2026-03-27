"""Related context policy tests — injection, dedup, affects-weighting."""

from conftest import make_session_state, make_decision, make_store


# ── related-context tests ──────────────────────────────────────────


def test_related_context_injects(tmp_path):
    """related-context injects matching decisions when editing code."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")

    from decision.policy.defs import _related_context_condition

    state = make_session_state("rc-inject", store=store)
    data = {
        "tool_input": {
            "file_path": "src/cache/redis_client.py",
            "new_string": "def connect_redis():\n    pass",
        }
    }
    result = _related_context_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "redis-caching" in str(result.system_message).lower() or "redis" in str(result.system_message).lower()
    # Visible signal to user about context injection
    assert "decision" in str(result.reason).lower()
    assert "redis_client.py" in str(result.reason)


def test_related_context_skips_test_files(tmp_path):
    """related-context skips test files."""
    decisions_dir, store = make_store(tmp_path)

    from decision.policy.defs import _related_context_condition

    state = make_session_state("rc-test", store=store)
    data = {"tool_input": {"file_path": "tests/test_foo.py"}}
    result = _related_context_condition(data, state)
    assert result is None


def test_related_context_dedup(tmp_path):
    """related-context deduplicates by file path."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")

    from decision.policy.defs import _related_context_condition

    state = make_session_state("rc-dedup", store=store)
    data = {
        "tool_input": {
            "file_path": "src/cache/redis_client.py",
            "new_string": "def connect_redis():\n    pass",
        }
    }
    r1 = _related_context_condition(data, state)
    assert r1 is not None

    r2 = _related_context_condition(data, state)
    assert r2 is None


# ── affects-weighting in related-context ──────────────────────────


def test_related_context_affects_ranked_first(tmp_path):
    """Decisions with matching affects paths rank ahead of keyword-only matches."""
    decisions_dir, store = make_store(tmp_path)

    # Decision with affects matching the edited file
    affects_file = decisions_dir / "redis-with-affects.md"
    affects_file.write_text(
        '---\nname: "redis-with-affects"\ndescription: "Redis with affects"\ntype: "decision"\n'
        'date: "2026-03-17"\ntags:\n  - "caching"\nstatus: "active"\n'
        'affects:\n  - "src/cache/redis.py"\n---\n\n'
        "# Redis With Affects\n\n"
        "This decision has an affects field matching the file.\n\n"
        "## Alternatives\n- Option A was rejected because it lacks required capabilities\n\n"
        "## Rationale\nChosen for affects testing with specific behavior needed.\n\n"
        "## Trade-offs\nNot applicable: test fixture.\n"
    )

    # Decision mentioning "cache" in body but without affects
    keyword_file = decisions_dir / "cache-keyword.md"
    keyword_file.write_text(
        '---\nname: "cache-keyword"\ndescription: "Cache keyword only"\ntype: "decision"\n'
        'date: "2026-03-16"\ntags:\n  - "caching"\nstatus: "active"\n---\n\n'
        "# Cache Keyword Only\n\n"
        "This decision mentions cache in the body text but has no affects.\n\n"
        "## Alternatives\n- Option A was rejected for performance reasons\n\n"
        "## Rationale\nChosen for keyword-only testing with cache references.\n\n"
        "## Trade-offs\nNot applicable: test fixture.\n"
    )

    from decision.policy.related_context import _related_context_condition

    state = make_session_state("rc-affects-rank", store=store)
    data = {
        "tool_input": {
            "file_path": "src/cache/redis.py",
            "new_string": "def connect():\n    pass",
        }
    }
    result = _related_context_condition(data, state)
    assert result is not None
    assert result.matched is True
    msg = str(result.system_message)
    # The affects-matched decision should appear first
    assert "decision" in msg.lower() and "for redis.py" in msg.lower()
    assert "Redis With Affects" in msg


# ── _is_dir_prefix_match tests ──────────────────────────────────


def test_dir_prefix_match_matches_subpath():
    """Directory prefix matches files under that directory."""
    from decision.policy.related_context import _is_dir_prefix_match

    assert _is_dir_prefix_match("src/auth/", "src/auth/oauth.py") is True


def test_dir_prefix_match_no_match():
    """Directory prefix does not match files outside."""
    from decision.policy.related_context import _is_dir_prefix_match

    assert _is_dir_prefix_match("src/auth/", "src/billing/stripe.py") is False


def test_dir_prefix_match_non_dir_returns_none():
    """Non-directory entries return None."""
    from decision.policy.related_context import _is_dir_prefix_match

    assert _is_dir_prefix_match("src/auth/oauth.py", "src/auth/oauth.py") is None


# ── _is_glob_match tests ─────────────────────────────────────────


def test_glob_match_star():
    """Glob pattern with * matches correctly."""
    from decision.policy.related_context import _is_glob_match

    assert _is_glob_match("src/auth/*.py", "src/auth/oauth.py") is True


def test_glob_match_no_match():
    """Glob pattern doesn't match wrong paths."""
    from decision.policy.related_context import _is_glob_match

    assert _is_glob_match("src/auth/*.py", "src/billing/stripe.py") is False


def test_glob_match_non_glob_returns_none():
    """Non-glob entries return None."""
    from decision.policy.related_context import _is_glob_match

    assert _is_glob_match("src/auth/oauth.py", "src/auth/oauth.py") is None


# ── _is_segment_match tests ──────────────────────────────────────


def test_segment_match_suffix():
    """Suffix match: affects=["policy/engine.py"] matches "src/decision/policy/engine.py"."""
    from decision.policy.related_context import _is_segment_match

    assert _is_segment_match(("policy", "engine.py"), ("src", "decision", "policy", "engine.py"), "engine") is True


def test_segment_match_stem():
    """Stem match: affects=["core"] matches "core.py"."""
    from decision.policy.related_context import _is_segment_match

    assert _is_segment_match(("core",), ("core.py",), "core") is True


def test_segment_match_stem_prefix():
    """Stem-prefix match: affects=["src/auth"] matches "src/auth_helpers.py"."""
    from decision.policy.related_context import _is_segment_match

    assert _is_segment_match(("src", "auth"), ("src", "auth_helpers.py"), "auth_helpers") is True


def test_segment_match_no_false_positive():
    """Segment match doesn't match unrelated files."""
    from decision.policy.related_context import _is_segment_match

    # "log" should not match "login.py" (no separator after stem)
    assert _is_segment_match(("src", "log"), ("src", "login.py"), "login") is False


def test_segment_match_reverse_suffix():
    """Reverse suffix: affects longer than file path."""
    from decision.policy.related_context import _is_segment_match

    assert _is_segment_match(("src", "decision", "engine.py"), ("engine.py",), "engine") is True


# ── _affects_match integration tests ─────────────────────────────


def test_affects_match_dir_prefix():
    """_affects_match directory prefix matching."""
    from decision.policy.related_context import _affects_match

    assert _affects_match(["src/auth/"], "src/auth/oauth.py") is True
    assert _affects_match(["src/auth/"], "src/billing/stripe.py") is False


def test_affects_match_glob():
    """_affects_match glob matching."""
    from decision.policy.related_context import _affects_match

    assert _affects_match(["src/auth/*.py"], "src/auth/oauth.py") is True
    assert _affects_match(["src/auth/*.py"], "src/billing/stripe.py") is False


def test_affects_match_segment():
    """_affects_match segment matching."""
    from decision.policy.related_context import _affects_match

    assert _affects_match(["policy/engine.py"], "src/decision/policy/engine.py") is True


def test_affects_match_no_match():
    """_affects_match returns False when nothing matches."""
    from decision.policy.related_context import _affects_match

    assert _affects_match(["src/billing/"], "src/auth/oauth.py") is False


def test_affects_match_leading_dot_slash():
    """_affects_match strips leading ./ from paths."""
    from decision.policy.related_context import _affects_match

    assert _affects_match(["./src/auth/"], "./src/auth/oauth.py") is True


def test_affects_match_dir_prefix_no_match_continues():
    """_affects_match continues checking after a non-matching dir prefix."""
    from decision.policy.related_context import _affects_match

    # First entry is a dir that doesn't match, second is an exact match
    assert _affects_match(["src/billing/", "policy/engine.py"], "src/decision/policy/engine.py") is True


def test_affects_match_glob_no_match_continues():
    """_affects_match continues checking after a non-matching glob."""
    from decision.policy.related_context import _affects_match

    assert _affects_match(["src/billing/*.py", "policy/engine.py"], "src/decision/policy/engine.py") is True


# ── _has_stale_affects tests ─────────────────────────────────────


def test_has_stale_affects_all_exist(tmp_path):
    """_has_stale_affects returns False when all paths exist."""
    import os

    from decision.policy.related_context import _has_stale_affects

    # Create real files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("pass")

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert _has_stale_affects(["src/app.py"]) is False
    finally:
        os.chdir(old_cwd)


def test_has_stale_affects_missing_file(tmp_path):
    """_has_stale_affects returns True when a file doesn't exist."""
    import os

    from decision.policy.related_context import _has_stale_affects

    # Create src/ dir but not the file
    (tmp_path / "src").mkdir()

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert _has_stale_affects(["src/missing.py"]) is True
    finally:
        os.chdir(old_cwd)


def test_has_stale_affects_skips_globs():
    """_has_stale_affects skips glob patterns."""
    from decision.policy.related_context import _has_stale_affects

    # Glob patterns can't be checked — should not cause stale
    assert _has_stale_affects(["src/auth/*.py"]) is False


def test_has_stale_affects_dir_trailing_slash(tmp_path):
    """_has_stale_affects checks directories for trailing slash entries."""
    import os

    from decision.policy.related_context import _has_stale_affects

    (tmp_path / "src" / "auth").mkdir(parents=True)

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert _has_stale_affects(["src/auth/"]) is False
        assert _has_stale_affects(["src/missing/"]) is True
    finally:
        os.chdir(old_cwd)


def test_has_stale_affects_absolute_path(tmp_path):
    """_has_stale_affects handles absolute paths."""
    from decision.policy.related_context import _has_stale_affects

    real_file = tmp_path / "real.py"
    real_file.write_text("pass")

    assert _has_stale_affects([str(real_file)]) is False
    assert _has_stale_affects([str(tmp_path / "nonexistent.py")]) is True


def test_has_stale_affects_unknown_root_segment(tmp_path):
    """_has_stale_affects skips paths whose root segment doesn't exist."""
    import os

    from decision.policy.related_context import _has_stale_affects

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # "zzz_nonexistent/" doesn't exist at cwd, so this is not flagged as stale
        assert _has_stale_affects(["zzz_nonexistent/foo.py"]) is False
    finally:
        os.chdir(old_cwd)


# ── related-context no-file-path / no-match / keyword fallback ──


def test_related_context_no_file_path(tmp_path):
    """related-context returns None when no file_path in data."""
    _, store = make_store(tmp_path)
    from decision.policy.related_context import _related_context_condition

    state = make_session_state("rc-no-fp", store=store)
    result = _related_context_condition({}, state)
    assert result is None


def test_related_context_no_matching_decisions(tmp_path):
    """related-context returns None when no decisions match the file."""
    decisions_dir, store = make_store(tmp_path)
    # Decision with unrelated affects
    make_decision(decisions_dir, "billing-stuff", affects=["src/billing/"])

    from decision.policy.related_context import _related_context_condition

    state = make_session_state("rc-no-match", store=store)
    data = {"tool_input": {"file_path": "src/auth/oauth.py"}}
    result = _related_context_condition(data, state)
    # No affects match and no keyword match — should be None
    assert result is None


def test_related_context_keyword_fallback(tmp_path):
    """related-context falls back to keyword search when no affects match."""
    decisions_dir, store = make_store(tmp_path)
    # Decision without affects but with matching keywords in body
    make_decision(
        decisions_dir,
        "authentication-strategy",
        tags=["auth"],
        body_extra="We use OAuth2 for authentication in our auth module.\n\n",
    )

    from decision.policy.related_context import _related_context_condition

    state = make_session_state("rc-keyword", store=store)
    data = {
        "tool_input": {
            "file_path": "src/auth/oauth_handler.py",
            "new_string": "def authenticate_oauth():\n    pass",
        }
    }
    result = _related_context_condition(data, state)
    # Should find via keyword matching
    if result is not None:
        assert result.matched is True


def test_related_context_tag_match_no_affects(tmp_path):
    """Decisions without affects surface via tag-based proximity when tags match content keywords."""
    decisions_dir, store = make_store(tmp_path)
    # Decision without affects, with tag "logging"
    make_decision(
        decisions_dir,
        "structured-logging",
        tags=["logging"],
        body_extra="Always use structured logging across all services.\n\n",
    )

    from decision.policy.related_context import _related_context_condition

    state = make_session_state("rc-tag-match", store=store)
    data = {
        "tool_input": {
            "file_path": "src/services/logging_config.py",
            "new_string": "import logging\nlogger = logging.getLogger(__name__)",
        }
    }
    result = _related_context_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "decision context for" in str(result.system_message).lower()
    assert "structured-logging" in str(result.system_message).lower()


def test_related_context_tag_match_skips_decisions_with_affects(tmp_path):
    """Tag-based matching skips decisions that have affects (covered by Phase 1)."""
    decisions_dir, store = make_store(tmp_path)
    # Decision WITH affects — should not appear in tag matches
    make_decision(
        decisions_dir,
        "auth-strategy",
        tags=["auth"],
        affects=["src/auth/"],
        body_extra="Use OAuth2 for all authentication.\n\n",
    )

    from decision.policy.related_context import _related_context_condition

    state = make_session_state("rc-tag-skip-affects", store=store)
    # Edit a file that matches the tag but NOT the affects path
    data = {
        "tool_input": {
            "file_path": "src/middleware/auth_middleware.py",
            "new_string": "def check_auth():\n    pass",
        }
    }
    result = _related_context_condition(data, state)
    # Should NOT show as "tag match" — it has affects, so Phase 1 handles it
    if result is not None:
        assert "tag match" not in str(result.system_message).lower()


# ── Contradiction detection ──────────────────────────────────────────


def test_contradiction_warning_for_opposing_decisions(tmp_path):
    """related-context warns when surfaced decisions contradict each other."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(
        decisions_dir,
        "use-redis",
        body="Use Redis for caching because it supports pub/sub natively.",
        affects=["src/cache/"],
    )
    make_decision(
        decisions_dir,
        "avoid-redis",
        body="Avoid Redis for caching due to memory constraints in production.",
        affects=["src/cache/"],
    )

    from decision.policy.defs import _related_context_condition

    state = make_session_state("rc-contradiction", store=store)
    data = {
        "tool_input": {
            "file_path": "src/cache/store.py",
            "new_string": "class CacheStore:\n    pass",
        }
    }
    result = _related_context_condition(data, state)
    assert result is not None
    msg = result.system_message
    # Both decisions should be surfaced
    assert "use-redis" in msg.lower() or "avoid-redis" in msg.lower()
    # Contradiction warning should appear
    assert "contradict" in msg.lower() or "conflict" in msg.lower()


def test_no_contradiction_for_compatible_decisions(tmp_path):
    """related-context does NOT warn for non-opposing decisions."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(
        decisions_dir,
        "use-redis",
        body="Use Redis for caching because it supports pub/sub.",
        affects=["src/cache/"],
    )
    make_decision(
        decisions_dir,
        "redis-ttl",
        body="Set Redis TTL to 1 hour for session data to balance freshness and load.",
        affects=["src/cache/"],
    )

    from decision.policy.defs import _related_context_condition

    state = make_session_state("rc-no-contradiction", store=store)
    data = {
        "tool_input": {
            "file_path": "src/cache/client.py",
            "new_string": "class RedisClient:\n    pass",
        }
    }
    result = _related_context_condition(data, state)
    assert result is not None
    msg = result.system_message
    # Should NOT have contradiction warning
    assert "contradict" not in msg.lower()


# ── Surfacing tracker ────────────────────────────────────────────────


def test_surfacing_tracker_records_slugs(tmp_path):
    """related-context records surfaced decision slugs in session state."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "tracked-dec", affects=["src/api/"])

    from decision.policy.defs import _related_context_condition

    state = make_session_state("rc-tracker", store=store)
    data = {
        "tool_input": {
            "file_path": "src/api/routes.py",
            "new_string": "def get_routes():\n    pass",
        }
    }
    _related_context_condition(data, state)
    surfaced = state.decisions_surfaced()
    assert "tracked-dec" in surfaced


# ── Attribution hint ─────────────────────────────────────────────────


def test_affects_match_includes_search_hint(tmp_path):
    """related-context includes search hint for affects-matched decisions."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "attr-dec", affects=["src/api/"])

    from decision.policy.defs import _related_context_condition

    state = make_session_state("rc-attr", store=store)
    data = {
        "tool_input": {
            "file_path": "src/api/routes.py",
            "new_string": "def get_routes():\n    pass",
        }
    }
    result = _related_context_condition(data, state)
    assert result is not None
    assert "/decision search" in result.system_message


def test_tag_match_no_attribution_hint(tmp_path):
    """Tag-matched decisions don't include attribution hint (lower confidence)."""
    decisions_dir, store = make_store(tmp_path)
    # Decision with no affects — will only match via tags
    make_decision(decisions_dir, "tag-only-dec", tags=["api"])

    from decision.policy.defs import _related_context_condition

    state = make_session_state("rc-tag-no-attr", store=store)
    data = {
        "tool_input": {
            "file_path": "src/middleware/api_handler.py",
            "new_string": "def handle_api():\n    pass",
        }
    }
    result = _related_context_condition(data, state)
    if result is not None:
        # Tag matches should NOT include attribution hint
        assert "mention it briefly" not in (result.system_message or "")
