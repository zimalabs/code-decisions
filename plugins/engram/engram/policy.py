"""Policy engine — evaluates registered policies for hook events."""
from __future__ import annotations

import enum
import json
import os
import dataclasses
import sys
from pathlib import Path
from typing import Any, Callable


class PolicyLevel(enum.IntEnum):
    """Evaluation priority — lower numeric value = evaluated first."""
    BLOCK = 0
    LIFECYCLE = 1
    CONTEXT = 2
    NUDGE = 3


@dataclasses.dataclass
class PolicyResult:
    """Structured output from a policy evaluation."""
    matched: bool = False
    decision: str = ""        # "block" or empty
    reason: str = ""
    system_message: str = ""
    additional_context: str = ""
    ok: bool = True           # for Stop/UserPromptSubmit hooks
    suppress_output: bool = False

    def to_hook_json(self, event: str) -> dict[str, Any]:
        """Serialize to the JSON shape expected by the hook event type."""
        if self.decision == "block":
            return {"decision": "block", "reason": self.reason}

        if self.decision == "reject":
            return {"ok": False, "reason": self.reason}

        if event == "SessionStart" and self.additional_context:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": self.additional_context,
                }
            }

        if event in ("Stop", "UserPromptSubmit"):
            result: dict[str, Any] = {"ok": self.ok}
            if self.reason:
                result["reason"] = self.reason
            return result

        if self.system_message:
            return {"systemMessage": self.system_message}

        return {}


@dataclasses.dataclass
class Policy:
    """A single enforceable policy."""
    name: str
    description: str
    level: PolicyLevel
    events: list[str]
    matchers: list[str]
    condition: Callable[[dict[str, Any], SessionState], PolicyResult | None]
    once_per_session: bool = False


class SessionState:
    """Unified session state — replaces scattered /tmp/engram-* files.

    Single directory /tmp/engram-policy-{session_id}/ with per-policy marker files.
    """

    def __init__(self, session_id: str | None = None):
        sid = session_id or os.environ.get("CLAUDE_SESSION_ID", str(os.getpid()))
        self._dir = Path(f"/tmp/engram-policy-{sid}")
        self._dir.mkdir(parents=True, exist_ok=True)

    def has_fired(self, policy_name: str) -> bool:
        return (self._dir / policy_name).exists()

    def mark_fired(self, policy_name: str) -> None:
        (self._dir / policy_name).touch()

    def has_recent_signals(self, engram_dir: str = ".engram") -> bool:
        """Check if any decision file is newer than index.db."""
        root = Path(engram_dir)
        index = root / "index.db"
        decisions = root / "decisions"
        private = root / "_private" / "decisions"

        if index.is_file():
            for d in (decisions, private):
                if d.is_dir():
                    for f in d.glob("*.md"):
                        if f.stat().st_mtime > index.stat().st_mtime:
                            return True
            return False

        # No index.db — check if any decision files exist at all
        for d in (decisions, private):
            if d.is_dir() and any(d.glob("*.md")):
                return True
        return False


def _matches_event(policy: Policy, event: str, tool_name: str) -> bool:
    """Check if a policy matches the given event and tool matcher."""
    if event not in policy.events:
        return False
    if not policy.matchers or "*" in policy.matchers:
        return True
    # Check if tool_name matches any matcher pattern (pipe-separated in hooks.json)
    for m in policy.matchers:
        if tool_name == m:
            return True
    return False


class PolicyEngine:
    """Evaluates registered policies for a given hook event."""

    def __init__(self) -> None:
        self._policies: list[Policy] = []

    def register(self, policy: Policy) -> None:
        self._policies.append(policy)

    def evaluate(self, event: str, input_data: dict[str, Any],
                 session_state: SessionState) -> str:
        """Filter policies by event/matcher, run conditions, return JSON."""
        # Determine tool name from input (for matcher filtering)
        tool_name = input_data.get("tool_name", "*")

        # Filter matching policies, sorted by level priority
        matching = [
            p for p in self._policies
            if _matches_event(p, event, tool_name)
        ]
        matching.sort(key=lambda p: p.level)

        merged_messages: list[str] = []
        merged_context: list[str] = []
        result_ok = True
        result_reason = ""
        any_matched = False

        for policy in matching:
            # once_per_session check
            if policy.once_per_session and session_state.has_fired(policy.name):
                continue

            try:
                result = policy.condition(input_data, session_state)
            except Exception as exc:
                print(f"engram: policy {policy.name} error: {exc}", file=sys.stderr)
                continue

            if result is None or not result.matched:
                continue

            any_matched = True

            # Mark fired if once_per_session
            if policy.once_per_session:
                session_state.mark_fired(policy.name)

            # BLOCK or REJECT — fail-fast
            if result.decision in ("block", "reject"):
                return json.dumps(result.to_hook_json(event))

            # Collect messages
            if result.system_message:
                merged_messages.append(result.system_message)
            if result.additional_context:
                merged_context.append(result.additional_context)
            if result.reason:
                result_reason = result.reason
            if not result.ok:
                result_ok = False

        # Build merged response
        if event == "SessionStart" and merged_context:
            return json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n\n".join(merged_context),
                }
            })

        if event in ("Stop", "UserPromptSubmit"):
            if any_matched:
                resp: dict[str, Any] = {"ok": result_ok}
                if result_reason:
                    resp["reason"] = result_reason
                if merged_messages:
                    resp["reason"] = (resp.get("reason", "") + "\n" + "\n".join(merged_messages)).strip()
                return json.dumps(resp)
            return "{}"

        if merged_messages:
            return json.dumps({"systemMessage": "\n\n".join(merged_messages)})

        return "{}"

    def list_policies(self) -> list[dict[str, Any]]:
        """Return policy metadata for introspection."""
        return [
            {
                "name": p.name,
                "description": p.description,
                "level": p.level.name,
                "events": p.events,
                "matchers": p.matchers,
                "once_per_session": p.once_per_session,
            }
            for p in sorted(self._policies, key=lambda p: (p.level, p.name))
        ]
