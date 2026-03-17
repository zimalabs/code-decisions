#!/usr/bin/env python3
"""engram core library — called by hooks and skills.

Pure functions, no side effects at import time.
Stdlib only: sqlite3, json, re, subprocess, pathlib, os, sys.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

__all__ = ["EngramStore", "Signal", "engram_path_to_keywords"]

# Resolve schema.sql relative to this file
ENGRAM_LIB_DIR = Path(__file__).resolve().parent
ENGRAM_SCHEMA_FILE = Path(os.environ.get("ENGRAM_SCHEMA_FILE", ENGRAM_LIB_DIR / "schema.sql"))

# ── Constants ────────────────────────────────────────────────────────

# Conventional commit prefixes that represent decisions
_DECISION_PREFIXES = re.compile(r"^(feat|feat!|breaking|refactor|perf)[:(]")

# Prefixes that are never decisions
_SKIP_PREFIXES = re.compile(r"^(fix|docs|test|tests|chore|ci|style|build|typo|wip|merge)[:(]")

# Commit message patterns that indicate architectural/dependency decisions
_DECISION_PATTERNS = re.compile(
    r"(migrate|switch to|replace|drop|remove|add support|adopt|introduce|upgrade|deprecate|rewrite)",
    re.IGNORECASE,
)

# Files whose presence in a commit's diff indicates a decision
_DECISION_FILES = re.compile(
    r"(Gemfile|package\.json|Cargo\.toml|go\.mod|requirements\.txt|Pipfile|pyproject\.toml"
    r"|schema\.rb|structure\.sql|docker-compose|Dockerfile|\.github/workflows|\.circleci|Makefile)"
)

# Merge/trivial commit patterns
_SKIP_PATTERNS = re.compile(
    r"^(merge branch|merge pull|bump version|wip$|wip:|fixup!|squash!)"
)

# Noise words for path_to_keywords
_NOISE_WORDS = frozenset("src lib app index test spec the and is of to in for a an".split())

# ── Type aliases ─────────────────────────────────────────────────────

StrPath = str | Path


# ── SQLite helper ────────────────────────────────────────────────────

@contextlib.contextmanager
def _connect(db_path: StrPath):
    """Context manager for SQLite connections."""
    conn = sqlite3.connect(str(db_path))
    try:
        yield conn
    finally:
        conn.close()


# ── FTS5 check ───────────────────────────────────────────────────────

def _check_fts5() -> bool:
    """Verify SQLite FTS5 module is available."""
    try:
        with _connect(":memory:") as conn:
            conn.execute("CREATE VIRTUAL TABLE _fts5_test USING fts5(x);")
    except sqlite3.OperationalError:
        print("engram: SQLite FTS5 module not available.", file=sys.stderr)
        print("engram: Install SQLite with FTS5 support:", file=sys.stderr)
        print('engram:   macOS:  brew install sqlite && export PATH="$(brew --prefix sqlite)/bin:$PATH"', file=sys.stderr)
        print("engram:   Ubuntu: sudo apt-get install -y libsqlite3-0", file=sys.stderr)
        print("engram:   Alpine: apk add sqlite", file=sys.stderr)
        return False
    return True


# ── Slug helpers ─────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Lowercase, replace non-alphanum with hyphens, collapse, trim, truncate to 50."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s[:50]


def _slug(filepath: StrPath) -> str:
    """Extract slug from filepath (basename without .md)."""
    return Path(filepath).stem


def _normalize_tags(raw: str) -> str:
    """Convert YAML-style [a, b, c] to valid JSON ["a","b","c"]."""
    raw = raw.strip()
    if not raw or raw == "[]":
        return "[]"
    if '"' in raw:
        return raw
    inner = raw.lstrip("[").rstrip("]")
    tags = [t.strip() for t in inner.split(",") if t.strip()]
    return json.dumps(tags)


def _parse_links(s: str) -> list[tuple[str, str]]:
    """Parse links: [related:foo, supersedes:bar] → list of (rel, target)."""
    s = s.strip().lstrip("[").rstrip("]")
    result = []
    for part in s.split(","):
        part = part.strip()
        if ":" in part:
            rel, target = part.split(":", 1)
            rel, target = rel.strip(), target.strip()
            if rel and target:
                result.append((rel, target))
    return result


# ── Frontmatter parser (shared) ─────────────────────────────────────

# Field name → transform function for frontmatter parsing
_FM_FIELDS: dict[str, callable] = {
    "type": str.strip,
    "date": str.strip,
    "tags": _normalize_tags,
    "source": str.strip,
    "supersedes": str.strip,
    "links": str.strip,
    "status": str.strip,
}


def _split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    """Split markdown into (frontmatter_lines, content_lines).

    Returns raw line lists — frontmatter lines exclude the --- delimiters.
    If no valid frontmatter, returns ([], all_lines).
    """
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return [], lines

    for i, line in enumerate(lines[1:], 1):
        if line == "---":
            return lines[1:i], lines[i + 1:]

    return [], lines


# ── Signal dataclass ─────────────────────────────────────────────────

@dataclasses.dataclass
class Signal:
    """Parsed representation of a signal markdown file."""
    title: str = ""
    body: str = ""
    sig_type: str = "decision"
    date: str = ""
    tags: str = "[]"
    source: str = ""
    supersedes: str = ""
    links: str = ""
    status: str = "active"
    _has_frontmatter: bool = dataclasses.field(default=True, repr=False)

    @classmethod
    def from_text(cls, text: str) -> Signal:
        """Parse markdown with YAML frontmatter into a Signal."""
        meta: dict[str, str] = {
            "type": "",
            "date": "",
            "tags": "[]",
            "source": "",
            "supersedes": "",
            "links": "",
            "status": "active",
        }

        fm_lines, content_lines = _split_frontmatter(text)
        has_fm = bool(fm_lines) or text.splitlines()[:1] == ["---"]

        for line in fm_lines:
            key, _, val = line.partition(":")
            if key in _FM_FIELDS:
                meta[key] = _FM_FIELDS[key](val)

        title = ""
        body_lines = []
        found_title = False
        for line in content_lines:
            if not found_title and line.startswith("# "):
                title = line[2:]
                found_title = True
                continue
            body_lines.append(line)

        body = "\n".join(body_lines) + "\n" if body_lines else ""

        return cls(
            title=title,
            body=body,
            sig_type=meta["type"] or "decision",
            date=meta["date"],
            tags=meta["tags"],
            source=meta["source"],
            supersedes=meta["supersedes"],
            links=meta["links"],
            status=meta["status"],
            _has_frontmatter=has_fm,
        )

    @classmethod
    def from_file(cls, filepath: StrPath) -> Signal:
        """Read and parse a signal file."""
        text = Path(filepath).read_text(errors="replace")
        return cls.from_text(text)

    @property
    def excerpt(self) -> str:
        """First non-empty, non-heading line of body, truncated to 120 chars."""
        for line in self.body.splitlines():
            if line and not line.startswith("#"):
                return line[:120]
        return ""

    @property
    def content(self) -> str:
        """Title + newline + body."""
        return self.title + "\n" + self.body

    def validate(self) -> tuple[bool, str]:
        """Validate signal fields. Returns (ok, errors_string)."""
        errors = []

        if not self._has_frontmatter:
            errors.append("missing frontmatter delimiters (---)")
        else:
            # Check date
            if not self.date or not re.match(r"^\d{4}-\d{2}-\d{2}$", self.date):
                errors.append("missing or invalid date: field (need YYYY-MM-DD)")

            # Check tags
            if not self.tags or self.tags == "[]":
                errors.append("tags: must have at least one tag (not empty [])")

        # Check title and lead paragraph
        if not self.title:
            errors.append("missing H1 title (# ...)")

        lead_paragraph = ""
        for line in self.body.splitlines():
            if not lead_paragraph:
                if not line or line.startswith("#"):
                    continue
                lead_paragraph = line

        if not lead_paragraph or len(lead_paragraph) < 20:
            errors.append("lead paragraph after title must exist and be >= 20 chars (explains why)")

        return (len(errors) == 0, "; ".join(errors) + "; " if errors else "")

    def parsed_links(self) -> list[tuple[str, str]]:
        """Parse links field into list of (rel, target)."""
        return _parse_links(self.links)


# ── Commit classification ────────────────────────────────────────────

def _is_decision_commit(subject: str, commit_hash: str) -> bool:
    """Check if a commit represents a decision worth capturing."""
    lower = subject.lower()

    # Skip: conventional commit prefixes that aren't decisions
    if _SKIP_PREFIXES.match(lower):
        return False

    # Skip: merge commits, version bumps, trivial messages
    if _SKIP_PATTERNS.match(lower):
        return False

    # Match: conventional commit prefixes that are decisions
    if _DECISION_PREFIXES.match(lower):
        return True

    # Match: keyword patterns in the message
    if _DECISION_PATTERNS.search(lower):
        return True

    # Match: significant file changes (schema, deps, CI, infra)
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            capture_output=True, text=True, errors="replace",
        )
        if _DECISION_FILES.search(result.stdout):
            return True
    except (OSError, subprocess.SubprocessError):
        pass

    return False


# ── Path to keywords ────────────────────────────────────────────────

def engram_path_to_keywords(filepath: str) -> str:
    """Extract search keywords from a file path."""
    if not filepath:
        return ""
    # Strip extension
    base = Path(filepath).with_suffix("").as_posix()
    # Split on / - _ .
    words = re.split(r"[/\-_.]", base)
    words = [w.lower() for w in words if w]

    seen = set()
    result = []
    for word in words:
        if word in _NOISE_WORDS:
            continue
        if word in seen:
            continue
        seen.add(word)
        result.append(word)

    return " ".join(result)


# ── EngramStore ──────────────────────────────────────────────────────

class EngramStore:
    """Manages an .engram directory — init, reindex, query, brief."""

    def __init__(self, dir_path: StrPath):
        self.root = Path(dir_path)
        self.db_path = self.root / "index.db"
        self.decisions_dir = self.root / "decisions"
        self.private_dir = self.root / "_private" / "decisions"

    @property
    def git_tracking(self) -> bool:
        """Check if git tracking is explicitly enabled via config."""
        config = self.root / "config"
        if not config.is_file():
            return False
        try:
            return "git_tracking=true" in config.read_text().splitlines()
        except OSError:
            return False

    @contextlib.contextmanager
    def connect(self):
        """Context manager for SQLite connections to index.db."""
        with _connect(self.db_path) as conn:
            yield conn

    def meta_get(self, key: str) -> str | None:
        """Read a value from the meta table."""
        if not self.db_path.is_file():
            return None
        try:
            with self.connect() as conn:
                row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
                return row[0] if row else None
        except sqlite3.Error:
            return None

    def meta_set(self, key: str, value: str) -> None:
        """Write a value to the meta table."""
        try:
            with self.connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    (key, value),
                )
                conn.commit()
        except sqlite3.Error:
            pass

    def init(self) -> bool:
        """Initialize .engram directory structure and index.db."""
        if not _check_fts5():
            return False
        self.decisions_dir.mkdir(parents=True, exist_ok=True)
        self.private_dir.mkdir(parents=True, exist_ok=True)

        # Only manage .gitignore when git tracking is enabled
        if self.git_tracking:
            gi = self.root / ".gitignore"
            if not gi.is_file():
                gi.write_text("index.db\nbrief.md\n_private/\nconfig\n")
            else:
                existing = gi.read_text()
                lines = existing.splitlines()
                for entry in ("_private/", "brief.md", "config"):
                    if entry not in lines:
                        existing += entry + "\n"
                gi.write_text(existing)

        if not self.db_path.is_file():
            with self.connect() as conn:
                conn.executescript(ENGRAM_SCHEMA_FILE.read_text())
        return True

    def _index_file(self, filepath: StrPath, private: int = 0) -> None:
        """Parse a signal markdown file and insert into index.db."""
        sig = Signal.from_file(filepath)

        if not sig.date:
            sig.date = date.today().isoformat()
        if not sig.title:
            sig.title = Path(filepath).stem

        slug = _slug(filepath)

        # Normalize status
        if sig.status not in ("active", "withdrawn"):
            sig.status = "active"

        # Validate — invalid overrides frontmatter status
        ok, _ = sig.validate()
        if not ok:
            sig.status = "invalid"
            print(f"engram: warning: {Path(filepath).name} is incomplete (missing rationale)", file=sys.stderr)

        with self.connect() as conn:
            conn.execute(
                "INSERT INTO signals (type, title, content, tags, source, date, file, private, excerpt, slug, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sig.sig_type, sig.title, sig.content, sig.tags, sig.source, sig.date,
                 str(filepath), private, sig.excerpt, slug, sig.status),
            )

            # Insert supersedes link
            if sig.supersedes:
                conn.execute(
                    "INSERT OR IGNORE INTO links (source_file, target_file, rel_type) VALUES (?, ?, 'supersedes')",
                    (slug, sig.supersedes),
                )

            # Insert other links
            if sig.links:
                for rel, target in sig.parsed_links():
                    conn.execute(
                        "INSERT OR IGNORE INTO links (source_file, target_file, rel_type) VALUES (?, ?, ?)",
                        (slug, target, rel),
                    )

            conn.commit()

    def reindex(self) -> None:
        """Destructive rebuild of index.db from signal files. Preserves meta table."""
        # Preserve meta table data
        meta_backup: list[tuple[str, str]] = []
        if self.db_path.is_file():
            try:
                with self.connect() as conn:
                    meta_backup = conn.execute("SELECT key, value FROM meta").fetchall()
            except sqlite3.Error:
                pass

        # Recreate index from scratch
        if self.db_path.is_file():
            self.db_path.unlink()
        with self.connect() as conn:
            conn.executescript(ENGRAM_SCHEMA_FILE.read_text())

            # Restore meta data
            for key, value in meta_backup:
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
            conn.commit()

        # Index public signals
        if self.decisions_dir.is_dir():
            for f in sorted(self.decisions_dir.glob("*.md")):
                self._index_file(str(f), private=0)

        # Index private signals
        if self.private_dir.is_dir():
            for f in sorted(self.private_dir.glob("*.md")):
                self._index_file(str(f), private=1)

    def ingest_commits(self) -> None:
        """Ingest decision-worthy commits as signal files."""
        if not self.git_tracking:
            return

        # Must be in a git repo
        try:
            subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return

        last_commit = self.meta_get("last_commit") or ""

        # Get log output
        if not last_commit:
            cmd = ["git", "log", "-50", "--format=%H|%s|%ai"]
        else:
            cmd = ["git", "log", f"{last_commit}..HEAD", "--format=%H|%s|%ai"]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
            log_output = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return

        if not log_output:
            return

        new_head = ""

        # Pre-build set of existing source tags for O(1) dedup lookups
        existing_sources: set[str] = set()
        for search_dir in (self.decisions_dir, self.private_dir):
            if search_dir.is_dir():
                for f in search_dir.glob("*.md"):
                    content = f.read_text(errors="replace")
                    for cl in content.splitlines():
                        if cl.startswith("source:"):
                            existing_sources.add(cl.strip())
                            break

        for line in log_output.splitlines():
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            commit_hash, subject, date_str = parts

            if not new_head:
                new_head = commit_hash

            if not _is_decision_commit(subject, commit_hash):
                continue

            # Dedup: skip if file with this source already exists
            if f"source: git:{commit_hash}" in existing_sources:
                continue

            commit_date = date_str.split()[0] if date_str else date.today().isoformat()
            slug = _slugify(subject)
            if not slug:
                slug = f"commit-{commit_hash[:7]}"

            filepath = self.decisions_dir / f"{slug}.md"

            # Manual signal with same slug already exists — defer to it
            if filepath.is_file():
                continue
            if (self.private_dir / f"{slug}.md").is_file():
                continue

            # Get diff stat
            try:
                stat_result = subprocess.run(
                    ["git", "show", "--stat", "--format=", commit_hash],
                    capture_output=True, text=True, errors="replace",
                )
                stat = stat_result.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                stat = ""

            # Extract commit body, strip Co-Authored-By trailers
            try:
                body_result = subprocess.run(
                    ["git", "log", "-1", "--format=%b", commit_hash],
                    capture_output=True, text=True, errors="replace",
                )
                body = body_result.stdout
                # Strip Co-Authored-By lines
                body = "\n".join(
                    line for line in body.splitlines()
                    if not line.lower().startswith("co-authored-by:")
                ).strip()
            except (OSError, subprocess.SubprocessError):
                body = ""

            # Build signal content
            signal = f"---\ntype: decision\ndate: {commit_date}\nsource: git:{commit_hash}\n---\n\n# {subject}\n\n"
            if body:
                signal += f"{body}\n\n{stat}\n"
            else:
                signal += f"{stat}\n"

            filepath.write_text(signal)

        # Update last_commit pointer
        if new_head:
            self.meta_set("last_commit", new_head)

    def ingest_plans(self) -> None:
        """Ingest Claude Code plan files as decision signals."""
        # Resolve project-scoped plans directory
        plans_dir = os.environ.get("ENGRAM_PLANS_DIR", "")
        if not plans_dir:
            project_key = os.getcwd().replace("/", "-")
            plans_dir = os.path.expanduser(f"~/.claude/projects/{project_key}/plans")

        plans_path = Path(plans_dir)

        # Safety: never ingest from the global plans directory
        global_plans = Path.home() / ".claude" / "plans"
        try:
            if global_plans.exists() and plans_path.exists():
                if plans_path.resolve() == global_plans.resolve():
                    return
        except OSError:
            pass

        if not plans_path.is_dir():
            return

        # Check last ingest timestamp
        last_ingest = self.meta_get("last_plan_ingest") or ""

        # Find plan files
        plan_files = list(plans_path.glob("*.md"))
        if last_ingest and self.db_path.is_file():
            db_mtime = self.db_path.stat().st_mtime
            plan_files = [f for f in plan_files if f.stat().st_mtime > db_mtime]

        if not plan_files:
            return

        today = date.today().isoformat()

        for plan_file in plan_files:
            basename = plan_file.stem

            # Dedup: skip if file with this source already exists
            source_tag = f"source: plan:{basename}"
            found = False
            if self.decisions_dir.is_dir():
                for f in self.decisions_dir.glob("*.md"):
                    if source_tag in f.read_text(errors="replace"):
                        found = True
                        break
            if found:
                continue

            # Extract title and context
            text = plan_file.read_text(errors="replace")
            title = ""
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:]
                    break
            if not title:
                title = basename

            # Extract context section
            context_lines = []
            in_context = False
            for line in text.splitlines():
                if line.startswith("## Context"):
                    in_context = True
                    continue
                if in_context and line.startswith("## "):
                    break
                if in_context:
                    context_lines.append(line)
            context = "\n".join(context_lines).strip()

            if not context:
                continue

            slug = _slugify(title)
            if not slug:
                slug = f"plan-{basename}"

            filepath = self.decisions_dir / f"plan-{slug}.md"
            signal = f"---\ntype: decision\ndate: {today}\nsource: plan:{basename}\n---\n\n# {title}\n\n{context}\n"
            filepath.write_text(signal)

        # Update last_plan_ingest timestamp
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.meta_set("last_plan_ingest", now)

    def brief(self) -> None:
        """Generate brief.md summary of decisions."""
        if not self.db_path.is_file():
            return

        with self.connect() as conn:
            # Build superseded set
            superseded_slugs = [
                row[0] for row in
                conn.execute("SELECT target_file FROM links WHERE rel_type='supersedes'").fetchall()
            ]

            superseded_count = len(superseded_slugs)

            # Build SQL exclusion for superseded slugs
            superseded_clause = ""
            superseded_params: list[str] = []
            if superseded_slugs:
                placeholders = ",".join("?" * len(superseded_slugs))
                superseded_clause = f"AND slug NOT IN ({placeholders})"
                superseded_params = superseded_slugs

            # Counts
            decision_count = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE type='decision' AND private=0 AND status='active'"
            ).fetchone()[0]

            invalid_count = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE type='decision' AND private=0 AND status='invalid'"
            ).fetchone()[0]

            withdrawn_count = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE type='decision' AND private=0 AND status='withdrawn'"
            ).fetchone()[0]

            brief = f"# Decision Context ({decision_count} decisions)"

            # Check distinct tag count
            distinct_tags = conn.execute(
                f"SELECT COUNT(DISTINCT j.value) FROM signals, json_each(signals.tags) j "
                f"WHERE signals.type='decision' AND signals.private=0 AND signals.status='active' "
                f"AND signals.tags != '[]' {superseded_clause}",
                superseded_params,
            ).fetchone()[0]

            if distinct_tags >= 3:
                # Tag-grouped decisions
                rows = conn.execute(
                    f"SELECT COALESCE(json_extract(s.tags, '$[0]'), '') as primary_tag, "
                    f"GROUP_CONCAT('- [' || s.date || '] ' || s.title || "
                    f"CASE WHEN s.excerpt != '' THEN ' — ' || s.excerpt ELSE '' END || "
                    f"CASE WHEN l.target_file IS NOT NULL THEN ' (supersedes: ' || l.target_file || ')' ELSE '' END"
                    f", CHAR(10)) "
                    f"FROM signals s LEFT JOIN links l ON l.source_file = s.slug AND l.rel_type = 'supersedes' "
                    f"WHERE s.type='decision' AND s.private=0 AND s.status='active' {superseded_clause} "
                    f"GROUP BY primary_tag ORDER BY MAX(s.date) DESC LIMIT 15",
                    superseded_params,
                ).fetchall()

                if rows:
                    brief += "\n\n## Recent Decisions"
                    for tag, entries in rows:
                        if not entries:
                            continue
                        if tag and tag != "[]":
                            brief += f"\n### {tag}\n{entries}"
                        else:
                            brief += f"\n{entries}"
            else:
                # Chronological decisions
                rows = conn.execute(
                    f"SELECT '- [' || s.date || '] ' || s.title || "
                    f"CASE WHEN s.excerpt != '' THEN ' — ' || s.excerpt ELSE '' END || "
                    f"CASE WHEN l.target_file IS NOT NULL THEN ' (supersedes: ' || l.target_file || ')' ELSE '' END "
                    f"FROM signals s LEFT JOIN links l ON l.source_file = s.slug AND l.rel_type = 'supersedes' "
                    f"WHERE s.type='decision' AND s.private=0 AND s.status='active' {superseded_clause} "
                    f"ORDER BY s.date DESC LIMIT 15",
                    superseded_params,
                ).fetchall()

                if rows:
                    decisions_text = "\n".join(row[0] for row in rows)
                    brief += f"\n\n## Recent Decisions\n{decisions_text}"

            # Footer
            private_count = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE private=1"
            ).fetchone()[0]

            footer_parts: list[str] = []
            if private_count > 0:
                footer_parts.append(f"{private_count} private signal(s)")
            if superseded_count > 0:
                footer_parts.append(f"{superseded_count} superseded signal(s)")
            if withdrawn_count > 0:
                footer_parts.append(f"{withdrawn_count} withdrawn signal(s)")
            if invalid_count > 0:
                footer_parts.append(f"{invalid_count} signal(s) incomplete (missing rationale)")

            if footer_parts:
                brief += f"\n\n*+ {', '.join(footer_parts)} not shown*"

        # Cap brief size
        max_lines = int(os.environ.get("ENGRAM_BRIEF_MAX_LINES", "50"))
        lines = brief.split("\n")
        if len(lines) > max_lines:
            brief = "\n".join(lines[:max_lines])
            brief += f"\n\n*... truncated to {max_lines} lines. Use @engram:query for full details.*"

        (self.root / "brief.md").write_text(brief + "\n")

    def resync(self) -> None:
        """Full sync: ingest commits, ingest plans, reindex, generate brief."""
        self.ingest_commits()
        self.ingest_plans()
        self.reindex()
        self.brief()

    def query_relevant(self, search_terms: str, limit: int = 3) -> str:
        """Search for signals matching keywords. Returns formatted string."""
        if not search_terms:
            return ""

        if not self.db_path.is_file():
            return ""

        # Build OR-joined FTS5 query
        terms = search_terms.split()
        if not terms:
            return ""
        fts_query = " OR ".join(terms)

        with self.connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT s.date, s.title, s.excerpt "
                    "FROM signals_fts fts JOIN signals s ON s.id = fts.rowid "
                    "WHERE signals_fts MATCH ? AND s.private = 0 AND s.status = 'active' "
                    "AND s.slug NOT IN (SELECT target_file FROM links WHERE rel_type = 'supersedes') "
                    "ORDER BY rank LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
            except sqlite3.Error:
                rows = []

        if not rows:
            return ""

        lines = []
        for row_date, title, excerpt in rows:
            if not title:
                continue
            if excerpt:
                lines.append(f"- [{row_date}] {title} — {excerpt}")
            else:
                lines.append(f"- [{row_date}] {title}")

        return "\n".join(lines)

    def tag_summary(self) -> str:
        """Return top topics summary string."""
        if not self.db_path.is_file():
            return ""

        with self.connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM signals WHERE private=0"
            ).fetchone()[0]
            if total < 5:
                return ""

            rows = conn.execute(
                "SELECT j.value AS tag, COUNT(*) AS cnt "
                "FROM signals, json_each(signals.tags) j "
                "WHERE signals.private = 0 AND signals.tags != '[]' "
                "GROUP BY j.value ORDER BY cnt DESC LIMIT 8"
            ).fetchall()

        if not rows:
            return ""

        parts = [f"{tag} ({cnt})" for tag, cnt in rows if tag]
        if not parts:
            return ""

        return "Top topics: " + ", ".join(parts)

    def find_incomplete(self, limit: int = 5) -> str:
        """Find signals with gaps. Returns pipe-delimited lines."""
        if not self.db_path.is_file():
            return ""

        with self.connect() as conn:
            rows = conn.execute(
                "SELECT s.slug, s.title, "
                "CASE WHEN s.tags = '[]' OR s.tags = '' THEN 'tags,' ELSE '' END "
                "|| CASE WHEN s.content NOT LIKE '%## Rationale%' AND s.content NOT LIKE '%## Alternatives%' THEN 'sections,' ELSE '' END "
                "|| CASE WHEN l.source_file IS NULL AND l2.target_file IS NULL THEN 'links,' ELSE '' END "
                "AS gap_types "
                "FROM signals s "
                "LEFT JOIN links l ON l.source_file = s.slug "
                "LEFT JOIN links l2 ON l2.target_file = s.slug "
                "WHERE (s.tags = '[]' OR s.tags = '' "
                "OR (s.content NOT LIKE '%## Rationale%' AND s.content NOT LIKE '%## Alternatives%') "
                "OR (l.source_file IS NULL AND l2.target_file IS NULL)) "
                "GROUP BY s.slug "
                "ORDER BY s.date DESC LIMIT ?",
                (limit,),
            ).fetchall()

        if not rows:
            return ""

        lines = []
        for slug, title, gaps in rows:
            gaps = gaps.rstrip(",")
            lines.append(f"{slug}|{title}|{gaps}")

        return "\n".join(lines)

    def uncommitted_summary(self) -> str:
        """Report uncommitted signals if git tracking is enabled."""
        if not self.git_tracking:
            return ""

        try:
            subprocess.run(["git", "rev-parse", "--show-toplevel"],
                           capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            return ""

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", str(self.decisions_dir), str(self.private_dir)],
                capture_output=True, text=True, errors="replace",
            )
            lines = [l for l in result.stdout.splitlines() if l.strip()]
        except (OSError, subprocess.SubprocessError):
            return ""

        if not lines:
            return ""

        return f"{len(lines)} uncommitted signal(s) in .engram/"


# ── Validate content from stdin ──────────────────────────────────────

def _validate_content_stdin() -> str:
    """Validate signal content read from stdin. For pre-tool-use hook."""
    text = sys.stdin.read()
    errors = []

    fm_lines, content_lines = _split_frontmatter(text)

    if not fm_lines and text.splitlines()[:1] != ["---"]:
        errors.append("missing opening --- frontmatter delimiter")
        errors.append("missing closing --- frontmatter delimiter")
    elif not fm_lines:
        errors.append("missing closing --- frontmatter delimiter")

    # Check date field
    has_date = any(
        re.match(r"^ *\d{4}-\d{2}-\d{2}", line.partition(":")[2])
        for line in fm_lines if line.startswith("date:")
    )
    if not has_date:
        errors.append("missing or invalid date: field (need YYYY-MM-DD)")

    # Check tags field
    tags_line = next((l for l in fm_lines if l.startswith("tags:")), None)
    if not tags_line:
        errors.append("missing tags: field")
    elif "[]" in tags_line:
        errors.append("tags: is empty, add at least one tag")

    # Check H1 title and lead paragraph
    has_title = False
    lead = ""
    for line in content_lines:
        if not has_title and line.startswith("# "):
            has_title = True
            continue
        if has_title:
            if not line or line.startswith("#"):
                continue
            lead = line
            break

    if not has_title:
        errors.append("missing H1 title (# ...)")
    if not lead or len(lead) < 20:
        errors.append("lead paragraph after title must exist and be >= 20 chars (explains why)")

    if errors:
        return "; ".join(errors) + "; "
    return ""


# ── CLI dispatch ────────────────────────────────────────────────────

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
}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 engram.py <command> [args...]", file=sys.stderr)
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
