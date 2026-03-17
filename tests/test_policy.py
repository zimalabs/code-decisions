#!/usr/bin/env python3
"""Policy engine test suite — pytest style.

Each test function creates its own .engram/ via the tmp_path fixture.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import engram

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = SCRIPT_DIR.parent / "plugin" / "schemas" / "schema.sql"

# Override schema file location
os.environ["ENGRAM_SCHEMA_FILE"] = str(SCHEMA_FILE)
engram.ENGRAM_SCHEMA_FILE = SCHEMA_FILE


# ── Test helpers ────────────────────────────────────────────────────

def _make_engram(tmp_path):
    """Create a fresh .engram/ in a temp dir, return (engram_dir_path, store)."""
    engram_dir = tmp_path / ".engram"
    store = engram.EngramStore(str(engram_dir))
    store.init()
    return engram_dir, store


def _make_session_state(test_name):
    """Create a SessionState with a unique session ID."""
    import uuid
    return engram.SessionState(session_id=f"test-{test_name}-{uuid.uuid4().hex[:8]}")


def _write_signal(engram_dir, slug="test-decision", private=False):
    """Write a valid signal file."""
    if private:
        target = engram_dir / "_private" / "decisions" / f"{slug}.md"
    else:
        target = engram_dir / "decisions" / f"{slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "+++\n"
        "date = 2026-03-17\n"
        "tags = [\"testing\"]\n"
        "+++\n\n"
        f"# {slug}\n\n"
        "This is a test decision with sufficient rationale for validation.\n\n"
        "## Alternatives\n- No alternative considered\n\n"
        "## Rationale\nChosen for testing purposes.\n"
    )
    return target


# ── PolicyEngine tests ──────────────────────────────────────────────

def test_engine_list_policies():
    """PolicyEngine.list_policies returns all registered policies."""
    engine = engram.PolicyEngine()
    p = engram.Policy(
        name="test-policy",
        description="A test",
        level=engram.PolicyLevel.NUDGE,
        events=["PostToolUse"],
        matchers=["Bash"],
        condition=lambda d, s: None,
    )
    engine.register(p)
    policies = engine.list_policies()
    assert len(policies) == 1
    assert policies[0]["name"] == "test-policy"
    assert policies[0]["level"] == "NUDGE"


def test_engine_evaluate_empty():
    """Evaluate with no matching policies returns {}."""
    engine = engram.PolicyEngine()
    state = _make_session_state("empty")
    result = engine.evaluate("PreToolUse", {}, state)
    assert result == "{}"


def test_engine_block_stops_evaluation():
    """BLOCK policy stops evaluation — subsequent policies don't run."""
    ran = []

    def blocker(d, s):
        ran.append("blocker")
        return engram.PolicyResult(matched=True, decision="block", reason="blocked")

    def nudger(d, s):
        ran.append("nudger")
        return engram.PolicyResult(matched=True, system_message="nudge")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("block-p", "", engram.PolicyLevel.BLOCK, ["PreToolUse"], ["*"], blocker))
    engine.register(engram.Policy("nudge-p", "", engram.PolicyLevel.NUDGE, ["PreToolUse"], ["*"], nudger))

    state = _make_session_state("block-stops")
    result = json.loads(engine.evaluate("PreToolUse", {"tool_name": "Bash"}, state))
    assert result["decision"] == "block"
    assert ran == ["blocker"]


def test_engine_nudge_collects_all():
    """Multiple NUDGE policies collect all messages."""

    def nudge1(d, s):
        return engram.PolicyResult(matched=True, system_message="msg1")

    def nudge2(d, s):
        return engram.PolicyResult(matched=True, system_message="msg2")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("n1", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], nudge1))
    engine.register(engram.Policy("n2", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], nudge2))

    state = _make_session_state("nudge-all")
    result = json.loads(engine.evaluate("PostToolUse", {"tool_name": "Write"}, state))
    assert "msg1" in str(result.get("systemMessage", ""))
    assert "msg2" in str(result.get("systemMessage", ""))


def test_engine_once_per_session():
    """once_per_session policies only fire once."""
    call_count = [0]

    def counter(d, s):
        call_count[0] += 1
        return engram.PolicyResult(matched=True, system_message="fired")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("once", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], counter, once_per_session=True))

    state = _make_session_state("once")
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)
    assert call_count[0] == 1


def test_engine_exception_isolation():
    """Policy exceptions don't crash the engine."""

    def exploder(d, s):
        raise RuntimeError("boom")

    def ok_policy(d, s):
        return engram.PolicyResult(matched=True, system_message="survived")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("explode", "", engram.PolicyLevel.CONTEXT, ["PostToolUse"], ["*"], exploder))
    engine.register(engram.Policy("ok", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], ok_policy))

    state = _make_session_state("exception")
    result = json.loads(engine.evaluate("PostToolUse", {"tool_name": "Write"}, state))
    assert "survived" in str(result.get("systemMessage", ""))


# ── commit-gate tests ───────────────────────────────────────────────

def test_commit_gate_nudges_plain_commit(tmp_path, monkeypatch):
    """commit-gate nudges (not blocks) git commit when no signal exists."""
    engram_dir, store = _make_engram(tmp_path)
    store.reindex()

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _commit_gate_condition
    state = _make_session_state("cg-nudge")
    data = {"tool_input": {"command": "git commit -m 'test'"}}
    result = _commit_gate_condition(data, state)
    assert result.matched is True
    assert "No decision signal" in str(result.system_message)
    assert result.decision == ""


def test_commit_gate_allows_amend(tmp_path, monkeypatch):
    """commit-gate allows git commit --amend."""
    engram_dir, store = _make_engram(tmp_path)

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _commit_gate_condition
    state = _make_session_state("cg-amend")
    data = {"tool_input": {"command": "git commit --amend -m 'test'"}}
    result = _commit_gate_condition(data, state)
    assert result is None


def test_commit_gate_allows_with_signal(tmp_path, monkeypatch):
    """commit-gate allows when a signal file exists newer than index."""
    engram_dir, store = _make_engram(tmp_path)
    store.reindex()
    # Write a signal after reindex so it's "newer"
    time.sleep(0.05)
    _write_signal(engram_dir)

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _commit_gate_condition
    state = _make_session_state("cg-signal")
    data = {"tool_input": {"command": "git commit -m 'test'"}}
    result = _commit_gate_condition(data, state)
    assert result is None


# ── delete-guard tests ──────────────────────────────────────────────

def test_delete_guard_blocks_rm(tmp_path, monkeypatch):
    """delete-guard blocks rm of signal files."""
    engram_dir, _ = _make_engram(tmp_path)

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _delete_guard_condition
    state = _make_session_state("dg-rm")

    data = {"tool_input": {"command": "rm .engram/decisions/foo.md"}}
    result = _delete_guard_condition(data, state)
    assert result.decision == "block"

    data2 = {"tool_input": {"command": "rm -rf .engram"}}
    result2 = _delete_guard_condition(data2, state)
    assert result2.decision == "block"


def test_delete_guard_allows_other(tmp_path, monkeypatch):
    """delete-guard allows rm of non-engram files."""
    engram_dir, _ = _make_engram(tmp_path)

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _delete_guard_condition
    state = _make_session_state("dg-other")
    data = {"tool_input": {"command": "rm other-file.txt"}}
    result = _delete_guard_condition(data, state)
    assert result is None


def test_delete_guard_blocks_git_checkout(tmp_path, monkeypatch):
    """delete-guard blocks git checkout -- of signal files."""
    engram_dir, _ = _make_engram(tmp_path)

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _delete_guard_condition
    state = _make_session_state("dg-checkout")
    data = {"tool_input": {"command": "git checkout -- .engram/decisions/foo.md"}}
    result = _delete_guard_condition(data, state)
    assert result.decision == "block"


# ── edit-guard tests ────────────────────────────────────────────────

def test_edit_guard_blocks_empty_new_string():
    """edit-guard blocks content deletion from signal files."""
    from engram._policy_defs import _edit_guard_condition
    state = _make_session_state("eg-empty")
    data = {
        "tool_input": {
            "file_path": ".engram/decisions/foo.md",
            "old_string": "some content",
            "new_string": "",
        }
    }
    result = _edit_guard_condition(data, state)
    assert result.decision == "block"


def test_edit_guard_allows_other_files():
    """edit-guard allows edits to non-signal files."""
    from engram._policy_defs import _edit_guard_condition
    state = _make_session_state("eg-other")
    data = {
        "tool_input": {
            "file_path": "src/main.py",
            "old_string": "some content",
            "new_string": "",
        }
    }
    result = _edit_guard_condition(data, state)
    assert result is None


def test_edit_guard_allows_signal_edit_with_content():
    """edit-guard allows edits that add content to signal files."""
    from engram._policy_defs import _edit_guard_condition
    state = _make_session_state("eg-content")
    data = {
        "tool_input": {
            "file_path": ".engram/decisions/foo.md",
            "old_string": "old text",
            "new_string": "new text with more detail",
        }
    }
    result = _edit_guard_condition(data, state)
    assert result is None


# ── content-validation tests ────────────────────────────────────────

def test_content_validation_rejects_missing_frontmatter():
    """content-validation rejects content without frontmatter."""
    from engram._policy_defs import _content_validation_condition
    state = _make_session_state("cv-missing")
    data = {
        "tool_input": {
            "file_path": ".engram/decisions/bad.md",
            "content": "No frontmatter here\nJust plain text\n",
        }
    }
    result = _content_validation_condition(data, state)
    assert result.ok is False
    assert "missing" in str(result.reason)


def test_content_validation_accepts_valid():
    """content-validation accepts valid signal content."""
    from engram._policy_defs import _content_validation_condition
    state = _make_session_state("cv-valid")
    data = {
        "tool_input": {
            "file_path": ".engram/decisions/good.md",
            "content": (
                "+++\ndate = 2026-03-17\ntags = [\"testing\"]\n+++\n\n"
                "# Good Decision\n\nThis is a valid decision with sufficient rationale.\n\n"
                "## Alternatives\n- None considered\n\n"
                "## Rationale\nChosen for testing.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is None


def test_content_validation_skips_non_signal():
    """content-validation ignores non-signal file paths."""
    from engram._policy_defs import _content_validation_condition
    state = _make_session_state("cv-skip")
    data = {
        "tool_input": {
            "file_path": "src/main.py",
            "content": "no frontmatter",
        }
    }
    result = _content_validation_condition(data, state)
    assert result is None


# ── session-context tests ───────────────────────────────────────────

def test_session_context_injects_brief(tmp_path, monkeypatch):
    """session-context injects brief content."""
    engram_dir, store = _make_engram(tmp_path)
    _write_signal(engram_dir)
    store.reindex()
    store.brief()

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _session_context_condition
    state = _make_session_state("sc-brief")
    result = _session_context_condition({}, state)
    assert result.matched is True
    assert "Decision Context" in str(result.additional_context)
    assert "persistent decision store" in str(result.additional_context)


# ── push-resync tests ──────────────────────────────────────────────

def test_push_resync_triggers_on_push(tmp_path, monkeypatch):
    """push-resync fires on git push commands."""
    engram_dir, store = _make_engram(tmp_path)

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _push_resync_condition
    state = _make_session_state("pr-push")
    data = {"tool_input": {"command": "git push origin main"}}
    result = _push_resync_condition(data, state)
    assert result.matched is True
    assert "resynced" in str(result.system_message)


def test_push_resync_ignores_other(tmp_path, monkeypatch):
    """push-resync ignores non-push commands."""
    engram_dir, _ = _make_engram(tmp_path)

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _push_resync_condition
    state = _make_session_state("pr-other")
    data = {"tool_input": {"command": "git pull"}}
    result = _push_resync_condition(data, state)
    assert result is None


# ── decision-language tests ─────────────────────────────────────────

def test_decision_language_detects():
    """decision-language detects decision phrases."""
    from engram._policy_defs import _decision_language_condition
    state = _make_session_state("dl-detect")
    data = {"tool_input": {"content": "Let's go with PostgreSQL for the database"}}
    result = _decision_language_condition(data, state)
    assert result.matched is True
    assert "capture" in str(result.reason)


def test_decision_language_detects_query():
    """decision-language detects past-decision queries."""
    from engram._policy_defs import _decision_language_condition
    state = _make_session_state("dl-query")
    data = {"tool_input": {"content": "Why did we choose Redis?"}}
    result = _decision_language_condition(data, state)
    assert result.matched is True
    assert "query" in str(result.reason)


def test_decision_language_ignores_normal():
    """decision-language ignores normal prompts."""
    from engram._policy_defs import _decision_language_condition
    state = _make_session_state("dl-normal")
    data = {"tool_input": {"content": "Add a new endpoint for users"}}
    result = _decision_language_condition(data, state)
    assert result is None


# ── stop-nudge tests ───────────────────────────────────────────────

def test_stop_nudge_no_signals(tmp_path, monkeypatch):
    """stop-nudge shows reflection prompt when no recent signals exist."""
    engram_dir, store = _make_engram(tmp_path)
    store.reindex()

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _stop_nudge_condition
    state = _make_session_state("sn-none")
    state.record_edit("src/main.py")  # session must have edits to trigger nudge
    result = _stop_nudge_condition({}, state)
    assert result.ok is True
    assert "Session reflection" in str(result.reason)


# ── capture-nudge tests ────────────────────────────────────────────

def test_capture_nudge_fires_on_code_edit(tmp_path, monkeypatch):
    """capture-nudge fires when editing code without recent signals."""
    engram_dir, store = _make_engram(tmp_path)
    store.reindex()

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _capture_nudge_condition
    state = _make_session_state("cn-code")
    # Need 3+ edits to trigger capture-nudge
    state.record_edit("src/a.py")
    state.record_edit("src/b.py")
    state.record_edit("src/c.py")
    data = {"tool_input": {"file_path": "src/main.py"}}
    result = _capture_nudge_condition(data, state)
    assert result.matched is True
    assert "capture" in str(result.system_message)


def test_capture_nudge_skips_test_files(tmp_path, monkeypatch):
    """capture-nudge skips test files."""
    engram_dir, _ = _make_engram(tmp_path)

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _capture_nudge_condition
    state = _make_session_state("cn-test")
    data = {"tool_input": {"file_path": "tests/test_foo.py"}}
    result = _capture_nudge_condition(data, state)
    assert result is None


# ── SessionState tests ──────────────────────────────────────────────

def test_session_state_has_fired():
    """SessionState tracks fired policies."""
    state = _make_session_state("state-fired")
    assert state.has_fired("test-policy") is False
    state.mark_fired("test-policy")
    assert state.has_fired("test-policy") is True


def test_session_state_recent_signals(tmp_path, monkeypatch):
    """SessionState.has_recent_signals detects new files."""
    engram_dir, store = _make_engram(tmp_path)
    store.reindex()

    monkeypatch.chdir(engram_dir.parent)
    state = _make_session_state("ss-recent")
    assert state.has_recent_signals() is False

    time.sleep(0.05)
    _write_signal(engram_dir)
    assert state.has_recent_signals() is True


# ── Full engine integration test ────────────────────────────────────

def test_full_engine_with_all_policies():
    """Load all policies and evaluate a PreToolUse event."""
    from engram._policy_defs import ALL_POLICIES

    engine = engram.PolicyEngine()
    for p in ALL_POLICIES:
        engine.register(p)

    policies = engine.list_policies()
    assert len(policies) == 15

    # Verify ordering — BLOCK first
    assert policies[0]["level"] == "BLOCK"

    # Evaluate a non-matching event
    state = _make_session_state("full-engine")
    result = engine.evaluate("PreToolUse", {"tool_name": "Read"}, state)
    assert result == "{}"


def test_policy_list_command():
    """python3 -m engram policy (no args) lists policies."""
    parent_dir = str(Path(__file__).resolve().parent.parent / "plugin" / "src")
    result = subprocess.run(
        [sys.executable, "-m", "engram", "policy"],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": parent_dir},
    )
    assert result.returncode == 0
    policies = json.loads(result.stdout)
    assert len(policies) == 15
    names = [p["name"] for p in policies]
    assert "commit-gate" in str(names)
    assert "delete-guard" in str(names)
    # Verify commit-gate is now NUDGE level, not BLOCK
    cg = [p for p in policies if p["name"] == "commit-gate"][0]
    assert cg["level"] == "NUDGE"


# ── Activity tracking tests (F) ──────────────────────────────────────

def test_session_state_activity_tracking():
    """SessionState tracks file edits."""
    state = _make_session_state("activity")
    assert state.edit_count() == 0
    assert state.has_edits() is False

    state.record_edit("src/main.py")
    assert state.edit_count() == 1
    assert state.has_edits() is True

    # Duplicate is ignored
    state.record_edit("src/main.py")
    assert state.edit_count() == 1

    state.record_edit("src/other.py")
    assert state.edit_count() == 2
    assert "src/main.py" in str(state.files_edited())


def test_session_state_activity_skips_engram():
    """SessionState.record_edit skips .engram/ paths."""
    state = _make_session_state("activity-skip")
    state.record_edit(".engram/decisions/foo.md")
    assert state.edit_count() == 0


def test_engine_records_edits():
    """PolicyEngine.evaluate records edits for PostToolUse Write/Edit/MultiEdit."""
    engine = engram.PolicyEngine()
    state = _make_session_state("engine-edits")

    # PostToolUse Write should record the edit
    engine.evaluate("PostToolUse", {
        "tool_name": "Write",
        "tool_input": {"file_path": "src/app.py", "content": "hello"},
    }, state)
    assert state.edit_count() == 1

    # PostToolUse Edit should also record
    engine.evaluate("PostToolUse", {
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/model.py", "old_string": "x", "new_string": "y"},
    }, state)
    assert state.edit_count() == 2

    # PostToolUse Read should NOT record
    engine.evaluate("PostToolUse", {
        "tool_name": "Read",
        "tool_input": {"file_path": "src/other.py"},
    }, state)
    assert state.edit_count() == 2


# ── TOML Config tests (A) ────────────────────────────────────────────

def test_store_load_config_toml(tmp_path):
    """EngramStore.load_config reads TOML config."""
    engram_dir, store = _make_engram(tmp_path)
    config_path = engram_dir / "config.toml"
    config_path.write_text('git_tracking = true\ntrace = false\n\n[policies]\ncommit-gate = "off"\n')

    cfg = store.load_config()
    assert cfg.get("git_tracking") is True
    assert cfg.get("trace") is False
    assert cfg.get("policies", {}).get("commit-gate") == "off"


def test_store_load_config_missing(tmp_path):
    """EngramStore.load_config returns empty dict when no config exists."""
    engram_dir, store = _make_engram(tmp_path)
    # Remove auto-created config.toml
    config_toml = engram_dir / "config.toml"
    if config_toml.is_file():
        config_toml.unlink()

    cfg = store.load_config()
    assert cfg == {}


def test_store_policy_config(tmp_path):
    """EngramStore.policy_config returns policies table."""
    engram_dir, store = _make_engram(tmp_path)
    config_path = engram_dir / "config.toml"
    config_path.write_text('[policies]\ncommit-gate = "off"\ncapture-nudge = "off"\n')

    pc = store.policy_config()
    assert pc.get("commit-gate") == "off"
    assert pc.get("capture-nudge") == "off"


def test_store_trace_enabled(tmp_path):
    """EngramStore.trace_enabled reads from config."""
    engram_dir, store = _make_engram(tmp_path)
    config_path = engram_dir / "config.toml"

    config_path.write_text("trace = true\n")
    assert store.trace_enabled is True

    config_path.write_text("trace = false\n")
    assert store.trace_enabled is False


def test_engine_apply_config_disables():
    """PolicyEngine.apply_config disables policies."""

    def always_match(d, s):
        return engram.PolicyResult(matched=True, system_message="fired")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("p1", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], always_match))
    engine.register(engram.Policy("p2", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], always_match))

    engine.apply_config({"p1": "off"})

    state = _make_session_state("disable")
    result = json.loads(engine.evaluate("PostToolUse", {"tool_name": "Write"}, state))
    msg = result.get("systemMessage", "")
    # p2 should fire, p1 should not — only one "fired" message
    assert msg == "fired"


def test_init_creates_default_config(tmp_path):
    """store.init() creates config.toml from template when no config exists."""
    engram_dir = tmp_path / ".engram"
    store = engram.EngramStore(str(engram_dir))
    store.init()

    config_path = engram_dir / "config.toml"
    assert config_path.is_file() is True
    content = config_path.read_text()
    assert "git_tracking" in content
    assert "[policies]" in content


# ── Content-aware context tests (E) ──────────────────────────────────

def test_extract_content_keywords():
    """_extract_content_keywords extracts meaningful words from edit content."""
    from engram._policy_defs import _extract_content_keywords

    # Edit with new_string
    data = {"tool_input": {"new_string": "def authenticate_user(self, token):\n    return verify(token)"}}
    kw = _extract_content_keywords(data)
    assert "authenticate" in str(kw)
    # 'self' and 'return' should be filtered as code noise
    assert "self" not in str(kw)

    # Empty input
    data2 = {"tool_input": {"new_string": ""}}
    kw2 = _extract_content_keywords(data2)
    assert kw2 == []

    # Short words filtered
    data3 = {"tool_input": {"content": "the and for"}}
    kw3 = _extract_content_keywords(data3)
    assert kw3 == []


def test_extract_content_keywords_max():
    """_extract_content_keywords respects max_words."""
    from engram._policy_defs import _extract_content_keywords
    data = {"tool_input": {"new_string": "authenticate validate serialize compress encrypt"}}
    kw = _extract_content_keywords(data, max_words=2)
    assert len(kw) == 2


# ── Smarter nudges tests (C) ─────────────────────────────────────────

def test_capture_nudge_requires_3_edits(tmp_path, monkeypatch):
    """capture-nudge only fires after 3+ edits."""
    engram_dir, store = _make_engram(tmp_path)
    store.reindex()

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _capture_nudge_condition
    state = _make_session_state("cn-threshold")

    # 0 edits — should not fire
    data = {"tool_input": {"file_path": "src/main.py"}}
    result = _capture_nudge_condition(data, state)
    assert result is None

    # Record 2 edits — still shouldn't fire
    state.record_edit("src/a.py")
    state.record_edit("src/b.py")
    result = _capture_nudge_condition(data, state)
    assert result is None

    # Record 3rd edit — now it should fire
    state.record_edit("src/c.py")
    result = _capture_nudge_condition(data, state)
    assert result.matched is True


def test_stop_nudge_silent_for_readonly(tmp_path, monkeypatch):
    """stop-nudge doesn't nudge for read-only sessions."""
    engram_dir, store = _make_engram(tmp_path)
    store.reindex()

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _stop_nudge_condition
    state = _make_session_state("sn-readonly")
    # No edits recorded — read-only session
    result = _stop_nudge_condition({}, state)
    assert result.ok is True
    # Should NOT have the "No new decision signals" reason
    reason = result.reason or ""
    assert "No new decision signals" not in str(reason)


def test_stop_nudge_fires_with_edits(tmp_path, monkeypatch):
    """stop-nudge shows reflection prompt when session has edits but no signals."""
    engram_dir, store = _make_engram(tmp_path)
    store.reindex()

    monkeypatch.chdir(engram_dir.parent)
    from engram._policy_defs import _stop_nudge_condition
    state = _make_session_state("sn-edits")
    state.record_edit("src/main.py")
    result = _stop_nudge_condition({}, state)
    assert result.ok is True
    assert "Session reflection" in str(result.reason)
    assert "src/main.py" in str(result.reason)


def test_decision_language_per_phrase_dedup():
    """decision-language deduplicates by matched phrase, not globally."""
    from engram._policy_defs import _decision_language_condition
    state = _make_session_state("dl-dedup")

    # First "let's go with" match
    data1 = {"tool_input": {"content": "Let's go with PostgreSQL"}}
    r1 = _decision_language_condition(data1, state)
    assert r1.matched is True

    # Same phrase again — should be suppressed
    data2 = {"tool_input": {"content": "Let's go with MySQL instead"}}
    r2 = _decision_language_condition(data2, state)
    assert r2 is None

    # Different phrase — should fire
    data3 = {"tool_input": {"content": "We decided on Redis"}}
    r3 = _decision_language_condition(data3, state)
    assert r3.matched is True


# ── Trace tests (B) ─────────────────────────────────────────────────

def test_engine_trace_collection():
    """PolicyEngine collects trace entries during evaluate."""

    def match_policy(d, s):
        return engram.PolicyResult(matched=True, system_message="hit")

    def skip_policy(d, s):
        return None

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("p-match", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], match_policy))
    engine.register(engram.Policy("p-skip", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], skip_policy))

    state = _make_session_state("trace")
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)

    assert len(engine._last_trace) == 2
    assert engine._last_trace[0]["matched"] is True
    assert engine._last_trace[0]["policy"] == "p-match"
    assert engine._last_trace[1]["matched"] is False


def test_engine_trace_disabled_policy():
    """Trace shows disabled policies as skipped."""

    def always(d, s):
        return engram.PolicyResult(matched=True, system_message="x")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("enabled", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], always))
    engine.register(engram.Policy("disabled", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], always))
    engine.apply_config({"disabled": "off"})

    state = _make_session_state("trace-disabled")
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)

    disabled_trace = [t for t in engine._last_trace if t["policy"] == "disabled"]
    assert len(disabled_trace) == 1
    assert disabled_trace[0]["skipped"] == "disabled"


def test_policy_command_with_trace():
    """python3 -m engram policy --trace outputs trace JSON."""
    parent_dir = str(Path(__file__).resolve().parent.parent / "plugin" / "src")
    result = subprocess.run(
        [sys.executable, "-m", "engram", "policy", "--trace", "PostToolUse"],
        input='{"tool_name": "Read"}',
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": parent_dir},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "result" in str(output)
    assert "trace" in str(output)
