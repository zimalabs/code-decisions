"""Constants used across the decision package."""

from __future__ import annotations

from pathlib import Path
from typing import Union

# ── Nudge budget (fixed — plugin is always advise-only) ───────────
NUDGE_BUDGET = 2

# Noise words for keyword extraction
NOISE_WORDS = frozenset(
    [
        "src",
        "lib",
        "app",
        "index",
        "test",
        "spec",
        "the",
        "and",
        "is",
        "of",
        "to",
        "in",
        "for",
        "a",
        "an",
    ]
)

# ── Named constants ──────────────────────────────────────────────────

SLUG_MAX_LEN = 50
EXCERPT_MAX_LEN = 200
EDIT_THRESHOLD = 5
MIN_LEAD_PARAGRAPH = 20
MIN_SECTION_TEXT = 50
RETURNING_USER_THRESHOLD = 5  # Skip explanatory text after this many decisions

# Keyword extraction
CONTENT_KEYWORD_LIMIT = 5
CONTENT_MIN_WORD_LEN = 4
IMPORTANT_SHORT_TERMS = frozenset(
    {
        "API",
        "SQL",
        "CSS",
        "XML",
        "JWT",
        "CLI",
        "SDK",
        "ORM",
        "MCP",
        "FTS",
        "SSR",
        "CDN",
        "DNS",
        "TLS",
        "SSH",
        "AWS",
        "GCP",
    }
)
PATH_KEYWORD_LIMIT = 5
PATH_MIN_SEGMENT_LEN = 3

# Query and context
RELATED_CONTEXT_LIMIT = 3
DEFAULT_QUERY_LIMIT = 3

# FTS5 index
INDEX_FILENAME = ".decision_index.db"
PREFIX_WILDCARD_MAX_LEN = 7  # terms <= this length get * suffix in FTS5
BUSY_TIMEOUT_MS = 3000  # SQLite busy_timeout for concurrent access

# Tool names for write-like operations (keep in sync with hooks.json matchers)
WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})


# Skip patterns for files that don't need decision context or nudges.
# dispatch.sh generates its fast-path list from this tuple at build time
# (see scripts/sync_skip_patterns.py). Keep patterns as simple substrings.
SKIP_FILE_PATTERNS = (
    "/memory/",
    "/decisions/",
    "_test.",
    ".test.",
    "/tests/",
    "/test/",
    "/spec/",
    "tests/",
    "test/",
    "spec/",
    "README.md",
    "CHANGELOG.md",
    "CLAUDE.md",
    "MEMORY.md",
    "/docs/",
    "/doc/",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".lock",
    # Images and media
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    # Non-code files
    "LICENSE",
    "Makefile",
    # Asset and vendor directories
    "/assets/",
    "/static/",
    "/public/",
    "/vendor/",
    # Fonts
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
)

# Capture nudge
FALSE_POSITIVE_WINDOW = 50  # chars to check after decision phrase for false positives

# Edit checkpoint
FOLLOWUP_EDIT_DELAY = 3  # min edits after capture-nudge before follow-up reminder

# Hook timing
SLOW_HOOK_THRESHOLD_MS = 500

# Implementation nudge — detect agent-side decisions from PostToolUse signals
IMPL_NEW_FILE_THRESHOLD = 3  # New files created before nudge fires
IMPL_NUDGE_MIN_EDITS = 6  # Minimum edit invocations before nudge evaluates
IMPL_NUDGE_COOLDOWN = 8  # Edit invocations between successive nudges
IMPL_BREADTH_FILE_THRESHOLD = 2  # New files needed when breadth condition also met
IMPL_BREADTH_DIR_THRESHOLD = 3  # Distinct directories needed for breadth condition

# Plan nudge — extract decisions from Claude Code plan files
PLAN_CANDIDATE_MAX = 5  # Max decision candidates to extract from a plan
PLAN_AFFECTS_MAX = 10  # Max file paths to extract from a plan

# Health check
STALENESS_COMMIT_THRESHOLD = 10
STALENESS_AGE_DAYS = 180  # Days before a decision is considered stale

# Similarity thresholds
TAG_SIMILARITY_THRESHOLD = 0.75  # edit distance ratio for near-duplicate tag detection

# Keyword search weights (fallback when FTS5 unavailable)
KEYWORD_WEIGHT_TITLE = 3
KEYWORD_WEIGHT_TAGS = 2
KEYWORD_WEIGHT_BODY = 1

# Coaching suppression — back off for experienced capturers
COACHING_SUPPRESS_THRESHOLD = 3  # sessions with captures needed to suppress coaching
COACHING_WINDOW = 5  # recent sessions to consider

# Never-surfaced detection
NEVER_SURFACED_AGE_DAYS = 30  # warn about recent decisions that never surfaced

# Session activity
MAX_SESSION_EDITS = 500  # Cap unique file paths tracked per session

# Transcript scanning (assistant decision detection at Stop time)
TRANSCRIPT_TAIL_BYTES = 65_536  # Read last 64KB of JSONL
TRANSCRIPT_MAX_BLOCKS = 20  # Max assistant text blocks to scan

# ── Type aliases ─────────────────────────────────────────────────────

StrPath = Union[str, Path]
