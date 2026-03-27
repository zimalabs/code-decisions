"""CONTEXT policy — inject related past decisions when editing code files."""

from __future__ import annotations

import sys
from typing import Any

from ..utils.constants import RELATED_CONTEXT_LIMIT, SKIP_FILE_PATTERNS
from ..utils.helpers import _path_to_keywords
from ._helpers import _extract_content_keywords, _extract_file_path
from .engine import PolicyResult, SessionState


def _is_dir_prefix_match(affects_entry: str, norm_str: str) -> bool | None:
    """Directory prefix: "src/auth/" matches "src/auth/oauth.py".

    Returns True/False for directory entries, None for non-directory entries.
    """
    if not affects_entry.endswith("/"):
        return None
    return norm_str.startswith(affects_entry)


def _is_glob_match(affects_entry: str, norm_str: str) -> bool | None:
    """Glob pattern: "src/auth/*.py" matches "src/auth/oauth.py".

    Returns True/False for glob entries, None for non-glob entries.
    """
    if "*" not in affects_entry and "?" not in affects_entry:
        return None
    import fnmatch

    return fnmatch.fnmatch(norm_str, affects_entry)


def _is_segment_match(affects_parts: tuple[str, ...], file_parts: tuple[str, ...], file_stem: str) -> bool:
    """Segment-based matching: suffix comparison, stem matching, and stem-prefix matching."""
    # Suffix match: affects=["policy/engine.py"] matches "src/decision/policy/engine.py"
    if len(affects_parts) <= len(file_parts):
        if file_parts[-len(affects_parts) :] == affects_parts:
            return True
    elif affects_parts[-len(file_parts) :] == file_parts:
        return True

    # Stem match: affects=["core"] matches "core.py"
    if len(affects_parts) == 1 and affects_parts[0] == file_stem:
        return True

    # Stem-prefix match: affects=["src/auth"] matches "src/auth_helpers.py"
    # Requires a separator (_, .) after the stem to avoid "log" matching "login.py"
    return (
        len(affects_parts) > 1
        and len(file_parts) == len(affects_parts)
        and file_parts[:-1] == affects_parts[:-1]
        and file_parts[-1] != affects_parts[-1]
        and (file_parts[-1].startswith(affects_parts[-1] + "_") or file_parts[-1].startswith(affects_parts[-1] + "."))
    )


def _affects_match(affects: list[str], edited_path: str) -> bool:
    """Check if an edited file matches any path in a decision's affects list.

    Supports three matching modes (checked in order):
    - Directory prefix: entries ending with ``/`` match all files under that dir
    - Glob pattern: entries with ``*`` or ``?`` use fnmatch matching
    - Segment matching: exact path-segment suffix comparison (avoids false
      positives like affects=["util"] matching "utilities.py")
    """
    from pathlib import PurePosixPath

    norm = PurePosixPath(edited_path.lstrip("./"))
    norm_str = str(norm)
    norm_parts = norm.parts
    for a in affects:
        a_stripped = a.lstrip("./")

        dir_result = _is_dir_prefix_match(a_stripped, norm_str)
        if dir_result is not None:
            if dir_result:
                return True
            continue

        glob_result = _is_glob_match(a_stripped, norm_str)
        if glob_result is not None:
            if glob_result:
                return True
            continue

        affects_parts = PurePosixPath(a_stripped).parts
        if _is_segment_match(affects_parts, norm_parts, norm.stem):
            return True

    return False


def _has_stale_affects(affects: list[str]) -> bool:
    """Check if any affects path no longer exists on disk."""
    from pathlib import Path

    from ..utils.git import get_repo_root

    root = get_repo_root() or Path.cwd()
    for p in affects:
        # Glob patterns can't be checked — skip them
        if "*" in p or "?" in p:
            continue
        pp = Path(p)
        # Directory paths (trailing /) check with is_dir()
        check = Path.is_dir if p.endswith("/") else Path.is_file
        if pp.is_absolute():
            if not check(pp):
                return True
        else:
            root_segment = pp.parts[0] if pp.parts else ""
            if root_segment and (root / root_segment).exists():
                if not check(root / pp):
                    return True
    return False


def _scan_for_contradictions(
    seen_slugs: set[str],
    affects_matches: list[str],
    store: Any,
) -> str | None:
    """Check if surfaced decisions contradict each other.

    Returns a warning string or None.
    """
    try:
        from ..utils.contradiction import detect_pairwise

        bodies = store.get_bodies(seen_slugs)
        if len(bodies) < 2:
            return None

        # Build decision tuples for pairwise check — need affects from index
        affects_data: dict[str, list[str]] = {}
        for slug, _title, _date, _tags, affects in store.decisions_with_affects():
            if slug in seen_slugs:
                affects_data[slug] = affects

        decisions: list[tuple[str, str, list[str], list[str]]] = [
            (slug, body, [], affects_data.get(slug, [])) for slug, body in bodies.items()
        ]
        conflicts = detect_pairwise(decisions, threshold=0.5)
        if not conflicts:
            return None

        warnings = []
        for slug_a, slug_b, _score in conflicts[:2]:  # cap at 2 warnings
            warnings.append(f"  - `{slug_a}` and `{slug_b}` may conflict")
        return "⚠ Potential contradictions:\n" + "\n".join(warnings) + "\n  Review both before proceeding."
    except Exception as exc:
        print(f"decision: contradiction check error: {exc}", file=sys.stderr)
        return None  # Never break Claude Code


def _related_context_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Inject related past decisions when editing code files."""
    fp = _extract_file_path(data)
    if not fp:
        return None

    if any(pat in fp for pat in SKIP_FILE_PATTERNS):
        return None

    # Dedup: skip if already injected for this file
    dedup_key = f"related-context-{fp}"
    if state.has_fired(dedup_key):
        return None

    store = state.get_store()

    # Phase 1: exact affects-path matching (queries index, avoids full file parsing)
    affects_matches: list[str] = []
    seen_slugs: set[str] = set()
    has_affects_slugs: set[str] = set()
    for slug, title, date, tags, affects in store.decisions_with_affects():
        has_affects_slugs.add(slug)
        if _affects_match(affects, fp):
            stale = _has_stale_affects(affects)
            annotation = " ⚠ has stale paths" if stale else ""
            affects_matches.append(f"- [{date}] **{title}** (tags: {', '.join(tags)}){annotation}")
            seen_slugs.add(slug)

    # Record which decisions were surfaced (for analytics)
    for slug in seen_slugs:
        state.record_decision_surfaced(slug)

    # Contradiction scan: if 2+ decisions surfaced for the same file, check for conflicts
    if len(seen_slugs) >= 2:
        contradiction_msg = _scan_for_contradictions(seen_slugs, affects_matches, store)
        if contradiction_msg:
            affects_matches.append(contradiction_msg)

    # Phase 1.5: tag-based proximity for decisions WITHOUT affects.
    # Cross-cutting decisions (e.g. "always use structured logging") have no
    # natural affects path — surface them when their tags match file/content keywords.
    tag_matches: list[str] = []
    if not affects_matches:
        path_kw = _path_to_keywords(fp)
        content_kw = _extract_content_keywords(data)
        all_keywords = {w.lower() for w in (path_kw.split() + content_kw) if w}
        if all_keywords:
            TAG_MATCH_LIMIT = 2
            for summary in store.list_summaries():
                if summary.slug in seen_slugs or summary.slug in has_affects_slugs:
                    continue
                # Only match decisions without affects (those with affects are covered by Phase 1)
                dec_tags = [t.lower() for t in summary.tags]
                if any(tag in all_keywords for tag in dec_tags):
                    tag_matches.append(f"- [{summary.date}] **{summary.title}** (tags: {', '.join(summary.tags)})")
                    seen_slugs.add(summary.slug)
                    if len(tag_matches) >= TAG_MATCH_LIMIT:
                        break

    # Phase 2: keyword-based query only if no affects or tag matches
    keyword_results = ""
    if not affects_matches and not tag_matches:
        remaining = RELATED_CONTEXT_LIMIT
        path_kw = _path_to_keywords(fp)
        content_kw = _extract_content_keywords(data)
        keywords = " ".join(filter(None, [path_kw] + content_kw))
        if keywords:
            keyword_results = store.query(keywords, remaining, exclude_slugs=seen_slugs)

    if not affects_matches and not tag_matches and not keyword_results:
        return None

    state.mark_fired(dedup_key)
    state.increment_activity_counter("context_injections")

    # Visual feedback so the user knows the plugin is working
    if seen_slugs:
        slug_list = ", ".join(sorted(seen_slugs)[:3])
        short_fp = fp.split("/")[-1] if "/" in fp else fp
        print(f"  ◆ surfaced: {slug_list} (editing {short_fp})", file=sys.stderr)

    short_path = fp.split("/")[-1] if "/" in fp else fp

    # Build compact one-liner context (title list only — full content available via /decision search)
    if affects_matches:
        titles = [m.split("**")[1] if "**" in m else m for m in affects_matches if not m.startswith("⚠")]
        title_list = ", ".join(f"`{t}`" for t in titles[:3])
        n = len(titles)
        count_hint = f" (+{n - 3} more)" if n > 3 else ""
        msg = f"[{n} decision{'s' if n != 1 else ''} for {short_path}: {title_list}{count_hint}]"
        # Append contradiction warnings if any
        contradictions = [m for m in affects_matches if m.startswith("⚠")]
        if contradictions:
            msg += " " + contradictions[0].split("\n")[0]
        msg += " Read with `/decision search`."
    elif tag_matches:
        titles = [m.split("**")[1] if "**" in m else m for m in tag_matches]
        title_list = ", ".join(f"`{t}`" for t in titles[:3])
        msg = f"[Decision context for {short_path}: {title_list}]"
    elif keyword_results:
        msg = f"[Decision context for {short_path} · keyword match]\n{keyword_results}"
    else:
        msg = ""

    return PolicyResult(
        matched=True,
        reason=f"Related decision(s) for {short_path}",
        system_message=msg,
    )
