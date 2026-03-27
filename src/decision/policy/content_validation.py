"""BLOCK policy — validate decision file content on Write."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from ._helpers import _extract_file_path, _is_decision_path
from .engine import PolicyResult, SessionState


def _record_capture() -> None:
    """Record that a decision was captured this session (for coaching suppression)."""
    import json
    import time

    from ..utils.helpers import _state_dir

    path = _state_dir() / "capture_history.json"
    try:
        history: list[float] = []
        if path.is_file():
            try:
                history = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        history.append(time.time())
        # Keep only last 20 entries
        history = history[-20:]
        path.write_text(json.dumps(history))
    except OSError:
        pass


def _content_validation_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Validate decision file content written via Write tool."""
    fp = _extract_file_path(data)
    if not fp or not _is_decision_path(fp):
        return None

    ti = data.get("tool_input", {})
    if not isinstance(ti, dict):
        return None

    content = ti.get("content", "")
    if not content:
        return None

    from ..core.decision import Decision

    dec = Decision.from_text(content)
    errors = dec.validate()

    if errors:
        # On validation failure, include capture template if not yet shown this session
        reason = "\n".join(f"- {e}" for e in errors)
        if not state.has_fired("_capture-template-shown"):
            state.mark_fired("_capture-template-shown")
            from .session_context import capture_template

            reason += "\n\n" + capture_template()
        return PolicyResult(
            matched=True,
            ok=False,
            decision="reject",
            reason=reason,
        )

    # On successful validation, inject template hint for first capture if not yet shown
    if not state.has_fired("_capture-template-shown"):
        state.mark_fired("_capture-template-shown")

    # Check affects first — if missing and we can infer, reject so agent re-writes with affects
    affects_result = _check_affects(dec, state, file_path=fp)
    if affects_result and affects_result.decision == "reject":
        return affects_result

    # Record successful capture for coaching suppression
    _record_capture()

    # Echo key metadata so the agent has structured data for confirmation
    affects_str = ", ".join(dec.affects) if dec.affects else "none"
    meta_msg = (
        f"Decision written: .claude/decisions/{dec.name}.md"
        f" | tags: {', '.join(dec.tags)}"
        f" | affects: {affects_str}"
        f" | date: {dec.date}"
    )
    result: PolicyResult | None = PolicyResult(matched=True, system_message=meta_msg)

    result = _merge_result(result, _check_overlap(dec, state, file_path=fp))
    result = _merge_result(result, _check_conflicts(dec, state))
    result = _merge_result(result, _check_reasoning_depth(dec))
    result = _merge_result(result, affects_result)
    return _maybe_tag_similarity_warning(dec, state, result)


def _check_overlap(dec: Any, state: SessionState, file_path: str = "") -> PolicyResult | None:
    """Check for overlapping active decisions and nudge consolidation."""
    if not dec.tags and not dec.affects:
        return None

    try:
        from ..utils.similarity import find_overlapping_decisions

        store = state.get_store()
        overlaps = find_overlapping_decisions(dec, store)
    except Exception:
        return None  # Never break Claude Code

    if not overlaps:
        return None

    overlap_lines = [f"  - `{slug}` — {title}" for slug, title, _score in overlaps[:3]]

    msg = (
        "Consolidation opportunity — this decision overlaps with:\n"
        + "\n".join(overlap_lines)
        + "\nConsider editing the existing decision instead of creating a new file, "
        "or verify these cover distinct concerns."
    )

    return PolicyResult(matched=True, system_message=msg)


def _merge_result(a: PolicyResult | None, b: PolicyResult | None) -> PolicyResult | None:
    """Merge two PolicyResults by concatenating system_messages."""
    if a is None:
        return b
    if b is None:
        return a
    msg_a = a.system_message or ""
    msg_b = b.system_message or ""
    combined = (msg_a + "\n\n" + msg_b).strip()
    return dataclasses.replace(a, system_message=combined) if combined else a


def _maybe_tag_similarity_warning(
    dec: Any, state: SessionState, base_result: PolicyResult | None
) -> PolicyResult | None:
    """Append a tag similarity warning if new tags look like near-duplicates of existing ones."""
    if not dec.tags:
        return base_result

    try:
        store = state.get_store()
        existing = list(store.all_tags().keys())
    except Exception:
        return base_result
    if not existing:
        return base_result

    from ..utils.similarity import similar_tags, suggest_tags_from_overlaps

    messages: list[str] = []

    matches = similar_tags(dec.tags, existing)
    if matches:
        warnings = [f'"{new}" is similar to existing tag "{ext}"' for new, ext in matches]
        messages.append("Tag similarity warning: " + "; ".join(warnings) + ". Consider reusing existing tags.")

    # Suggest related tags from overlapping decisions
    try:
        suggested = suggest_tags_from_overlaps(dec, store)
        if suggested:
            messages.append(
                "Related tags (from decisions with overlapping content): " + ", ".join(f"`{t}`" for t in suggested)
            )
    except Exception:
        pass  # Never break Claude Code

    if not messages:
        return base_result

    combined_msg = "\n".join(messages)
    if base_result and base_result.system_message:
        return dataclasses.replace(
            base_result,
            system_message=base_result.system_message + "\n\n" + combined_msg,
        )

    return PolicyResult(matched=True, system_message=combined_msg)


def _check_conflicts(dec: Any, state: SessionState) -> PolicyResult | None:
    """Check if a new decision contradicts existing ones."""
    if not dec.affects and not dec.tags:
        return None
    try:
        from ..utils.contradiction import find_contradictions
        from ..utils.similarity import find_overlapping_decisions

        store = state.get_store()
        overlaps = find_overlapping_decisions(dec, store, threshold=2.0, max_results=5)
        if not overlaps:
            return None

        # Get bodies for overlapping decisions
        overlap_slugs = {slug for slug, _, _ in overlaps}
        bodies = store.get_bodies(overlap_slugs)

        # Get affects for overlapping decisions
        affects_data: dict[str, list[str]] = {}
        for slug, _t, _d, _tags, affects in store.decisions_with_affects():
            if slug in overlap_slugs:
                affects_data[slug] = affects

        warnings: list[str] = []
        for slug, title, _score in overlaps:
            body = bodies.get(slug, "")
            if not body:
                continue
            contradiction = find_contradictions(dec.body, body, dec.affects, affects_data.get(slug, []))
            if contradiction >= 0.5:
                warnings.append(f"  - `{slug}` ({title})")

        if not warnings:
            return None

        msg = (
            "Potential conflict with existing decision(s):\n"
            + "\n".join(warnings)
            + "\nReview for consistency — if intentional, consider updating the older decision."
        )
        return PolicyResult(matched=True, system_message=msg)
    except Exception:
        return None  # Never break Claude Code


_ALTERNATIVES_RE = re.compile(
    r"\b(instead of|rather than|alternative|considered|rejected|ruled out|over)\b",
    re.IGNORECASE,
)


def _check_reasoning_depth(dec: Any) -> PolicyResult | None:
    """Nudge when a decision's reasoning is thin."""
    body = dec.body
    if not body:
        return None

    # Skip if body is already substantive (>200 chars of non-heading content)
    content_lines = [ln for ln in body.splitlines() if ln and not ln.startswith("#")]
    content_text = " ".join(content_lines)
    if len(content_text) > 200:
        return None  # Long enough — don't nag

    from ..core.decision import Decision

    has_reasoning = bool(Decision._REASONING_RE.search(body))
    has_alternatives = bool(_ALTERNATIVES_RE.search(body))

    if has_reasoning and has_alternatives:
        return None  # Looks substantive

    suggestions: list[str] = []
    if not has_reasoning:
        suggestions.append("why this choice was made (reasoning language like 'because', 'trade-off')")
    if not has_alternatives:
        suggestions.append("alternatives you rejected ('instead of X', 'ruled out Y')")

    if not suggestions:
        return None

    msg = "This decision's reasoning could be richer. Consider adding:\n" + "\n".join(f"  - {s}" for s in suggestions)
    return PolicyResult(matched=True, system_message=msg)


def _check_affects(dec: Any, state: SessionState, file_path: str = "") -> PolicyResult | None:
    """Warn if affects is empty or contains stale paths, auto-suggesting files.

    Stale-path warnings only fire for new decisions (file doesn't exist yet).
    Old decisions often reference renamed/moved files — that's expected, not an error.
    """
    if dec.affects:
        # Check stale paths on both new and existing decisions — stale affects
        # silently degrade proximity matching over time as files are renamed/deleted.
        from pathlib import Path

        cwd = Path.cwd()
        # Files touched this session are intentional (edited or deleted)
        session_files = set(state.files_edited())
        stale = []
        for p in dec.affects:
            if p in session_files:
                continue
            pp = Path(p)
            # Directory paths (trailing /) are valid — they match all files under that dir
            if p.endswith("/"):
                if pp.is_absolute():
                    if not pp.is_dir():
                        stale.append(p)
                else:
                    root_segment = pp.parts[0] if pp.parts else ""
                    if root_segment and (cwd / root_segment).exists():
                        if not (cwd / pp).is_dir():
                            stale.append(p)
                continue
            # Glob patterns can't be checked on disk — skip them
            if "*" in p or "?" in p:
                continue
            if pp.is_absolute():
                if not pp.is_file():
                    stale.append(p)
            else:
                # Only check relative paths whose root segment exists in CWD
                # (avoids false positives when CWD doesn't match project root)
                root_segment = pp.parts[0] if pp.parts else ""
                if root_segment and (cwd / root_segment).exists():
                    if not (cwd / pp).is_file():
                        stale.append(p)
        messages: list[str] = []
        if stale:
            stale_list = ", ".join(f'"{s}"' for s in stale[:5])
            messages.append(
                f"Warning: affects paths not found on disk: {stale_list}. "
                "Verify these paths are correct — stale paths degrade related-context matching."
            )
        # Suggest additional affects from sibling decisions with shared tags
        if dec.tags:
            try:
                store = state.get_store()
                from ..utils.affects import suggest_additional_affects

                additional = suggest_additional_affects(dec.affects, dec.tags, store)
                if additional:
                    suggestion_list = ", ".join(f'"{s}"' for s in additional)
                    messages.append(
                        f"Other decisions with these tags also affect: {suggestion_list}. "
                        "Consider adding them if this decision applies there too."
                    )
            except Exception:
                pass  # Never break Claude Code
        if messages:
            return PolicyResult(matched=True, system_message="\n\n".join(messages))
        return None

    # Auto-fill affects from session edits — reject so the agent re-writes with affects included
    edited = state.files_edited()
    if edited:
        from ..utils.affects import infer_affects

        suggestions = infer_affects(edited)
        if suggestions:
            affects_yaml = "\n".join(f'  - "{s}"' for s in suggestions)
            return PolicyResult(
                matched=True,
                ok=False,
                decision="reject",
                reason=(
                    "Decision is missing `affects` — add these inferred paths and rewrite:\n"
                    f"affects:\n{affects_yaml}\n"
                    "Insert the `affects` block into the YAML frontmatter, then write again."
                ),
            )

    # Fallback: suggest affects from decisions with shared tags
    if dec.tags:
        try:
            store = state.get_store()
            from ..utils.affects import suggest_affects_from_tags

            tag_suggestions = suggest_affects_from_tags(dec.tags, store)
            if tag_suggestions:
                affects_yaml = "\n".join(f'  - "{s}"' for s in tag_suggestions)
                return PolicyResult(
                    matched=True,
                    ok=False,
                    decision="reject",
                    reason=(
                        "Decision is missing `affects` — add these paths from related decisions and rewrite:\n"
                        f"affects:\n{affects_yaml}\n"
                        "Insert the `affects` block into the YAML frontmatter, then write again."
                    ),
                )
        except Exception:
            pass  # Never break Claude Code

    # No suggestions available — warn but allow the write through
    return PolicyResult(
        matched=True,
        system_message=(
            "This decision has no `affects` paths — it won't auto-surface when editing "
            'related files. Add paths like `"src/relevant_dir/"` or specific files. '
            "Tip: check which files relate to this topic, or look at affects from "
            "`/decision --tags`."
        ),
    )
