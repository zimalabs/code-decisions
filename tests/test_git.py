"""Git utility test suite."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from decision.utils.git import get_repo_root


def test_get_repo_root():
    """get_repo_root returns a Path when inside a git repo."""
    root = get_repo_root()
    # We're running tests from within a git repo
    assert root is not None
    assert isinstance(root, Path)
    assert (root / ".git").exists()


def test_graceful_without_git():
    """Returns None when git is unavailable."""
    with patch("decision.utils.git.subprocess.run", side_effect=OSError("no git")):
        assert get_repo_root() is None


def test_graceful_on_timeout():
    """Returns None on timeout."""
    with patch(
        "decision.utils.git.subprocess.run",
        side_effect=subprocess.TimeoutExpired("git", 5),
    ):
        assert get_repo_root() is None


def test_graceful_on_nonzero_exit():
    """Handles non-zero exit codes gracefully."""
    mock_result = subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="fatal")
    with patch("decision.utils.git.subprocess.run", return_value=mock_result):
        assert get_repo_root() is None
