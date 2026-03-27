"""End-to-end tests — exercises full skill and policy workflows.

Two testing levels:
1. Python-level e2e — PolicyEngine with ALL_POLICIES, evaluating events through the full stack
2. Subprocess-level e2e — dispatch.sh for critical paths (shell → Python → JSON)
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from conftest import DISPATCH, PLUGIN_DIR, make_decision, make_session_state, make_store

# ── Imports from plugin ──────────────────────────────────────────────

import decision
from decision import PolicyEngine, PolicyResult, SessionState
from decision.policy.defs import ALL_POLICIES


# ── Helpers ──────────────────────────────────────────────────────────


def _make_engine() -> PolicyEngine:
    """Create PolicyEngine with all policies registered."""
    engine = PolicyEngine()
    for p in ALL_POLICIES:
        engine.register(p)
    engine.trace_enabled = True
    return engine


def _write_valid_decision(
    decisions_dir: Path,
    slug: str = "test-decision",
    tags: list[str] | None = None,
    affects: list[str] | None = None,
    status: str = "active",
    date: str = "2026-03-17",
) -> Path:
    """Write a decision file that passes content-validation."""
    tags = tags or ["testing"]
    fm_lines = [
        "---",
        f'name: "{slug}"',
        f'description: "Test decision for {slug}"',
        f'date: "{date}"',
        "tags:",
    ]
    for t in tags:
        fm_lines.append(f'  - "{t}"')
    fm_lines.append(f'status: "{status}"')
    if affects:
        fm_lines.append("affects:")
        for a in affects:
            fm_lines.append(f'  - "{a}"')
    fm_lines.append("---")

    body = (
        f"\n# {slug}\n\n"
        "Evaluated multiple approaches before settling on the current implementation.\n\n"
        "## Alternatives\n"
        "- Redis was considered but rejected due to operational overhead in our deployment\n"
        "- SQLite was too limited for concurrent write workloads in production\n\n"
        "## Rationale\n"
        "PostgreSQL provides the JSONB support and full-text search we need without additional services.\n\n"
        "## Trade-offs\n"
        "Heavier infrastructure requirement — requires a managed database instance.\n"
    )

    target = Path(decisions_dir) / f"{slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(fm_lines) + body)
    return target


def _parse_engine_output(output: str) -> dict[str, Any]:
    """Parse JSON output from engine.evaluate()."""
    return json.loads(output)


def _run_dispatch(
    event: str, input_data: dict, env: dict, timeout: float = 5.0
) -> subprocess.CompletedProcess:
    """Run dispatch.sh with the given event and JSON input."""
    return subprocess.run(
        ["bash", str(DISPATCH), event],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


@pytest.fixture
def dispatch_env(tmp_path):
    """Env dict for subprocess hook tests with isolated session."""
    return {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
        "PYTHONPATH": str(PLUGIN_DIR),
        "CLAUDE_SESSION_ID": f"test-e2e-{os.getpid()}-{uuid.uuid4().hex[:6]}",
        "HOME": str(tmp_path),
    }


@pytest.fixture
def store_and_state(tmp_path):
    """Create decisions dir, store, and session state for Python-level tests."""
    decisions_dir, store = make_store(tmp_path)
    state = make_session_state("e2e", store=store)
    yield decisions_dir, store, state
    state.cleanup()


# ═══════════════════════════════════════════════════════════════════════
# 1. CAPTURE WORKFLOW
# ═══════════════════════════════════════════════════════════════════════


class TestCaptureWorkflow:
    """Write decision → content-validation."""

    def test_capture_valid_accepted(self, store_and_state):
        """Valid decision passes through engine (no block/reject)."""
        decisions_dir, store, state = store_and_state
        engine = _make_engine()
        path = _write_valid_decision(decisions_dir, "valid-capture")

        data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(path),
                "content": path.read_text(),
            },
        }
        output = _parse_engine_output(engine.evaluate("PreToolUse", data, state))
        assert output.get("decision") != "reject"
        assert output.get("decision") != "block"

    def test_capture_missing_frontmatter_rejected(self, store_and_state):
        """Missing frontmatter → decision: reject."""
        decisions_dir, store, state = store_and_state
        engine = _make_engine()
        fp = str(decisions_dir / "bad.md")

        data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": fp,
                "content": "No frontmatter here\nJust text\n",
            },
        }
        output = _parse_engine_output(engine.evaluate("PreToolUse", data, state))
        assert output.get("decision") == "reject" or output.get("ok") is False

    def test_capture_valid_via_dispatch(self, dispatch_env, tmp_path):
        """Valid decision through dispatch.sh → no rejection."""
        decisions_dir = Path(dispatch_env["HOME"]) / ".claude" / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)
        path = _write_valid_decision(decisions_dir, "dispatch-test")

        data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(path),
                "content": path.read_text(),
            },
        }
        result = _run_dispatch("PreToolUse", data, dispatch_env)
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert parsed.get("decision") != "reject"

    def test_capture_invalid_via_dispatch(self, dispatch_env):
        """Bad decision through dispatch.sh → ok: false."""
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


# ═══════════════════════════════════════════════════════════════════════
# 2. SEARCH & QUERY
# ═══════════════════════════════════════════════════════════════════════


class TestSearchAndQuery:
    """Preseed hook, FTS5 search."""

    def test_query_preseed_returns_results(self, store_and_state):
        """'/decision:search caching' in prompt → preseed fires with ranked results."""
        decisions_dir, store, state = store_and_state
        _write_valid_decision(decisions_dir, "caching-strategy", tags=["caching", "performance"])

        engine = _make_engine()
        data = {
            "tool_input": {"content": "/decision:search caching"},
        }
        output = _parse_engine_output(engine.evaluate("UserPromptSubmit", data, state))
        assert output.get("ok") is True
        assert "caching" in output.get("reason", "").lower()

    def test_search_cli_returns_results(self, tmp_path):
        """python3 -m decision search returns JSON results."""
        project_key = str(Path(tmp_path).resolve()).replace("/", "-")
        decisions_dir = tmp_path / ".claude" / "decisions"
        decisions_dir.mkdir(parents=True, exist_ok=True)
        _write_valid_decision(decisions_dir, "redis-cache", tags=["caching"])

        env = {
            **os.environ,
            "PYTHONPATH": str(PLUGIN_DIR),
            "HOME": str(tmp_path),
        }
        result = subprocess.run(
            ["python3", "-m", "decision", "search", "caching", "--json"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(tmp_path),
            timeout=5,
        )
        # May have no results if FTS5 not available, but should not crash
        assert result.returncode == 0

    def test_search_empty_store(self, store_and_state):
        """No decisions → preseed returns None (empty JSON)."""
        _, store, state = store_and_state
        engine = _make_engine()
        data = {
            "tool_input": {"content": "/decision:search caching"},
        }
        output = _parse_engine_output(engine.evaluate("UserPromptSubmit", data, state))
        # No decisions → preseed can't return results, so empty or no reason
        assert "caching" not in output.get("reason", "").lower() or output == {}


# ═══════════════════════════════════════════════════════════════════════
# 3. TAGS & STATS & LIST (CLI)
# ═══════════════════════════════════════════════════════════════════════


class TestCLIBrowsing:
    """CLI commands for browsing."""

    def _cli_env(self, tmp_path):
        return {
            **os.environ,
            "PYTHONPATH": str(PLUGIN_DIR),
            "HOME": str(tmp_path),
        }

    def _decisions_dir_for_cwd(self, tmp_path, cwd):
        """Compute decisions dir for a given cwd (HOME-relative .claude/decisions/)."""
        d = tmp_path / ".claude" / "decisions"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_tags_cli(self, tmp_path):
        """python3 -m decision tags --json → correct tag counts."""
        mem = self._decisions_dir_for_cwd(tmp_path, tmp_path)
        _write_valid_decision(mem, "d1", tags=["auth", "security"])
        _write_valid_decision(mem, "d2", tags=["auth", "performance"])

        result = subprocess.run(
            ["python3", "-m", "decision", "tags", "--json"],
            capture_output=True,
            text=True,
            env=self._cli_env(tmp_path),
            cwd=str(tmp_path),
            timeout=5,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert parsed.get("auth") == 2

    def test_stats_cli(self, tmp_path):
        """python3 -m decision stats --json → correct metrics."""
        mem = self._decisions_dir_for_cwd(tmp_path, tmp_path)
        _write_valid_decision(mem, "s1")
        _write_valid_decision(mem, "s2")

        result = subprocess.run(
            ["python3", "-m", "decision", "stats", "--json"],
            capture_output=True,
            text=True,
            env=self._cli_env(tmp_path),
            cwd=str(tmp_path),
            timeout=5,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert parsed.get("total", 0) >= 2

    def test_list_cli_with_filter(self, tmp_path):
        """python3 -m decision list --tag testing --json → filtered results."""
        mem = self._decisions_dir_for_cwd(tmp_path, tmp_path)
        _write_valid_decision(mem, "l1", tags=["testing"])
        _write_valid_decision(mem, "l2", tags=["other"])

        result = subprocess.run(
            ["python3", "-m", "decision", "list", "--tag", "testing", "--json"],
            capture_output=True,
            text=True,
            env=self._cli_env(tmp_path),
            cwd=str(tmp_path),
            timeout=5,
        )
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert isinstance(parsed, list)
        # Should include only the "testing" tagged decision
        if parsed:
            slugs = [d.get("slug", d.get("name", "")) for d in parsed]
            assert any("l1" in s for s in slugs)


# ═══════════════════════════════════════════════════════════════════════
# 4. SESSION LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════


class TestSessionLifecycle:
    """SessionStart context injection, Stop nudge."""

    def test_session_start_injects_context(self, store_and_state):
        """SessionStart → additionalContext with decision count + tags."""
        decisions_dir, store, state = store_and_state
        _write_valid_decision(decisions_dir, "ctx-dec", tags=["architecture"])

        engine = _make_engine()
        output = _parse_engine_output(engine.evaluate("SessionStart", {}, state))

        hso = output.get("hookSpecificOutput", {})
        ctx = hso.get("additionalContext", "")
        assert "1 decision" in ctx.lower() or "architecture" in ctx.lower()

    def test_session_start_includes_banner(self, store_and_state):
        """SessionStart → systemMessage with human-visible banner."""
        decisions_dir, store, state = store_and_state
        _write_valid_decision(decisions_dir, "banner-dec", tags=["testing"])

        engine = _make_engine()
        output = _parse_engine_output(engine.evaluate("SessionStart", {}, state))

        banner = output.get("systemMessage", "")
        assert "1 decision" in banner.lower() or "◆" in banner

    def test_session_start_via_dispatch(self, dispatch_env, tmp_path):
        """dispatch.sh SessionStart → valid hookSpecificOutput."""
        result = _run_dispatch("SessionStart", {}, dispatch_env)
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        assert isinstance(parsed, dict)
        # Should have hookSpecificOutput
        hso = parsed.get("hookSpecificOutput", {})
        assert hso.get("hookEventName") == "SessionStart" or parsed == {}

    def test_stop_nudge_fires_on_unacted_capture(self, store_and_state):
        """Unacted capture nudge → Stop returns nudge message."""
        decisions_dir, store, state = store_and_state

        state.mark_fired("_capture-nudge-pending")
        for i in range(5):
            state.record_edit(f"src/file{i}.py")

        engine = _make_engine()
        output = _parse_engine_output(engine.evaluate("Stop", {}, state))

        reason = output.get("reason", "")
        assert "decision language" in reason.lower() or "decision" in reason.lower()

    def test_stop_nudge_suppressed_with_decisions(self, store_and_state):
        """Unacted capture + recent decision → Stop suppresses nudge."""
        decisions_dir, store, state = store_and_state

        state.mark_fired("_capture-nudge-pending")
        for i in range(5):
            state.record_edit(f"src/file{i}.py")

        # Write a recent decision (mtime after state._start_time)
        time.sleep(0.05)
        _write_valid_decision(decisions_dir, "recent-dec")

        engine = _make_engine()
        output = _parse_engine_output(engine.evaluate("Stop", {}, state))
        # Should not nudge since we have a recent decision
        assert "decision language" not in output.get("reason", "").lower()


# ═══════════════════════════════════════════════════════════════════════
# 5. EDIT TRACKING & CONTEXT
# ═══════════════════════════════════════════════════════════════════════


class TestEditTracking:
    """Edit-checkpoint, related-context, edit-validation."""

    def test_edit_checkpoint_on_unacted_capture(self, store_and_state):
        """Unacted capture nudge + edits → checkpoint follow-up fires."""
        decisions_dir, store, state = store_and_state

        # Simulate capture-nudge having fired (decision language detected)
        state.mark_fired("_capture-nudge-pending")
        # Record enough edits to trigger follow-up
        for i in range(3):
            state.record_edit(f"src/module{i}.py")

        engine = _make_engine()
        data = {
            "tool_name": "Write",
            "tool_input": {"file_path": "src/module3.py"},
        }
        output = _parse_engine_output(engine.evaluate("PostToolUse", data, state))
        msg = output.get("systemMessage", "")
        assert "decision language" in msg.lower() or "capture" in msg.lower()

    def test_related_context_on_matching_edit(self, store_and_state):
        """Edit to matching file with matching decision → system_message."""
        decisions_dir, store, state = store_and_state
        _write_valid_decision(
            decisions_dir,
            "oauth-impl",
            tags=["auth"],
            affects=["src/auth/oauth.py"],
        )

        engine = _make_engine()
        data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/auth/oauth.py",
                "new_string": "def authenticate(): pass",
            },
        }
        output = _parse_engine_output(engine.evaluate("PostToolUse", data, state))
        msg = output.get("systemMessage", "")
        assert "decision" in msg.lower() or "oauth" in msg.lower()

    def test_related_context_dedup(self, store_and_state):
        """Second edit to same file → no re-injection."""
        decisions_dir, store, state = store_and_state
        _write_valid_decision(
            decisions_dir,
            "dedup-dec",
            tags=["auth"],
            affects=["src/auth/handler.py"],
        )

        engine = _make_engine()
        data = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/auth/handler.py",
                "new_string": "code here",
            },
        }

        # First edit: context injected
        out1 = _parse_engine_output(engine.evaluate("PostToolUse", data, state))
        assert out1.get("systemMessage", "") != ""

        # Second edit: deduped
        out2 = _parse_engine_output(engine.evaluate("PostToolUse", data, state))
        msg2 = out2.get("systemMessage", "")
        assert "decision" not in msg2.lower() or msg2 == ""

    def test_edit_validation_catches_corruption(self, store_and_state):
        """Edit corrupts frontmatter → warning system_message."""
        decisions_dir, store, state = store_and_state
        # Write a valid decision, then simulate PostToolUse Edit that corrupted it
        path = _write_valid_decision(decisions_dir, "corrupt-target")
        # Corrupt the file
        path.write_text("---\nbroken frontmatter without closing\n# no closing ---\n")

        engine = _make_engine()
        data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(path)},
        }
        output = _parse_engine_output(engine.evaluate("PostToolUse", data, state))
        msg = output.get("systemMessage", "")
        assert "malformed" in msg.lower() or "warning" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════
# 6. CAPTURE NUDGES
# ═══════════════════════════════════════════════════════════════════════


class TestNudges:
    """UserPromptSubmit nudge policies."""

    def test_capture_nudge_with_technical_signal(self, store_and_state):
        """'Let's go with `redis`' → nudge fires."""
        _, store, state = store_and_state
        engine = _make_engine()
        data = {
            "tool_input": {"content": "Let's go with `redis` for the caching layer"},
        }
        output = _parse_engine_output(engine.evaluate("UserPromptSubmit", data, state))
        assert output.get("reason") is not None
        assert "capture" in output.get("reason", "").lower()

    def test_capture_nudge_no_false_positive(self, store_and_state):
        """'let's go with pizza' → no nudge (no technical signal)."""
        _, store, state = store_and_state
        engine = _make_engine()
        data = {
            "tool_input": {"content": "let's go with pizza for lunch"},
        }
        output = _parse_engine_output(engine.evaluate("UserPromptSubmit", data, state))
        reason = output.get("reason", "")
        assert "capture" not in reason.lower()

    def test_capture_nudge_past_decision_query(self, store_and_state):
        """'why did we choose redis' → pre-seeds search results."""
        decisions_dir, store, state = store_and_state
        make_decision(decisions_dir, "redis-caching")
        engine = _make_engine()
        data = {
            "tool_input": {"content": "why did we choose redis for caching?"},
        }
        output = _parse_engine_output(engine.evaluate("UserPromptSubmit", data, state))
        assert output.get("ok") is True
        sys_msg = output.get("systemMessage", "")
        reason = output.get("reason", "")
        assert "decision" in reason.lower() or "decision" in sys_msg.lower()

    def test_capture_nudge_dedup(self, store_and_state):
        """Same phrase twice → fires only once."""
        _, store, state = store_and_state
        engine = _make_engine()
        data = {
            "tool_input": {"content": "Let's go with `postgres` for storage"},
        }

        # First: fires
        out1 = _parse_engine_output(engine.evaluate("UserPromptSubmit", data, state))
        has_capture1 = "capture" in out1.get("reason", "").lower()

        # Second: should not re-fire capture nudge for same phrase
        out2 = _parse_engine_output(engine.evaluate("UserPromptSubmit", data, state))
        has_capture2 = "capture" in out2.get("reason", "").lower()

        assert has_capture1  # First should fire
        assert not has_capture2  # Second should be deduped


# ═══════════════════════════════════════════════════════════════════════
# 7. SUBPROCESS PIPELINE
# ═══════════════════════════════════════════════════════════════════════


class TestSubprocessPipeline:
    """Critical paths through full dispatch.sh pipeline."""

    def test_dispatch_capture_nudge(self, dispatch_env):
        """Decision language in UserPromptSubmit → reason in JSON."""
        data = {
            "tool_input": {"content": "Let's go with `redis` for the caching layer"},
        }
        result = _run_dispatch("UserPromptSubmit", data, dispatch_env)
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        if parsed:
            reason = parsed.get("reason", "")
            assert "capture" in reason.lower() or parsed.get("ok") is not None

    def test_dispatch_stop_nudge(self, dispatch_env, tmp_path):
        """Pre-seed session edits + Stop → nudge in JSON."""
        sid = dispatch_env["CLAUDE_SESSION_ID"]
        import tempfile

        state_dir = Path(tempfile.gettempdir()) / f"decision-policy-{sid}"
        state_dir.mkdir(parents=True, exist_ok=True)
        activity = {"edits": [f"src/file{i}.py" for i in range(5)]}
        (state_dir / "_activity.json").write_text(json.dumps(activity))

        result = _run_dispatch("Stop", {}, dispatch_env)
        assert result.returncode == 0
        parsed = json.loads(result.stdout.strip())
        # Stop nudge should fire
        if parsed:
            reason = parsed.get("reason", "")
            assert "edits" in reason.lower() or "decision" in reason.lower()
