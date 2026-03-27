"""SQLite FTS5 derived search index for decision files.

The index is a cache — delete it and it rebuilds from markdown.
Markdown files remain the source of truth.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
import time
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import NamedTuple

from ..core.decision import Decision
from ..utils.constants import BUSY_TIMEOUT_MS, DEFAULT_QUERY_LIMIT, INDEX_FILENAME, PREFIX_WILDCARD_MAX_LEN, StrPath
from ..utils.helpers import _file_lock, _log

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_schema_cache: str | None = None


def _get_schema() -> str:
    """Lazily read schema.sql on first use (no I/O at import time)."""
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = _SCHEMA_PATH.read_text()
    return _schema_cache


@dataclasses.dataclass(slots=True)
class DecisionSummary:
    """Lightweight decision summary from the FTS5 index (no file parsing)."""

    slug: str
    title: str
    date: str
    description: str
    tags: list[str]
    excerpt: str


@dataclasses.dataclass(slots=True)
class SearchResult:
    """A single search result from the FTS5 index."""

    slug: str
    title: str
    date: str
    tags: list[str]
    excerpt: str
    rank: float


class DecisionAffects(NamedTuple):
    """Decision with its affects paths — used by related-context and coverage."""

    slug: str
    title: str
    date: str
    tags: list[str]
    affects: list[str]


def _parse_json_list(raw: str) -> list[str]:
    """Parse a JSON array string, falling back to comma-split for legacy data.

    Tags and affects are stored as JSON arrays (e.g. '["auth","api"]') in the
    FTS5 index. Early versions stored them as comma-separated strings
    (e.g. 'auth, api'). This function handles both formats so the index
    remains backward-compatible when reading rows written by older versions.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (json.JSONDecodeError, TypeError):
        if raw.lstrip().startswith(("[", "{")):
            _log(f"warning: malformed JSON in index field: {raw[:60]}")
        pass
    # Legacy: comma-separated (only if it looks like a real comma list)
    if "," in raw:
        return [t.strip() for t in raw.split(",") if t.strip()]
    stripped = raw.strip()
    return [stripped] if stripped else []


class DecisionIndex:
    """SQLite FTS5 derived index over decision markdown files."""

    # Skip re-syncing if checked within this many seconds (avoids redundant stat calls
    # when multiple index methods are called in a single policy evaluation).
    _FRESHNESS_TTL_SECS = 0.5

    def __init__(self, decisions_dir: StrPath, *, db_dir: StrPath | None = None) -> None:
        self.decisions_dir = Path(decisions_dir)
        if db_dir is not None:
            state = Path(db_dir)
            state.mkdir(parents=True, exist_ok=True)
        else:
            from ..utils.helpers import _state_dir

            state = _state_dir()
        self.db_path = state / INDEX_FILENAME
        self._lock_path = self.db_path.with_suffix(".lock")
        self._available: bool | None = None
        self._last_fresh: float = 0.0

    @contextmanager
    def _acquire_lock(self) -> Generator[None, None, None]:
        """Acquire an exclusive file lock to serialize index writes."""
        with _file_lock(self._lock_path):
            yield

    @property
    def available(self) -> bool:
        """True if FTS5 is supported by the current SQLite build."""
        if self._available is None:
            self._available = self._check_fts5()
        return self._available

    def ensure_fresh(self) -> None:
        """Sync index with markdown files: add new, update modified, remove deleted.

        Skips if already synced within _FRESHNESS_TTL_SECS to avoid redundant
        stat calls when multiple index methods run in a single evaluation.
        """
        if not self.available:
            return
        now = time.monotonic()
        if self._last_fresh and (now - self._last_fresh) < self._FRESHNESS_TTL_SECS:
            return
        if not self.db_path.exists():
            self._rebuild()
        else:
            try:
                self._sync()
            except sqlite3.DatabaseError:
                self._delete_and_rebuild()
        self._last_fresh = time.monotonic()

    def invalidate(self) -> None:
        """Reset freshness TTL so the next ensure_fresh() re-syncs."""
        self._last_fresh = 0.0

    def search(self, query: str, limit: int = DEFAULT_QUERY_LIMIT) -> list[SearchResult]:
        """FTS5 MATCH search with BM25 ranking."""
        if not self.available:
            return []
        self.ensure_fresh()
        fts_query = self._sanitize_query(query)
        if not fts_query:
            return []
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    """
                    SELECT d.slug, d.title, d.date, d.tags, d.excerpt,
                           rank
                    FROM decisions_fts
                    JOIN decisions d ON d.rowid = decisions_fts.rowid
                    WHERE decisions_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
        except sqlite3.OperationalError:
            # Malformed query or corrupt db
            return []
        except sqlite3.DatabaseError:
            self._delete_and_rebuild()
            return []
        return [
            SearchResult(
                slug=r[0],
                title=r[1],
                date=r[2],
                tags=_parse_json_list(r[3]),
                excerpt=r[4] or "",
                rank=r[5],
            )
            for r in rows
        ]

    def by_tag(self, tag: str) -> list[SearchResult]:
        """Exact tag match on the decisions table."""
        if not self.available:
            return []
        self.ensure_fresh()
        try:
            with closing(self._connect()) as conn:
                # Tags stored as JSON array; use LIKE with escaped JSON string
                # Matches both `["tag"]` and `[..., "tag", ...]`
                pattern = f'%"{tag}"%'
                rows = conn.execute(
                    """
                    SELECT slug, title, date, tags, excerpt
                    FROM decisions
                    WHERE tags LIKE ?
                    ORDER BY date DESC
                    """,
                    (pattern,),
                ).fetchall()
        except sqlite3.DatabaseError:
            self._delete_and_rebuild()
            return []
        # Post-filter for exact tag match (LIKE is loose)
        results = []
        for r in rows:
            tags = _parse_json_list(r[3])
            if tag in tags:
                results.append(
                    SearchResult(
                        slug=r[0],
                        title=r[1],
                        date=r[2],
                        tags=tags,
                        excerpt=r[4] or "",
                        rank=0.0,
                    )
                )
        return results

    def decisions_with_affects(self) -> list[DecisionAffects]:
        """Return decisions with non-empty affects paths.

        Used by related-context to avoid parsing all decision files from disk.
        """
        if not self.available:
            return []
        self.ensure_fresh()
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    """
                    SELECT slug, title, date, tags, affects
                    FROM decisions
                    WHERE affects IS NOT NULL
                      AND affects != '[]'
                      AND affects != ''
                    """,
                ).fetchall()
        except sqlite3.DatabaseError:
            self._delete_and_rebuild()
            return []
        return [
            DecisionAffects(
                slug=r[0],
                title=r[1],
                date=r[2],
                tags=_parse_json_list(r[3]),
                affects=_parse_json_list(r[4]),
            )
            for r in rows
        ]

    def get_bodies(self, slugs: set[str]) -> dict[str, str]:
        """Return {slug: body} for the given slugs (single SQL query)."""
        if not slugs or not self.available:
            return {}
        self.ensure_fresh()
        try:
            placeholders = ",".join("?" for _ in slugs)
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    f"SELECT slug, body FROM decisions WHERE slug IN ({placeholders})",  # noqa: S608
                    list(slugs),
                ).fetchall()
        except sqlite3.DatabaseError:
            return {}
        return {r[0]: r[1] for r in rows if r[1]}

    def all_tags(self) -> dict[str, int]:
        """Return tag -> count for active decisions."""
        if not self.available:
            return {}
        self.ensure_fresh()
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute("SELECT tags FROM decisions").fetchall()
        except sqlite3.DatabaseError:
            self._delete_and_rebuild()
            return {}
        counts: dict[str, int] = {}
        for (tags_str,) in rows:
            if not tags_str:
                continue
            for tag in _parse_json_list(tags_str):
                if tag:
                    counts[tag] = counts.get(tag, 0) + 1
        return counts

    def list_summaries(self) -> list[DecisionSummary]:
        """Return lightweight decision summaries from the index (no file parsing).

        Progressive loading: use this for browsing, then read the full file on demand.
        """
        if not self.available:
            return []
        self.ensure_fresh()
        try:
            with closing(self._connect()) as conn:
                rows = conn.execute(
                    """
                    SELECT slug, title, date, description, tags, excerpt
                    FROM decisions
                    ORDER BY date DESC
                    """,
                ).fetchall()
        except sqlite3.DatabaseError:
            self._delete_and_rebuild()
            return []
        return [
            DecisionSummary(
                slug=r[0],
                title=r[1],
                date=r[2],
                description=r[3] or "",
                tags=_parse_json_list(r[4]),
                excerpt=r[5] or "",
            )
            for r in rows
        ]

    # ── Private ──────────────────────────────────────────────────────

    def _check_fts5(self) -> bool:
        """Test whether FTS5 is available."""
        try:
            with closing(sqlite3.connect(":memory:")) as conn:
                conn.execute("CREATE VIRTUAL TABLE _t USING fts5(x)")
                conn.execute("DROP TABLE _t")
            return True
        except sqlite3.OperationalError:
            return False

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _gather_disk_files(self) -> dict[str, tuple[Path, float]]:
        """Gather decision files from decisions directory."""
        disk_files: dict[str, tuple[Path, float]] = {}

        if self.decisions_dir.is_dir():
            for f in self.decisions_dir.glob("*.md"):
                try:
                    mtime = f.stat().st_mtime
                except FileNotFoundError:
                    continue
                slug = f.stem
                disk_files[slug] = (f, mtime)

        return disk_files

    def _sync(self) -> None:
        """Incremental sync: add new files, update modified files, remove deleted files."""
        with self._acquire_lock():
            disk_files = self._gather_disk_files()

            with closing(self._connect()) as conn:
                # Get indexed slugs and their mtimes
                indexed: dict[str, float] = {}
                for row in conn.execute("SELECT slug, mtime FROM decisions").fetchall():
                    indexed[row[0]] = row[1]

                # Delete: in index but not on disk
                deleted = set(indexed) - set(disk_files)
                for slug in deleted:
                    conn.execute("DELETE FROM decisions WHERE slug = ?", (slug,))

                # Add or update: on disk but not in index, or mtime changed
                for slug, (fpath, mtime) in disk_files.items():
                    if slug in indexed and indexed[slug] == mtime:
                        continue  # unchanged
                    self._upsert_file(conn, slug, fpath, mtime)

                conn.commit()

    def _upsert_file(self, conn: sqlite3.Connection, slug: str, fpath: Path, mtime: float) -> None:
        """Parse a decision file and insert or replace it in the index."""
        try:
            d = Decision.from_file(fpath)
        except (OSError, ValueError) as exc:
            _log(f"index: skipping {fpath.name}: {exc}")
            return
        conn.execute(
            """
            INSERT OR REPLACE INTO decisions
                (slug, title, date, description, tags, affects, body, excerpt, mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                slug,
                d.title,
                d.date,
                d.description,
                json.dumps(d.tags),
                json.dumps(d.affects),
                d.body,
                d.reasoning_excerpt,
                mtime,
            ),
        )

    def _rebuild_impl(self) -> None:
        """Core rebuild logic — assumes the caller already holds the file lock."""
        if self.db_path.exists():
            self.db_path.unlink()

        disk_files = self._gather_disk_files()

        with closing(self._connect()) as conn:
            conn.executescript(_get_schema())
            for slug, (fpath, mtime) in sorted(disk_files.items()):
                self._upsert_file(conn, slug, fpath, mtime)
            conn.commit()

    def _rebuild(self) -> None:
        """Full rebuild — used for initial creation and corruption recovery."""
        with self._acquire_lock():
            self._rebuild_impl()

    def _delete_and_rebuild(self) -> None:
        """Delete corrupt db and rebuild under file lock (safe against concurrent processes)."""
        with self._acquire_lock():
            _log("index: corrupt db, rebuilding")
            self._rebuild_impl()

    @staticmethod
    def _sanitize_query(terms: str) -> str:
        """Split into words, strip non-alnum, add * to short terms.

        Multi-token queries use AND (all tokens must match) to avoid false
        positives from a single common word.  Single-token queries stay loose.
        """
        # Cap query length to prevent excessively long FTS5 queries
        terms = terms[:1000]
        words = []
        # Split on whitespace, underscores, and hyphens to handle snake_case/kebab-case
        tokens = re.split(r"[\s_\-]+", terms)
        for word in tokens:
            clean = re.sub(r"[^a-zA-Z0-9]", "", word)
            if not clean:
                continue
            if len(clean) <= PREFIX_WILDCARD_MAX_LEN:
                clean += "*"
            words.append(clean)
        if len(words) <= 1:
            return " ".join(words)
        # AND semantics: every token must appear somewhere in the document
        return " AND ".join(words)
