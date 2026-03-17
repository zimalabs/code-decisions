"""Policy definitions — one Policy per hook behavior, ported from shell scripts."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from ._commits import engram_path_to_keywords
from ._constants import _NOISE_WORDS
from .policy import Policy, PolicyLevel, PolicyResult, SessionState
from .store import EngramStore

ENGRAM_DIR = ".engram"

# Code noise words to filter from content keyword extraction
_CODE_NOISE = frozenset(
    {
        "self",
        "return",
        "import",
        "from",
        "class",
        "def",
        "none",
        "true",
        "false",
        "with",
        "elif",
        "else",
        "pass",
        "raise",
        "yield",
        "async",
        "await",
        "lambda",
        "assert",
        "global",
        "while",
        "break",
        "continue",
        "except",
        "finally",
        "print",
        "super",
        "init",
        "args",
        "kwargs",
        "dict",
        "list",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "type",
        "null",
        "undefined",
        "const",
        "function",
        "this",
        "that",
        "var",
        "void",
        "new",
        "delete",
        "typeof",
        "instanceof",
        "require",
        "module",
        "exports",
        "default",
        "value",
        "name",
        "data",
        "result",
        "error",
        "string",
        "number",
        "object",
        "array",
    }
)


# ── Helpers ──────────────────────────────────────────────────────────


def _extract_content_keywords(data: dict[str, Any], max_words: int = 3) -> list[str]:
    """Extract meaningful words from edit/write content for search."""
    ti = data.get("tool_input", {})
    if not isinstance(ti, dict):
        return []

    # Prefer new_string (Edit), fall back to content (Write)
    text = ti.get("new_string", "") or ti.get("content", "")
    if not text:
        return []

    # Tokenize: split on non-alphanumeric, keep words >= 4 chars
    words = re.findall(r"[a-zA-Z]{4,}", text)

    # Filter noise
    all_noise = _NOISE_WORDS | _CODE_NOISE
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        lower = w.lower()
        if lower in all_noise or lower in seen:
            continue
        seen.add(lower)
        result.append(lower)
        if len(result) >= max_words:
            break

    return result


def _extract_command(data: dict[str, Any]) -> str:
    """Extract command string from hook input."""
    # tool_input.command for Bash tool
    ti = data.get("tool_input", {})
    if isinstance(ti, dict):
        return ti.get("command", "")  # type: ignore[no-any-return]
    return ""


def _extract_file_path(data: dict[str, Any]) -> str:
    """Extract file_path from hook input."""
    ti = data.get("tool_input", {})
    if isinstance(ti, dict):
        return ti.get("file_path", "")  # type: ignore[no-any-return]
    return ""


def _is_engram_signal_path(path: str) -> bool:
    """Check if path targets .engram/decisions/ or .engram/_private/decisions/."""
    return ".engram/decisions/" in path or ".engram/_private/decisions/" in path


def _json_escape(s: str) -> str:
    """Escape a string for embedding in JSON."""
    import json

    return json.dumps(s)[1:-1]  # strip surrounding quotes


# ── BLOCK policies ───────────────────────────────────────────────────


def _commit_gate_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Nudge about missing signals on git commit (no longer blocks)."""
    if not Path(f"{ENGRAM_DIR}/decisions").is_dir():
        return None

    cmd = _extract_command(data)
    if not cmd:
        return None

    # Only nudge on git commit (not amend, not other git commands)
    if not cmd.startswith("git commit"):
        return None
    if "--amend" in cmd:
        return None

    if state.has_recent_signals(ENGRAM_DIR):
        return None

    # Nudge once, don't block
    return PolicyResult(
        matched=True,
        system_message=(
            "No decision signal written this session. If you made significant decisions, "
            "consider writing a signal after this commit (use /engram:capture)."
        ),
    )


def _delete_guard_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Block deletion of .engram signal files."""
    if not Path(ENGRAM_DIR).is_dir():
        return None

    cmd = _extract_command(data)
    if not cmd:
        return None

    # rm targeting specific signal files
    if re.search(r"rm\b.*\.engram/decisions/", cmd) or re.search(r"rm\b.*\.engram/_private/decisions/", cmd):
        return PolicyResult(
            matched=True,
            decision="block",
            reason=(
                "Signals are append-only \u2014 do not delete .engram/ decision files. "
                "Write a new signal with status: withdrawn instead."
            ),
        )

    # rm -rf or rm -r targeting .engram
    if re.search(r"rm\b.*-r[f ]?.*\.engram", cmd) or re.search(r"rm\b.*-rf.*\.engram", cmd):
        return PolicyResult(
            matched=True,
            decision="block",
            reason="Do not delete the .engram/ directory or its contents. Signals are append-only.",
        )

    # git checkout -- .engram/decisions/
    if re.search(r"git checkout.*--.*\.engram/(decisions|_private)/", cmd):
        return PolicyResult(
            matched=True,
            decision="block",
            reason=(
                "Do not revert .engram/ signal files. Signals are append-only \u2014 "
                "write a new signal with status: withdrawn instead."
            ),
        )

    # git restore .engram/decisions/
    if re.search(r"git restore.*\.engram/(decisions|_private)/", cmd):
        return PolicyResult(
            matched=True,
            decision="block",
            reason="Do not restore/revert .engram/ signal files. Signals are append-only.",
        )

    return None


def _edit_guard_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Block content deletion from signal files via Edit tool."""
    fp = _extract_file_path(data)
    if not fp or not _is_engram_signal_path(fp):
        return None

    ti = data.get("tool_input", {})
    if not isinstance(ti, dict):
        return None

    old_string = ti.get("old_string", "")
    if not old_string:
        return None

    new_string = ti.get("new_string", "")
    if not new_string:
        return PolicyResult(
            matched=True,
            decision="block",
            reason=(
                "Signals are append-only \u2014 do not delete content from .engram/ decision files. "
                "To retract a decision, set status: withdrawn in frontmatter."
            ),
        )

    return None


def _content_validation_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Validate signal file content written via Write tool."""
    fp = _extract_file_path(data)
    if not fp or not _is_engram_signal_path(fp):
        return None

    ti = data.get("tool_input", {})
    if not isinstance(ti, dict):
        return None

    content = ti.get("content", "")
    if not content:
        return None

    # Validate using Signal.validate() for consistency
    from .signal import Signal

    sig = Signal.from_text(content)
    ok, errors = sig.validate()

    if not ok:
        return PolicyResult(
            matched=True,
            ok=False,
            decision="reject",
            reason=errors,
        )

    return None


# ── LIFECYCLE policies ───────────────────────────────────────────────


def _session_init_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Initialize engram and resync at session start."""
    store = EngramStore(ENGRAM_DIR)

    store.init()
    store.resync()

    # Gather stats for banner
    decisions = 0
    private = 0
    if store.db_path.is_file():
        try:
            with store.connect() as conn:
                decisions = conn.execute("SELECT COUNT(*) FROM signals WHERE type='decision'").fetchone()[0]
                private = conn.execute("SELECT COUNT(*) FROM signals WHERE private=1").fetchone()[0]
        except sqlite3.Error:
            pass

    # Print banner to stderr
    lines = ["", "  \u25c6 engram active", f"  \u251c\u2500 {decisions} decisions"]
    uncommitted_msg = store.uncommitted_summary()
    if uncommitted_msg:
        lines.append(f"  \u251c\u2500 {uncommitted_msg}")
    if private > 0:
        lines.append(f"  \u251c\u2500 {private} private signals")
    lines.append(f"  \u2514\u2500 {decisions} signals indexed")
    lines.append("")
    print("\n".join(lines), file=sys.stderr)

    return PolicyResult(matched=True)


def _session_cleanup_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Resync at session end."""
    if not Path(ENGRAM_DIR).is_dir():
        return None
    store = EngramStore(ENGRAM_DIR)
    store.resync()
    return PolicyResult(matched=True)


def _push_resync_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Auto-resync after git push."""
    if not Path(ENGRAM_DIR).is_dir():
        return None

    cmd = _extract_command(data)
    if not cmd or not cmd.startswith("git push"):
        return None

    store = EngramStore(ENGRAM_DIR)
    store.resync()

    return PolicyResult(
        matched=True,
        system_message="engram resynced after push.",
    )


# ── CONTEXT policies ────────────────────────────────────────────────


def _session_context_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Inject brief and behavioral instructions at session start."""
    brief_path = Path(ENGRAM_DIR) / "brief.md"
    if not brief_path.is_file():
        return None

    brief = brief_path.read_text()
    if not brief:
        return None

    instructions = brief

    # For large signal stores, append tag summary
    store = EngramStore(ENGRAM_DIR)
    decisions = 0
    if store.db_path.is_file():
        try:
            with store.connect() as conn:
                decisions = conn.execute("SELECT COUNT(*) FROM signals WHERE type='decision'").fetchone()[0]
        except sqlite3.Error:
            pass

    if decisions > 30:
        tag_line = store.tag_summary()
        if tag_line:
            instructions += "\n" + tag_line

    instructions += (
        "\n\n---\n"
        "You have a persistent decision store via engram (.engram/ directory).\n"
        "When you make a significant decision, write a signal file:\n"
        "  Write .engram/decisions/{slug}.md  (use the decision schema)\n"
        "\n"
        "For PRIVATE signals (sensitive, excluded from brief and context):\n"
        "  Write .engram/_private/decisions/{slug}.md\n"
        "\n"
        "To query past signals:\n"
        "  /engram:query <question>"
    )

    return PolicyResult(
        matched=True,
        additional_context=instructions,
    )


def _related_context_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Inject related past decisions when editing code files."""
    fp = _extract_file_path(data)
    if not fp:
        return None

    # Skip .engram/ paths, tests, docs, config files
    skip_patterns = (
        ".engram/",
        "_test.",
        ".test.",
        "/tests/",
        "/test/",
        "/spec/",
        "tests/",
        "test/",
        "spec/",
        ".md",
        "/docs/",
        "/doc/",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".lock",
    )
    if any(pat in fp for pat in skip_patterns):
        return None

    index_path = Path(ENGRAM_DIR) / "index.db"
    if not index_path.is_file():
        return None

    path_keywords = engram_path_to_keywords(fp)
    content_kw = _extract_content_keywords(data)
    keywords = " ".join(filter(None, [path_keywords] + content_kw))
    if not keywords:
        return None

    # Dedup: skip if already injected for these keywords
    dedup_key = f"related-context-{keywords}"
    if state.has_fired(dedup_key):
        return None

    store = EngramStore(ENGRAM_DIR)
    results = store.query_relevant(keywords, 3)
    if not results:
        return None

    state.mark_fired(dedup_key)
    return PolicyResult(
        matched=True,
        system_message=f"Related past decisions:\n{results}",
    )


def _subagent_context_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Inject brief into subagent results."""
    if not Path(ENGRAM_DIR).is_dir():
        return None

    msg_parts = []

    brief_path = Path(ENGRAM_DIR) / "brief.md"
    if brief_path.is_file():
        brief = brief_path.read_text()
        if brief:
            msg_parts.append(brief)

    # Nudge about capture (once per session)
    if not state.has_fired("subagent-context"):
        state.mark_fired("subagent-context")
        msg_parts.append("If this subagent made architectural decisions, capture them with /engram:capture.")

    if not msg_parts:
        return None

    return PolicyResult(
        matched=True,
        system_message="\n\n".join(msg_parts),
    )


def _compact_context_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Regenerate and re-inject brief before context is compacted."""
    if not Path(ENGRAM_DIR).is_dir():
        return None

    store = EngramStore(ENGRAM_DIR)
    store.reindex()
    store.brief()

    brief_path = Path(ENGRAM_DIR) / "brief.md"
    if not brief_path.is_file():
        return None

    brief = brief_path.read_text()
    if not brief:
        return None

    return PolicyResult(
        matched=True,
        system_message=brief,
    )


# ── NUDGE policies ──────────────────────────────────────────────────


def _capture_nudge_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Nudge about decision capture after code edits (once per session, after 3+ edits)."""
    fp = _extract_file_path(data)
    if not fp:
        return None

    # Skip .engram/ paths, tests, docs, config files
    skip_patterns = (
        ".engram/",
        "_test.",
        ".test.",
        "/tests/",
        "/test/",
        "/spec/",
        "tests/",
        "test/",
        "spec/",
        ".md",
        "/docs/",
        "/doc/",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".lock",
    )
    if any(pat in fp for pat in skip_patterns):
        return None

    if not Path(f"{ENGRAM_DIR}/decisions").is_dir():
        return None

    # Significance threshold: only nudge after 3+ qualifying edits
    if state.edit_count() < 3:
        return None

    if state.has_recent_signals(ENGRAM_DIR):
        return None

    return PolicyResult(
        matched=True,
        system_message="Consider recording this decision with /engram:capture.",
    )


def _stop_nudge_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Reflection prompt at stop — summarize session edits and ask about decisions."""
    decisions_dir = Path(ENGRAM_DIR) / "decisions"
    if not decisions_dir.is_dir():
        return PolicyResult(matched=True, ok=True)

    index_path = Path(ENGRAM_DIR) / "index.db"
    has_recent = False
    if index_path.is_file():
        for f in decisions_dir.glob("*.md"):
            if f.stat().st_mtime > index_path.stat().st_mtime:
                has_recent = True
                break

    if has_recent:
        # Check for incomplete signals — nudge toward backfill
        if index_path.is_file() and not state.has_fired("backfill-nudge"):
            try:
                store = EngramStore(ENGRAM_DIR)
                with store.connect() as conn:
                    invalid_count = conn.execute("SELECT COUNT(*) FROM signals WHERE status='invalid'").fetchone()[0]
                if invalid_count > 0:
                    state.mark_fired("backfill-nudge")
                    return PolicyResult(
                        matched=True,
                        ok=True,
                        reason=f"{invalid_count} incomplete signal(s) \u2014 consider /engram:backfill to enrich them.",
                    )
            except sqlite3.Error:
                pass
        return PolicyResult(matched=True, ok=True)

    if not index_path.is_file():
        return PolicyResult(matched=True, ok=True)

    # Read-only session guard: don't nudge if no code was edited
    if not state.has_edits():
        return PolicyResult(matched=True, ok=True)

    # Build a reflection prompt with the list of edited files
    edited = state.files_edited()
    files_summary = ", ".join(edited[:10])
    if len(edited) > 10:
        files_summary += f" (+{len(edited) - 10} more)"

    return PolicyResult(
        matched=True,
        ok=True,
        reason=(
            f"Session reflection: you edited {len(edited)} file(s): {files_summary}. "
            "Which of these changes were significant decisions "
            "(architecture, new features, refactors, dependency changes)? "
            "Write signals for those with /engram:capture. Skip if all changes were routine."
        ),
    )


def _decision_language_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Detect decision language in user messages."""
    ti = data.get("tool_input", {})
    if isinstance(ti, dict):
        prompt = ti.get("content", "")
    else:
        prompt = ""

    if not prompt:
        return None

    prompt_lower = prompt.lower()

    # Check for past-decision queries (always respond, no dedup)
    if re.search(r"(why did we|what was decided|what did we decide|remind me)", prompt_lower):
        return PolicyResult(
            matched=True,
            ok=True,
            reason="Past signals may exist \u2014 consider /engram:query.",
        )

    # Check for decision language (per-phrase dedup)
    match = re.search(
        r"(let.?s go with|we decided|switching to|going with|the decision is|we.?ll use|agreed on|settled on)",
        prompt_lower,
    )
    if match:
        phrase = match.group(1)
        dedup_key = f"decision-language-{phrase}"
        if state.has_fired(dedup_key):
            return None
        state.mark_fired(dedup_key)
        return PolicyResult(
            matched=True,
            ok=True,
            reason="That sounds like a decision \u2014 consider /engram:capture.",
        )

    return None


def _incomplete_nudge_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Suggest enrichment for incomplete signals at notification time."""
    index_path = Path(ENGRAM_DIR) / "index.db"
    if not index_path.is_file():
        return None

    try:
        store = EngramStore(ENGRAM_DIR)
        with store.connect() as conn:
            invalid_count = conn.execute("SELECT COUNT(*) FROM signals WHERE status='invalid'").fetchone()[0]
    except sqlite3.Error:
        return None

    if invalid_count <= 0:
        return None

    return PolicyResult(
        matched=True,
        system_message=f"{invalid_count} incomplete decision(s) \u2014 consider /engram:backfill to enrich them.",
    )


# ── Registry ─────────────────────────────────────────────────────────

ALL_POLICIES: list[Policy] = [
    # NUDGE (was BLOCK — downgraded to reduce adversarial compliance)
    Policy(
        name="commit-gate",
        description="Nudge about missing signals on git commit",
        level=PolicyLevel.NUDGE,
        events=["PostToolUse"],
        matchers=["Bash"],
        condition=_commit_gate_condition,
        once_per_session=True,
    ),
    Policy(
        name="delete-guard",
        description="Block deletion of .engram signal files",
        level=PolicyLevel.BLOCK,
        events=["PreToolUse"],
        matchers=["Bash"],
        condition=_delete_guard_condition,
    ),
    Policy(
        name="edit-guard",
        description="Block content deletion from signal files via Edit tool",
        level=PolicyLevel.BLOCK,
        events=["PreToolUse"],
        matchers=["Edit"],
        condition=_edit_guard_condition,
    ),
    Policy(
        name="content-validation",
        description="Validate signal file frontmatter and structure on Write",
        level=PolicyLevel.BLOCK,
        events=["PreToolUse"],
        matchers=["Write"],
        condition=_content_validation_condition,
    ),
    # LIFECYCLE
    Policy(
        name="session-init",
        description="Initialize engram directory, resync index, print banner",
        level=PolicyLevel.LIFECYCLE,
        events=["SessionStart"],
        matchers=["*"],
        condition=_session_init_condition,
    ),
    Policy(
        name="session-cleanup",
        description="Resync index at session end",
        level=PolicyLevel.LIFECYCLE,
        events=["SessionEnd"],
        matchers=["*"],
        condition=_session_cleanup_condition,
    ),
    Policy(
        name="push-resync",
        description="Auto-resync after git push",
        level=PolicyLevel.LIFECYCLE,
        events=["PostToolUse"],
        matchers=["Bash"],
        condition=_push_resync_condition,
    ),
    # CONTEXT
    Policy(
        name="session-context",
        description="Inject decision brief and instructions at session start",
        level=PolicyLevel.CONTEXT,
        events=["SessionStart"],
        matchers=["*"],
        condition=_session_context_condition,
    ),
    Policy(
        name="related-context",
        description="Inject related past decisions when editing code files",
        level=PolicyLevel.CONTEXT,
        events=["PostToolUse"],
        matchers=["Write", "Edit", "MultiEdit"],
        condition=_related_context_condition,
    ),
    Policy(
        name="subagent-context",
        description="Inject brief into subagent results",
        level=PolicyLevel.CONTEXT,
        events=["SubagentStop"],
        matchers=["*"],
        condition=_subagent_context_condition,
    ),
    Policy(
        name="compact-context",
        description="Regenerate and re-inject brief before context compaction",
        level=PolicyLevel.CONTEXT,
        events=["PreCompact"],
        matchers=["*"],
        condition=_compact_context_condition,
    ),
    # NUDGE
    Policy(
        name="capture-nudge",
        description="Nudge about decision capture after code edits",
        level=PolicyLevel.NUDGE,
        events=["PostToolUse"],
        matchers=["Write", "Edit", "MultiEdit"],
        condition=_capture_nudge_condition,
        once_per_session=True,
    ),
    Policy(
        name="stop-nudge",
        description="Check for recent signals at stop; nudge if none",
        level=PolicyLevel.NUDGE,
        events=["Stop"],
        matchers=["*"],
        condition=_stop_nudge_condition,
    ),
    Policy(
        name="decision-language",
        description="Detect decision language in user messages",
        level=PolicyLevel.NUDGE,
        events=["UserPromptSubmit"],
        matchers=["*"],
        condition=_decision_language_condition,
    ),
    Policy(
        name="incomplete-nudge",
        description="Suggest enrichment for incomplete signals",
        level=PolicyLevel.NUDGE,
        events=["Notification"],
        matchers=["*"],
        condition=_incomplete_nudge_condition,
        once_per_session=True,
    ),
]
