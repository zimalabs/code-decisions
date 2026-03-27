"""Content validation policy tests — frontmatter, affects, stale paths, tags, YAML, overlap."""

import os

import pytest

import decision
from conftest import make_session_state, make_decision, make_store


# ── content-validation tests ────────────────────────────────────────


def test_content_validation_rejects_missing_frontmatter():
    """content-validation rejects content without frontmatter."""
    from decision.policy.defs import _content_validation_condition

    state = make_session_state("cv-missing")
    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/bad.md",
            "content": "No frontmatter here\nJust plain text\n",
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert result.ok is False
    assert "frontmatter" in str(result.reason)


def test_content_validation_accepts_valid():
    """content-validation accepts valid decision content."""
    from decision.policy.defs import _content_validation_condition

    state = make_session_state("cv-valid")
    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/good.md",
            "content": (
                '---\nname: "good"\ndescription: "A good decision"\n'
                'date: "2026-03-17"\ntags:\n  - "testing"\n'
                'affects:\n  - "app/main.py"\n---\n\n'
                "# Good Decision\n\nThis is a valid decision with sufficient rationale.\n\n"
                "## Alternatives\n"
                "- Option A was considered but rejected because it lacks the required capabilities for this use case\n\n"
                "## Rationale\n"
                "Chosen for testing purposes because it provides the specific behavior we need for validation.\n\n"
                "## Trade-offs\n"
                "Not applicable: test fixture with no real-world trade-offs.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert result.ok is not False
    assert "Decision written:" in str(result.system_message)
    assert "good.md" in str(result.system_message)


def test_content_validation_skips_non_decision():
    """content-validation ignores non-decision file paths."""
    from decision.policy.defs import _content_validation_condition

    state = make_session_state("cv-skip")
    data = {
        "tool_input": {
            "file_path": "src/main.py",
            "content": "no frontmatter",
        }
    }
    result = _content_validation_condition(data, state)
    assert result is None


# ── affects warning tests ────────────────────────────────────────


def test_content_validation_warns_empty_affects():
    """content-validation suggests affects when any files have been edited."""
    from decision.policy.defs import _content_validation_condition

    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/no_affects.md",
            "content": (
                '---\nname: "no-affects"\ndescription: "No affects field"\ntype: "decision"\n'
                'date: "2026-03-19"\ntags:\n  - "testing"\n---\n\n'
                "# Decision Without Affects\n\nThis decision has no affects field.\n\n"
                "## Alternatives\n"
                "- Option A was considered but rejected because it lacks the required capabilities\n"
                "- Option B was also rejected due to performance concerns in production\n\n"
                "## Rationale\n"
                "The `target_module.run()` function needs p99 latency under 100ms; "
                "this approach achieves 50ms.\n\n"
                "## Trade-offs\n"
                "Migration required for existing callers — estimated 3 hours of work.\n"
            ),
        }
    }

    # No edits → metadata echo + missing affects warning
    state = make_session_state("cv-affects-warn")
    result = _content_validation_condition(data, state)
    assert result is not None
    assert "Decision written:" in str(result.system_message)
    assert "no `affects` paths" in str(result.system_message) or "Auto-suggested" in str(result.system_message)

    # With 1 edit: rejects so agent re-writes with affects
    state1 = make_session_state("cv-affects-warn-one-edit")
    state1.record_edit("src/a.py")
    result1 = _content_validation_condition(data, state1)
    assert result1 is not None
    assert result1.matched is True
    assert result1.ok is False
    assert result1.decision == "reject"
    assert "affects" in result1.reason

    # With 3+ edits: still rejects with inferred affects
    state2 = make_session_state("cv-affects-warn-edits")
    state2.record_edit("src/a.py")
    state2.record_edit("src/b.py")
    state2.record_edit("src/c.py")
    result2 = _content_validation_condition(data, state2)
    assert result2 is not None
    assert result2.matched is True
    assert result2.ok is False
    assert result2.decision == "reject"
    assert "affects" in result2.reason


# ── Auto-suggest affects tests ──────────────────────────────────────


def test_content_validation_suggests_affects_from_session():
    """content-validation suggests affects paths from session edits."""
    from decision.policy.defs import _content_validation_condition

    state = make_session_state("cv-affects-suggest")
    state.record_edit("src/auth/handler.py")
    state.record_edit("src/auth/middleware.py")
    state.record_edit("src/auth/config.py")

    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/no_affects2.md",
            "content": (
                '---\nname: "no-affects2"\ndescription: "No affects"\ntype: "decision"\n'
                'date: "2026-03-20"\ntags:\n  - "auth"\n---\n\n'
                "# Auth Decision\n\nChose JWT over sessions for stateless auth.\n\n"
                "## Alternatives\n"
                "- Sessions — but requires sticky load balancing which adds operational complexity\n"
                "- OAuth only — however doesn't work for service-to-service auth in our architecture\n\n"
                "## Rationale\n"
                "The `auth.handler` module needs p99 latency under 50ms; "
                "JWT avoids database lookups on every request.\n\n"
                "## Trade-offs\n"
                "Token revocation requires a blocklist — 500ms extra latency on logout.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert result.matched is True
    # With smart inference, 3 files in same dir → directory prefix; rejects so agent re-writes
    assert result.ok is False
    assert result.decision == "reject"
    assert "src/auth/" in result.reason
    assert "affects" in result.reason


# ── Lightweight capture tests ──────────────────────────────────────


def test_content_validation_accepts_without_sections():
    """content-validation accepts decisions without sections."""
    from decision.policy.defs import _content_validation_condition

    state = make_session_state("cv-no-sections")
    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/light.md",
            "content": (
                '---\nname: "light"\ndescription: "Quick decision"\n'
                'date: "2026-03-20"\ntags:\n  - "styling"\n'
                'affects:\n  - "app/styles.css"\n---\n\n'
                "# Used Tailwind over CSS modules\n\n"
                "The rest of the project uses Tailwind and switching would fragment the styling approach.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None, "Decisions without sections should still get metadata echo"
    assert result.ok is not False
    assert "Decision written:" in str(result.system_message)
    assert "light.md" in str(result.system_message)


def test_content_validation_rejects_missing_title():
    """content-validation still requires title."""
    from decision.policy.defs import _content_validation_condition

    state = make_session_state("cv-no-title")
    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/bad_light.md",
            "content": (
                '---\nname: "bad-light"\ndescription: "Missing title"\n'
                'date: "2026-03-20"\ntags:\n  - "test"\n---\n\n'
                "No H1 title here, just text.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert result.decision == "reject"
    assert "title" in str(result.reason)


# ── Stale affects path warning ──────────────────────────────────────


def test_content_validation_warns_stale_affects(tmp_path):
    """content-validation warns when affects paths don't exist on disk."""
    from decision.policy.defs import _content_validation_condition

    # Change to tmp_path so relative paths are checked there
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Create a src/ dir but not src/nonexistent.py
        (tmp_path / "src").mkdir()
        _, store = make_store(tmp_path)

        state = make_session_state("cv-stale-affects", store=store)
        data = {
            "tool_input": {
                "file_path": "/home/user/.claude/projects/test/decisions/stale.md",
                "content": (
                    '---\nname: "stale"\ndescription: "Has stale paths"\ntype: "decision"\n'
                    'date: "2026-03-20"\ntags:\n  - "test"\n'
                    'affects:\n  - "src/nonexistent.py"\n---\n\n'
                    "# Stale Affects\n\nThis decision references a file that doesn't exist.\n\n"
                    "## Alternatives\n"
                    "- Option A — rejected because it doesn't meet requirements for our use case\n"
                    "- Option B — rejected due to performance concerns in production environment\n\n"
                    "## Rationale\n"
                    "The `handler.process()` function needs p99 latency under 100ms; "
                    "this approach achieves 50ms.\n\n"
                    "## Trade-offs\n"
                    "Migration required for existing callers — estimated 3 hours of work.\n"
                ),
            }
        }
        result = _content_validation_condition(data, state)
        assert result is not None
        assert "stale" in str(result.system_message).lower() or "not found" in str(result.system_message).lower()
    finally:
        os.chdir(old_cwd)


def test_content_validation_skips_stale_warning_for_session_edited_files(tmp_path):
    """affects paths that were edited this session are not flagged as stale."""
    from decision.policy.defs import _content_validation_condition

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # src/ exists but src/deleted.py does not (it was deleted this session)
        (tmp_path / "src").mkdir()
        _, store = make_store(tmp_path)

        state = make_session_state("cv-stale-session-edit", store=store)
        # Simulate that src/deleted.py was edited (and then deleted) this session
        state.record_edit("src/deleted.py")

        data = {
            "tool_input": {
                "file_path": "/home/user/.claude/projects/test/decisions/del.md",
                "content": (
                    '---\nname: "del"\ndescription: "Refs deleted file"\ntype: "decision"\n'
                    'date: "2026-03-20"\ntags:\n  - "test"\n'
                    'affects:\n  - "src/deleted.py"\n---\n\n'
                    "# Deleted File Decision\n\nThis decision references a file deleted this session.\n\n"
                    "## Alternatives\n"
                    "- Option A — rejected because it doesn't meet requirements for our use case\n"
                    "- Option B — rejected due to performance concerns in production environment\n\n"
                    "## Rationale\n"
                    "The `handler.process()` function needs p99 latency under 100ms; "
                    "this approach achieves 50ms.\n\n"
                    "## Trade-offs\n"
                    "Migration required for existing callers — estimated 3 hours of work.\n"
                ),
            }
        }
        result = _content_validation_condition(data, state)
        # Should NOT warn about stale paths — the file was touched this session
        # (metadata echo is expected)
        assert result is None or "not found" not in str(result.system_message or "").lower()
    finally:
        os.chdir(old_cwd)


# ── Tag similarity warning in content validation ─────────────────────


def test_content_validation_tag_similarity_warning(tmp_path):
    """content-validation warns on near-duplicate tags."""
    decisions_dir, store = make_store(tmp_path)
    # Create an existing decision with tag "hooks"
    make_decision(decisions_dir, "existing", tags=["hooks"])

    from decision.policy.content_validation import _content_validation_condition

    state = make_session_state("cv-tag-sim", store=store)
    # Write a new decision with similar tag "hook" (plural mismatch)
    data = {
        "tool_input": {
            "file_path": str(decisions_dir / "new-hook.md"),
            "content": (
                '---\nname: "new-hook"\ndescription: "Test"\ntype: "decision"\n'
                'date: "2026-03-17"\ntags:\n  - "hook"\n---\n\n'
                "# New Hook Decision\n\nThis is a lightweight decision about hooks.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert "similar" in str(result.system_message).lower()


# ── Multi-line YAML detection tests ──────────────────────────────────


def test_frontmatter_collapses_literal_block_scalar():
    """Frontmatter parser auto-collapses literal block scalars (|) to single line."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    text = '---\ndescription: |\n  This is a\n  multi-line value\n---\nBody\n'
    fields, content = _split_yaml_frontmatter(text)
    assert fields["description"] == "This is a multi-line value"


def test_frontmatter_collapses_folded_block_scalar():
    """Frontmatter parser auto-collapses folded block scalars (>) to single line."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    text = '---\ndescription: >\n  This is a\n  folded value\n---\nBody\n'
    fields, content = _split_yaml_frontmatter(text)
    assert fields["description"] == "This is a folded value"


def test_frontmatter_block_scalar_with_strip_indicator():
    """Block scalar with strip indicator (|-) is handled."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    text = '---\ndescription: |-\n  Stripped block\n  content here\n---\nBody\n'
    fields, _ = _split_yaml_frontmatter(text)
    assert fields["description"] == "Stripped block content here"


def test_frontmatter_block_scalar_followed_by_key():
    """Block scalar stops at next non-indented key."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    text = '---\ndescription: |\n  Multi-line\n  description\ndate: "2026-01-01"\n---\nBody\n'
    fields, _ = _split_yaml_frontmatter(text)
    assert fields["description"] == "Multi-line description"
    assert fields["date"] == "2026-01-01"


# ── Overlap detection tests ──────────────────────────────────────────


def test_overlap_nudge_fires_on_tag_overlap(tmp_path):
    """Consolidation nudge fires when new decision shares 2+ tags with existing."""
    from decision.policy.content_validation import _content_validation_condition

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "existing-auth", tags=["auth", "security"])

    state = make_session_state("cv-overlap-tags", store=store)
    data = {
        "tool_input": {
            "file_path": str(decisions_dir / "new-auth.md"),
            "content": (
                '---\nname: "new-auth"\ndescription: "Another auth decision"\n'
                'date: "2026-03-25"\ntags:\n  - "auth"\n  - "security"\n'
                'affects:\n  - "src/auth.py"\n---\n\n'
                "# New Auth Decision\n\nAnother decision about auth and security.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert "consolidat" in str(result.system_message).lower() or "overlap" in str(result.system_message).lower()
    assert "existing-auth" in str(result.system_message)


def test_overlap_nudge_fires_on_affects_overlap(tmp_path):
    """Consolidation nudge fires when new decision shares affects paths with existing."""
    from decision.policy.content_validation import _content_validation_condition

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "existing-billing", tags=["billing"], affects=["src/billing/", "src/payments.py"])

    state = make_session_state("cv-overlap-affects", store=store)
    data = {
        "tool_input": {
            "file_path": str(decisions_dir / "new-billing.md"),
            "content": (
                '---\nname: "new-billing"\ndescription: "Billing approach"\n'
                'date: "2026-03-25"\ntags:\n  - "payments"\n'
                'affects:\n  - "src/billing/"\n  - "src/payments.py"\n---\n\n'
                "# New Billing Decision\n\nAnother decision about billing and payments.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert "consolidat" in str(result.system_message).lower() or "overlap" in str(result.system_message).lower()
    assert "existing-billing" in str(result.system_message)


def test_overlap_nudge_below_threshold_silent(tmp_path):
    """No nudge when overlap is below threshold (only 1 shared tag)."""
    from decision.policy.content_validation import _content_validation_condition

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "existing-misc", tags=["architecture", "frontend"])

    state = make_session_state("cv-overlap-below", store=store)
    data = {
        "tool_input": {
            "file_path": str(decisions_dir / "new-misc.md"),
            "content": (
                '---\nname: "new-misc"\ndescription: "Different topic"\n'
                'date: "2026-03-25"\ntags:\n  - "architecture"\n  - "backend"\n'
                'affects:\n  - "src/api.py"\n---\n\n'
                "# New Misc Decision\n\nA different topic that shares one tag.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    # Only 1 shared tag = score 2, below threshold 4 (metadata echo is fine)
    assert result is None or "consolidat" not in str(result.system_message or "").lower()


# ── Affects suggestion engine (additional affects from sibling decisions) ───


def test_content_validation_suggests_additional_affects(tmp_path):
    """content-validation suggests additional affects from sibling decisions."""
    from decision.policy.content_validation import _content_validation_condition

    decisions_dir, store = make_store(tmp_path)
    # Two existing decisions tagged "auth" both affect src/middleware/
    make_decision(decisions_dir, "auth-jwt", tags=["auth"], affects=["src/auth/", "src/middleware/"])
    make_decision(decisions_dir, "auth-sessions", tags=["auth"], affects=["src/auth/", "src/middleware/"])

    state = make_session_state("cv-additional-affects", store=store)
    # New decision tagged "auth" only has src/auth/ — should suggest src/middleware/
    data = {
        "tool_input": {
            "file_path": str(decisions_dir / "auth-new.md"),
            "content": (
                '---\nname: "auth-new"\ndescription: "New auth decision"\n'
                'date: "2026-03-26"\ntags:\n  - "auth"\n'
                'affects:\n  - "src/auth/"\n---\n\n'
                "# New Auth Decision\n\nChose token-based auth for the new API.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    msg = str(result.system_message or "")
    assert "src/middleware/" in msg, f"Should suggest src/middleware/ from sibling decisions. Got: {msg}"


# ── content-validation: tool_input edge cases ────────────────────────


def test_content_validation_non_dict_tool_input():
    """content-validation returns None when tool_input is not a dict."""
    from decision.policy.content_validation import _content_validation_condition

    state = make_session_state("cv-bad-ti")
    data = {"tool_input": "not a dict"}
    result = _content_validation_condition(data, state)
    assert result is None


def test_content_validation_empty_content():
    """content-validation returns None when content is empty."""
    from decision.policy.content_validation import _content_validation_condition

    state = make_session_state("cv-empty-content")
    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/empty.md",
            "content": "",
        }
    }
    result = _content_validation_condition(data, state)
    assert result is None


# ── content-validation: stale affects path branches ────────────────


def test_stale_affects_absolute_path(tmp_path):
    """content-validation rejects absolute affects paths."""
    from decision.policy.content_validation import _content_validation_condition

    _, store = make_store(tmp_path)
    state = make_session_state("cv-abs-stale", store=store)
    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/abs.md",
            "content": (
                '---\nname: "abs"\ndescription: "Abs path"\n'
                'date: "2026-03-20"\ntags:\n  - "test"\n'
                'affects:\n  - "/nonexistent/absolute/path.py"\n---\n\n'
                "# Absolute Path\n\nThis references an absolute path that doesn't exist.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert result.decision == "reject"
    assert "absolute" in str(result.reason).lower()


def test_stale_affects_glob_skipped(tmp_path):
    """content-validation skips glob patterns in affects (no disk check)."""
    from decision.policy.content_validation import _content_validation_condition

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        (tmp_path / "src").mkdir()
        _, store = make_store(tmp_path)
        state = make_session_state("cv-glob-skip", store=store)
        data = {
            "tool_input": {
                "file_path": "/home/user/.claude/projects/test/decisions/glob.md",
                "content": (
                    '---\nname: "glob"\ndescription: "Glob pattern"\n'
                    'date: "2026-03-20"\ntags:\n  - "test"\n'
                    'affects:\n  - "src/**/*.py"\n---\n\n'
                    "# Glob Pattern\n\nThis uses a glob pattern in affects.\n"
                ),
            }
        }
        result = _content_validation_condition(data, state)
        # Glob patterns should not trigger stale warning (metadata echo is fine)
        assert result is None or "not found" not in str(result.system_message or "").lower()
    finally:
        os.chdir(old_cwd)


def test_stale_affects_dir_path(tmp_path):
    """content-validation warns on directory affects that don't exist."""
    from decision.policy.content_validation import _content_validation_condition

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        (tmp_path / "src").mkdir()
        _, store = make_store(tmp_path)
        state = make_session_state("cv-dir-stale", store=store)
        data = {
            "tool_input": {
                "file_path": "/home/user/.claude/projects/test/decisions/dir.md",
                "content": (
                    '---\nname: "dir"\ndescription: "Dir path"\n'
                    'date: "2026-03-20"\ntags:\n  - "test"\n'
                    'affects:\n  - "src/nonexistent/"\n---\n\n'
                    "# Dir Path\n\nThis references a nonexistent directory.\n"
                ),
            }
        }
        result = _content_validation_condition(data, state)
        assert result is not None
        assert "not found" in str(result.system_message).lower()
    finally:
        os.chdir(old_cwd)


def test_stale_affects_dir_absolute(tmp_path):
    """content-validation rejects absolute dir affects paths."""
    from decision.policy.content_validation import _content_validation_condition

    _, store = make_store(tmp_path)
    state = make_session_state("cv-abs-dir", store=store)
    data = {
        "tool_input": {
            "file_path": "/home/user/.claude/projects/test/decisions/absdir.md",
            "content": (
                '---\nname: "absdir"\ndescription: "Abs dir"\n'
                'date: "2026-03-20"\ntags:\n  - "test"\n'
                'affects:\n  - "/nonexistent/dir/"\n---\n\n'
                "# Abs Dir\n\nReferences an absolute directory that doesn't exist.\n"
            ),
        }
    }
    result = _content_validation_condition(data, state)
    assert result is not None
    assert result.decision == "reject"
    assert "absolute" in str(result.reason).lower()


# ── _check_overlap edge cases ───────────────────────────────────────


def test_check_overlap_no_tags_no_affects():
    """_check_overlap returns None when decision has no tags and no affects."""
    from decision.policy.content_validation import _check_overlap

    class FakeDec:
        tags = []
        affects = []

    state = make_session_state("co-empty")
    result = _check_overlap(FakeDec(), state)
    assert result is None


def test_check_overlap_exception_returns_none(tmp_path):
    """_check_overlap returns None when find_overlapping_decisions raises."""
    from unittest.mock import patch

    from decision.policy.content_validation import _check_overlap

    class FakeDec:
        tags = ["auth"]
        affects = ["src/auth.py"]

    _, store = make_store(tmp_path)
    state = make_session_state("co-exc", store=store)
    with patch("decision.utils.similarity.find_overlapping_decisions", side_effect=Exception("boom")):
        result = _check_overlap(FakeDec(), state)
    assert result is None


# ── _maybe_tag_similarity_warning edge cases ─────────────────────────


def test_tag_similarity_store_exception(tmp_path):
    """_maybe_tag_similarity_warning returns base_result when store.all_tags raises."""
    from unittest.mock import patch

    from decision.policy.content_validation import _maybe_tag_similarity_warning
    from decision.policy.engine import PolicyResult

    class FakeDec:
        tags = ["auth"]

    _, store = make_store(tmp_path)
    state = make_session_state("ts-exc", store=store)
    base = PolicyResult(matched=True, system_message="base")

    with patch.object(store, "all_tags", side_effect=Exception("boom")):
        result = _maybe_tag_similarity_warning(FakeDec(), state, base)
    assert result is base


def test_suggest_tags_exception(tmp_path):
    """_maybe_tag_similarity_warning handles suggest_tags_from_overlaps exception."""
    from unittest.mock import patch

    from decision.policy.content_validation import _maybe_tag_similarity_warning
    from decision.policy.engine import PolicyResult

    class FakeDec:
        tags = ["auth"]

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "existing", tags=["authentication"])  # similar tag
    state = make_session_state("ts-sug-exc", store=store)
    base = PolicyResult(matched=True, system_message="base")

    with patch("decision.utils.similarity.suggest_tags_from_overlaps", side_effect=Exception("boom")):
        result = _maybe_tag_similarity_warning(FakeDec(), state, base)
    # Should still have the tag similarity warning from similar_tags, just not the suggestion
    assert result is not None


# ── _check_affects: relative path root segment absent ────────────────


def test_check_affects_relative_dir_root_absent(tmp_path):
    """_check_affects skips stale check when root segment doesn't exist in CWD."""
    from decision.policy.content_validation import _check_affects

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Don't create 'nonexistent_root/' in tmp_path
        class FakeDec:
            tags = ["test"]
            affects = ["nonexistent_root/bar/"]

        _, store = make_store(tmp_path)
        state = make_session_state("ca-dir-absent", store=store)
        result = _check_affects(FakeDec(), state)
        # Should not warn about stale — root segment doesn't exist, so skip the check
        if result is not None:
            assert "not found" not in str(result.system_message or "").lower()
    finally:
        os.chdir(old_cwd)


def test_check_affects_relative_file_root_absent(tmp_path):
    """_check_affects skips stale check for files when root segment absent."""
    from decision.policy.content_validation import _check_affects

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        class FakeDec:
            tags = ["test"]
            affects = ["nonexistent_root/file.py"]

        _, store = make_store(tmp_path)
        state = make_session_state("ca-file-absent", store=store)
        result = _check_affects(FakeDec(), state)
        if result is not None:
            assert "not found" not in str(result.system_message or "").lower()
    finally:
        os.chdir(old_cwd)


# ── _check_affects: tag-based fallback suggestion ────────────────────


def test_check_affects_tag_fallback_suggest(tmp_path):
    """_check_affects suggests affects from tag-sibling decisions when no affects and no edits."""
    from decision.policy.content_validation import _check_affects

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "sibling-1", tags=["caching"], affects=["src/cache/"])
    make_decision(decisions_dir, "sibling-2", tags=["caching"], affects=["src/cache/"])

    class FakeDec:
        tags = ["caching"]
        affects = []

    state = make_session_state("ca-tag-fb", store=store)
    result = _check_affects(FakeDec(), state)
    assert result is not None
    assert result.ok is False
    assert result.decision == "reject"
    assert "src/cache/" in result.reason or "affects" in result.reason


def test_check_affects_tag_fallback_exception(tmp_path):
    """_check_affects falls through to generic warning when suggest_affects_from_tags raises."""
    from unittest.mock import patch

    from decision.policy.content_validation import _check_affects

    decisions_dir, store = make_store(tmp_path)

    class FakeDec:
        tags = ["caching"]
        affects = []

    state = make_session_state("ca-tag-exc", store=store)
    with patch("decision.utils.affects.suggest_affects_from_tags", side_effect=Exception("boom")):
        result = _check_affects(FakeDec(), state)
    assert result is not None
    assert "no `affects` paths" in str(result.system_message).lower()


# ── _check_affects: additional affects exception ─────────────────────


def test_check_affects_additional_suggestion_exception(tmp_path):
    """_check_affects handles suggest_additional_affects exception gracefully."""
    from unittest.mock import patch

    from decision.policy.content_validation import _check_affects

    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        (tmp_path / "src").mkdir(exist_ok=True)
        (tmp_path / "src" / "auth.py").write_text("# auth")
        decisions_dir, store = make_store(tmp_path)

        class FakeDec:
            tags = ["auth"]
            affects = ["src/auth.py"]

        state = make_session_state("ca-add-exc", store=store)
        with patch("decision.utils.affects.suggest_additional_affects", side_effect=Exception("boom")):
            result = _check_affects(FakeDec(), state)
        # Should not crash — result is None or has stale/metadata info
        assert result is None or isinstance(result, decision.PolicyResult)
    finally:
        os.chdir(old_cwd)


# ── Capture history recording ─────────────────────────────────────────


def test_capture_records_history():
    """Successful decision capture records timestamp in capture_history.json."""
    import json

    from decision.policy.content_validation import _record_capture
    from decision.utils.helpers import _state_dir

    _record_capture()

    path = _state_dir() / "capture_history.json"
    assert path.is_file()
    history = json.loads(path.read_text())
    assert len(history) >= 1
    assert isinstance(history[-1], float)
