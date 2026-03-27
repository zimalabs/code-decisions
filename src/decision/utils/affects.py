"""Smart affects inference from session edit history."""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from .constants import SKIP_FILE_PATTERNS

_MAX_AFFECTS = 5


def infer_affects(edited_files: list[str]) -> list[str]:
    """Infer affects paths from session edits, preferring directory prefixes.

    Groups files by directory — if >=2 files share a directory, uses the
    directory prefix (e.g. ``src/auth/``) instead of individual paths.
    Singleton files stay as specific paths. Filters out test/config/doc files.
    Caps at ``_MAX_AFFECTS`` entries.
    """
    # Filter noise files
    filtered = [f for f in edited_files if not _is_noise(f)]
    if not filtered:
        return []

    # Normalize paths
    normalized = [str(PurePosixPath(f.lstrip("./"))) for f in filtered]

    # Group by parent directory
    by_dir: defaultdict[str, list[str]] = defaultdict(list)
    for p in normalized:
        parent = str(PurePosixPath(p).parent)
        by_dir[parent].append(p)

    result: list[str] = []
    for directory, files in sorted(by_dir.items(), key=lambda x: -len(x[1])):
        if len(result) >= _MAX_AFFECTS:
            break
        if directory == ".":
            # Root-level files — keep as individual paths
            for f in files:
                if len(result) >= _MAX_AFFECTS:
                    break
                result.append(f)
        elif len(files) >= 2:
            # Multiple files in same dir → use directory prefix
            result.append(directory + "/")
        else:
            # Single file in a dir → keep as specific path
            result.append(files[0])

    return result


def suggest_affects_from_tags(tags: list[str], store: object) -> list[str]:
    """Suggest affects paths from existing decisions that share tags.

    Looks at decisions with overlapping tags and returns their affects paths,
    deduplicated and capped at ``_MAX_AFFECTS``. Prefers directory prefixes.
    """
    from ..store.store import DecisionStore

    if not isinstance(store, DecisionStore):
        return []

    tag_set = set(tags)
    seen: dict[str, int] = {}  # path → frequency

    for _slug, _title, _date, dec_tags, affects in store.decisions_with_affects():
        if not tag_set & set(dec_tags):
            continue
        for p in affects:
            seen[p] = seen.get(p, 0) + 1

    if not seen:
        return []

    # Sort by frequency (most common first), then alphabetically
    ranked = sorted(seen, key=lambda p: (-seen[p], p))
    return ranked[:_MAX_AFFECTS]


def suggest_additional_affects(existing_affects: list[str], tags: list[str], store: object) -> list[str]:
    """Suggest affects paths that other decisions with shared tags have, but this one doesn't.

    Useful when a decision already has some affects but may be missing related paths
    that sibling decisions (same tags) also reference.
    """
    from ..store.store import DecisionStore

    if not isinstance(store, DecisionStore) or not tags:
        return []

    tag_set = set(tags)
    existing_set = set(existing_affects)
    # Normalize: strip trailing slashes and ./ for comparison
    existing_normalized = {p.rstrip("/").lstrip("./") for p in existing_affects}

    seen: dict[str, int] = {}  # path → frequency across sibling decisions

    for _slug, _title, _date, dec_tags, affects in store.decisions_with_affects():
        if not tag_set & set(dec_tags):
            continue
        for p in affects:
            # Skip paths the decision already has
            p_norm = p.rstrip("/").lstrip("./")
            if p in existing_set or p_norm in existing_normalized:
                continue
            # Skip if an existing directory prefix already covers this path
            if any(p_norm.startswith(e.rstrip("/")) for e in existing_normalized):
                continue
            seen[p] = seen.get(p, 0) + 1

    if not seen:
        return []

    # Only suggest paths referenced by 2+ sibling decisions (high confidence)
    confident = {p: count for p, count in seen.items() if count >= 2}
    if not confident:
        # Take the single most frequent path as a best-effort suggestion
        top = max(seen, key=lambda p: seen[p])
        confident = {top: seen[top]}

    ranked = sorted(confident, key=lambda p: (-confident[p], p))
    return ranked[:_MAX_AFFECTS]


def _is_noise(path: str) -> bool:
    """Check if a file path matches noise patterns (tests, config, docs)."""
    if path.endswith(".md"):
        return True
    return any(pat in path for pat in SKIP_FILE_PATTERNS)
