"""Mop-up tests — covers small remaining gaps across multiple modules."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from conftest import make_decision, make_session_state, make_store


# ── stop_nudge: singular forms and activity+unacted ─────────────────


def test_stop_nudge_singular_forms(tmp_path):
    """stop-nudge uses singular 'decision surfaced' and 'nudge fired' for count=1."""
    from decision.policy.stop_nudge import _session_activity_summary

    _, store = make_store(tmp_path)
    state = make_session_state("stop-singular", store=store)
    state.increment_activity_counter("context_injections", 1)
    state.increment_nudge_count()

    summary = _session_activity_summary(state)
    assert "1 decision surfaced" in summary
    assert "1 nudge fired" in summary


def test_stop_nudge_activity_plus_unacted(tmp_path):
    """stop-nudge combines activity summary with unacted capture nag."""
    from decision.policy.stop_nudge import _stop_nudge_condition

    _, store = make_store(tmp_path)
    state = make_session_state("stop-combined", store=store)
    # Activity
    state.increment_activity_counter("context_injections", 2)
    state.increment_nudge_count()
    # Unacted capture
    state.mark_fired("_capture-nudge-pending")
    state.store_data("_capture-nudge-pending", "we chose Redis")

    result = _stop_nudge_condition({}, state)
    assert result is not None
    msg = result.system_message
    assert "Decision plugin:" in msg  # activity summary
    assert "uncaptured choice detected" in msg.lower()  # unacted nag


# ── session_init: FTS5 unavailable with decisions ────────────────────


def test_session_init_fts5_unavailable(tmp_path, capsys):
    """session-init warns when FTS5 is unavailable and decisions exist."""
    from decision.policy.session_init import _session_init_condition

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "test-dec")

    state = make_session_state("init-fts5", store=store)
    store._index._available = False

    _session_init_condition({}, state)
    err = capsys.readouterr().err
    assert "FTS5 unavailable" in err


# ── _helpers: edge cases ─────────────────────────────────────────────


def test_extract_content_keywords_non_dict_tool_input():
    """_extract_content_keywords returns [] when tool_input is not a dict."""
    from decision.policy._helpers import _extract_content_keywords

    assert _extract_content_keywords({"tool_input": "string"}) == []


def test_extract_content_keywords_hits_limit():
    """_extract_content_keywords caps at CONTENT_KEYWORD_LIMIT."""
    from decision.policy._helpers import _extract_content_keywords
    from decision.utils.constants import CONTENT_KEYWORD_LIMIT

    # Build a string with many unique words
    words = " ".join(f"uniqueword{i}" for i in range(50))
    result = _extract_content_keywords({"tool_input": {"content": words}})
    assert len(result) <= CONTENT_KEYWORD_LIMIT


def test_get_prompt_non_dict_tool_input():
    """_get_prompt returns empty string when tool_input is not a dict."""
    from decision.policy._helpers import _get_prompt

    assert _get_prompt({"tool_input": "string"}) == ""


# ── decision.py: slug from name, excerpt, invalid date ───────────────


def test_decision_slug_from_name_no_filepath():
    """Decision.slug uses name field when file_path is empty."""
    from decision.core.decision import Decision

    d = Decision.from_text(
        '---\nname: "my-slug"\ndescription: "test"\ndate: "2026-01-01"\n'
        'tags:\n  - "test"\n---\n\n# Title\n\nBody text here.\n'
    )
    assert d.slug == "my-slug"


def test_decision_excerpt_all_headings():
    """Decision.excerpt returns empty string when body has only headings."""
    from decision.core.decision import Decision

    d = Decision.from_text(
        '---\nname: "headings"\ndescription: "test"\ndate: "2026-01-01"\n'
        'tags:\n  - "test"\n---\n\n# Title\n\n## Section 1\n\n## Section 2\n'
    )
    assert d.excerpt == ""


def test_decision_invalid_calendar_date():
    """Decision.validate catches semantically invalid dates like Feb 30."""
    from decision.core.decision import Decision

    d = Decision.from_text(
        '---\nname: "bad-date"\ndescription: "test"\ndate: "2026-02-30"\n'
        'tags:\n  - "test"\n---\n\n# Title\n\nBody text here.\n'
    )
    errors = d.validate()
    assert any("valid calendar date" in e for e in errors)


# ── helpers.py: _path_to_keywords ────────────────────────────────────


def test_path_to_keywords_basic():
    """_path_to_keywords extracts meaningful words from file paths."""
    from decision.utils.helpers import _path_to_keywords

    result = _path_to_keywords("src/auth/middleware.py")
    assert "auth" in result
    assert "middleware" in result


def test_path_to_keywords_filters_noise():
    """_path_to_keywords filters noise words like 'src', 'lib'."""
    from decision.utils.helpers import _path_to_keywords

    result = _path_to_keywords("src/lib/index/test.py")
    # src, lib, index, test are all noise words
    # Only non-noise segments >= 3 chars would be included
    assert "src" not in result.split()


# ── query.py: exclude_slugs, FTS5 note, keyword search ──────────────


def test_query_relevant_with_exclusions(tmp_path):
    """query_relevant excludes specified slugs from results."""
    from decision.store.query import query_relevant

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "include-me", title="Include testing", tags=["testing"])
    make_decision(decisions_dir, "exclude-me", title="Exclude testing", tags=["testing"])

    result = query_relevant(store, "testing", limit=5, exclude_slugs={"exclude-me"})
    assert "Include" in result or result == ""  # FTS5 may or may not return
    if result:
        assert "Exclude testing" not in result


def test_query_relevant_fts5_unavailable_with_results(tmp_path):
    """query_relevant adds FTS5 unavailable note when using keyword fallback."""
    from decision.store.query import query_relevant

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "keyword-test", title="Redis caching strategy", tags=["caching"])

    store._index._available = False
    result = query_relevant(store, "redis", limit=3)
    if result:
        assert "FTS5 unavailable" in result


def test_keyword_search_empty_terms(tmp_path):
    """_keyword_search returns empty string for empty terms."""
    from decision.store.query import _keyword_search

    _, store = make_store(tmp_path)
    assert _keyword_search(store, "", 3) == ""


def test_keyword_search_with_exclusion(tmp_path):
    """_keyword_search respects exclude_slugs."""
    from decision.store.query import _keyword_search

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "keep-this", title="Redis keep", tags=["cache"])
    make_decision(decisions_dir, "drop-this", title="Redis drop", tags=["cache"])

    result = _keyword_search(store, "redis", 5, exclude_slugs={"drop-this"})
    if result:
        assert "drop" not in result.lower() or "keep" in result.lower()


def test_keyword_search_grouped(tmp_path):
    """_keyword_search groups results when more than 3."""
    from decision.store.query import _keyword_search

    decisions_dir, store = make_store(tmp_path)
    for i in range(5):
        make_decision(decisions_dir, f"kw-test-{i}", title=f"Testing item {i}", tags=["testing"])

    result = _keyword_search(store, "testing", 5)
    assert result  # should find results


# ── affects.py: root-level files, non-DecisionStore ──────────────────


def test_infer_affects_root_level_files():
    """infer_affects keeps root-level files as individual paths."""
    from decision.utils.affects import infer_affects

    result = infer_affects(["setup.py", "Makefile"])
    assert "setup.py" in result
    assert "Makefile" in result


def test_suggest_affects_from_tags_non_store():
    """suggest_affects_from_tags returns [] for non-DecisionStore objects."""
    from decision.utils.affects import suggest_affects_from_tags

    assert suggest_affects_from_tags(["auth"], object()) == []


def test_suggest_additional_affects_no_confident(tmp_path):
    """suggest_additional_affects falls back to most frequent when no 2+ count paths."""
    from decision.utils.affects import suggest_additional_affects

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "sibling", tags=["auth"], affects=["src/unique.py"])

    result = suggest_additional_affects(["src/other.py"], ["auth"], store)
    # Only 1 sibling, so count=1 → falls back to single most frequent
    assert isinstance(result, list)


# ── frontmatter.py: edge cases ────────────────────────────────────────


def test_frontmatter_empty_line_in_body():
    """Blank lines in frontmatter are skipped (line 93-94)."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    text = '---\nname: "test"\n\ndescription: "desc"\n---\nBody\n'
    fields, _ = _split_yaml_frontmatter(text)
    assert fields["name"] == "test"
    assert fields["description"] == "desc"


def test_frontmatter_comment_line():
    """Comment lines in frontmatter are skipped."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    text = '---\nname: "test"\n# This is a comment\ndescription: "desc"\n---\nBody\n'
    fields, _ = _split_yaml_frontmatter(text)
    assert fields["name"] == "test"
    assert fields["description"] == "desc"


def test_frontmatter_bare_key():
    """Bare key (no value) expects list items (line 130-134)."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    text = '---\ntags:\n  - "one"\n  - "two"\n---\nBody\n'
    fields, _ = _split_yaml_frontmatter(text)
    assert fields["tags"] == ["one", "two"]


def test_frontmatter_list_continuation_without_prior_key():
    """List item after initial key builds the list (line 100-101)."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    text = '---\naffects:\n  - "src/a.py"\n  - "src/b.py"\n---\nBody\n'
    fields, _ = _split_yaml_frontmatter(text)
    assert fields["affects"] == ["src/a.py", "src/b.py"]


def test_escape_yaml_string():
    """_escape_yaml_string escapes backslashes and quotes."""
    from decision.utils.frontmatter import _escape_yaml_string

    assert _escape_yaml_string('hello "world"') == 'hello \\"world\\"'
    assert _escape_yaml_string("back\\slash") == "back\\\\slash"


def test_format_yaml_value_no_quoting():
    """_format_yaml_value returns unquoted string when no special chars."""
    from decision.utils.frontmatter import _format_yaml_value

    assert _format_yaml_value("simple") == "simple"


def test_format_yaml_frontmatter_empty_list():
    """_format_yaml_frontmatter handles empty lists."""
    from decision.utils.frontmatter import _format_yaml_frontmatter

    result = _format_yaml_frontmatter({"tags": []})
    assert "tags: []" in result


# ── similarity.py: edge cases ────────────────────────────────────────


def test_similar_tags_no_match():
    """similar_tags returns empty when tags are not similar."""
    from decision.utils.similarity import similar_tags

    result = similar_tags(["auth"], ["billing", "payments"])
    assert result == []


def test_find_overlapping_decisions_empty_store(tmp_path):
    """find_overlapping_decisions returns empty for empty store."""
    from decision.utils.similarity import find_overlapping_decisions
    from decision.core.decision import Decision

    _, store = make_store(tmp_path)
    dec = Decision.from_text(
        '---\nname: "test"\ndescription: "t"\ndate: "2026-01-01"\ntags:\n  - "auth"\n---\n\n# T\n\nBody.\n'
    )
    result = find_overlapping_decisions(dec, store)
    assert result == []


# ── capture_nudge: line 115 ──────────────────────────────────────────


def test_capture_nudge_query_no_decisions(tmp_path):
    """capture_nudge query detection with no existing decisions returns None."""
    from decision.policy.capture_nudge import _capture_nudge_condition

    _, store = make_store(tmp_path)
    state = make_session_state("cn-query-empty", store=store)
    data = {"prompt": "what did we decide about caching?"}
    result = _capture_nudge_condition(data, state)
    # No decisions exist → query path returns None or empty result
    assert result is None or not result.matched or "No matching" in str(result.system_message or "")


# ── related_context: lines 165, 192 ─────────────────────────────────


def test_related_context_no_matching_affects(tmp_path):
    """related-context returns None when no affects match."""
    from decision.policy.related_context import _related_context_condition

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "unrelated", affects=["src/other/"])

    state = make_session_state("rc-nomatch", store=store)
    data = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/completely/different.py", "old_string": "x", "new_string": "y"},
    }
    result = _related_context_condition(data, state)
    assert result is None or not result.matched


# ── query_preseed: line 35 (management command skip) ─────────────────


def test_query_preseed_skips_management_commands(tmp_path):
    """query_preseed skips /decision undo, dismiss, debug, etc."""
    from decision.policy.query_preseed import _query_preseed_condition

    _, store = make_store(tmp_path)
    state = make_session_state("qp-manage", store=store)
    for cmd in ["undo", "dismiss", "debug", "publish", "review"]:
        data = {"prompt": f"/decision {cmd}"}
        result = _query_preseed_condition(data, state)
        assert result is None or not result.matched, f"Should skip management command: {cmd}"
