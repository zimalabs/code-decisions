"""engram core library — called by hooks and skills.

Pure functions, no side effects at import time.
Stdlib only: sqlite3, json, re, subprocess, pathlib, os, sys.
"""
from __future__ import annotations

import os
from pathlib import Path

from ._commits import _is_decision_commit, engram_path_to_keywords
from ._helpers import _check_fts5
from .policy import Policy, PolicyEngine, PolicyLevel, PolicyResult, SessionState
from .signal import Signal
from .store import EngramStore

__all__ = [
    "EngramStore", "Signal", "engram_path_to_keywords",
    "_is_decision_commit", "_check_fts5",
    "Policy", "PolicyEngine", "PolicyLevel", "PolicyResult", "SessionState",
]

# src/engram/ → src/ → plugin/ (CLAUDE_PLUGIN_ROOT)
ENGRAM_LIB_DIR = Path(__file__).resolve().parent.parent.parent
ENGRAM_SCHEMA_FILE = Path(
    os.environ.get("ENGRAM_SCHEMA_FILE", ENGRAM_LIB_DIR / "schemas" / "schema.sql")
)
