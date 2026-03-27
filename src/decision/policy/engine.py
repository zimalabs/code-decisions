"""Policy engine — evaluates registered policies for hook events."""

from __future__ import annotations

import dataclasses
import enum
import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import time
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..utils.constants import NUDGE_BUDGET, WRITE_TOOLS
from ..utils.helpers import _log

if TYPE_CHECKING:
    from ..store import DecisionStore


class PolicyLevel(enum.IntEnum):
    """Evaluation priority — lower numeric value = evaluated first."""

    BLOCK = 0
    LIFECYCLE = 1
    CONTEXT = 2
    NUDGE = 3


@dataclasses.dataclass(slots=True)
class PolicyResult:
    """Structured output from a policy evaluation."""

    matched: bool = False
    decision: str = ""  # "block" or "reject" or empty
    reason: str = ""
    system_message: str = ""
    additional_context: str = ""
    ok: bool = True  # for Stop/UserPromptSubmit hooks

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


@dataclasses.dataclass(slots=True)
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
    """Unified session state — tracks activity and policy firing.

    Single directory /tmp/decision-policy-{session_id}/ with per-policy marker files.

    Requires CLAUDE_SESSION_ID env var (set by Claude Code) for cross-process
    session tracking. Falls back to PID if unset, which means concurrent hook
    invocations without CLAUDE_SESSION_ID each get independent state dirs.
    """

    def __init__(self, session_id: str | None = None, store: DecisionStore | None = None):
        sid = session_id or os.environ.get("CLAUDE_SESSION_ID")
        if sid is None:
            # Stable fallback: hash cwd + parent PID so child processes share state
            raw = f"{os.getcwd()}:{os.getppid()}"
            sid = hashlib.sha256(raw.encode()).hexdigest()[:16]
            self._session_id_fallback = True
            _log("CLAUDE_SESSION_ID not set, using stable fallback from cwd+ppid")
        else:
            self._session_id_fallback = False
        self._dir = Path(tempfile.gettempdir()) / f"decision-policy-{sid}"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._activity: dict[str, Any] = self._load_activity_from_disk()
        self._start_time = float(int(time.time()))
        self._store: DecisionStore | None = store

    def get_store(self) -> DecisionStore:
        """Return a cached DecisionStore instance (created lazily)."""
        if self._store is None:
            from ..store import DecisionStore

            self._store = DecisionStore()
        return self._store

    @staticmethod
    def _safe_marker(key: str) -> str:
        """Convert a dedup key to a safe flat filename using a hash suffix."""
        # If the key contains path separators, use a hash to avoid collisions
        if "/" in key or "\\" in key:
            h = hashlib.sha256(key.encode()).hexdigest()[:12]
            return f"_marker_{h}"
        return key

    def has_fired(self, policy_name: str) -> bool:
        safe_name = self._safe_marker(policy_name)
        return (self._dir / safe_name).exists()

    def mark_fired(self, policy_name: str) -> None:
        """Mark a policy as fired. Uses exclusive creation to be safe against races."""
        safe_name = self._safe_marker(policy_name)
        path = self._dir / safe_name
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            pass  # already marked — benign race

    def store_data(self, key: str, value: str) -> None:
        """Store a string value alongside a marker key."""
        safe = self._safe_marker(key)
        path = self._dir / f"{safe}.data"
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        except OSError:
            pass

    def load_data(self, key: str) -> str:
        """Load stored data for a marker key. Returns empty string if absent."""
        safe = self._safe_marker(key)
        path = self._dir / f"{safe}.data"
        try:
            return path.read_text()
        except (OSError, ValueError):
            return ""

    def try_claim(self, policy_name: str) -> bool:
        """Atomically check-and-mark a policy as fired. Returns True if this call claimed it.

        Uses exclusive file creation (O_CREAT|O_EXCL) to avoid TOCTOU races
        when concurrent hook invocations run the same once_per_session policy.
        """
        safe_name = self._safe_marker(policy_name)
        path = self._dir / safe_name
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            return False

    # ── File locking ──────────────────────────────────────────────────

    @contextmanager
    def _acquire_activity_lock(self) -> Generator[None, None, None]:
        """Acquire an exclusive file lock to serialize activity/nudge writes."""
        lock_path = self._dir / "_activity.lock"
        self._dir.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as fd:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)

    # ── Activity tracking ─────────────────────────────────────────────

    def _activity_path(self) -> Path:
        return self._dir / "_activity.json"

    def _load_activity_from_disk(self) -> dict[str, Any]:
        p = self._activity_path()
        if p.is_file():
            try:
                data: dict[str, Any] = json.loads(p.read_text())
                return data
            except json.JSONDecodeError:
                _log(f"warning: corrupt activity file {p}, resetting")
            except OSError:
                pass
        return {"edits": []}

    def _save_activity(self) -> None:
        """Persist activity to disk atomically (lock + write to temp + rename)."""
        target = self._activity_path()
        try:
            with self._acquire_activity_lock():
                # Re-read from disk under lock to merge concurrent updates
                disk = self._load_activity_from_disk()
                # Merge: take max of counters, union of edit lists
                disk_edits = disk.get("edits", [])
                mem_edits = self._activity.get("edits", [])
                merged_edits = list(dict.fromkeys(disk_edits + mem_edits))  # union, preserving order
                self._activity["edits"] = merged_edits
                for key in ("edit_invocations", "decisions_surfaced", "nudges_fired"):
                    self._activity[key] = max(self._activity.get(key, 0), disk.get(key, 0))
                # Merge surfaced slugs (union, preserving order)
                disk_surfaced = disk.get("surfaced", [])
                mem_surfaced = self._activity.get("surfaced", [])
                if disk_surfaced or mem_surfaced:
                    self._activity["surfaced"] = list(dict.fromkeys(disk_surfaced + mem_surfaced))

                fd, tmp = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
                closed = False
                try:
                    os.write(fd, json.dumps(self._activity).encode())
                    os.close(fd)
                    closed = True
                    os.rename(tmp, str(target))
                except BaseException:
                    if not closed:
                        os.close(fd)
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                    raise
        except OSError as exc:
            _log(f"warning: failed to save activity: {exc}")

    def record_edit(self, file_path: str) -> None:
        """Record a code file edit (skips memory/ and decisions/ paths, caps at MAX_SESSION_EDITS).

        Persists on every call — each hook invocation creates a fresh SessionState
        from disk, so batching would lose the invocation counter.
        """
        if "/memory/" in file_path or "/decisions/" in file_path:
            return
        # Track total invocations (for checkpoint) and unique files (for stop_nudge/gate)
        self._activity["edit_invocations"] = self._activity.get("edit_invocations", 0) + 1
        edits = self._activity.get("edits", [])
        if file_path not in edits:
            from ..utils.constants import MAX_SESSION_EDITS

            if len(edits) >= MAX_SESSION_EDITS:
                return  # cap reached — gate/checkpoint thresholds are far below this
            edits.append(file_path)
            self._activity["edits"] = edits
        self._save_activity()

    def edit_count(self) -> int:
        return len(self._activity.get("edits", []))

    def edit_invocations(self) -> int:
        """Total number of edit tool calls (not deduplicated by file)."""
        return int(self._activity.get("edit_invocations", 0))

    def files_edited(self) -> list[str]:
        return list(self._activity.get("edits", []))

    def has_edits(self) -> bool:
        return self.edit_count() > 0

    def record_decision_surfaced(self, slug: str) -> None:
        """Record that a decision was surfaced this session (deduped, capped at 100)."""
        surfaced: list[str] = self._activity.get("surfaced", [])
        if slug not in surfaced:
            if len(surfaced) >= 100:
                return
            surfaced.append(slug)
            self._activity["surfaced"] = surfaced
            self._save_activity()

    def decisions_surfaced(self) -> list[str]:
        """Return slugs of decisions surfaced this session."""
        return list(self._activity.get("surfaced", []))

    def flush_activity(self) -> None:
        """Flush pending activity to disk (call before cross-process reads)."""
        if self._activity.get("edits"):
            self._save_activity()

    def cleanup(self) -> None:
        """Remove this session's state directory."""
        if self._dir.is_dir():
            shutil.rmtree(self._dir, ignore_errors=True)

    @staticmethod
    def cleanup_stale(max_age_seconds: int = 86400) -> int:
        """Remove /tmp/decision-policy-* dirs older than max_age_seconds. Returns count removed."""
        import tempfile

        removed = 0
        tmp = Path(tempfile.gettempdir())
        cutoff = time.time() - max_age_seconds
        for d in tmp.glob("decision-policy-*"):
            if not d.is_dir():
                continue
            try:
                if d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
        return removed

    # ── Nudge budget ────────────────────────────────────────────────

    def _nudge_count_path(self) -> Path:
        return self._dir / "_nudge_count"

    def nudge_count(self) -> int:
        """Read the per-session nudge counter from disk."""
        p = self._nudge_count_path()
        try:
            return int(p.read_text().strip())
        except (OSError, ValueError):
            return 0

    def increment_nudge_count(self) -> None:
        """Increment and persist the nudge counter atomically."""
        target = self._nudge_count_path()
        try:
            with self._acquire_activity_lock():
                # Re-read under lock to avoid lost increments
                count = self.nudge_count() + 1
                fd, tmp = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
                closed = False
                try:
                    os.write(fd, str(count).encode())
                    os.close(fd)
                    closed = True
                    os.rename(tmp, str(target))
                except BaseException:
                    if not closed:
                        os.close(fd)
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                    raise
        except OSError as exc:
            _log(f"warning: failed to save nudge count: {exc}")

    def nudge_budget_remaining(self, budget: int) -> bool:
        """Check if the nudge budget has remaining capacity."""
        return self.nudge_count() < budget

    def mark_nudges_dismissed(self) -> None:
        """Mark all nudges as dismissed for this session."""
        self.mark_fired("_nudges-dismissed")

    def nudges_dismissed(self) -> bool:
        """Check if nudges have been dismissed this session."""
        return self.has_fired("_nudges-dismissed")

    def increment_activity_counter(self, counter_name: str, amount: int = 1) -> None:
        """Increment a named activity counter in the activity file."""
        self._activity[counter_name] = self._activity.get(counter_name, 0) + amount
        self._save_activity()

    def get_activity_counter(self, counter_name: str) -> int:
        """Read a named activity counter."""
        return int(self._activity.get(counter_name, 0))

    def has_recent_decisions(self, decisions_dir: str | Path) -> bool:
        """Check if any decision file was modified after session state init."""
        d = Path(decisions_dir)
        if not d.is_dir():
            return False
        for f in d.glob("*.md"):
            try:
                if f.stat().st_mtime >= self._start_time:
                    return True
            except OSError:
                continue
        return False


def _matches_event(policy: Policy, event: str, tool_name: str) -> bool:
    """Check if a policy matches the given event and tool matcher."""
    if event not in policy.events:
        return False
    if not policy.matchers or "*" in policy.matchers:
        return True
    for m in policy.matchers:
        if tool_name == m:
            return True
    return False


class PolicyEngine:
    """Evaluates registered policies for a given hook event."""

    def __init__(self) -> None:
        self._policies: list[Policy] = []
        self.last_trace: list[dict[str, Any]] = []
        self.trace_enabled: bool = False

    def register(self, policy: Policy) -> None:
        self._policies.append(policy)

    @staticmethod
    def record_activity(event: str, input_data: dict[str, Any], session_state: SessionState) -> None:
        """Record edit activity from PostToolUse events. Call before evaluate."""
        if event == "PostToolUse":
            tool_name = input_data.get("tool_name", "")
            if tool_name in WRITE_TOOLS:
                ti = input_data.get("tool_input", {})
                if isinstance(ti, dict):
                    file_path = ti.get("file_path", "")
                    if file_path:
                        session_state.record_edit(file_path)

    @staticmethod
    def _trace_entry(
        policy: Policy,
        *,
        matched: bool = False,
        skipped: str = "",
        decision: str = "",
        elapsed_ms: float = 0,
    ) -> dict[str, Any]:
        """Build a single trace entry for policy evaluation diagnostics."""
        return {
            "policy": policy.name,
            "level": policy.level.name,
            "matched": matched,
            "skipped": skipped,
            "decision": decision,
            "elapsed_ms": elapsed_ms,
        }

    def evaluate(self, event: str, input_data: dict[str, Any], session_state: SessionState) -> str:
        """Filter policies by event/matcher, run conditions, return JSON."""
        eval_t0 = time.monotonic()
        self.record_activity(event, input_data, session_state)

        tool_name = input_data.get("tool_name", "*")

        matching = [p for p in self._policies if _matches_event(p, event, tool_name)]
        matching.sort(key=lambda p: p.level)

        merged_messages: list[str] = []
        merged_context: list[str] = []
        merged_reasons: list[str] = []
        result_ok = True
        any_matched = False
        self.last_trace = []

        for policy in matching:
            if policy.once_per_session and session_state.has_fired(policy.name):
                self.last_trace.append(self._trace_entry(policy, skipped="once_per_session"))
                continue

            # Nudge budget — skip remaining NUDGE policies when budget exhausted.
            if policy.level == PolicyLevel.NUDGE:
                budget = NUDGE_BUDGET
                if budget > 0 and not session_state.nudge_budget_remaining(budget):
                    self.last_trace.append(self._trace_entry(policy, skipped="nudge_budget_exhausted"))
                    continue

            t0 = time.monotonic()
            try:
                result = policy.condition(input_data, session_state)
            except Exception as exc:
                elapsed = round((time.monotonic() - t0) * 1000, 1)
                self.last_trace.append(self._trace_entry(policy, skipped=f"error: {exc}", elapsed_ms=elapsed))
                tb = traceback.format_exception(exc)
                _log(f"policy {policy.name} error: {type(exc).__name__}: {exc}\n{''.join(tb)}")
                continue
            elapsed = round((time.monotonic() - t0) * 1000, 1)

            if result is None or not result.matched:
                self.last_trace.append(self._trace_entry(policy, elapsed_ms=elapsed))
                continue

            any_matched = True
            decision = result.decision or ""

            self.last_trace.append(self._trace_entry(policy, matched=True, decision=decision, elapsed_ms=elapsed))

            if policy.once_per_session:
                session_state.mark_fired(policy.name)

            if policy.level == PolicyLevel.NUDGE:
                session_state.increment_nudge_count()

            # BLOCK or REJECT — fail-fast
            if decision in ("block", "reject"):
                self._emit_trace(event)
                return json.dumps(result.to_hook_json(event))

            if result.system_message:
                merged_messages.append(result.system_message)
            if result.additional_context:
                merged_context.append(result.additional_context)
            if result.reason:
                merged_reasons.append(result.reason)
            if not result.ok:
                result_ok = False

        # Plugin is always advisory — force ok=True
        result_ok = True

        # Track cumulative hook time for session activity summary
        eval_elapsed_ms = int((time.monotonic() - eval_t0) * 1000)
        session_state.increment_activity_counter("total_hook_ms", eval_elapsed_ms)

        self._emit_trace(event)
        return self._build_merged_response(
            event, merged_messages, merged_context, merged_reasons, result_ok, any_matched
        )

    @staticmethod
    def _build_merged_response(
        event: str,
        merged_messages: list[str],
        merged_context: list[str],
        merged_reasons: list[str],
        result_ok: bool,
        any_matched: bool,
    ) -> str:
        """Build the final JSON response from merged policy results."""
        if event == "SessionStart" and (merged_context or merged_messages):
            resp: dict[str, Any] = {}
            if merged_context:
                resp["hookSpecificOutput"] = {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n\n".join(merged_context),
                }
            if merged_messages:
                resp["systemMessage"] = "\n\n".join(merged_messages)
            return json.dumps(resp)

        if event in ("Stop", "UserPromptSubmit"):
            if any_matched:
                resp = {"ok": result_ok}
                all_reasons = merged_reasons + merged_messages
                if all_reasons:
                    resp["reason"] = "\n".join(all_reasons)
                return json.dumps(resp)
            return "{}"

        if merged_messages:
            result: dict[str, Any] = {"systemMessage": "\n\n".join(merged_messages)}
            if merged_reasons:
                result["reason"] = " | ".join(merged_reasons)
            return json.dumps(result)

        return "{}"

    def _emit_trace(self, event: str) -> None:
        """Print one-line trace summary to stderr if tracing is enabled."""
        if not self.trace_enabled:
            return
        matched = [t["policy"] for t in self.last_trace if t["matched"]]
        if matched:
            _log(f"trace: {event} -> {', '.join(matched)}")
        else:
            _log(f"trace: {event} -> (none matched)")

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
