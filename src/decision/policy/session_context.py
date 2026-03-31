"""CONTEXT policy — inject decision summary and instructions at session start."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .engine import PolicyResult, SessionState

if TYPE_CHECKING:
    from ..store import DecisionStore


def _stale_affects_slugs(store: DecisionStore) -> list[str]:
    """Return slugs of decisions with affects paths that no longer exist on disk."""
    cwd = Path.cwd()
    stale: list[str] = []
    for d in store.list_decisions():
        if not d.affects:
            continue
        for p in d.affects:
            pp = Path(p)
            resolved = pp if pp.is_absolute() else cwd / pp
            if not resolved.exists():
                stale.append(d.slug)
                break
    return stale


def capture_template() -> str:
    """Return the decision capture template.

    Used by session-context (onboarding) and content-validation (lazy injection).
    """
    return (
        "Do NOT read the schema file. Use this template directly:\n"
        "```\n"
        "---\n"
        'name: "slug-name"\n'
        'description: "Actionable constraint — enough to act on without reading the file"\n'
        'date: "YYYY-MM-DD"\n'
        "tags:\n"
        '  - "topic"\n'
        "affects:\n"
        '  - "src/billing/"           # directory — all files under billing/\n'
        '  - "src/auth/middleware.py"  # specific file\n'
        "---\n\n"
        "# Title of the decision\n\n"
        "Why this choice was made (at least 20 characters).\n"
        "```\n"
        "Write to `.claude/decisions/{slug}.md`. "
        "Always populate `affects` — auto-infer from files edited this session "
        "(deduplicate to directory prefixes when 3+ files share a dir). "
        "Never leave affects empty — decisions without it are invisible to proximity context. "
        "The rules index at `.claude/rules/decisions.md` updates automatically. "
        "Confirm briefly, then continue with whatever the user asked."
    )


def _cli_prefix() -> str:
    """Return the shell prefix needed to run `python3 -m decision` outside hooks."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    if plugin_root:
        return f'PYTHONPATH="{plugin_root}" python3 -m decision'
    return "python3 -m decision"


def _session_context_condition(data: dict[str, Any], state: SessionState) -> PolicyResult | None:
    """Inject decision summary and instructions at session start."""
    from ..utils.constants import RETURNING_USER_THRESHOLD

    store = state.get_store()
    decisions = store.list_decisions()

    if not decisions:
        # First-run onboarding: concise value prop with a concrete "try it" prompt
        context = (
            "Decision plugin active — no decisions captured yet.\n\n"
            "**How it works:** When you choose between approaches, just say why "
            '(e.g. "let\'s use Redis because pub/sub") — the plugin captures it automatically. '
            "Future sessions and teammates inherit the reasoning via git.\n\n"
            "**Try it now:** Make a technical choice in this session and explain your reasoning. "
            "The plugin will write a decision file to `.claude/decisions/` — no slash command needed.\n\n"
            "Or use `/decision tour` for a quick interactive walkthrough."
        )
        cli = _cli_prefix()
        context += f"\n\nDecision CLI: `{cli}`"
        return PolicyResult(matched=True, additional_context=context)

    decisions.sort(key=lambda d: d.date, reverse=True)

    tag_counts = store.all_tags()
    topic_count = len(tag_counts)
    context = f"◆ {len(decisions)} decisions · {topic_count} topics · /decision search\n\n"

    if len(decisions) >= RETURNING_USER_THRESHOLD:
        # Returning user: slim context — just the summary + brief reminders.
        # Full template is injected lazily at capture time via content-validation.
        context += (
            "Auto-capture decisions when choosing between approaches. "
            "Search `/decision <topic>` before proposing.\n"
            "Decisions = technical choices shared via git (not personal preferences — those are memories)."
        )
    else:
        # Onboarding user (<5 decisions): concise instructions — full template
        # injects lazily at first capture via content-validation policy.
        context += (
            "Auto-capture decisions when choosing between approaches — write to "
            "`.claude/decisions/`. No confirmation needed.\n"
            "Search `/decision <topic>` before proposing. `/decision help` for all commands.\n"
            "First capture? The plugin will show the template automatically."
        )

    # Surface stale affects so users know some decisions may not surface correctly
    stale_slugs = _stale_affects_slugs(store)
    stale_count = len(stale_slugs)
    if stale_slugs:
        slug_list = ", ".join(f"`{s}`" for s in stale_slugs[:3])
        more = f" (and {stale_count - 3} more)" if stale_count > 3 else ""
        context += (
            f"\n⚠ {stale_count} decision{'s have' if stale_count != 1 else ' has'} stale `affects` paths"
            f": {slug_list}{more}"
            " — run `/decision list` to review."
        )

    # Surface degraded-mode warning so users know search quality is reduced
    if not store._index.available:
        context += "\n⚠ FTS5 unavailable — search is using keyword fallback (results may be less relevant)."

    # Inject CLI prefix so skills can run `python3 -m decision` with correct PYTHONPATH
    cli = _cli_prefix()
    context += f"\n\nDecision CLI: `{cli}`"

    # 1-line banner for the human (systemMessage) + full context for the agent (additionalContext)
    banner = f"◆ {len(decisions)} decisions · {topic_count} topics"
    if stale_slugs:
        banner += f" · ⚠ {stale_count} stale"

    return PolicyResult(matched=True, system_message=banner, additional_context=context)
