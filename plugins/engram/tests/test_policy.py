#!/usr/bin/env python3
"""Policy engine test suite — plain Python, no external deps.

Each test function creates its own .engram/ in a temp directory.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

# Add parent directory to path so we can import engram
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engram

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = SCRIPT_DIR.parent / "schemas" / "schema.sql"
TEST_DIR = Path(tempfile.mkdtemp(prefix="engram-policy-test."))
PASS = 0
FAIL = 0

# Override schema file location
os.environ["ENGRAM_SCHEMA_FILE"] = str(SCHEMA_FILE)
os.environ["ENGRAM_PLANS_DIR"] = str(TEST_DIR / "plans")
engram.ENGRAM_SCHEMA_FILE = SCHEMA_FILE


# ── Test helpers ────────────────────────────────────────────────────

def _pass(name):
    global PASS
    PASS += 1
    print(f"  PASS: {name}")


def _fail(name, msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL: {name} — {msg}")


def assert_eq(name, actual, expected):
    if actual == expected:
        _pass(name)
    else:
        _fail(name, f"expected '{expected}', got '{actual}'")


def assert_contains(name, text, substring):
    if substring in str(text):
        _pass(name)
    else:
        _fail(name, f"output does not contain '{substring}'")


def assert_not_contains(name, text, substring):
    if substring in str(text):
        _fail(name, f"output should not contain '{substring}'")
    else:
        _pass(name)


def _make_engram(test_name):
    """Create a fresh .engram/ in a temp dir, return (engram_dir_path, store)."""
    d = TEST_DIR / test_name
    d.mkdir(parents=True, exist_ok=True)
    engram_dir = d / ".engram"
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
    print("\n── test_engine_list_policies ──")
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
    assert_eq("list length", len(policies), 1)
    assert_eq("policy name", policies[0]["name"], "test-policy")
    assert_eq("policy level", policies[0]["level"], "NUDGE")


def test_engine_evaluate_empty():
    """Evaluate with no matching policies returns {}."""
    print("\n── test_engine_evaluate_empty ──")
    engine = engram.PolicyEngine()
    state = _make_session_state("empty")
    result = engine.evaluate("PreToolUse", {}, state)
    assert_eq("empty result", result, "{}")


def test_engine_block_stops_evaluation():
    """BLOCK policy stops evaluation — subsequent policies don't run."""
    print("\n── test_engine_block_stops_evaluation ──")
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
    assert_eq("decision", result["decision"], "block")
    assert_eq("only blocker ran", ran, ["blocker"])


def test_engine_nudge_collects_all():
    """Multiple NUDGE policies collect all messages."""
    print("\n── test_engine_nudge_collects_all ──")

    def nudge1(d, s):
        return engram.PolicyResult(matched=True, system_message="msg1")

    def nudge2(d, s):
        return engram.PolicyResult(matched=True, system_message="msg2")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("n1", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], nudge1))
    engine.register(engram.Policy("n2", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], nudge2))

    state = _make_session_state("nudge-all")
    result = json.loads(engine.evaluate("PostToolUse", {"tool_name": "Write"}, state))
    assert_contains("has msg1", result.get("systemMessage", ""), "msg1")
    assert_contains("has msg2", result.get("systemMessage", ""), "msg2")


def test_engine_once_per_session():
    """once_per_session policies only fire once."""
    print("\n── test_engine_once_per_session ──")
    call_count = [0]

    def counter(d, s):
        call_count[0] += 1
        return engram.PolicyResult(matched=True, system_message="fired")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("once", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], counter, once_per_session=True))

    state = _make_session_state("once")
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)
    assert_eq("condition called once", call_count[0], 1)


def test_engine_exception_isolation():
    """Policy exceptions don't crash the engine."""
    print("\n── test_engine_exception_isolation ──")

    def exploder(d, s):
        raise RuntimeError("boom")

    def ok_policy(d, s):
        return engram.PolicyResult(matched=True, system_message="survived")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("explode", "", engram.PolicyLevel.CONTEXT, ["PostToolUse"], ["*"], exploder))
    engine.register(engram.Policy("ok", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], ok_policy))

    state = _make_session_state("exception")
    result = json.loads(engine.evaluate("PostToolUse", {"tool_name": "Write"}, state))
    assert_contains("survived", result.get("systemMessage", ""), "survived")


# ── commit-gate tests ───────────────────────────────────────────────

def test_commit_gate_blocks_plain_commit():
    """commit-gate blocks git commit when no signal exists."""
    print("\n── test_commit_gate_blocks_plain_commit ──")
    engram_dir, store = _make_engram("commit-gate-block")
    store.reindex()

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _commit_gate_condition
        state = _make_session_state("cg-block")
        data = {"tool_input": {"command": "git commit -m 'test'"}}
        result = _commit_gate_condition(data, state)
        assert_eq("blocks", result.decision, "block")
        assert_contains("reason", result.reason, "No decision signal")
    finally:
        os.chdir(orig_cwd)


def test_commit_gate_allows_amend():
    """commit-gate allows git commit --amend."""
    print("\n── test_commit_gate_allows_amend ──")
    engram_dir, store = _make_engram("commit-gate-amend")

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _commit_gate_condition
        state = _make_session_state("cg-amend")
        data = {"tool_input": {"command": "git commit --amend -m 'test'"}}
        result = _commit_gate_condition(data, state)
        assert_eq("allows amend", result, None)
    finally:
        os.chdir(orig_cwd)


def test_commit_gate_allows_with_signal():
    """commit-gate allows when a signal file exists newer than index."""
    print("\n── test_commit_gate_allows_with_signal ──")
    engram_dir, store = _make_engram("commit-gate-signal")
    store.reindex()
    # Write a signal after reindex so it's "newer"
    time.sleep(0.05)
    _write_signal(engram_dir)

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _commit_gate_condition
        state = _make_session_state("cg-signal")
        data = {"tool_input": {"command": "git commit -m 'test'"}}
        result = _commit_gate_condition(data, state)
        assert_eq("allows with signal", result, None)
    finally:
        os.chdir(orig_cwd)


# ── delete-guard tests ──────────────────────────────────────────────

def test_delete_guard_blocks_rm():
    """delete-guard blocks rm of signal files."""
    print("\n── test_delete_guard_blocks_rm ──")
    engram_dir, _ = _make_engram("delete-guard-rm")

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _delete_guard_condition
        state = _make_session_state("dg-rm")

        data = {"tool_input": {"command": "rm .engram/decisions/foo.md"}}
        result = _delete_guard_condition(data, state)
        assert_eq("blocks rm", result.decision, "block")

        data2 = {"tool_input": {"command": "rm -rf .engram"}}
        result2 = _delete_guard_condition(data2, state)
        assert_eq("blocks rm -rf", result2.decision, "block")
    finally:
        os.chdir(orig_cwd)


def test_delete_guard_allows_other():
    """delete-guard allows rm of non-engram files."""
    print("\n── test_delete_guard_allows_other ──")
    engram_dir, _ = _make_engram("delete-guard-other")

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _delete_guard_condition
        state = _make_session_state("dg-other")
        data = {"tool_input": {"command": "rm other-file.txt"}}
        result = _delete_guard_condition(data, state)
        assert_eq("allows other rm", result, None)
    finally:
        os.chdir(orig_cwd)


def test_delete_guard_blocks_git_checkout():
    """delete-guard blocks git checkout -- of signal files."""
    print("\n── test_delete_guard_blocks_git_checkout ──")
    engram_dir, _ = _make_engram("delete-guard-checkout")

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _delete_guard_condition
        state = _make_session_state("dg-checkout")
        data = {"tool_input": {"command": "git checkout -- .engram/decisions/foo.md"}}
        result = _delete_guard_condition(data, state)
        assert_eq("blocks checkout", result.decision, "block")
    finally:
        os.chdir(orig_cwd)


# ── edit-guard tests ────────────────────────────────────────────────

def test_edit_guard_blocks_empty_new_string():
    """edit-guard blocks content deletion from signal files."""
    print("\n── test_edit_guard_blocks_empty_new_string ──")
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
    assert_eq("blocks empty new_string", result.decision, "block")


def test_edit_guard_allows_other_files():
    """edit-guard allows edits to non-signal files."""
    print("\n── test_edit_guard_allows_other_files ──")
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
    assert_eq("allows other files", result, None)


def test_edit_guard_allows_signal_edit_with_content():
    """edit-guard allows edits that add content to signal files."""
    print("\n── test_edit_guard_allows_signal_edit_with_content ──")
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
    assert_eq("allows edit with content", result, None)


# ── content-validation tests ────────────────────────────────────────

def test_content_validation_rejects_missing_frontmatter():
    """content-validation rejects content without frontmatter."""
    print("\n── test_content_validation_rejects_missing_frontmatter ──")
    from engram._policy_defs import _content_validation_condition
    state = _make_session_state("cv-missing")
    data = {
        "tool_input": {
            "file_path": ".engram/decisions/bad.md",
            "content": "No frontmatter here\nJust plain text\n",
        }
    }
    result = _content_validation_condition(data, state)
    assert_eq("rejects", result.ok, False)
    assert_contains("reason has error", result.reason, "missing")


def test_content_validation_accepts_valid():
    """content-validation accepts valid signal content."""
    print("\n── test_content_validation_accepts_valid ──")
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
    assert_eq("accepts valid", result, None)


def test_content_validation_skips_non_signal():
    """content-validation ignores non-signal file paths."""
    print("\n── test_content_validation_skips_non_signal ──")
    from engram._policy_defs import _content_validation_condition
    state = _make_session_state("cv-skip")
    data = {
        "tool_input": {
            "file_path": "src/main.py",
            "content": "no frontmatter",
        }
    }
    result = _content_validation_condition(data, state)
    assert_eq("skips non-signal", result, None)


# ── session-context tests ───────────────────────────────────────────

def test_session_context_injects_brief():
    """session-context injects brief content."""
    print("\n── test_session_context_injects_brief ──")
    engram_dir, store = _make_engram("session-context")
    _write_signal(engram_dir)
    store.reindex()
    store.brief()

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _session_context_condition
        state = _make_session_state("sc-brief")
        result = _session_context_condition({}, state)
        assert_eq("matched", result.matched, True)
        assert_contains("has brief", result.additional_context, "Decision Context")
        assert_contains("has instructions", result.additional_context, "persistent decision store")
    finally:
        os.chdir(orig_cwd)


# ── push-resync tests ──────────────────────────────────────────────

def test_push_resync_triggers_on_push():
    """push-resync fires on git push commands."""
    print("\n── test_push_resync_triggers_on_push ──")
    engram_dir, store = _make_engram("push-resync")

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _push_resync_condition
        state = _make_session_state("pr-push")
        data = {"tool_input": {"command": "git push origin main"}}
        result = _push_resync_condition(data, state)
        assert_eq("matched", result.matched, True)
        assert_contains("message", result.system_message, "resynced")
    finally:
        os.chdir(orig_cwd)


def test_push_resync_ignores_other():
    """push-resync ignores non-push commands."""
    print("\n── test_push_resync_ignores_other ──")
    engram_dir, _ = _make_engram("push-resync-other")

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _push_resync_condition
        state = _make_session_state("pr-other")
        data = {"tool_input": {"command": "git pull"}}
        result = _push_resync_condition(data, state)
        assert_eq("ignores pull", result, None)
    finally:
        os.chdir(orig_cwd)


# ── decision-language tests ─────────────────────────────────────────

def test_decision_language_detects():
    """decision-language detects decision phrases."""
    print("\n── test_decision_language_detects ──")
    from engram._policy_defs import _decision_language_condition
    state = _make_session_state("dl-detect")
    data = {"tool_input": {"content": "Let's go with PostgreSQL for the database"}}
    result = _decision_language_condition(data, state)
    assert_eq("matched", result.matched, True)
    assert_contains("nudge", result.reason, "capture")


def test_decision_language_detects_query():
    """decision-language detects past-decision queries."""
    print("\n── test_decision_language_detects_query ──")
    from engram._policy_defs import _decision_language_condition
    state = _make_session_state("dl-query")
    data = {"tool_input": {"content": "Why did we choose Redis?"}}
    result = _decision_language_condition(data, state)
    assert_eq("matched", result.matched, True)
    assert_contains("query nudge", result.reason, "query")


def test_decision_language_ignores_normal():
    """decision-language ignores normal prompts."""
    print("\n── test_decision_language_ignores_normal ──")
    from engram._policy_defs import _decision_language_condition
    state = _make_session_state("dl-normal")
    data = {"tool_input": {"content": "Add a new endpoint for users"}}
    result = _decision_language_condition(data, state)
    assert_eq("no match", result, None)


# ── stop-nudge tests ───────────────────────────────────────────────

def test_stop_nudge_no_signals():
    """stop-nudge nudges when no recent signals exist."""
    print("\n── test_stop_nudge_no_signals ──")
    engram_dir, store = _make_engram("stop-nudge")
    store.reindex()

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _stop_nudge_condition
        state = _make_session_state("sn-none")
        state.record_edit("src/main.py")  # session must have edits to trigger nudge
        result = _stop_nudge_condition({}, state)
        assert_eq("ok", result.ok, True)
        assert_contains("nudge reason", result.reason, "No new decision signals")
    finally:
        os.chdir(orig_cwd)


# ── capture-nudge tests ────────────────────────────────────────────

def test_capture_nudge_fires_on_code_edit():
    """capture-nudge fires when editing code without recent signals."""
    print("\n── test_capture_nudge_fires_on_code_edit ──")
    engram_dir, store = _make_engram("capture-nudge")
    store.reindex()

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _capture_nudge_condition
        state = _make_session_state("cn-code")
        # Need 3+ edits to trigger capture-nudge
        state.record_edit("src/a.py")
        state.record_edit("src/b.py")
        state.record_edit("src/c.py")
        data = {"tool_input": {"file_path": "src/main.py"}}
        result = _capture_nudge_condition(data, state)
        assert_eq("matched", result.matched, True)
        assert_contains("nudge", result.system_message, "capture")
    finally:
        os.chdir(orig_cwd)


def test_capture_nudge_skips_test_files():
    """capture-nudge skips test files."""
    print("\n── test_capture_nudge_skips_test_files ──")
    engram_dir, _ = _make_engram("capture-nudge-test")

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _capture_nudge_condition
        state = _make_session_state("cn-test")
        data = {"tool_input": {"file_path": "tests/test_foo.py"}}
        result = _capture_nudge_condition(data, state)
        assert_eq("skips tests", result, None)
    finally:
        os.chdir(orig_cwd)


# ── SessionState tests ──────────────────────────────────────────────

def test_session_state_has_fired():
    """SessionState tracks fired policies."""
    print("\n── test_session_state_has_fired ──")
    state = _make_session_state("state-fired")
    assert_eq("not fired initially", state.has_fired("test-policy"), False)
    state.mark_fired("test-policy")
    assert_eq("fired after mark", state.has_fired("test-policy"), True)


def test_session_state_recent_signals():
    """SessionState.has_recent_signals detects new files."""
    print("\n── test_session_state_recent_signals ──")
    engram_dir, store = _make_engram("state-signals")
    store.reindex()

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        state = _make_session_state("ss-recent")
        assert_eq("no recent initially", state.has_recent_signals(), False)

        time.sleep(0.05)
        _write_signal(engram_dir)
        assert_eq("recent after write", state.has_recent_signals(), True)
    finally:
        os.chdir(orig_cwd)


# ── Full engine integration test ────────────────────────────────────

def test_full_engine_with_all_policies():
    """Load all policies and evaluate a PreToolUse event."""
    print("\n── test_full_engine_with_all_policies ──")
    from engram._policy_defs import ALL_POLICIES

    engine = engram.PolicyEngine()
    for p in ALL_POLICIES:
        engine.register(p)

    policies = engine.list_policies()
    assert_eq("policy count", len(policies), 15)

    # Verify ordering — BLOCK first
    assert_eq("first is BLOCK", policies[0]["level"], "BLOCK")

    # Evaluate a non-matching event
    state = _make_session_state("full-engine")
    result = engine.evaluate("PreToolUse", {"tool_name": "Read"}, state)
    assert_eq("no match for Read", result, "{}")


def test_policy_list_command():
    """python3 -m engram policy (no args) lists policies."""
    print("\n── test_policy_list_command ──")
    import subprocess

    parent_dir = str(Path(__file__).resolve().parent.parent)
    result = subprocess.run(
        [sys.executable, "-m", "engram", "policy"],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": parent_dir},
    )
    assert_eq("exit code", result.returncode, 0)
    policies = json.loads(result.stdout)
    assert_eq("policy count", len(policies), 15)
    names = [p["name"] for p in policies]
    assert_contains("has commit-gate", str(names), "commit-gate")
    assert_contains("has delete-guard", str(names), "delete-guard")


# ── Activity tracking tests (F) ──────────────────────────────────────

def test_session_state_activity_tracking():
    """SessionState tracks file edits."""
    print("\n── test_session_state_activity_tracking ──")
    state = _make_session_state("activity")
    assert_eq("no edits initially", state.edit_count(), 0)
    assert_eq("has_edits false", state.has_edits(), False)

    state.record_edit("src/main.py")
    assert_eq("one edit", state.edit_count(), 1)
    assert_eq("has_edits true", state.has_edits(), True)

    # Duplicate is ignored
    state.record_edit("src/main.py")
    assert_eq("no dup", state.edit_count(), 1)

    state.record_edit("src/other.py")
    assert_eq("two edits", state.edit_count(), 2)
    assert_contains("files_edited", str(state.files_edited()), "src/main.py")


def test_session_state_activity_skips_engram():
    """SessionState.record_edit skips .engram/ paths."""
    print("\n── test_session_state_activity_skips_engram ──")
    state = _make_session_state("activity-skip")
    state.record_edit(".engram/decisions/foo.md")
    assert_eq("skipped engram path", state.edit_count(), 0)


def test_engine_records_edits():
    """PolicyEngine.evaluate records edits for PostToolUse Write/Edit/MultiEdit."""
    print("\n── test_engine_records_edits ──")
    engine = engram.PolicyEngine()
    state = _make_session_state("engine-edits")

    # PostToolUse Write should record the edit
    engine.evaluate("PostToolUse", {
        "tool_name": "Write",
        "tool_input": {"file_path": "src/app.py", "content": "hello"},
    }, state)
    assert_eq("recorded write", state.edit_count(), 1)

    # PostToolUse Edit should also record
    engine.evaluate("PostToolUse", {
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/model.py", "old_string": "x", "new_string": "y"},
    }, state)
    assert_eq("recorded edit", state.edit_count(), 2)

    # PostToolUse Read should NOT record
    engine.evaluate("PostToolUse", {
        "tool_name": "Read",
        "tool_input": {"file_path": "src/other.py"},
    }, state)
    assert_eq("read not recorded", state.edit_count(), 2)


# ── TOML Config tests (A) ────────────────────────────────────────────

def test_store_load_config_toml():
    """EngramStore.load_config reads TOML config."""
    print("\n── test_store_load_config_toml ──")
    engram_dir, store = _make_engram("config-toml")
    config_path = engram_dir / "config.toml"
    config_path.write_text('git_tracking = true\ntrace = false\n\n[policies]\ncommit-gate = "off"\n')

    cfg = store.load_config()
    assert_eq("git_tracking", cfg.get("git_tracking"), True)
    assert_eq("trace", cfg.get("trace"), False)
    assert_eq("policy off", cfg.get("policies", {}).get("commit-gate"), "off")


def test_store_load_config_missing():
    """EngramStore.load_config returns empty dict when no config exists."""
    print("\n── test_store_load_config_missing ──")
    engram_dir, store = _make_engram("config-missing")
    # Remove auto-created config.toml
    config_toml = engram_dir / "config.toml"
    if config_toml.is_file():
        config_toml.unlink()

    cfg = store.load_config()
    assert_eq("empty config", cfg, {})


def test_store_policy_config():
    """EngramStore.policy_config returns policies table."""
    print("\n── test_store_policy_config ──")
    engram_dir, store = _make_engram("policy-config")
    config_path = engram_dir / "config.toml"
    config_path.write_text('[policies]\ncommit-gate = "off"\ncapture-nudge = "off"\n')

    pc = store.policy_config()
    assert_eq("commit-gate off", pc.get("commit-gate"), "off")
    assert_eq("capture-nudge off", pc.get("capture-nudge"), "off")


def test_store_trace_enabled():
    """EngramStore.trace_enabled reads from config."""
    print("\n── test_store_trace_enabled ──")
    engram_dir, store = _make_engram("trace-config")
    config_path = engram_dir / "config.toml"

    config_path.write_text("trace = true\n")
    assert_eq("trace on", store.trace_enabled, True)

    config_path.write_text("trace = false\n")
    assert_eq("trace off", store.trace_enabled, False)


def test_engine_apply_config_disables():
    """PolicyEngine.apply_config disables policies."""
    print("\n── test_engine_apply_config_disables ──")

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
    assert_eq("only p2 fired", msg, "fired")


def test_init_creates_default_config():
    """store.init() creates config.toml from template when no config exists."""
    print("\n── test_init_creates_default_config ──")
    d = TEST_DIR / "init-config"
    d.mkdir(parents=True, exist_ok=True)
    engram_dir = d / ".engram"
    store = engram.EngramStore(str(engram_dir))
    store.init()

    config_path = engram_dir / "config.toml"
    assert_eq("config created", config_path.is_file(), True)
    content = config_path.read_text()
    assert_contains("has git_tracking", content, "git_tracking")
    assert_contains("has policies section", content, "[policies]")


# ── Content-aware context tests (E) ──────────────────────────────────

def test_extract_content_keywords():
    """_extract_content_keywords extracts meaningful words from edit content."""
    print("\n── test_extract_content_keywords ──")
    from engram._policy_defs import _extract_content_keywords

    # Edit with new_string
    data = {"tool_input": {"new_string": "def authenticate_user(self, token):\n    return verify(token)"}}
    kw = _extract_content_keywords(data)
    assert_contains("has authenticate", str(kw), "authenticate")
    # 'self' and 'return' should be filtered as code noise
    assert_not_contains("no self", str(kw), "self")

    # Empty input
    data2 = {"tool_input": {"new_string": ""}}
    kw2 = _extract_content_keywords(data2)
    assert_eq("empty result", kw2, [])

    # Short words filtered
    data3 = {"tool_input": {"content": "the and for"}}
    kw3 = _extract_content_keywords(data3)
    assert_eq("short words filtered", kw3, [])


def test_extract_content_keywords_max():
    """_extract_content_keywords respects max_words."""
    print("\n── test_extract_content_keywords_max ──")
    from engram._policy_defs import _extract_content_keywords
    data = {"tool_input": {"new_string": "authenticate validate serialize compress encrypt"}}
    kw = _extract_content_keywords(data, max_words=2)
    assert_eq("max 2 words", len(kw), 2)


# ── Smarter nudges tests (C) ─────────────────────────────────────────

def test_capture_nudge_requires_3_edits():
    """capture-nudge only fires after 3+ edits."""
    print("\n── test_capture_nudge_requires_3_edits ──")
    engram_dir, store = _make_engram("capture-nudge-threshold")
    store.reindex()

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _capture_nudge_condition
        state = _make_session_state("cn-threshold")

        # 0 edits — should not fire
        data = {"tool_input": {"file_path": "src/main.py"}}
        result = _capture_nudge_condition(data, state)
        assert_eq("no fire at 0 edits", result, None)

        # Record 2 edits — still shouldn't fire
        state.record_edit("src/a.py")
        state.record_edit("src/b.py")
        result = _capture_nudge_condition(data, state)
        assert_eq("no fire at 2 edits", result, None)

        # Record 3rd edit — now it should fire
        state.record_edit("src/c.py")
        result = _capture_nudge_condition(data, state)
        assert_eq("fires at 3 edits", result.matched, True)
    finally:
        os.chdir(orig_cwd)


def test_stop_nudge_silent_for_readonly():
    """stop-nudge doesn't nudge for read-only sessions."""
    print("\n── test_stop_nudge_silent_for_readonly ──")
    engram_dir, store = _make_engram("stop-nudge-readonly")
    store.reindex()

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _stop_nudge_condition
        state = _make_session_state("sn-readonly")
        # No edits recorded — read-only session
        result = _stop_nudge_condition({}, state)
        assert_eq("ok", result.ok, True)
        # Should NOT have the "No new decision signals" reason
        reason = result.reason or ""
        assert_not_contains("no nudge for readonly", reason, "No new decision signals")
    finally:
        os.chdir(orig_cwd)


def test_stop_nudge_fires_with_edits():
    """stop-nudge nudges when session has edits but no signals."""
    print("\n── test_stop_nudge_fires_with_edits ──")
    engram_dir, store = _make_engram("stop-nudge-edits")
    store.reindex()

    orig_cwd = os.getcwd()
    os.chdir(engram_dir.parent)
    try:
        from engram._policy_defs import _stop_nudge_condition
        state = _make_session_state("sn-edits")
        state.record_edit("src/main.py")
        result = _stop_nudge_condition({}, state)
        assert_eq("ok", result.ok, True)
        assert_contains("nudge with edits", result.reason, "No new decision signals")
    finally:
        os.chdir(orig_cwd)


def test_decision_language_per_phrase_dedup():
    """decision-language deduplicates by matched phrase, not globally."""
    print("\n── test_decision_language_per_phrase_dedup ──")
    from engram._policy_defs import _decision_language_condition
    state = _make_session_state("dl-dedup")

    # First "let's go with" match
    data1 = {"tool_input": {"content": "Let's go with PostgreSQL"}}
    r1 = _decision_language_condition(data1, state)
    assert_eq("first match", r1.matched, True)

    # Same phrase again — should be suppressed
    data2 = {"tool_input": {"content": "Let's go with MySQL instead"}}
    r2 = _decision_language_condition(data2, state)
    assert_eq("same phrase suppressed", r2, None)

    # Different phrase — should fire
    data3 = {"tool_input": {"content": "We decided on Redis"}}
    r3 = _decision_language_condition(data3, state)
    assert_eq("different phrase fires", r3.matched, True)


# ── Trace tests (B) ─────────────────────────────────────────────────

def test_engine_trace_collection():
    """PolicyEngine collects trace entries during evaluate."""
    print("\n── test_engine_trace_collection ──")

    def match_policy(d, s):
        return engram.PolicyResult(matched=True, system_message="hit")

    def skip_policy(d, s):
        return None

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("p-match", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], match_policy))
    engine.register(engram.Policy("p-skip", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], skip_policy))

    state = _make_session_state("trace")
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)

    assert_eq("trace has 2 entries", len(engine._last_trace), 2)
    assert_eq("first matched", engine._last_trace[0]["matched"], True)
    assert_eq("first policy", engine._last_trace[0]["policy"], "p-match")
    assert_eq("second not matched", engine._last_trace[1]["matched"], False)


def test_engine_trace_disabled_policy():
    """Trace shows disabled policies as skipped."""
    print("\n── test_engine_trace_disabled_policy ──")

    def always(d, s):
        return engram.PolicyResult(matched=True, system_message="x")

    engine = engram.PolicyEngine()
    engine.register(engram.Policy("enabled", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], always))
    engine.register(engram.Policy("disabled", "", engram.PolicyLevel.NUDGE, ["PostToolUse"], ["*"], always))
    engine.apply_config({"disabled": "off"})

    state = _make_session_state("trace-disabled")
    engine.evaluate("PostToolUse", {"tool_name": "Write"}, state)

    disabled_trace = [t for t in engine._last_trace if t["policy"] == "disabled"]
    assert_eq("disabled traced", len(disabled_trace), 1)
    assert_eq("skipped reason", disabled_trace[0]["skipped"], "disabled")


def test_policy_command_with_trace():
    """python3 -m engram policy --trace outputs trace JSON."""
    print("\n── test_policy_command_with_trace ──")
    import subprocess

    parent_dir = str(Path(__file__).resolve().parent.parent)
    result = subprocess.run(
        [sys.executable, "-m", "engram", "policy", "--trace", "PostToolUse"],
        input='{"tool_name": "Read"}',
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": parent_dir},
    )
    assert_eq("exit code", result.returncode, 0)
    output = json.loads(result.stdout)
    assert_contains("has result", str(output), "result")
    assert_contains("has trace", str(output), "trace")


# ── Runner ──────────────────────────────────────────────────────────

def main():
    print("=== engram policy tests ===")

    # Engine tests
    test_engine_list_policies()
    test_engine_evaluate_empty()
    test_engine_block_stops_evaluation()
    test_engine_nudge_collects_all()
    test_engine_once_per_session()
    test_engine_exception_isolation()

    # Policy tests
    test_commit_gate_blocks_plain_commit()
    test_commit_gate_allows_amend()
    test_commit_gate_allows_with_signal()
    test_delete_guard_blocks_rm()
    test_delete_guard_allows_other()
    test_delete_guard_blocks_git_checkout()
    test_edit_guard_blocks_empty_new_string()
    test_edit_guard_allows_other_files()
    test_edit_guard_allows_signal_edit_with_content()
    test_content_validation_rejects_missing_frontmatter()
    test_content_validation_accepts_valid()
    test_content_validation_skips_non_signal()
    test_session_context_injects_brief()
    test_push_resync_triggers_on_push()
    test_push_resync_ignores_other()
    test_decision_language_detects()
    test_decision_language_detects_query()
    test_decision_language_ignores_normal()
    test_stop_nudge_no_signals()
    test_capture_nudge_fires_on_code_edit()
    test_capture_nudge_skips_test_files()
    test_session_state_has_fired()
    test_session_state_recent_signals()
    test_full_engine_with_all_policies()
    test_policy_list_command()

    # Activity tracking (F)
    test_session_state_activity_tracking()
    test_session_state_activity_skips_engram()
    test_engine_records_edits()

    # TOML Config (A)
    test_store_load_config_toml()
    test_store_load_config_missing()
    test_store_policy_config()
    test_store_trace_enabled()
    test_engine_apply_config_disables()
    test_init_creates_default_config()

    # Content-aware context (E)
    test_extract_content_keywords()
    test_extract_content_keywords_max()

    # Smarter nudges (C)
    test_capture_nudge_requires_3_edits()
    test_stop_nudge_silent_for_readonly()
    test_stop_nudge_fires_with_edits()
    test_decision_language_per_phrase_dedup()

    # Trace (B)
    test_engine_trace_collection()
    test_engine_trace_disabled_policy()
    test_policy_command_with_trace()

    # Summary
    print(f"\n{'=' * 40}")
    total = PASS + FAIL
    print(f"  {PASS}/{total} passed")
    if FAIL:
        print(f"  {FAIL} FAILED")

    # Cleanup
    shutil.rmtree(TEST_DIR, ignore_errors=True)

    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
