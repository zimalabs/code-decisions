"""Tests for contradiction detection utilities."""

from decision.utils.contradiction import (
    _extract_subjects,
    _subjects_overlap,
    detect_pairwise,
    find_contradictions,
)


# ── _extract_subjects tests ──────────────────────────────────────────


def test_extract_subjects_basic():
    subjects = _extract_subjects("We use Redis for caching.", "use")
    assert len(subjects) == 1
    assert "redis for caching" in subjects[0]


def test_extract_subjects_avoid():
    subjects = _extract_subjects("Avoid polling in the event loop.", "avoid")
    assert len(subjects) == 1
    assert "polling" in subjects[0]


def test_extract_subjects_case_insensitive():
    subjects = _extract_subjects("Always validate input at boundaries.", "always")
    assert len(subjects) >= 1


def test_extract_subjects_no_match():
    subjects = _extract_subjects("This has no verbs of interest.", "use")
    assert subjects == []


# ── _subjects_overlap tests ──────────────────────────────────────────


def test_subjects_overlap_exact():
    assert _subjects_overlap(["redis"], ["redis"])


def test_subjects_overlap_word_overlap():
    assert _subjects_overlap(["redis for caching"], ["redis for sessions"])


def test_subjects_overlap_no_match():
    assert not _subjects_overlap(["redis"], ["postgres"])


# ── find_contradictions tests ────────────────────────────────────────


def test_no_affects_overlap_returns_zero():
    """Decisions about different areas can't contradict."""
    score = find_contradictions(
        "Use Redis for caching.",
        "Avoid Redis for sessions.",
        ["src/cache/"],
        ["src/auth/"],
    )
    assert score == 0.0


def test_opposing_language_with_affects_overlap():
    """Decisions with overlapping affects and opposing verbs score high."""
    score = find_contradictions(
        "Use Redis for caching because it supports pub/sub.",
        "Avoid Redis for caching due to memory constraints.",
        ["src/cache/"],
        ["src/cache/"],
    )
    assert score >= 0.5


def test_non_opposing_language_scores_zero():
    """Decisions with overlapping affects but no opposing language score zero."""
    score = find_contradictions(
        "Use Redis for caching.",
        "Use Memcached for session storage.",
        ["src/cache/"],
        ["src/cache/"],
    )
    assert score == 0.0


def test_always_vs_never():
    score = find_contradictions(
        "Always validate input at the API boundary.",
        "Never validate input at the API boundary — trust internal callers.",
        ["src/api/"],
        ["src/api/"],
    )
    assert score >= 0.5


def test_prefer_vs_reject():
    score = find_contradictions(
        "Prefer server-side rendering for initial load.",
        "Reject server-side rendering — use client-only.",
        ["src/web/"],
        ["src/web/"],
    )
    assert score >= 0.5


def test_directory_containment_counts_as_overlap():
    """src/auth/ overlaps with src/auth/handler.py."""
    score = find_contradictions(
        "Use JWT tokens for auth.",
        "Avoid JWT tokens for auth.",
        ["src/auth/"],
        ["src/auth/handler.py"],
    )
    assert score >= 0.5


# ── detect_pairwise tests ───────────────────────────────────────────


def test_detect_pairwise_finds_conflicts():
    decisions = [
        ("dec-a", "Use Redis for caching.", ["cache"], ["src/cache/"]),
        ("dec-b", "Avoid Redis for caching.", ["cache"], ["src/cache/"]),
        ("dec-c", "Use Postgres for storage.", ["db"], ["src/db/"]),
    ]
    conflicts = detect_pairwise(decisions, threshold=0.5)
    assert len(conflicts) >= 1
    slugs = {(a, b) for a, b, _ in conflicts}
    assert ("dec-a", "dec-b") in slugs


def test_detect_pairwise_no_conflicts():
    decisions = [
        ("dec-a", "Use Redis for caching.", ["cache"], ["src/cache/"]),
        ("dec-b", "Use Postgres for storage.", ["db"], ["src/db/"]),
    ]
    conflicts = detect_pairwise(decisions, threshold=0.5)
    assert conflicts == []


def test_detect_pairwise_sorted_by_score():
    decisions = [
        ("dec-a", "Always use Redis.", ["cache"], ["src/cache/"]),
        ("dec-b", "Never use Redis.", ["cache"], ["src/cache/"]),
        ("dec-c", "Prefer Redis.", ["cache"], ["src/cache/"]),
        ("dec-d", "Reject Redis.", ["cache"], ["src/cache/"]),
    ]
    conflicts = detect_pairwise(decisions, threshold=0.3)
    if len(conflicts) >= 2:
        assert conflicts[0][2] >= conflicts[1][2]  # sorted descending
