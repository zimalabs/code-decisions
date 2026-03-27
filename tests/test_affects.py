"""Tests for smart affects inference from session edits."""

from conftest import make_decision, make_store
from decision.utils.affects import infer_affects, suggest_additional_affects


def test_groups_files_by_directory():
    """Multiple files in same dir → directory prefix."""
    files = ["src/auth/oauth.py", "src/auth/jwt.py", "src/auth/middleware.py"]
    result = infer_affects(files)
    assert result == ["src/auth/"]


def test_singleton_stays_specific():
    """Single file in a dir stays as specific path."""
    files = ["src/billing/refunds.py"]
    result = infer_affects(files)
    assert result == ["src/billing/refunds.py"]


def test_mixed_grouping():
    """Mix of grouped dirs and singleton files."""
    files = [
        "src/auth/oauth.py",
        "src/auth/jwt.py",
        "src/billing/refunds.py",
    ]
    result = infer_affects(files)
    assert "src/auth/" in result
    assert "src/billing/refunds.py" in result
    assert len(result) == 2


def test_filters_test_files():
    """Test files are excluded."""
    files = ["src/auth/oauth.py", "tests/test_auth.py"]
    result = infer_affects(files)
    assert result == ["src/auth/oauth.py"]
    assert not any("test" in r for r in result)


def test_filters_markdown():
    """Markdown files are excluded."""
    files = ["src/auth/oauth.py", "README.md", "CLAUDE.md"]
    result = infer_affects(files)
    assert result == ["src/auth/oauth.py"]


def test_filters_config():
    """Config files are excluded."""
    files = ["src/auth/oauth.py", "config.json", "settings.yaml"]
    result = infer_affects(files)
    assert result == ["src/auth/oauth.py"]


def test_caps_at_max():
    """Result capped at 5 entries."""
    files = [f"src/mod{i}/file.py" for i in range(10)]
    result = infer_affects(files)
    assert len(result) <= 5


def test_empty_input():
    """Empty input returns empty list."""
    assert infer_affects([]) == []


def test_all_noise():
    """All noise files returns empty list."""
    files = ["tests/test_foo.py", "README.md", "config.json"]
    result = infer_affects(files)
    assert result == []


def test_normalizes_leading_dot_slash():
    """Leading ./ is stripped."""
    files = ["./src/auth/oauth.py", "./src/auth/jwt.py"]
    result = infer_affects(files)
    assert result == ["src/auth/"]


def test_root_level_files_stay_individual():
    """Files at root level stay as individual paths."""
    files = ["main.py", "setup.py"]
    result = infer_affects(files)
    assert "main.py" in result
    assert "setup.py" in result


def test_dir_with_more_files_sorted_first():
    """Directories with more files are prioritized."""
    files = [
        "src/auth/a.py",
        "src/auth/b.py",
        "src/auth/c.py",
        "src/billing/x.py",
        "src/billing/y.py",
    ]
    result = infer_affects(files)
    assert result[0] == "src/auth/"
    assert result[1] == "src/billing/"


# ── suggest_additional_affects tests ──────────────────────────────


def test_suggest_additional_from_sibling_decisions(tmp_path):
    """Suggests affects from decisions with shared tags that this decision doesn't have."""
    decisions_dir, store = make_store(tmp_path)
    # Two existing decisions tagged "auth" that both affect src/middleware/
    make_decision(decisions_dir, "auth-jwt", tags=["auth"], affects=["src/auth/", "src/middleware/"])
    make_decision(decisions_dir, "auth-sessions", tags=["auth"], affects=["src/auth/", "src/middleware/"])

    # New decision tagged "auth" that only has src/auth/
    additional = suggest_additional_affects(["src/auth/"], ["auth"], store)
    assert "src/middleware/" in additional


def test_suggest_additional_skips_existing(tmp_path):
    """Does not suggest paths already in the decision's affects."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "perf-1", tags=["performance"], affects=["src/cache/", "src/db/"])
    make_decision(decisions_dir, "perf-2", tags=["performance"], affects=["src/cache/", "src/db/"])

    # Already has both paths — nothing to suggest
    additional = suggest_additional_affects(["src/cache/", "src/db/"], ["performance"], store)
    assert additional == []


def test_suggest_additional_skips_covered_by_dir_prefix(tmp_path):
    """Does not suggest specific files if a directory prefix already covers them."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "auth-1", tags=["auth"], affects=["src/auth/handler.py"])
    make_decision(decisions_dir, "auth-2", tags=["auth"], affects=["src/auth/handler.py"])

    # Existing affects has the directory prefix — specific file is already covered
    additional = suggest_additional_affects(["src/auth/"], ["auth"], store)
    assert "src/auth/handler.py" not in additional


def test_suggest_additional_no_shared_tags(tmp_path):
    """Returns empty when no decisions share tags."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "billing-1", tags=["billing"], affects=["src/billing/"])

    additional = suggest_additional_affects(["src/auth/"], ["auth"], store)
    assert additional == []


def test_suggest_additional_empty_tags(tmp_path):
    """Returns empty when no tags provided."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "test-1", tags=["test"], affects=["src/test/"])

    additional = suggest_additional_affects(["src/auth/"], [], store)
    assert additional == []
