#!/usr/bin/env python3
"""Sync skip patterns from constants.py into dispatch.sh.

Reads SKIP_FILE_PATTERNS from Python, rewrites the marked region in
dispatch.sh so the bash fast-path stays in sync automatically.

Run: python scripts/sync_skip_patterns.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DISPATCH = ROOT / "src" / "hooks" / "dispatch.sh"

sys.path.insert(0, str(ROOT / "src"))
from decision.utils.constants import SKIP_FILE_PATTERNS  # noqa: E402


def _format_bash_patterns(patterns: tuple[str, ...]) -> str:
    """Format patterns as a bash `for pat in ...` line with continuation."""
    # Split into two lines for readability (~80 chars each)
    items = list(patterns)
    mid = len(items) // 2
    line1 = " ".join(items[:mid])
    line2 = " ".join(items[mid:])
    return (
        f"        for pat in {line1} \\\n"
        f"                   {line2}; do"
    )


def main() -> None:
    text = DISPATCH.read_text()

    # Replace between BEGIN/END markers
    pattern = re.compile(
        r"(# BEGIN SKIP_PATTERNS[^\n]*\n)"
        r".*?"
        r"(# END SKIP_PATTERNS)",
        re.DOTALL,
    )

    replacement = (
        r"\1"
        "        _skip=false\n"
        + _format_bash_patterns(SKIP_FILE_PATTERNS)
        + "\n"
        + r"        \2"
    )

    new_text, count = pattern.subn(replacement, text)
    if count == 0:
        print("ERROR: Could not find BEGIN/END SKIP_PATTERNS markers in dispatch.sh", file=sys.stderr)
        sys.exit(1)

    if new_text == text:
        print("Skip patterns already in sync.")
    else:
        DISPATCH.write_text(new_text)
        print(f"Updated dispatch.sh with {len(SKIP_FILE_PATTERNS)} skip patterns.")


if __name__ == "__main__":
    main()
