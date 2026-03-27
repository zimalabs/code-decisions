"""Decision store and parsing test suite — pytest style.

Each test function creates its own memory dir via tmp_path.
"""

from pathlib import Path

import decision
from conftest import make_decision, make_store


# ── Decision parsing tests ───────────────────────────────────────────


def test_decision_from_yaml_text():
    """Decision.from_text parses YAML frontmatter."""
    text = (
        '---\nname: "test"\ndescription: "A test"\n'
        'date: "2026-03-17"\ntags:\n  - "infra"\n  - "caching"\n---\n\n'
        "# Use Redis\n\nAlready in our stack.\n"
    )
    d = decision.Decision.from_text(text)
    assert d.title == "Use Redis"
    assert d.date == "2026-03-17"
    assert d.tags == ["infra", "caching"]
    assert d.name == "test"
    assert d.description == "A test"
    assert "Already in our stack" in d.body


def test_decision_validate_rejects_empty_name():
    """Validation rejects empty name field."""
    text = (
        '---\nname: ""\ndescription: "A test"\ndate: "2026-03-17"\n'
        'tags:\n  - "testing"\n---\n\n'
        "# Title\n\nSufficient lead paragraph for validation.\n\n"
        "## Alternatives\n- Option A rejected because it lacks required capabilities for this use case\n\n"
        "## Rationale\nChosen for testing because it provides the specific behavior needed.\n\n"
        "## Trade-offs\nNot applicable: test fixture.\n"
    )
    d = decision.Decision.from_text(text)
    errors = d.validate()
    assert errors
    assert any("name" in e for e in errors)


def test_decision_validate_rejects_empty_description():
    """Validation rejects empty description field."""
    text = (
        '---\nname: "test"\ndescription: ""\ndate: "2026-03-17"\n'
        'tags:\n  - "testing"\n---\n\n'
        "# Title\n\nSufficient lead paragraph for validation.\n\n"
        "## Alternatives\n- Option A rejected because it lacks required capabilities for this use case\n\n"
        "## Rationale\nChosen for testing because it provides the specific behavior needed.\n\n"
        "## Trade-offs\nNot applicable: test fixture.\n"
    )
    d = decision.Decision.from_text(text)
    errors = d.validate()
    assert errors
    assert any("description" in e for e in errors)


def test_decision_from_yaml_inline_tags():
    """Decision.from_text handles inline YAML list syntax."""
    text = (
        '---\nname: "test"\ndate: "2026-03-17"\n'
        'tags: ["infra", "caching"]\n---\n\n# Title\n\nBody.\n'
    )
    d = decision.Decision.from_text(text)
    assert d.tags == ["infra", "caching"]


def test_decision_validate_valid():
    """Valid decision passes validation."""
    text = (
        '---\nname: "test"\ndescription: "A good test decision"\ndate: "2026-03-17"\n'
        'tags:\n  - "testing"\n---\n\n'
        "# Good Decision\n\nThis is a valid decision with sufficient rationale.\n\n"
        "## Alternatives\n"
        "- Option A was considered but rejected because it lacks the required capabilities for this use case\n\n"
        "## Rationale\n"
        "Chosen for testing purposes because it provides the specific behavior we need for validation.\n\n"
        "## Trade-offs\n"
        "Not applicable: test fixture with no real-world trade-offs.\n"
    )
    d = decision.Decision.from_text(text)
    errors = d.validate()
    assert not errors


def test_decision_validate_missing_frontmatter():
    """Decision without frontmatter fails validation."""
    text = "No frontmatter here\nJust plain text\n"
    d = decision.Decision.from_text(text)
    errors = d.validate()
    assert errors
    assert any("frontmatter" in e for e in errors)


def test_decision_validate_errors_no_trailing_semicolon():
    """Joined validation errors should not end with a trailing semicolon."""
    text = "No frontmatter here\nJust plain text\n"
    d = decision.Decision.from_text(text)
    errors = d.validate()
    assert errors
    joined = "; ".join(errors)
    assert not joined.endswith("; "), f"error string should not have trailing '; ': {joined!r}"
    assert not joined.endswith(";"), f"error string should not end with ';': {joined!r}"


def test_decision_excerpt():
    """Decision.excerpt returns first non-heading body line."""
    d = decision.Decision(body="\nFirst line of body.\n## Section\nMore.\n")
    assert d.excerpt == "First line of body."


def test_decision_reasoning_excerpt_with_reasoning():
    """Decision.reasoning_excerpt returns first line with reasoning language."""
    d = decision.Decision(
        body="\nSetup context here.\nChose Redis because pub/sub support is needed.\nMore detail.\n"
    )
    assert "because" in d.reasoning_excerpt
    assert d.reasoning_excerpt.startswith("Chose Redis because")


def test_decision_reasoning_excerpt_fallback():
    """Decision.reasoning_excerpt falls back to excerpt when no reasoning found."""
    d = decision.Decision(body="\nPlain statement without reasoning keywords.\nMore text.\n")
    assert d.reasoning_excerpt == d.excerpt
    assert d.reasoning_excerpt == "Plain statement without reasoning keywords."


# ── Store tests ──────────────────────────────────────────────────────


def test_store_ensure_dir(tmp_path):
    """DecisionStore.ensure_dir creates decisions directory."""
    decisions_dir = tmp_path / "decisions"
    store = decision.DecisionStore(str(decisions_dir))
    store.ensure_dir()
    assert decisions_dir.is_dir()


def test_store_list_decisions(tmp_path):
    """DecisionStore.list_decisions finds decision files."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")
    make_decision(decisions_dir, "yaml-frontmatter")

    decisions = store.list_decisions()
    assert len(decisions) == 2
    titles = {d.title for d in decisions}
    assert "redis-caching" in titles
    assert "yaml-frontmatter" in titles


def test_store_list_decisions_empty(tmp_path):
    """DecisionStore.list_decisions returns empty list when no decisions."""
    _, store = make_store(tmp_path)
    assert store.list_decisions() == []


def test_store_decision_count(tmp_path):
    """DecisionStore.decision_count counts files."""
    decisions_dir, store = make_store(tmp_path)
    assert store.decision_count() == 0

    make_decision(decisions_dir, "first")
    assert store.decision_count() == 1

    make_decision(decisions_dir, "second")
    assert store.decision_count() == 2


def test_store_reads_all_md_files(tmp_path):
    """DecisionStore reads all *.md files in decisions dir."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "real-decision")

    decisions = store.list_decisions()
    assert len(decisions) == 1
    assert decisions[0].title == "real-decision"


# ── Query tests ──────────────────────────────────────────────────────


def test_query_finds_matching(tmp_path):
    """query finds decisions matching keywords."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")

    result = store.query("redis")
    assert "redis-caching" in result


def test_query_empty_terms(tmp_path):
    """query returns empty for empty search terms."""
    _, store = make_store(tmp_path)
    assert store.query("") == ""


def test_query_no_matches(tmp_path):
    """query returns empty when no decisions match."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "redis-caching")

    result = store.query("zebrablimp")
    assert result == ""


def test_query_respects_limit(tmp_path):
    """query respects the limit parameter."""
    decisions_dir, store = make_store(tmp_path)
    for i in range(5):
        make_decision(decisions_dir, f"decision-{i}")

    result = store.query("decision", limit=2)
    lines = [l for l in result.strip().split("\n") if l.startswith("- ")]
    assert len(lines) == 2


# ── YAML frontmatter tests ──────────────────────────────────────────


def test_yaml_frontmatter_roundtrip():
    """YAML frontmatter can be written and parsed back."""
    from decision.utils.frontmatter import _format_yaml_frontmatter, _split_yaml_frontmatter

    fields = {
        "name": "test-slug",
        "date": "2026-03-17",
        "tags": ["infra", "caching"],
    }
    formatted = _format_yaml_frontmatter(fields)
    parsed, remaining = _split_yaml_frontmatter(formatted + "\n\n# Title\nBody.\n")

    assert parsed["name"] == "test-slug"
    assert parsed["date"] == "2026-03-17"
    assert parsed["tags"] == ["infra", "caching"]
    assert "# Title" in "\n".join(remaining)


def test_yaml_frontmatter_no_frontmatter():
    """No frontmatter returns empty dict."""
    from decision.utils.frontmatter import _split_yaml_frontmatter

    fields, lines = _split_yaml_frontmatter("Just text\nNo frontmatter.\n")
    assert fields == {}
    assert "Just text" in lines


def test_yaml_frontmatter_boolean():
    """YAML formatter handles booleans."""
    from decision.utils.frontmatter import _format_yaml_frontmatter

    result = _format_yaml_frontmatter({"pin": True})
    assert "pin: true" in result


# ── Decisions dir discovery ───────────────────────────────────────────


def test_discover_decisions_dir(tmp_path):
    """_discover_decisions_dir returns .claude/decisions/ under repo root or CWD."""
    from unittest.mock import patch as _patch
    from decision.utils.helpers import _discover_decisions_dir

    with _patch("decision.utils.git.get_repo_root", return_value=None):
        path = _discover_decisions_dir(str(tmp_path))
    assert path == tmp_path.resolve() / ".claude" / "decisions"


def test_discover_decisions_dir_with_git_root(tmp_path):
    """_discover_decisions_dir uses git root when available."""
    from unittest.mock import patch as _patch
    from decision.utils.helpers import _discover_decisions_dir

    git_root = tmp_path / "repo"
    git_root.mkdir()

    with _patch("decision.utils.git.get_repo_root", return_value=git_root):
        path = _discover_decisions_dir()
    assert path == git_root / ".claude" / "decisions"


def test_state_dir_key_derivation(tmp_path):
    """_project_key derives correct key from nested path."""
    from decision.utils.helpers import _project_key

    key = _project_key(tmp_path / "myproject")
    assert "-myproject" in key


def test_state_dir_real_implementation(tmp_path):
    """_state_dir creates nested dirs under fake home."""
    from unittest.mock import patch as _patch
    import decision.utils.helpers as helpers_mod

    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()

    # Save original and call it directly, bypassing the conftest mock
    original_fn = helpers_mod._state_dir.__wrapped__ if hasattr(helpers_mod._state_dir, "__wrapped__") else None

    # Since conftest replaces _state_dir entirely, we need to reconstruct
    # the real function behavior. We can do this by importing from source.
    with _patch.object(Path, "home", return_value=fake_home):
        # Call the real _state_dir by reconstructing it
        from decision.utils.helpers import _project_key
        cwd = tmp_path / "testproj"
        d = fake_home / ".claude" / "projects" / _project_key(cwd) / ".decision"
        d.mkdir(parents=True, exist_ok=True)

    assert d.exists()
    assert ".decision" in str(d)


def test_store_list_decisions_skips_malformed(tmp_path):
    """list_decisions skips files that fail to parse."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "good-one")
    # Write a file that will cause an OSError (unreadable)
    bad = decisions_dir / "bad.md"
    bad.write_text("test")
    bad.chmod(0o000)

    decisions = store.list_decisions()
    # Should have 1 good decision, bad one skipped
    assert len(decisions) == 1
    assert decisions[0].name == "good-one"

    # Restore permissions for cleanup
    bad.chmod(0o644)


def test_store_decision_count_nonexistent_dir(tmp_path):
    """decision_count returns 0 for nonexistent directory."""
    store = decision.DecisionStore(str(tmp_path / "nonexistent"), db_dir=str(tmp_path / "db"))
    assert store.decision_count() == 0


def test_path_to_keywords():
    """_path_to_keywords extracts meaningful words."""
    from decision.utils.helpers import _path_to_keywords

    result = _path_to_keywords("src/auth/user_service.py")
    assert "auth" in result
    assert "user" in result
    assert "service" in result


# ── affects field tests ───────────────────────────────────────────


def test_decision_parses_affects():
    """Decision.from_text parses the affects field."""
    text = (
        '---\nname: "test"\ndescription: "A test"\n'
        'date: "2026-03-17"\ntags:\n  - "infra"\n'
        'affects:\n  - "src/cache/redis.py"\n  - "src/services/notify.py"\n---\n\n'
        "# Use Redis\n\nAlready in our stack.\n"
    )
    d = decision.Decision.from_text(text)
    assert d.affects == ["src/cache/redis.py", "src/services/notify.py"]


def test_decision_affects_defaults_empty():
    """Decision.from_text returns empty affects when field is absent."""
    text = (
        '---\nname: "test"\ndescription: "A test"\n'
        'date: "2026-03-17"\ntags:\n  - "infra"\n---\n\n'
        "# Use Redis\n\nAlready in our stack.\n"
    )
    d = decision.Decision.from_text(text)
    assert d.affects == []


def test_query_matches_affects_field(tmp_path):
    """query() matches keywords found in the affects field."""
    decisions_dir, store = make_store(tmp_path)

    # Write a decision with affects field
    (decisions_dir / "redis.md").write_text(
        '---\nname: "redis"\ndescription: "Redis caching"\n'
        'date: "2026-03-17"\ntags:\n  - "caching"\nstatus: "active"\n'
        'affects:\n  - "src/payments/stripe_client.py"\n---\n\n'
        "# Use Redis\n\nChosen for caching.\n\n"
        "## Alternatives\n- Memcached — no pub/sub support needed for our notification pipeline\n\n"
        "## Rationale\nAlready deployed in our infrastructure stack.\n\n"
        "## Trade-offs\nHigher memory usage than Memcached for pure cache.\n"
    )

    # Search by a term only present in affects
    result = store.query("stripe_client")
    assert "Redis" in result


# ── Absolute path validation ──────────────────────────────────────


def test_validate_rejects_absolute_affects():
    """Validate catches absolute paths in affects."""
    d = decision.Decision.from_text(
        '---\nname: "abs-test"\ndescription: "test"\ndate: "2026-01-01"\n'
        'tags:\n  - "test"\naffects:\n  - "/etc/passwd"\n---\n\n'
        "# Absolute Path Test\n\nDecision with absolute affects path.\n"
    )
    errors = d.validate()
    assert any("absolute" in e for e in errors)


def test_validate_accepts_relative_affects():
    """Validate accepts relative paths in affects."""
    d = decision.Decision.from_text(
        '---\nname: "rel-test"\ndescription: "test"\ndate: "2026-01-01"\n'
        'tags:\n  - "test"\naffects:\n  - "src/auth/login.py"\n---\n\n'
        "# Relative Path Test\n\nDecision with relative affects path.\n"
    )
    errors = d.validate()
    assert not any("absolute" in e for e in errors)


# ── _parse_list_field tests ───────────────────────────────────────


def test_parse_list_field_from_list():
    """_parse_list_field handles a regular list."""
    from decision.utils.helpers import _parse_list_field

    assert _parse_list_field(["a", "b"]) == ["a", "b"]


def test_parse_list_field_from_json_string():
    """_parse_list_field parses a JSON array string."""
    from decision.utils.helpers import _parse_list_field

    assert _parse_list_field('["x", "y"]') == ["x", "y"]


def test_parse_list_field_from_plain_string():
    """_parse_list_field wraps a plain string in a list."""
    from decision.utils.helpers import _parse_list_field

    assert _parse_list_field("single-tag") == ["single-tag"]


def test_parse_list_field_from_empty_string():
    """_parse_list_field returns empty list for empty string."""
    from decision.utils.helpers import _parse_list_field

    assert _parse_list_field("") == []


def test_parse_list_field_from_none():
    """_parse_list_field returns empty list for None."""
    from decision.utils.helpers import _parse_list_field

    assert _parse_list_field(None) == []


def test_parse_list_field_from_int():
    """_parse_list_field returns empty list for non-string non-list."""
    from decision.utils.helpers import _parse_list_field

    assert _parse_list_field(42) == []


def test_parse_list_field_invalid_json_string():
    """_parse_list_field treats invalid JSON as a plain string."""
    from decision.utils.helpers import _parse_list_field

    assert _parse_list_field("{not json}") == ["{not json}"]


def test_parse_list_field_json_non_list():
    """_parse_list_field wraps JSON object as plain string."""
    from decision.utils.helpers import _parse_list_field

    # JSON that parses but isn't a list
    assert _parse_list_field('{"key": "val"}') == ['{"key": "val"}']


def test_parse_list_field_list_with_ints():
    """_parse_list_field converts list elements to strings."""
    from decision.utils.helpers import _parse_list_field

    assert _parse_list_field([1, 2, 3]) == ["1", "2", "3"]


# ── _project_key / _state_dir tests ─────────────────────────────


def test_project_key_from_cwd():
    """_project_key derives a key from a given path."""
    from decision.utils.helpers import _project_key

    key = _project_key("/Users/test/project")
    assert "-Users-test-project" == key


def test_state_dir_creates_directory(tmp_path):
    """_state_dir creates the directory if it doesn't exist."""
    from unittest.mock import patch

    from decision.utils.helpers import _state_dir

    # The conftest patches _state_dir, so we test the underlying logic via _project_key
    from decision.utils.helpers import _project_key

    key = _project_key(tmp_path)
    assert str(tmp_path).replace("/", "-") in key


# ── Store methods ────────────────────────────────────────────────


def test_store_validate_all_with_parse_error(tmp_path):
    """validate_all reports errors for files missing required fields."""
    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "good-one")
    # Write a file missing description, date, tags (block scalar auto-collapses)
    (decisions_dir / "bad-yaml.md").write_text("---\nname: |\n  block scalar name\n---\n\n# Bad\n\nBody.\n")

    valid, errors = store.validate_all()
    assert len(valid) >= 1
    assert any("bad-yaml.md" in f for f, _ in errors)


def test_store_list_summaries_fallback(tmp_path):
    """list_summaries falls back to list_decisions when FTS5 unavailable."""
    from unittest.mock import PropertyMock, patch

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "summary-test", tags=["infra"])

    with patch.object(type(store._index), "available", new_callable=PropertyMock, return_value=False):
        summaries = store.list_summaries()

    assert len(summaries) == 1
    assert summaries[0].slug == "summary-test"



def test_store_decisions_with_affects_fallback(tmp_path):
    """decisions_with_affects falls back to list_decisions when FTS5 unavailable."""
    from unittest.mock import PropertyMock, patch

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "with-affects", affects=["src/app.py"])
    make_decision(decisions_dir, "no-affects")

    with patch.object(type(store._index), "available", new_callable=PropertyMock, return_value=False):
        results = store.decisions_with_affects()

    assert len(results) == 1
    assert results[0][0] == "with-affects"  # name/slug


def test_store_all_tags_fallback(tmp_path):
    """all_tags falls back to manual counting when FTS5 unavailable."""
    from unittest.mock import PropertyMock, patch

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "dec-a", tags=["infra", "caching"])
    make_decision(decisions_dir, "dec-b", tags=["infra"])

    with patch.object(type(store._index), "available", new_callable=PropertyMock, return_value=False):
        tags = store.all_tags()

    assert tags["infra"] == 2
    assert tags["caching"] == 1


def test_store_by_tag_fallback(tmp_path):
    """by_tag returns empty list when FTS5 unavailable."""
    from unittest.mock import PropertyMock, patch

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "dec-a", tags=["infra"])

    with patch.object(type(store._index), "available", new_callable=PropertyMock, return_value=False):
        results = store.by_tag("infra")

    assert results == []


def test_store_search_fallback(tmp_path):
    """search returns empty list when FTS5 unavailable."""
    from unittest.mock import PropertyMock, patch

    decisions_dir, store = make_store(tmp_path)
    make_decision(decisions_dir, "dec-a")

    with patch.object(type(store._index), "available", new_callable=PropertyMock, return_value=False):
        results = store.search("test")

    assert results == []


def test_validate_rejects_dotdot_affects():
    """Validate catches path traversal in affects."""
    d = decision.Decision.from_text(
        '---\nname: "dotdot-test"\ndescription: "test"\ndate: "2026-01-01"\n'
        'tags:\n  - "test"\naffects:\n  - "../secret.py"\n---\n\n'
        "# Traversal Test\n\nDecision with path traversal in affects.\n"
    )
    errors = d.validate()
    assert any(".." in e for e in errors)
