"""Tests for DecisionStore.validate_all() and the validate CLI command."""

from conftest import make_decision, make_store


def test_validate_all_returns_valid_decisions(tmp_path):
    """validate_all returns all valid decisions with no errors."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "good-one")
    make_decision(decisions_dir, "good-two")

    valid, errors = store.validate_all()
    assert len(valid) == 2
    assert len(errors) == 0


def test_validate_all_catches_missing_frontmatter(tmp_path):
    """validate_all reports files without YAML frontmatter."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "good-one")
    # Write a broken file with no frontmatter
    (decisions_dir / "broken.md").write_text("# No frontmatter\n\nJust text.\n")

    valid, errors = store.validate_all()
    assert len(valid) == 1
    assert any(f == "broken.md" for f, _ in errors)


def test_validate_all_catches_missing_name(tmp_path):
    """validate_all reports decisions with missing name field."""
    decisions_dir, store = make_store(tmp_path)
    (decisions_dir / "no-name.md").write_text(
        '---\ndescription: "test"\ndate: "2026-01-01"\ntags:\n  - "t"\n---\n\n'
        "# Title\n\nSome explanation of the decision.\n"
    )

    valid, errors = store.validate_all()
    assert len(valid) == 0
    assert any("name" in err for _, err in errors)


def test_validate_all_catches_absolute_affects(tmp_path):
    """validate_all reports decisions with absolute paths in affects."""
    decisions_dir, store = make_store(tmp_path)
    (decisions_dir / "abs-path.md").write_text(
        '---\nname: "abs-path"\ndescription: "test"\ndate: "2026-01-01"\n'
        'tags:\n  - "t"\naffects:\n  - "/etc/passwd"\n---\n\n'
        "# Absolute Path\n\nDecision with absolute affects path.\n"
    )

    valid, errors = store.validate_all()
    assert len(valid) == 0
    assert any("absolute" in err for _, err in errors)


def test_validate_all_empty_dir(tmp_path):
    """validate_all on empty dir returns empty lists."""
    _, store = make_store(tmp_path)
    valid, errors = store.validate_all()
    assert valid == []
    assert errors == []


def test_validate_all_nonexistent_dir(tmp_path):
    """validate_all on nonexistent dir returns empty lists."""
    import decision

    store = decision.DecisionStore(str(tmp_path / "nonexistent"), db_dir=str(tmp_path / "db"))
    valid, errors = store.validate_all()
    assert valid == []
    assert errors == []


def test_validate_cli_clean(tmp_path, capsys):
    """validate CLI command prints success on clean files."""
    from unittest.mock import patch

    from decision.cli import _cmd_validate
    from decision.store import DecisionStore

    decisions_dir, _ = make_store(tmp_path)
    make_decision(decisions_dir, "good-one")

    with patch("decision.store.store.DecisionStore.validate_all", return_value=(["fake"], [])):
        with patch("decision.store.store.DecisionStore.__init__", return_value=None):
            _cmd_validate(type("Args", (), {})())

    out = capsys.readouterr().out
    assert "valid" in out.lower()


def test_validate_cli_errors(tmp_path, capsys):
    """validate CLI command exits 1 on errors."""
    from unittest.mock import patch

    import pytest

    from decision.cli import _cmd_validate

    with patch(
        "decision.store.store.DecisionStore.validate_all",
        return_value=([], [("broken.md", "missing name field")]),
    ):
        with patch("decision.store.store.DecisionStore.__init__", return_value=None):
            with pytest.raises(SystemExit, match="1"):
                _cmd_validate(type("Args", (), {})())

    out = capsys.readouterr().out
    assert "broken.md" in out
