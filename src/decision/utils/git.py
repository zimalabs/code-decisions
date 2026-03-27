"""Git utility functions — stdlib subprocess, graceful failures."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_repo_root() -> Path | None:
    """Return the git repo root, or None if not in a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None
