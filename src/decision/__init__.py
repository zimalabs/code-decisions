"""decision — Decision memory for Claude Code.

Captures why choices were made so future sessions inherit context instead of repeating debates.
Pure functions, no side effects at import time. Stdlib only.
"""

from __future__ import annotations

from ._version import __version__
from .core import Decision
from .policy import Policy, PolicyEngine, PolicyLevel, PolicyResult, SessionState
from .store import DecisionIndex, DecisionStore, SearchResult

__all__ = [
    "__version__",
    "Decision",
    "DecisionIndex",
    "DecisionStore",
    "Policy",
    "PolicyEngine",
    "PolicyLevel",
    "PolicyResult",
    "SearchResult",
    "SessionState",
]
