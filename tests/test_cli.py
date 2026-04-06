"""CLI tests — covers all commands in cli.py."""

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from decision.cli import main, _cmd_policy

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "src"


def _decisions_dir_for(tmp_path):
    """Return the decisions dir that _with_home will set up."""
    return tmp_path.resolve() / ".claude" / "decisions"


def _with_home(tmp_path):
    """Patch HOME and decisions dir to tmp_path for isolated CLI tests."""
    resolved = tmp_path.resolve()
    decisions_dir = resolved / ".claude" / "decisions"
    home_patch = patch.dict(os.environ, {"HOME": str(resolved)})
    # Prevent DecisionStore from auto-discovering the real repo's .claude/decisions/
    repo_patch = patch("decision.utils.git.get_repo_root", return_value=resolved)
    # Isolate state dir to avoid db collisions with real repo
    state_dir = resolved / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_patch = patch("decision.utils.helpers._state_dir", return_value=state_dir)

    class _combined:
        def __enter__(self):
            home_patch.__enter__()
            repo_patch.__enter__()
            state_patch.__enter__()
            return self

        def __exit__(self, *args):
            state_patch.__exit__(*args)
            repo_patch.__exit__(*args)
            home_patch.__exit__(*args)

    return _combined()


# ── Help ─────────────────────────────────────────────────────────────


def test_help_lists_user_commands(capsys):
    """help lists all user-facing commands."""
    with patch.object(sys, "argv", ["decision", "help"]):
        main()
    out = capsys.readouterr().out
    for cmd in ("search", "show", "list", "tags", "stats", "help"):
        assert cmd in out


def test_help_does_not_list_policy(capsys):
    """help does NOT list the internal policy command."""
    with patch.object(sys, "argv", ["decision", "help"]):
        main()
    out = capsys.readouterr().out
    assert "policy" not in out.lower() or "policy" not in out.split("Commands:")[1]


def test_main_no_args_shows_help(capsys):
    """main() with no args prints help and exits 0."""
    with patch.object(sys, "argv", ["decision"]):
        with pytest.raises(SystemExit, match="0"):
            main()
    out = capsys.readouterr().out
    assert "search" in out


def test_main_unknown_command():
    """main() with unknown command exits 1."""
    with patch.object(sys, "argv", ["decision", "bogus"]):
        with pytest.raises(SystemExit, match="1"):
            main()


# ── Flag Aliases ─────────────────────────────────────────────────────


def test_flag_alias_help(capsys):
    """--help shows the same output as the help subcommand."""
    with patch.object(sys, "argv", ["decision", "--help"]):
        with pytest.raises(SystemExit, match="0"):
            main()
    out = capsys.readouterr().out
    assert "search" in out


def test_flag_alias_tags(tmp_path, capsys):
    """--tags works as an alias for the tags subcommand."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "--tags"]):
            main()
    # Should not raise — empty output is fine for 0 decisions


def test_flag_alias_stats(tmp_path, capsys):
    """--stats works as an alias for the stats subcommand."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "--stats"]):
            main()
    out = capsys.readouterr().out
    assert "Decisions:" in out


def test_flag_alias_coverage(tmp_path, capsys):
    """--coverage works as an alias for the coverage subcommand."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "--coverage"]):
            main()
    out = capsys.readouterr().out
    assert "coverage" in out.lower()


def test_flag_alias_health(tmp_path, capsys):
    """--health maps to stats --health."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "--health"]):
            main()
    out = capsys.readouterr().out
    assert "Decisions:" in out


# ── Search ───────────────────────────────────────────────────────────


def test_search_no_args():
    """search with no keywords exits 1."""
    with patch.object(sys, "argv", ["decision", "search"]):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_search_no_results(tmp_path, capsys):
    """search with no matching decisions prints message."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch.object(sys, "argv", ["decision", "search", "nonexistent"]):
            main()
    out = capsys.readouterr().out
    assert "No results" in out


def test_search_finds_decisions(tmp_path, capsys):
    """search finds indexed decisions."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "redis-caching")

        # Force index build
        from decision.store import DecisionStore

        store = DecisionStore(str(decisions_dir))
        store.search("redis")  # triggers index

        with patch.object(sys, "argv", ["decision", "search", "redis"]):
            main()
    out = capsys.readouterr().out
    assert "redis" in out.lower()


def test_search_json(tmp_path, capsys):
    """search --json returns valid JSON array."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch.object(sys, "argv", ["decision", "search", "nonexistent", "--json"]):
            main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)


def test_search_limit(tmp_path, capsys):
    """search --limit N respects the limit."""
    from conftest import make_decision
    from decision.utils.helpers import _discover_decisions_dir

    with _with_home(tmp_path):
        decisions_dir = _discover_decisions_dir()
        decisions_dir.mkdir(parents=True, exist_ok=True)
        for i in range(5):
            make_decision(decisions_dir, f"testing-item-{i}")

        # Build index
        from decision.store import DecisionStore

        store = DecisionStore(str(decisions_dir))
        store.search("testing")

        with patch.object(sys, "argv", ["decision", "search", "testing", "--limit", "2", "--json"]):
            main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert len(data) <= 2


# ── Show ─────────────────────────────────────────────────────────────


def test_show_no_args():
    """show with no slug exits 1."""
    with patch.object(sys, "argv", ["decision", "show"]):
        with pytest.raises(SystemExit, match="1"):
            main()


def test_show_exact_slug(tmp_path, capsys):
    """show with exact slug prints the decision."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "my-exact-decision")

        with patch.object(sys, "argv", ["decision", "show", "my-exact-decision"]):
            main()
    out = capsys.readouterr().out
    assert "my-exact-decision" in out
    assert "tags:" in out  # rendered metadata


def test_show_partial_match(tmp_path, capsys):
    """show with partial slug matches uniquely."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "unique-redis-caching")

        with patch.object(sys, "argv", ["decision", "show", "unique-redis"]):
            main()
    out = capsys.readouterr().out
    assert "unique-redis-caching" in out


def test_show_ambiguous(tmp_path, capsys):
    """show with ambiguous slug lists matches and exits 1."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "redis-caching")
        make_decision(decisions_dir, "redis-sessions")

        with patch.object(sys, "argv", ["decision", "show", "redis"]):
            with pytest.raises(SystemExit, match="1"):
                main()
    err = capsys.readouterr().err
    assert "Ambiguous" in err


def test_show_not_found(tmp_path):
    """show with unknown slug exits 1."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "show", "nonexistent"]):
            with pytest.raises(SystemExit, match="1"):
                main()


# ── List ─────────────────────────────────────────────────────────────


def test_list_empty(tmp_path, capsys):
    """list with no decisions prints message."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "list"]):
            main()
    out = capsys.readouterr().out
    assert "No decisions" in out


def test_list_shows_decisions(tmp_path, capsys):
    """list shows decision titles and dates."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "my-test-decision")

        with patch.object(sys, "argv", ["decision", "list"]):
            main()
    out = capsys.readouterr().out
    assert "my-test-decision" in out
    assert "2026-03-17" in out
    assert "decision(s)" in out


def test_list_tag_filter(tmp_path, capsys):
    """list --tag filters by tag."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "tagged-one")

        with patch.object(sys, "argv", ["decision", "list", "--tag", "testing"]):
            main()
        out1 = capsys.readouterr().out
        assert "tagged-one" in out1

        with patch.object(sys, "argv", ["decision", "list", "--tag", "nonexistent"]):
            main()
        out2 = capsys.readouterr().out
        assert "No matching" in out2


def test_list_json(tmp_path, capsys):
    """list --json returns valid JSON array."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "json-test")

        with patch.object(sys, "argv", ["decision", "list", "--json"]):
            main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["slug"] == "json-test"
    assert "title" in data[0]
    assert "date" in data[0]
    assert "tags" in data[0]


def test_list_json_empty(tmp_path, capsys):
    """list --json with no decisions returns empty array."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "list", "--json"]):
            main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data == []


# ── Tags ─────────────────────────────────────────────────────────────


def test_tags_empty(tmp_path, capsys):
    """tags with no decisions prints message."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch.object(sys, "argv", ["decision", "tags"]):
            main()
    out = capsys.readouterr().out
    assert "No tags" in out


def test_tags_with_decisions(tmp_path, capsys):
    """tags shows sorted output with counts."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "one")
        make_decision(decisions_dir, "two")

        with patch.object(sys, "argv", ["decision", "tags"]):
            main()
    out = capsys.readouterr().out
    assert "testing:" in out


def test_tags_json(tmp_path, capsys):
    """tags --json returns valid JSON object."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "one")

        with patch.object(sys, "argv", ["decision", "tags", "--json"]):
            main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert isinstance(data, dict)
    assert "testing" in data


# ── Stats ────────────────────────────────────────────────────────────


def test_stats_empty(tmp_path, capsys):
    """stats with no decisions shows zeros."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch.object(sys, "argv", ["decision", "stats"]):
            main()
    out = capsys.readouterr().out
    assert "Decisions: 0" in out


def test_stats_with_decisions(tmp_path, capsys):
    """stats shows correct counts."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "one")
        make_decision(decisions_dir, "two")

        with patch.object(sys, "argv", ["decision", "stats"]):
            main()
    out = capsys.readouterr().out
    assert "Decisions: 2" in out
    assert "Tags:" in out
    assert "Index:" in out


def test_stats_json(tmp_path, capsys):
    """stats --json returns all expected keys."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch.object(sys, "argv", ["decision", "stats", "--json"]):
            main()
    out = capsys.readouterr().out
    data = json.loads(out)
    for key in ("total", "recent_30d", "unique_tags", "tagged", "untagged", "index_available"):
        assert key in data


# ── Policy (internal) ────────────────────────────────────────────────


def test_policy_list(capsys):
    """policy with no event lists all policies."""
    with patch.object(sys, "argv", ["decision", "policy"]):
        main()
    captured = capsys.readouterr()
    policies = json.loads(captured.out)
    assert len(policies) == 12


def test_policy_evaluate_event(capsys):
    """policy evaluates event with stdin JSON."""
    with patch.object(sys, "argv", ["decision", "policy", "PreToolUse"]):
        with patch("sys.stdin", StringIO('{"tool_name": "Read"}')):
            _cmd_policy()
    captured = capsys.readouterr()
    assert captured.out.strip()


def test_policy_evaluate_empty_stdin(capsys):
    """policy handles empty stdin."""
    with patch.object(sys, "argv", ["decision", "policy", "PreToolUse"]):
        with patch("sys.stdin", StringIO("")):
            _cmd_policy()
    captured = capsys.readouterr()
    assert captured.out.strip() == "{}"


def test_policy_evaluate_invalid_json(capsys):
    """policy handles invalid JSON input gracefully."""
    with patch.object(sys, "argv", ["decision", "policy", "PreToolUse"]):
        with patch("sys.stdin", StringIO("not json")):
            _cmd_policy()
    captured = capsys.readouterr()
    assert captured.out.strip() == "{}"


def test_policy_trace_flag(capsys):
    """policy with --trace includes trace in output."""
    with patch.object(sys, "argv", ["decision", "policy", "PreToolUse", "--trace"]):
        with patch("sys.stdin", StringIO('{"tool_name": "Read"}')):
            _cmd_policy()
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert "trace" in output
    assert "result" in output


def test_policy_trace_with_empty_result(capsys):
    """policy with --trace handles empty result."""
    with patch.object(sys, "argv", ["decision", "policy", "PostToolUse", "--trace"]):
        with patch("sys.stdin", StringIO('{"tool_name": "Read"}')):
            _cmd_policy()
    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert "trace" in output


# ── Subprocess CLI tests ─────────────────────────────────────────────


def test_subprocess_policy_list():
    """Subprocess: python3 -m decision policy lists all 10 policies."""
    result = subprocess.run(
        [sys.executable, "-m", "decision", "policy"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PLUGIN_DIR)},
    )
    assert result.returncode == 0
    policies = json.loads(result.stdout)
    assert len(policies) == 12


def test_subprocess_policy_evaluate():
    """Subprocess: python3 -m decision policy PreToolUse evaluates stdin JSON."""
    result = subprocess.run(
        [sys.executable, "-m", "decision", "policy", "PreToolUse"],
        input='{"tool_name": "Read"}',
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PLUGIN_DIR)},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert isinstance(output, dict)


def test_subprocess_trace_flag():
    """Subprocess: --trace produces trace+result keys."""
    result = subprocess.run(
        [sys.executable, "-m", "decision", "policy", "PreToolUse", "--trace"],
        input='{"tool_name": "Read"}',
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(PLUGIN_DIR)},
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "trace" in output
    assert "result" in output


def test_main_routes_list(tmp_path, capsys):
    """main() routes 'list'."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "list"]):
            main()
    out = capsys.readouterr().out
    assert "No decisions" in out


# ── Search grouping & render ───────────────────────────────────────


def test_search_grouped(tmp_path, capsys):
    """search --group groups results by tag."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        for i in range(6):
            make_decision(decisions_dir, f"testing-item-{i}")

        from decision.store import DecisionStore

        store = DecisionStore(str(decisions_dir))
        store.search("testing")

        with patch.object(sys, "argv", ["decision", "search", "testing", "--group"]):
            main()
    out = capsys.readouterr().out
    assert "testing" in out


def test_show_renders_decision(tmp_path, capsys):
    """show renders metadata and body of a decision."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "render-test", tags=["auth"], affects=["src/auth.py"])

        with patch.object(sys, "argv", ["decision", "show", "render-test"]):
            main()
    out = capsys.readouterr().out
    assert "render-test" in out
    assert "auth" in out
    assert "src/auth.py" in out


def test_show_substring_suggestion(tmp_path, capsys):
    """show with a slug that only substring-matches gives suggestions."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "my-auth-decision")

        with patch.object(sys, "argv", ["decision", "show", "auth"]):
            with pytest.raises(SystemExit, match="1"):
                main()
    err = capsys.readouterr().err
    assert "Similar" in err


def test_show_not_found_no_dir(tmp_path):
    """show exits 1 when decisions dir doesn't exist."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "show", "nonexistent"]):
            with pytest.raises(SystemExit, match="1"):
                main()


def test_stats_text_output(tmp_path, capsys):
    """stats text output includes all sections."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "affects-dec", affects=["src/app.py"])
        make_decision(decisions_dir, "no-affects-dec")

        with patch.object(sys, "argv", ["decision", "stats"]):
            main()
    out = capsys.readouterr().out
    assert "Decisions:" in out
    assert "Recent" in out
    assert "Affects:" in out
    assert "missing affects" in out


def test_version_flag(capsys):
    """--version prints version and exits 0."""
    with patch.object(sys, "argv", ["decision", "--version"]):
        with pytest.raises(SystemExit, match="0"):
            main()
    out = capsys.readouterr().out
    assert "decision" in out


# ── Undo ──────────────────────────────────────────────────────────────


def test_undo_most_recent_untracked(tmp_path, capsys):
    """undo with no slug deletes the most recent untracked file."""
    import time

    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        old = make_decision(decisions_dir, "old-decision", date="2026-03-01")
        target = make_decision(decisions_dir, "new-decision", date="2026-03-20")
        # Explicitly stagger mtimes so sort order is deterministic
        now = time.time()
        os.utime(old, (now - 10, now - 10))
        os.utime(target, (now, now))

        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")):
            with patch.object(sys, "argv", ["decision", "undo"]):
                main()
        out = capsys.readouterr().out
        assert "Deleted: new-decision" in out
        assert not target.exists()


def test_undo_with_slug(tmp_path, capsys):
    """undo with a specific slug deletes that file."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        target = make_decision(decisions_dir, "my-slug")

        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")):
            with patch.object(sys, "argv", ["decision", "undo", "my-slug"]):
                main()
        out = capsys.readouterr().out
        assert "Deleted: my-slug" in out
        assert not target.exists()


def test_undo_git_tracked(tmp_path, capsys):
    """undo restores from git when the file is tracked."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        target = make_decision(decisions_dir, "tracked-dec")

        def fake_run(cmd, **kwargs):
            if "ls-files" in cmd:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=str(target), stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            with patch.object(sys, "argv", ["decision", "undo", "tracked-dec"]):
                main()
        out = capsys.readouterr().out
        assert "Restored: tracked-dec (from git)" in out


def test_undo_no_decisions_dir(tmp_path):
    """undo exits 1 when decisions dir doesn't exist."""
    with _with_home(tmp_path):
        # Do NOT create decisions dir
        with patch.object(sys, "argv", ["decision", "undo"]):
            with pytest.raises(SystemExit, match="1"):
                main()


def test_undo_no_decisions_to_undo(tmp_path):
    """undo exits 1 when decisions dir is empty and no slug given."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch.object(sys, "argv", ["decision", "undo"]):
            with pytest.raises(SystemExit, match="1"):
                main()


def test_undo_git_timeout(tmp_path, capsys):
    """undo falls through to delete when git times out."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        target = make_decision(decisions_dir, "timeout-dec")

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5)):
            with patch.object(sys, "argv", ["decision", "undo", "timeout-dec"]):
                main()
        out = capsys.readouterr().out
        assert "Deleted: timeout-dec" in out
        assert not target.exists()


# ── Health ────────────────────────────────────────────────────────────


def test_stats_health_stale_and_orphaned(tmp_path, capsys):
    """stats --health shows stale decisions and orphaned affects."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(
            decisions_dir,
            "stale-dec",
            affects=["src/nonexistent_file.py"],
            date="2025-01-01",
        )

        def fake_run(cmd, **kwargs):
            if "git" in cmd and "log" in cmd:
                # Return --format=%H %aI --name-only output with enough commits
                blocks = []
                for i in range(15):
                    h = f"{'a' * 40}"
                    blocks.append(f"{h} 2025-06-{i + 1:02d}T00:00:00+00:00")
                    blocks.append("src/nonexistent_file.py")
                    blocks.append("")
                lines = "\n".join(blocks)
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=lines, stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=fake_run):
            with patch.object(sys, "argv", ["decision", "stats", "--health"]):
                main()
        out = capsys.readouterr().out
        assert "Potentially stale" in out
        assert "stale-dec" in out
        assert "Orphaned affects" in out


def test_stats_health_clean(tmp_path, capsys):
    """stats --health shows clean output when no issues."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        # Create a real file for the affects path
        src_dir = tmp_path.resolve() / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        real_file = src_dir / "app.py"
        real_file.write_text("# app")
        make_decision(decisions_dir, "healthy-dec", affects=["src/app.py"], date="2026-03-25")

        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")):
            with patch.object(sys, "argv", ["decision", "stats", "--health"]):
                main()
        out = capsys.readouterr().out
        assert "No stale decisions" in out


def test_stats_health_git_exception(tmp_path, capsys):
    """stats --health continues when git log raises an exception."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "err-dec", affects=["src/broken.py"], date="2025-01-01")

        with patch("subprocess.run", side_effect=Exception("git broke")):
            with patch.object(sys, "argv", ["decision", "stats", "--health"]):
                main()
        out = capsys.readouterr().out
        # Should not crash — prints no stale since exception skips the decision
        assert "Decisions:" in out


# ── Dismiss ───────────────────────────────────────────────────────────


def test_dismiss_command(tmp_path, capsys):
    """dismiss prints confirmation."""
    with _with_home(tmp_path):
        with patch.object(sys, "argv", ["decision", "dismiss"]):
            main()
    out = capsys.readouterr().out
    assert "Nudges dismissed" in out


# ── Coverage ──────────────────────────────────────────────────────────


def test_coverage_text_output(tmp_path, capsys):
    """coverage shows text output with coverage percentage."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "auth-dec", affects=["src/auth/"])

        with patch("subprocess.run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="src/auth/login.py\nsrc/billing/charge.py\n", stderr=""
        )):
            with patch.object(sys, "argv", ["decision", "coverage"]):
                main()
        out = capsys.readouterr().out
        assert "Decision coverage:" in out
        assert "%" in out


def test_coverage_json_output(tmp_path, capsys):
    """coverage --json returns valid JSON with expected keys."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "auth-dec", affects=["src/auth/"])

        with patch("subprocess.run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="src/auth/login.py\nsrc/billing/charge.py\n", stderr=""
        )):
            with patch.object(sys, "argv", ["decision", "coverage", "--json"]):
                main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "total_files" in data
        assert "covered" in data
        assert "uncovered" in data
        assert "coverage_pct" in data
        assert "uncovered_dirs" in data


def test_coverage_no_source_files(tmp_path, capsys):
    """coverage shows message when no source files found."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )):
            with patch.object(sys, "argv", ["decision", "coverage"]):
                main()
        out = capsys.readouterr().out
        assert "No source files" in out


def test_coverage_git_unavailable(tmp_path):
    """coverage exits 1 when git is not available."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            with patch.object(sys, "argv", ["decision", "coverage"]):
                with pytest.raises(SystemExit, match="1"):
                    main()


def test_coverage_excludes_non_code_files(tmp_path, capsys):
    """coverage excludes images, LICENSE, Makefile, and other non-code files."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        git_output = "src/app.py\nassets/logo.png\nLICENSE\nMakefile\nstatic/icon.svg\n"
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout=git_output, stderr=""
        )):
            with patch.object(sys, "argv", ["decision", "coverage", "--json"]):
                main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_files"] == 1  # only src/app.py


def test_group_by_dir():
    """_group_by_dir groups files by parent directory."""
    from decision.cli import _group_by_dir

    result = _group_by_dir(["src/a.py", "src/b.py", "lib/c.py"])
    assert result == {"src": 2, "lib": 1}


def test_group_by_dir_root():
    """_group_by_dir handles root-level files."""
    from decision.cli import _group_by_dir

    result = _group_by_dir(["setup.py", "Makefile"])
    assert result == {".": 2}


# ── Show edge cases ──────────────────────────────────────────────────


def test_show_not_found_no_substring_match(tmp_path, capsys):
    """show with a slug that has no substring matches gives 'Try: search' hint."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "alpha-beta")

        with patch.object(sys, "argv", ["decision", "show", "zzz-nothing"]):
            with pytest.raises(SystemExit, match="1"):
                main()
    err = capsys.readouterr().err
    assert "Try:" in err


# ── Tree command ─────────────────────────────────────────────────────


def test_tree_empty(tmp_path, capsys):
    """tree with no decisions shows empty message."""
    with _with_home(tmp_path):
        _decisions_dir_for(tmp_path).mkdir(parents=True, exist_ok=True)
        with patch.object(sys, "argv", ["decision", "tree"]):
            main()
    out = capsys.readouterr().out
    assert "No decisions found" in out


def test_tree_groups_by_area(tmp_path, capsys):
    """tree groups decisions by their affects directory."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "auth-jwt", affects=["src/auth/"])
        make_decision(decisions_dir, "cache-redis", affects=["src/cache/store.py"])

        with patch.object(sys, "argv", ["decision", "tree"]):
            main()
    out = capsys.readouterr().out
    assert "src/auth/" in out
    assert "auth-jwt" in out
    assert "src/cache/" in out
    assert "cache-redis" in out


def test_tree_json(tmp_path, capsys):
    """tree --json returns structured output."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "test-dec", affects=["src/api/"])

        with patch.object(sys, "argv", ["decision", "tree", "--json"]):
            main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "areas" in data


def test_tree_no_affects_group(tmp_path, capsys):
    """tree shows decisions without affects in a fallback group."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "no-affects-dec", affects=[])

        with patch.object(sys, "argv", ["decision", "tree"]):
            main()
    out = capsys.readouterr().out
    assert "no affects" in out


# ── Enrich command ───────────────────────────────────────────────────


def test_enrich_thin_decision(tmp_path, capsys):
    """enrich identifies reasoning gaps in a thin decision."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "thin-dec", body="Short body.", affects=["src/"])

        with patch.object(sys, "argv", ["decision", "enrich", "thin-dec"]):
            main()
    out = capsys.readouterr().out
    assert "Reasoning gaps" in out or "reasoning" in out.lower()


def test_enrich_json_output(tmp_path, capsys):
    """enrich --json returns structured findings."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "json-dec", affects=["src/"])

        with patch.object(sys, "argv", ["decision", "enrich", "json-dec", "--json"]):
            main()
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "conflicts" in data
    assert "reasoning_gaps" in data
    assert "missing_affects" in data
    assert "suggestions" in data


def test_enrich_well_formed(tmp_path, capsys):
    """enrich reports no issues for a well-formed decision."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        # Create the affects directory so it's not flagged as stale
        (tmp_path.resolve() / "src" / "cache").mkdir(parents=True, exist_ok=True)

        make_decision(
            decisions_dir,
            "good-dec",
            body=(
                "Chose Redis over Memcached because it supports pub/sub natively. "
                "Instead of rolling our own message queue, Redis provides reliable delivery "
                "with minimal operational overhead. The trade-off is slightly higher memory usage, "
                "but the simplicity of a single service outweighs the cost."
            ),
            affects=["src/cache/"],
        )

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path.resolve())
            with patch.object(sys, "argv", ["decision", "enrich", "good-dec"]):
                main()
        finally:
            os.chdir(old_cwd)
    out = capsys.readouterr().out
    assert "no enrichment needed" in out.lower() or "well-formed" in out.lower()


# ── Surfacing analytics ──────────────────────────────────────────────


def test_stats_health_surfacing_analytics(tmp_path, capsys):
    """stats --health shows surfacing analytics when history exists."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "surfaced-dec", affects=["src/api/"])
        make_decision(decisions_dir, "never-dec", affects=["src/db/"])

        # Write surfacing history — surfaced-dec seen 15 times, never-dec absent
        state_dir = tmp_path.resolve() / ".state"
        state_dir.mkdir(parents=True, exist_ok=True)
        history_path = state_dir / "surfacing_history.json"
        history_path.write_text(json.dumps({"surfaced-dec": 15}))

        with patch.object(sys, "argv", ["decision", "stats", "--health"]):
            with patch("subprocess.run", side_effect=Exception("no git")):
                main()
    out = capsys.readouterr().out
    assert "Surfacing analytics" in out
    assert "never-dec" in out.lower() or "Never surfaced" in out


def test_stats_health_no_surfacing_data(tmp_path, capsys):
    """stats --health shows 'no data yet' when no surfacing history."""
    from conftest import make_decision

    with _with_home(tmp_path):
        decisions_dir = _decisions_dir_for(tmp_path)
        decisions_dir.mkdir(parents=True, exist_ok=True)
        make_decision(decisions_dir, "some-dec", affects=["src/"])

        with patch.object(sys, "argv", ["decision", "stats", "--health"]):
            with patch("subprocess.run", side_effect=Exception("no git")):
                main()
    out = capsys.readouterr().out
    assert "no data yet" in out

