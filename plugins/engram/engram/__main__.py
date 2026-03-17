"""CLI dispatch — enables `python3 -m engram <command>`."""
from __future__ import annotations

import json
import sys

from ._commits import engram_path_to_keywords
from ._validate import _validate_content_stdin
from .store import EngramStore


def _arg(n: int, default: str = ".engram") -> str:
    """Get sys.argv[n] or default."""
    return sys.argv[n] if len(sys.argv) > n else default


def _cmd_init() -> None:
    sys.exit(0 if EngramStore(_arg(2)).init() else 1)


def _cmd_query() -> None:
    result = EngramStore(_arg(2)).query_relevant(_arg(3, ""), int(_arg(4, "3")))
    if result:
        print(result)


def _cmd_tag_summary() -> None:
    result = EngramStore(_arg(2)).tag_summary()
    if result:
        print(result, end="")


def _cmd_find_incomplete() -> None:
    result = EngramStore(_arg(2)).find_incomplete(int(_arg(3, "5")))
    if result:
        print(result)


def _cmd_path_to_keywords() -> None:
    result = engram_path_to_keywords(_arg(2, ""))
    if result:
        print(result, end="")


def _cmd_uncommitted_summary() -> None:
    result = EngramStore(_arg(2)).uncommitted_summary()
    if result:
        print(result)


def _cmd_validate_content() -> None:
    errors = _validate_content_stdin()
    if errors:
        print(errors, file=sys.stderr)
        sys.exit(1)


def _cmd_policy() -> None:
    """Evaluate policies for a hook event, or list all policies."""
    from ._policy_defs import ALL_POLICIES
    from .policy import PolicyEngine, SessionState

    event = _arg(2, "")

    if not event:
        # List mode — print all policies as JSON
        engine = PolicyEngine()
        for p in ALL_POLICIES:
            engine.register(p)
        print(json.dumps(engine.list_policies(), indent=2))
        return

    # Check for --trace flag
    trace_flag = "--trace" in sys.argv

    # Evaluate mode — read stdin JSON, evaluate policies, print result
    input_text = sys.stdin.read()
    try:
        input_data = json.loads(input_text) if input_text.strip() else {}
    except json.JSONDecodeError:
        input_data = {}

    engine = PolicyEngine()
    for p in ALL_POLICIES:
        engine.register(p)

    # Load config and apply
    store = EngramStore(".engram")
    policy_cfg = store.policy_config()
    if policy_cfg:
        engine.apply_config(policy_cfg)

    # Enable tracing from config or --trace flag
    if trace_flag or store.trace_enabled:
        engine._trace_enabled = True

    state = SessionState()
    result = engine.evaluate(event, input_data, state)

    # If --trace flag, output result + trace as JSON
    if trace_flag:
        parsed = json.loads(result) if result else {}
        print(json.dumps({"result": parsed, "trace": engine._last_trace}, indent=2))
    else:
        print(result)


_COMMANDS: dict[str, callable] = {
    "init": _cmd_init,
    "resync": lambda: EngramStore(_arg(2)).resync(),
    "reindex": lambda: EngramStore(_arg(2)).reindex(),
    "brief": lambda: EngramStore(_arg(2)).brief(),
    "query": _cmd_query,
    "tag-summary": _cmd_tag_summary,
    "find-incomplete": _cmd_find_incomplete,
    "path-to-keywords": _cmd_path_to_keywords,
    "uncommitted-summary": _cmd_uncommitted_summary,
    "validate-content": _cmd_validate_content,
    "ingest-commits": lambda: EngramStore(_arg(2)).ingest_commits(),
    "ingest-plans": lambda: EngramStore(_arg(2)).ingest_plans(),
    "policy": _cmd_policy,
}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 -m engram <command> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    handler = _COMMANDS.get(cmd)
    if handler:
        handler()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
