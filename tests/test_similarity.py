"""Tests for tag similarity utilities."""

from decision.utils.similarity import _levenshtein, similar_tags


# ── Levenshtein tests ─────────────────────────────────────────────────


def test_levenshtein_identical():
    assert _levenshtein("abc", "abc") == 0


def test_levenshtein_empty():
    assert _levenshtein("", "abc") == 3
    assert _levenshtein("abc", "") == 3
    assert _levenshtein("", "") == 0


def test_levenshtein_single_edit():
    assert _levenshtein("cat", "bat") == 1
    assert _levenshtein("cat", "cats") == 1
    assert _levenshtein("cats", "cat") == 1


def test_levenshtein_multiple_edits():
    assert _levenshtein("kitten", "sitting") == 3


# ── similar_tags tests ────────────────────────────────────────────────


def test_similar_tags_plural():
    """Detects plural variants."""
    matches = similar_tags(["hook"], ["hooks", "auth"])
    assert ("hook", "hooks") in matches


def test_similar_tags_hyphen():
    """Detects hyphen normalization."""
    matches = similar_tags(["precommit"], ["pre-commit", "auth"])
    assert ("precommit", "pre-commit") in matches


def test_similar_tags_containment():
    """Detects prefix/suffix containment."""
    matches = similar_tags(["enforce"], ["enforcement", "auth"])
    assert ("enforce", "enforcement") in matches


def test_similar_tags_edit_distance():
    """Detects near matches by edit distance."""
    matches = similar_tags(["caching"], ["cachng", "database"])
    assert ("caching", "cachng") in matches


def test_similar_tags_exact_match_ignored():
    """Exact match is not flagged."""
    matches = similar_tags(["auth"], ["auth", "hooks"])
    assert len(matches) == 0


def test_similar_tags_empty_existing():
    """No matches when existing tags are empty."""
    matches = similar_tags(["auth"], [])
    assert len(matches) == 0


def test_similar_tags_no_false_positives():
    """Unrelated tags produce no matches."""
    matches = similar_tags(["database"], ["frontend", "hooks", "auth"])
    assert len(matches) == 0


# ── Levenshtein max_dist early-exit ──────────────────────────────────


def test_levenshtein_max_dist_returns_early():
    """max_dist causes early return when distance exceeds threshold."""
    # "abc" vs "xyz" has distance 3
    assert _levenshtein("abc", "xyz", max_dist=1) == 2  # max_dist + 1


def test_levenshtein_max_dist_exact():
    """max_dist equal to actual distance returns the correct value."""
    assert _levenshtein("cat", "bat", max_dist=1) == 1


def test_levenshtein_max_dist_no_effect_when_large():
    """Large max_dist produces same result as no max_dist."""
    assert _levenshtein("kitten", "sitting", max_dist=100) == 3


def test_levenshtein_max_dist_negative_means_unlimited():
    """Negative max_dist (default) means no early exit."""
    assert _levenshtein("kitten", "sitting") == 3
    assert _levenshtein("kitten", "sitting", max_dist=-1) == 3


def test_similar_tags_with_early_exit_same_results():
    """Early exit optimization doesn't change similar_tags results."""
    new = ["caching", "hook", "precommit", "enforce"]
    existing = ["cachng", "hooks", "pre-commit", "enforcement", "database"]
    matches = similar_tags(new, existing)
    # All expected matches should still be found
    assert ("caching", "cachng") in matches
    assert ("hook", "hooks") in matches
    assert ("precommit", "pre-commit") in matches
    assert ("enforce", "enforcement") in matches
