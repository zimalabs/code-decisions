"""Integration tests — dispatch.sh end-to-end subprocess tests.

Tests the primary user-facing path: shell → Python policy engine → JSON output.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import DISPATCH, PLUGIN_DIR


@pytest.fixture
def dispatch_env(tmp_path):
    """Env dict for subprocess hook tests with isolated session."""
    return {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
        "PYTHONPATH": str(PLUGIN_DIR),
        "CLAUDE_SESSION_ID": f"test-dispatch-{os.getpid()}",
        "HOME": str(tmp_path),  # isolate memory path
    }


def _run_dispatch(event: str, input_data: dict, env: dict, timeout: float = 5.0) -> subprocess.CompletedProcess:
    """Run dispatch.sh with the given event and JSON input."""
    return subprocess.run(
        ["bash", str(DISPATCH), event],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


# ── Basic dispatch ──────────────────────────────────────────────────


def test_dispatch_returns_valid_json(dispatch_env):
    """dispatch.sh returns valid JSON for any event."""
    result = _run_dispatch("PreToolUse", {"tool_name": "Read"}, dispatch_env)
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert isinstance(parsed, dict)


def test_dispatch_session_start(dispatch_env):
    """dispatch.sh handles SessionStart and returns context."""
    result = _run_dispatch("SessionStart", {}, dispatch_env)
    assert result.returncode == 0
    output = result.stdout.strip()
    assert output  # should produce some output
    parsed = json.loads(output)
    assert isinstance(parsed, dict)


def test_dispatch_non_matching_event(dispatch_env):
    """Non-matching event returns empty JSON."""
    result = _run_dispatch("PreToolUse", {"tool_name": "Read"}, dispatch_env)
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert parsed == {}


def test_dispatch_user_prompt_submit(dispatch_env):
    """dispatch.sh handles UserPromptSubmit event."""
    result = _run_dispatch(
        "UserPromptSubmit",
        {"tool_input": {"content": "What does this function do?"}},
        dispatch_env,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert isinstance(parsed, dict)


def test_dispatch_stop_event(dispatch_env):
    """dispatch.sh handles Stop event."""
    result = _run_dispatch("Stop", {}, dispatch_env)
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert isinstance(parsed, dict)


# ── Error handling ──────────────────────────────────────────────────


def test_dispatch_empty_stdin(dispatch_env):
    """dispatch.sh handles empty stdin gracefully."""
    result = subprocess.run(
        ["bash", str(DISPATCH), "PreToolUse"],
        input="",
        capture_output=True,
        text=True,
        env=dispatch_env,
        timeout=5,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert isinstance(parsed, dict)


def test_dispatch_invalid_json_stdin(dispatch_env):
    """dispatch.sh handles invalid JSON stdin gracefully."""
    result = subprocess.run(
        ["bash", str(DISPATCH), "PreToolUse"],
        input="not valid json {{{",
        capture_output=True,
        text=True,
        env=dispatch_env,
        timeout=5,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert isinstance(parsed, dict)


def test_dispatch_missing_plugin_root():
    """dispatch.sh exits 0 with error when CLAUDE_PLUGIN_ROOT is unset."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    result = subprocess.run(
        ["bash", str(DISPATCH), "PreToolUse"],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    assert result.returncode == 0
    assert "not configured" in result.stderr


def test_dispatch_invalid_plugin_root():
    """dispatch.sh exits 0 with error when plugin files not found."""
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": "/nonexistent/path"}
    result = subprocess.run(
        ["bash", str(DISPATCH), "PreToolUse"],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    assert result.returncode == 0
    assert "not found" in result.stderr


# ── Timeout safety ──────────────────────────────────────────────────


def test_dispatch_completes_under_timeout(dispatch_env):
    """dispatch.sh completes well under the 5s hook timeout."""
    import time

    start = time.monotonic()
    result = _run_dispatch("PreToolUse", {"tool_name": "Write"}, dispatch_env)
    elapsed = time.monotonic() - start
    assert result.returncode == 0
    assert elapsed < 5.0, f"dispatch took {elapsed:.1f}s — too slow for 10s hook timeout"


# ── Content validation via dispatch ─────────────────────────────────


def test_dispatch_content_validation_rejects(dispatch_env):
    """Full pipeline: content-validation rejects bad decision via dispatch."""
    data = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/home/user/project/.claude/decisions/bad.md",
            "content": "No frontmatter here\nJust text\n",
        },
    }
    result = _run_dispatch("PreToolUse", data, dispatch_env)
    assert result.returncode == 0
    parsed = json.loads(result.stdout.strip())
    assert parsed.get("ok") is False or parsed.get("decision") == "reject"


# ── Skip-pattern sync ─────────────────────────────────────────────


def test_skip_patterns_in_sync():
    """dispatch.sh skip patterns match SKIP_FILE_PATTERNS in constants.py."""
    from decision.utils.constants import SKIP_FILE_PATTERNS

    # Extract patterns from dispatch.sh
    dispatch_text = DISPATCH.read_text()
    # Match the for loop: "for pat in <patterns>; do"
    m = re.search(r"for pat in (.*?);", dispatch_text, re.DOTALL)
    assert m, "Could not find skip pattern loop in dispatch.sh"
    raw = m.group(1)
    # Split on whitespace (patterns span continuation lines)
    shell_patterns = set(raw.split())
    # Remove line-continuation backslashes
    shell_patterns.discard("\\")

    python_patterns = set(SKIP_FILE_PATTERNS)

    assert shell_patterns == python_patterns, (
        f"Skip patterns out of sync.\n"
        f"  Only in dispatch.sh: {shell_patterns - python_patterns}\n"
        f"  Only in constants.py: {python_patterns - shell_patterns}"
    )


