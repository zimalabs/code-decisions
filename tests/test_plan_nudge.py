"""Plan nudge policy tests — extract decisions from Claude Code plan files."""

from conftest import make_decision, make_session_state, make_store

SAMPLE_PLAN = """\
# Plan: Use event sourcing for audit trail

## Context
We need to track all changes to financial records.

## Design
Chose event sourcing over CRUD with audit table because it provides
a complete, immutable history without schema coupling.

### Trade-off
Event sourcing adds replay complexity but eliminates the risk of
audit table drift.

### Instead of
- Direct SQL audit triggers — fragile across schema migrations
- Change Data Capture — requires infrastructure we don't have

## Files to Change
### New: `src/events/store.py`
### Modify: `src/models/transaction.py`
### New: `src/events/replay.py`
"""

PLAN_NO_DECISIONS = """\
# Plan: Update README

## Context
README is out of date.

## Changes
Update the installation section.
"""


def _plan_write(fp, content):
    return {"tool_name": "Write", "tool_input": {"file_path": fp, "content": content}}


def _code_write(fp):
    return {"tool_name": "Write", "tool_input": {"file_path": fp, "content": "class Foo:\n    pass"}}


def _code_edit(fp):
    return {"tool_name": "Edit", "tool_input": {"file_path": fp, "new_string": "updated"}}


# ── Phase 1: Plan file extraction ────────────────────────────────────


def test_extracts_candidates_from_plan(tmp_path):
    """Writing a plan file stores candidates but returns None."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _load_candidates, _plan_nudge_condition

    state = make_session_state("plan-extract", store=store)
    result = _plan_nudge_condition(
        _plan_write("/home/user/.claude/plans/test-plan.md", SAMPLE_PLAN), state
    )
    assert result is None  # Never nudge during plan mode

    candidates = _load_candidates(state)
    assert len(candidates) >= 1
    # Should find "chose event sourcing" or similar
    titles = " ".join(c["title"].lower() for c in candidates)
    assert "chose" in titles or "instead of" in titles or "trade" in titles


def test_extracts_file_paths_as_affects(tmp_path):
    """_extract_plan_affects returns paths from plan."""
    from decision.policy.plan_nudge import _extract_plan_affects

    affects = _extract_plan_affects(SAMPLE_PLAN)
    assert "src/events/store.py" in affects
    assert "src/models/transaction.py" in affects
    assert "src/events/replay.py" in affects


def test_edit_to_plan_ignored(tmp_path):
    """Edit tool to a plan file is ignored (no full content)."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition

    state = make_session_state("plan-edit", store=store)
    data = {"tool_name": "Edit", "tool_input": {"file_path": "/home/.claude/plans/x.md", "new_string": "patch"}}
    result = _plan_nudge_condition(data, state)
    assert result is None
    assert not state.has_fired("_plan-candidates-ready")


def test_no_candidates_from_plain_plan(tmp_path):
    """Plan with no decision language stores nothing."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _load_candidates, _plan_nudge_condition

    state = make_session_state("plan-plain", store=store)
    _plan_nudge_condition(
        _plan_write("/home/.claude/plans/plain.md", PLAN_NO_DECISIONS), state
    )
    assert not state.has_fired("_plan-candidates-ready")
    assert _load_candidates(state) == []


# ── Phase 2: Nudge on first implementation edit ──────────────────────


def test_nudges_on_first_impl_edit(tmp_path):
    """After plan write, first code Write triggers nudge with candidates."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition

    state = make_session_state("plan-nudge", store=store)

    # Phase 1: write plan
    _plan_nudge_condition(
        _plan_write("/home/.claude/plans/test.md", SAMPLE_PLAN), state
    )

    # Phase 2: first code edit
    result = _plan_nudge_condition(_code_write("src/events/store.py"), state)
    assert result is not None
    assert result.matched is True
    assert "decision-worthy" in result.system_message
    assert "chose" in result.system_message.lower() or "event" in result.system_message.lower()


def test_fires_only_once(tmp_path):
    """Second implementation edit returns None."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition

    state = make_session_state("plan-once", store=store)
    _plan_nudge_condition(
        _plan_write("/home/.claude/plans/test.md", SAMPLE_PLAN), state
    )

    # First fires
    result1 = _plan_nudge_condition(_code_write("src/events/store.py"), state)
    assert result1 is not None

    # Second silent
    result2 = _plan_nudge_condition(_code_write("src/events/replay.py"), state)
    assert result2 is None


def test_silent_when_dismissed(tmp_path):
    """No nudge when nudges are dismissed."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition

    state = make_session_state("plan-dismissed", store=store)
    state.mark_nudges_dismissed()
    _plan_nudge_condition(
        _plan_write("/home/.claude/plans/test.md", SAMPLE_PLAN), state
    )
    result = _plan_nudge_condition(_code_write("src/events/store.py"), state)
    assert result is None


def test_silent_when_decision_captured(tmp_path):
    """No nudge if decisions were already captured."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition

    state = make_session_state("plan-captured", store=store)
    _plan_nudge_condition(
        _plan_write("/home/.claude/plans/test.md", SAMPLE_PLAN), state
    )

    # Simulate decision capture
    make_decision(decisions_dir, "event-sourcing-dec")

    result = _plan_nudge_condition(_code_write("src/events/store.py"), state)
    assert result is None


def test_includes_affects_in_message(tmp_path):
    """Nudge message includes extracted affects paths."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition

    state = make_session_state("plan-affects-msg", store=store)
    _plan_nudge_condition(
        _plan_write("/home/.claude/plans/test.md", SAMPLE_PLAN), state
    )
    result = _plan_nudge_condition(_code_write("src/events/store.py"), state)
    assert result is not None
    assert "src/events/store.py" in result.system_message


# ── Stop-nudge integration ───────────────────────────────────────────


def test_stop_nudge_includes_plan_candidates(tmp_path):
    """Stop-nudge shows plan candidates when uncaptured."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition
    from decision.policy.stop_nudge import _stop_nudge_condition

    state = make_session_state("plan-stop", store=store)
    _plan_nudge_condition(
        _plan_write("/home/.claude/plans/test.md", SAMPLE_PLAN), state
    )

    result = _stop_nudge_condition({}, state)
    assert result is not None
    assert "plan" in result.system_message.lower()
    assert "uncaptured" in result.system_message.lower()


def test_stop_nudge_silent_after_capture(tmp_path):
    """Stop-nudge omits plan candidates if decisions were captured."""
    decisions_dir, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition
    from decision.policy.stop_nudge import _stop_nudge_condition

    state = make_session_state("plan-stop-ok", store=store)
    _plan_nudge_condition(
        _plan_write("/home/.claude/plans/test.md", SAMPLE_PLAN), state
    )

    make_decision(decisions_dir, "captured-dec")

    result = _stop_nudge_condition({}, state)
    if result is not None:
        assert "none captured" not in result.system_message.lower()


# ── _is_plan_file ────────────────────────────────────────────────────


def test_is_plan_file():
    from decision.policy.plan_nudge import _is_plan_file

    assert _is_plan_file("/home/user/.claude/plans/my-plan.md")
    assert _is_plan_file("/Users/dev/.claude/plans/test.md")
    assert not _is_plan_file("/home/user/.claude/decisions/some.md")
    assert not _is_plan_file("/home/user/.claude/plans/data.json")
    assert not _is_plan_file("src/plans/readme.md")  # no .claude/ prefix


# ── Superpowers spec/plan support ───────────────────────────────────

SUPERPOWERS_SPEC = """\
# Auth System Design

## Context
We need user authentication for the API.

## Approach 1: JWT tokens
Stateless, scales horizontally, no session storage needed.

## Approach 2: Session cookies
Simpler to implement, but requires Redis for session storage.

## Decision
Chose JWT over session cookies because stateless auth scales
better across our multi-region deployment without shared state.

Instead of bcrypt we opted for argon2 for password hashing
because it's more resistant to GPU-based attacks.

## Files to Change
### New: `src/auth/jwt.py`
### Modify: `src/models/user.py`
"""

SUPERPOWERS_PLAN = """\
# Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

## Task 1: Create JWT module
Decided to use PyJWT rather than python-jose because it has
fewer dependencies and covers our use case.

## Files to Change
### New: `src/auth/jwt.py`
### New: `tests/test_jwt.py`
"""


def test_is_plan_file_superpowers_spec():
    from decision.policy.plan_nudge import _is_plan_file

    assert _is_plan_file("/project/docs/superpowers/specs/2026-04-13-auth-design.md")
    assert _is_plan_file("/project/docs/superpowers/plans/2026-04-13-auth-plan.md")
    assert not _is_plan_file("/project/docs/superpowers/specs/notes.txt")
    assert not _is_plan_file("/project/docs/other/specs/design.md")


def test_extracts_candidates_from_superpowers_spec(tmp_path):
    """Writing a superpowers spec extracts decision candidates."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _load_candidates, _plan_nudge_condition

    state = make_session_state("sp-spec", store=store)
    result = _plan_nudge_condition(
        _plan_write("docs/superpowers/specs/2026-04-13-auth-design.md", SUPERPOWERS_SPEC),
        state,
    )
    assert result is None  # Phase 1 never nudges

    candidates = _load_candidates(state)
    assert len(candidates) >= 2
    titles = " ".join(c["title"].lower() for c in candidates)
    assert "chose" in titles or "jwt" in titles or "approach" in titles


def test_extracts_approach_sections(tmp_path):
    """_extract_decision_candidates picks up approach/option patterns."""
    from decision.policy.plan_nudge import _extract_decision_candidates

    candidates = _extract_decision_candidates(SUPERPOWERS_SPEC)
    titles = " ".join(c["title"].lower() for c in candidates)
    # Should find both decision language AND approach sections
    assert "chose" in titles or "opted" in titles or "instead" in titles
    assert "approach" in titles or "jwt" in titles


def test_superpowers_spec_nudge_on_impl_edit(tmp_path):
    """After superpowers spec write, first code edit triggers nudge."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition

    state = make_session_state("sp-nudge", store=store)

    # Phase 1: write spec
    _plan_nudge_condition(
        _plan_write("docs/superpowers/specs/2026-04-13-auth-design.md", SUPERPOWERS_SPEC),
        state,
    )

    # Phase 2: first code edit
    result = _plan_nudge_condition(_code_write("src/auth/jwt.py"), state)
    assert result is not None
    assert result.matched is True
    assert "superpowers spec" in result.system_message
    assert "auth-design" in result.system_message


def test_superpowers_plan_nudge_message(tmp_path):
    """Superpowers plan nudge references 'plan' not 'spec'."""
    _, store = make_store(tmp_path)
    from decision.policy.plan_nudge import _plan_nudge_condition

    state = make_session_state("sp-plan-msg", store=store)

    _plan_nudge_condition(
        _plan_write("docs/superpowers/plans/2026-04-13-auth-plan.md", SUPERPOWERS_PLAN),
        state,
    )
    result = _plan_nudge_condition(_code_write("src/auth/jwt.py"), state)
    assert result is not None
    assert "superpowers plan" in result.system_message
    assert "auth-plan" in result.system_message


def test_superpowers_spec_affects_extracted(tmp_path):
    """Superpowers spec file paths are extracted as affects."""
    from decision.policy.plan_nudge import _extract_plan_affects

    affects = _extract_plan_affects(SUPERPOWERS_SPEC)
    assert "src/auth/jwt.py" in affects
    assert "src/models/user.py" in affects
