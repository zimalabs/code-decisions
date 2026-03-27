"""Edit validation policy tests — malformed detection, valid passthrough."""

from conftest import make_session_state


# ── edit-validation tests ──────────────────────────────────────────


def test_edit_validation_warns_on_malformed(tmp_path):
    """edit-validation warns when an edit leaves a decision file malformed."""
    from decision.policy.defs import _edit_validation_condition

    # Write a malformed decision file in a decisions/ directory
    decisions_dir = tmp_path / "decisions"
    decisions_dir.mkdir(exist_ok=True)
    (decisions_dir / "broken.md").write_text("Still no frontmatter here\nJust text\n")

    state = make_session_state("ev-malformed")
    data = {
        "tool_input": {
            "file_path": str(decisions_dir / "broken.md"),
            "old_string": "No frontmatter",
            "new_string": "Still no frontmatter",
        }
    }
    result = _edit_validation_condition(data, state)
    assert result is not None
    assert result.matched is True
    assert "malformed" in str(result.system_message)


def test_edit_validation_silent_on_valid(tmp_path):
    """edit-validation returns None when the decision file is still valid."""
    from decision.policy.defs import _edit_validation_condition

    dec_dir = tmp_path / "decisions"
    dec_dir.mkdir(exist_ok=True)
    valid_file = dec_dir / "good.md"
    valid_file.write_text(
        '---\nname: "good"\ndescription: "A good decision"\ntype: "decision"\n'
        'date: "2026-03-17"\ntags:\n  - "testing"\n---\n\n'
        "# Good Decision\n\nThis is a valid decision with sufficient rationale.\n\n"
        "## Alternatives\n"
        "- Option A was considered but rejected because it lacks the required capabilities for this use case\n\n"
        "## Rationale\n"
        "Chosen for testing purposes because it provides the specific behavior we need for validation.\n\n"
        "## Trade-offs\n"
        "Not applicable: test fixture with no real-world trade-offs.\n"
    )

    state = make_session_state("ev-valid")
    data = {
        "tool_input": {
            "file_path": str(valid_file),
            "old_string": "old",
            "new_string": "new",
        }
    }
    result = _edit_validation_condition(data, state)
    assert result is None


def test_edit_validation_skips_non_decision(tmp_path):
    """edit-validation ignores non-decision file paths."""
    from decision.policy.defs import _edit_validation_condition

    state = make_session_state("ev-skip")
    data = {
        "tool_input": {
            "file_path": "src/main.py",
            "old_string": "x",
            "new_string": "y",
        }
    }
    result = _edit_validation_condition(data, state)
    assert result is None


def test_edit_validation_skips_nonexistent_file():
    """edit-validation returns None when the file doesn't exist."""
    from decision.policy.edit_validation import _edit_validation_condition

    state = make_session_state("ev-nofile")
    data = {
        "tool_input": {
            "file_path": "/nonexistent/decisions/missing.md",
        }
    }
    result = _edit_validation_condition(data, state)
    assert result is None


def test_edit_validation_skips_unreadable_file(tmp_path):
    """edit-validation returns None when file can't be read."""
    from unittest.mock import patch
    from decision.policy.edit_validation import _edit_validation_condition

    dec_dir = tmp_path / "decisions"
    dec_dir.mkdir()
    f = dec_dir / "unreadable.md"
    f.write_text("---\nname: test\n---\n# Test\n\nBody.\n")

    state = make_session_state("ev-unreadable")
    data = {"tool_input": {"file_path": str(f)}}

    with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
        result = _edit_validation_condition(data, state)
    assert result is None
