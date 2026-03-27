"""Shared fixtures and helpers for decision tests."""

import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "src"
DISPATCH = PLUGIN_DIR / "hooks" / "dispatch.sh"


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolate_state_dir(tmp_path):
    """Redirect _state_dir to tmp_path so tests never touch the real state dir."""
    state_dir = tmp_path / ".decision-state"
    state_dir.mkdir()
    with patch("decision.utils.helpers._state_dir", return_value=state_dir):
        yield


@pytest.fixture
def dispatch_env():
    """Env dict for subprocess hook tests."""
    return {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)}


# ── Shared helpers (plain functions, not fixtures) ───────────────────


def make_store(tmp_path):
    """Create a fresh decisions dir in a temp dir, return (decisions_dir, store)."""
    import decision

    decisions_dir = tmp_path / "decisions"
    store = decision.DecisionStore(str(decisions_dir), db_dir=str(tmp_path / "db"))
    store.ensure_dir()
    return decisions_dir, store


def make_session_state(test_name, store=None):
    """Create a SessionState with a unique session ID and optional store."""
    import decision

    return decision.SessionState(session_id=f"test-{test_name}-{uuid.uuid4().hex[:8]}", store=store)


_DECISION_BODIES = [
    (
        "This is a test decision with sufficient rationale for validation.\n\n"
        "## Alternatives\n"
        "- Option A was considered but rejected because it lacks the required capabilities for this use case\n\n"
        "## Rationale\n"
        "Chosen for testing purposes because it provides the specific behavior needed for validation.\n\n"
        "## Trade-offs\n"
        "Not applicable: test fixture with no real-world trade-offs.\n"
    ),
    (
        "Evaluated multiple approaches before settling on the current implementation.\n\n"
        "## Alternatives\n"
        "- Redis was considered but rejected due to operational overhead in our deployment\n"
        "- SQLite was too limited for concurrent write workloads in production\n\n"
        "## Rationale\n"
        "PostgreSQL provides the JSONB support and full-text search we need without additional services.\n\n"
        "## Trade-offs\n"
        "Heavier infrastructure requirement — requires a managed database instance.\n"
    ),
    (
        "Standardizing on a single pattern to reduce cognitive overhead across the codebase.\n\n"
        "## Alternatives\n"
        "- Service objects with dependency injection — adds boilerplate without clear benefit here\n"
        "- Plain module functions — loses the ability to compose and test in isolation\n\n"
        "## Rationale\n"
        "The `Command` pattern with `call()` keeps each operation in a single file with clear inputs/outputs.\n\n"
        "## Trade-offs\n"
        "Slightly more files than inline logic — 15% increase in file count but improved test isolation.\n"
    ),
]


def make_decision(
    decisions_dir,
    slug="test-decision",
    *,
    title=None,
    tags=None,
    date="2026-03-17",
    affects=None,
    body=None,
    body_extra="",
    description="Test decision",
):
    """Write a valid decision file with YAML frontmatter.

    Supports all optional fields for test customization. Selects body template
    deterministically from slug hash when body is not provided.
    """
    tags = tags or ["testing"]
    affects = affects or []

    tags_yaml = "\n".join(f'  - "{t}"' for t in tags)
    affects_yaml = "\n".join(f'  - "{a}"' for a in affects)
    affects_block = f"affects:\n{affects_yaml}\n" if affects else ""

    if title is None:
        title = slug

    if body is None:
        body = _DECISION_BODIES[hash(slug) % len(_DECISION_BODIES)]

    target = Path(decisions_dir) / f"{slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f'---\nname: "{slug}"\ndescription: "{description}"\n'
        f'date: "{date}"\ntags:\n{tags_yaml}\n'
        f'{affects_block}---\n\n'
        f"# {title}\n\n"
        f"{body_extra}"
        + body
    )
    return target
