"""EngramStore — manages an .engram directory."""
from __future__ import annotations

import contextlib
import os
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from ._constants import StrPath
from ._commits import _is_decision_commit
from ._frontmatter import _format_toml_frontmatter
from ._helpers import _check_fts5, _connect, _parse_links, _slug, _slugify
from .signal import Signal


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
        import engram
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
                conn.executescript(engram.ENGRAM_SCHEMA_FILE.read_text())
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
        import engram

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
            conn.executescript(engram.ENGRAM_SCHEMA_FILE.read_text())

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

        # Pre-build set of existing source values for O(1) dedup lookups
        existing_sources: set[str] = set()
        for search_dir in (self.decisions_dir, self.private_dir):
            if search_dir.is_dir():
                for f in search_dir.glob("*.md"):
                    content = f.read_text(errors="replace")
                    for cl in content.splitlines():
                        cl_stripped = cl.strip()
                        if cl_stripped.startswith("source"):
                            _, _, val = cl_stripped.partition("=")
                            val = val.strip().strip('"')
                            if val:
                                existing_sources.add(val)
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
            if f"git:{commit_hash}" in existing_sources:
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
            fm = _format_toml_frontmatter({"date": commit_date, "source": f"git:{commit_hash}"})
            signal = f"{fm}\n\n# {subject}\n\n"
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
            source_val = f"plan:{basename}"
            found = False
            if self.decisions_dir.is_dir():
                for f in self.decisions_dir.glob("*.md"):
                    if source_val in f.read_text(errors="replace"):
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
            fm = _format_toml_frontmatter({"date": today, "source": f"plan:{basename}"})
            signal = f"{fm}\n\n# {title}\n\n{context}\n"
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
