"""Policy engine — evaluates registered policies for hook events."""
from __future__ import annotations

import dataclasses
import enum
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


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

    # ── Activity tracking ─────────────────────────────────────────────

    def _activity_path(self) -> Path:
        return self._dir / "_activity.json"

    def _load_activity(self) -> dict[str, Any]:
        p = self._activity_path()
        if p.is_file():
            try:
                return json.loads(p.read_text())  # type: ignore[no-any-return]
            except (json.JSONDecodeError, OSError):
                pass
        return {"edits": []}

    def _save_activity(self, data: dict[str, Any]) -> None:
        try:
            self._activity_path().write_text(json.dumps(data))
        except OSError:
            pass

    def record_edit(self, file_path: str) -> None:
        """Record a code file edit (skips .engram/ paths)."""
        if ".engram/" in file_path:
            return
        activity = self._load_activity()
        edits = activity.get("edits", [])
        if file_path not in edits:
            edits.append(file_path)
            activity["edits"] = edits
            self._save_activity(activity)

    def edit_count(self) -> int:
        return len(self._load_activity().get("edits", []))

    def files_edited(self) -> list[str]:
        return list(self._load_activity().get("edits", []))

    def has_edits(self) -> bool:
        return self.edit_count() > 0

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
        self._disabled: set[str] = set()
        self._last_trace: list[dict[str, Any]] = []
        self._trace_enabled: bool = False

    def register(self, policy: Policy) -> None:
        self._policies.append(policy)

    def apply_config(self, config: dict[str, str]) -> None:
        """Disable policies listed as 'off' in config."""
        self._disabled = {
            name for name, value in config.items()
            if value == "off"
        }

    def evaluate(self, event: str, input_data: dict[str, Any],
                 session_state: SessionState) -> str:
        """Filter policies by event/matcher, run conditions, return JSON."""
        # Record edits for activity tracking
        if event == "PostToolUse":
            tool_name_for_edit = input_data.get("tool_name", "")
            if tool_name_for_edit in ("Write", "Edit", "MultiEdit"):
                fp = input_data.get("tool_input", {})
                if isinstance(fp, dict):
                    file_path = fp.get("file_path", "")
                    if file_path:
                        session_state.record_edit(file_path)

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
        self._last_trace = []

        for policy in matching:
            # Skip disabled policies
            if policy.name in self._disabled:
                self._last_trace.append({
                    "policy": policy.name, "level": policy.level.name,
                    "matched": False, "skipped": "disabled", "decision": "", "elapsed_ms": 0,
                })
                continue

            # once_per_session check
            if policy.once_per_session and session_state.has_fired(policy.name):
                self._last_trace.append({
                    "policy": policy.name, "level": policy.level.name,
                    "matched": False, "skipped": "once_per_session", "decision": "", "elapsed_ms": 0,
                })
                continue

            t0 = time.monotonic()
            try:
                result = policy.condition(input_data, session_state)
            except Exception as exc:
                elapsed = round((time.monotonic() - t0) * 1000, 1)
                self._last_trace.append({
                    "policy": policy.name, "level": policy.level.name,
                    "matched": False, "skipped": f"error: {exc}", "decision": "", "elapsed_ms": elapsed,
                })
                print(f"engram: policy {policy.name} error: {exc}", file=sys.stderr)
                continue
            elapsed = round((time.monotonic() - t0) * 1000, 1)

            if result is None or not result.matched:
                self._last_trace.append({
                    "policy": policy.name, "level": policy.level.name,
                    "matched": False, "skipped": "", "decision": "", "elapsed_ms": elapsed,
                })
                continue

            any_matched = True
            decision = result.decision or ""

            self._last_trace.append({
                "policy": policy.name, "level": policy.level.name,
                "matched": True, "skipped": "", "decision": decision, "elapsed_ms": elapsed,
            })

            # Mark fired if once_per_session
            if policy.once_per_session:
                session_state.mark_fired(policy.name)

            # BLOCK or REJECT — fail-fast
            if decision in ("block", "reject"):
                self._emit_trace(event)
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

        self._emit_trace(event)

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

    def _emit_trace(self, event: str) -> None:
        """Print one-line trace summary to stderr if tracing is enabled."""
        if not self._trace_enabled:
            return
        matched = [t["policy"] for t in self._last_trace if t["matched"]]
        if matched:
            print(f"engram trace: {event} -> {', '.join(matched)}", file=sys.stderr)
        else:
            print(f"engram trace: {event} -> (none matched)", file=sys.stderr)

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
