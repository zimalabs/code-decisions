"""Plugin-aware decision seeding — detect installed plugins, seed methodology decisions."""

from __future__ import annotations

import dataclasses
import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

from ..store.store import DecisionStore
from ..utils.frontmatter import _format_yaml_frontmatter

MANIFEST_FILE = ".seeded.json"
PLUGINS_JSON = Path.home() / ".claude" / "plugins" / "installed_plugins.json"


@dataclasses.dataclass
class SeedDecision:
    """Template for a decision to seed from a detected plugin."""

    slug: str
    name: str
    description: str
    tags: list[str]
    affects: list[str]
    title: str
    body: str


class SeedRegistry:
    """Registry of decision seeds keyed by plugin identity."""

    def __init__(self) -> None:
        self._seeds: dict[str, Callable[[], list[SeedDecision]]] = {}

    def register(self, plugin_pattern: str, factory: Callable[[], list[SeedDecision]]) -> None:
        """Register a seed factory for a plugin name pattern."""
        self._seeds[plugin_pattern] = factory

    def detect_installed_plugins(self) -> set[str]:
        """Read installed_plugins.json and return matched plugin patterns."""
        try:
            data = json.loads(PLUGINS_JSON.read_text())
        except (OSError, json.JSONDecodeError):
            return set()

        plugin_keys = list(data.get("plugins", {}).keys())
        matched: set[str] = set()
        for pattern in self._seeds:
            for key in plugin_keys:
                if pattern in key:
                    matched.add(pattern)
                    break
        return matched

    def seed_decisions(self, store: DecisionStore) -> int:
        """Seed decisions for detected plugins. Returns count of newly created files."""
        detected = self.detect_installed_plugins()
        if not detected:
            return 0

        manifest = _load_manifest(store.decisions_dir)
        count = 0
        today = date.today().isoformat()

        for pattern in detected:
            factory = self._seeds[pattern]
            seeds = factory()
            already_seeded = set(manifest.get("seeded", {}).get(pattern, {}).get("slugs", []))

            new_slugs: list[str] = []
            for seed in seeds:
                if seed.slug in already_seeded:
                    continue  # previously seeded (possibly deleted by user)

                dest = store.decisions_dir / f"{seed.slug}.md"
                if dest.exists():
                    # File exists (maybe user-created) — record in manifest but don't overwrite
                    new_slugs.append(seed.slug)
                    continue

                frontmatter = _format_yaml_frontmatter(
                    {
                        "name": seed.name,
                        "description": seed.description,
                        "date": today,
                        "tags": seed.tags,
                        "affects": seed.affects,
                    }
                )
                content = f"{frontmatter}\n\n# {seed.title}\n\n{seed.body}\n"
                dest.write_text(content)
                new_slugs.append(seed.slug)
                count += 1

            if new_slugs:
                seeded_section = manifest.setdefault("seeded", {})
                entry = seeded_section.setdefault(pattern, {"slugs": [], "seeded_at": today})
                entry["slugs"] = sorted(set(entry["slugs"]) | set(new_slugs))

        if count:
            _save_manifest(store.decisions_dir, manifest)

        return count


def _load_manifest(decisions_dir: Path) -> dict[str, Any]:
    """Load the seeding manifest from .seeded.json."""
    path = decisions_dir / MANIFEST_FILE
    try:
        result: dict[str, Any] = json.loads(path.read_text())
        return result
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "seeded": {}}


def _save_manifest(decisions_dir: Path, manifest: dict[str, Any]) -> None:
    """Save the seeding manifest to .seeded.json."""
    manifest["version"] = 1
    path = decisions_dir / MANIFEST_FILE
    path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n")


_registry: SeedRegistry | None = None


def get_registry() -> SeedRegistry:
    """Return the singleton seed registry, lazily populated."""
    global _registry
    if _registry is None:
        _registry = SeedRegistry()
        from ._superpowers import superpowers_seeds

        _registry.register("superpowers", superpowers_seeds)
    return _registry
