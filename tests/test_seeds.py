"""Tests for plugin-aware decision seeding."""

import json
from pathlib import Path
from unittest.mock import patch

from conftest import make_store

from decision.core.decision import Decision
from decision.seeds import MANIFEST_FILE, SeedDecision, SeedRegistry, _load_manifest


# ── Seed validation ──────────────────────────────────────────────────


def test_superpowers_seeds_pass_validation():
    """Every superpowers seed decision must pass Decision.validate()."""
    from decision.seeds._superpowers import superpowers_seeds

    for seed in superpowers_seeds():
        frontmatter = (
            f"---\n"
            f'name: "{seed.name}"\n'
            f'description: "{seed.description}"\n'
            f'date: "2026-04-13"\n'
            f"tags:\n"
        )
        for tag in seed.tags:
            frontmatter += f'  - "{tag}"\n'
        if seed.affects:
            frontmatter += "affects:\n"
            for a in seed.affects:
                frontmatter += f'  - "{a}"\n'
        frontmatter += "---\n"
        text = f"{frontmatter}\n# {seed.title}\n\n{seed.body}\n"
        d = Decision.from_text(text)
        errors = d.validate()
        assert errors == [], f"Seed {seed.slug} failed validation: {errors}"


def test_superpowers_seeds_have_unique_slugs():
    """All slugs must be unique."""
    from decision.seeds._superpowers import superpowers_seeds

    slugs = [s.slug for s in superpowers_seeds()]
    assert len(slugs) == len(set(slugs))


def test_superpowers_seeds_prefixed():
    """All slugs should be prefixed with 'superpowers-'."""
    from decision.seeds._superpowers import superpowers_seeds

    for seed in superpowers_seeds():
        assert seed.slug.startswith("superpowers-"), f"{seed.slug} missing prefix"


# ── Detection ────────────────────────────────────────────────────────


def _make_plugins_json(tmp_path, plugin_keys):
    """Create a mock installed_plugins.json."""
    plugins = {}
    for key in plugin_keys:
        plugins[key] = [{"scope": "user", "installPath": str(tmp_path / "cache" / key)}]
    data = {"version": 2, "plugins": plugins}
    path = tmp_path / "installed_plugins.json"
    path.write_text(json.dumps(data))
    return path


def test_detect_superpowers_installed(tmp_path):
    """Registry detects superpowers when present in installed_plugins.json."""
    plugins_json = _make_plugins_json(tmp_path, ["superpowers@superpowers-marketplace"])
    registry = SeedRegistry()
    registry.register("superpowers", lambda: [])

    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        detected = registry.detect_installed_plugins()

    assert "superpowers" in detected


def test_detect_superpowers_official_marketplace(tmp_path):
    """Registry detects superpowers from the official marketplace key."""
    plugins_json = _make_plugins_json(tmp_path, ["superpowers@claude-plugins-official"])
    registry = SeedRegistry()
    registry.register("superpowers", lambda: [])

    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        detected = registry.detect_installed_plugins()

    assert "superpowers" in detected


def test_detect_no_superpowers(tmp_path):
    """Registry returns empty when superpowers is not installed."""
    plugins_json = _make_plugins_json(tmp_path, ["other-plugin@marketplace"])
    registry = SeedRegistry()
    registry.register("superpowers", lambda: [])

    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        detected = registry.detect_installed_plugins()

    assert detected == set()


def test_detect_missing_plugins_json(tmp_path):
    """Missing installed_plugins.json returns empty set."""
    registry = SeedRegistry()
    registry.register("superpowers", lambda: [])

    with patch("decision.seeds.PLUGINS_JSON", tmp_path / "nonexistent.json"):
        detected = registry.detect_installed_plugins()

    assert detected == set()


def test_detect_corrupt_plugins_json(tmp_path):
    """Corrupt installed_plugins.json returns empty set."""
    bad_json = tmp_path / "installed_plugins.json"
    bad_json.write_text("not json {{{")
    registry = SeedRegistry()
    registry.register("superpowers", lambda: [])

    with patch("decision.seeds.PLUGINS_JSON", bad_json):
        detected = registry.detect_installed_plugins()

    assert detected == set()


# ── Seeding ──────────────────────────────────────────────────────────


def _make_registry_with_seeds(plugins_json):
    """Create a registry with superpowers seeds and mocked detection."""
    from decision.seeds._superpowers import superpowers_seeds

    registry = SeedRegistry()
    registry.register("superpowers", superpowers_seeds)
    return registry


def test_seed_creates_files(tmp_path):
    """seed_decisions creates decision files when superpowers is detected."""
    plugins_json = _make_plugins_json(tmp_path, ["superpowers@marketplace"])
    _, store = make_store(tmp_path)

    registry = _make_registry_with_seeds(plugins_json)
    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        count = registry.seed_decisions(store)

    assert count == 8
    assert (store.decisions_dir / "superpowers-tdd.md").is_file()
    assert (store.decisions_dir / "superpowers-design-first.md").is_file()


def test_seed_idempotent(tmp_path):
    """Second call to seed_decisions creates 0 new files."""
    plugins_json = _make_plugins_json(tmp_path, ["superpowers@marketplace"])
    _, store = make_store(tmp_path)

    registry = _make_registry_with_seeds(plugins_json)
    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        first = registry.seed_decisions(store)
        second = registry.seed_decisions(store)

    assert first == 8
    assert second == 0


def test_seed_respects_deletion(tmp_path):
    """Deleted decision file is not re-created on subsequent seed."""
    plugins_json = _make_plugins_json(tmp_path, ["superpowers@marketplace"])
    _, store = make_store(tmp_path)

    registry = _make_registry_with_seeds(plugins_json)
    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        registry.seed_decisions(store)

    # Delete one decision
    tdd_file = store.decisions_dir / "superpowers-tdd.md"
    assert tdd_file.exists()
    tdd_file.unlink()

    # Seed again — should not recreate
    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        count = registry.seed_decisions(store)

    assert count == 0
    assert not tdd_file.exists()


def test_seed_writes_manifest(tmp_path):
    """Seeding creates a .seeded.json manifest."""
    plugins_json = _make_plugins_json(tmp_path, ["superpowers@marketplace"])
    _, store = make_store(tmp_path)

    registry = _make_registry_with_seeds(plugins_json)
    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        registry.seed_decisions(store)

    manifest = _load_manifest(store.decisions_dir)
    assert "superpowers" in manifest["seeded"]
    assert len(manifest["seeded"]["superpowers"]["slugs"]) == 8


def test_seed_noop_when_not_installed(tmp_path):
    """No files created when superpowers is not installed."""
    plugins_json = _make_plugins_json(tmp_path, ["other-plugin@marketplace"])
    _, store = make_store(tmp_path)

    registry = _make_registry_with_seeds(plugins_json)
    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        count = registry.seed_decisions(store)

    assert count == 0
    assert not (store.decisions_dir / MANIFEST_FILE).exists()


def test_seeded_files_are_valid_decisions(tmp_path):
    """Every file created by seeding must parse and validate as a Decision."""
    plugins_json = _make_plugins_json(tmp_path, ["superpowers@marketplace"])
    _, store = make_store(tmp_path)

    registry = _make_registry_with_seeds(plugins_json)
    with patch("decision.seeds.PLUGINS_JSON", plugins_json):
        registry.seed_decisions(store)

    for md_file in store.decisions_dir.glob("superpowers-*.md"):
        d = Decision.from_file(md_file)
        errors = d.validate()
        assert errors == [], f"{md_file.name} failed validation: {errors}"
