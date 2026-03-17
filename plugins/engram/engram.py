#!/usr/bin/env python3
"""engram core library — called by hooks and skills.

Pure functions, no side effects at import time.
Stdlib only: sqlite3, json, re, subprocess, pathlib, os, sys.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path

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


# ── FTS5 check ───────────────────────────────────────────────────────

def _check_fts5():
    """Verify SQLite FTS5 module is available."""
    try:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE VIRTUAL TABLE _fts5_test USING fts5(x);")
        conn.close()
    except sqlite3.OperationalError:
        print("engram: SQLite FTS5 module not available.", file=sys.stderr)
        print("engram: Install SQLite with FTS5 support:", file=sys.stderr)
        print('engram:   macOS:  brew install sqlite && export PATH="$(brew --prefix sqlite)/bin:$PATH"', file=sys.stderr)
        print("engram:   Ubuntu: sudo apt-get install -y libsqlite3-0", file=sys.stderr)
        print("engram:   Alpine: apk add sqlite", file=sys.stderr)
        return False
    return True


# ── Config ───────────────────────────────────────────────────────────

def _git_tracking_enabled(dir_path):
    """Check if git tracking is explicitly enabled via config."""
    config = Path(dir_path) / "config"
    if not config.is_file():
        return False
    try:
        return "git_tracking=true" in config.read_text().splitlines()
    except OSError:
        return False


# ── Slug helpers ─────────────────────────────────────────────────────

def _slugify(text):
    """Lowercase, replace non-alphanum with hyphens, collapse, trim, truncate to 50."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]", "-", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s[:50]


def _slug(filepath):
    """Extract slug from filepath (basename without .md)."""
    return Path(filepath).stem


def _extract_excerpt(body):
    """First non-empty, non-heading line of body, truncated to 120 chars."""
    for line in body.splitlines():
        if line and not line.startswith("#"):
            return line[:120]
    return ""


def _normalize_tags(raw):
    """Convert YAML-style [a, b, c] to valid JSON ["a","b","c"]."""
    raw = raw.strip()
    if not raw or raw == "[]":
        return "[]"
    if '"' in raw:
        return raw
    inner = raw.lstrip("[").rstrip("]")
    tags = [t.strip() for t in inner.split(",") if t.strip()]
    return json.dumps(tags)


def _parse_links(s):
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

def _parse_frontmatter(text):
    """Parse markdown with YAML frontmatter.

    Returns (metadata_dict, title, body) where:
    - metadata_dict has keys: type, date, tags, source, supersedes, links, status
    - title is the first H1 heading (without '# ')
    - body is everything after the title
    """
    lines = text.splitlines()
    meta = {
        "type": "",
        "date": "",
        "tags": "[]",
        "source": "",
        "supersedes": "",
        "links": "",
        "status": "active",
    }
    title = ""
    body_lines = []

    in_frontmatter = False
    has_open = False
    past_frontmatter = False
    found_title = False

    for line in lines:
        if not past_frontmatter:
            if line == "---":
                if not has_open:
                    has_open = True
                    in_frontmatter = True
                    continue
                else:
                    past_frontmatter = True
                    continue
            if in_frontmatter:
                if line.startswith("type:"):
                    meta["type"] = line[len("type:"):].strip()
                elif line.startswith("date:"):
                    meta["date"] = line[len("date:"):].strip()
                elif line.startswith("tags:"):
                    meta["tags"] = _normalize_tags(line[len("tags:"):].strip())
                elif line.startswith("source:"):
                    meta["source"] = line[len("source:"):].strip()
                elif line.startswith("supersedes:"):
                    meta["supersedes"] = line[len("supersedes:"):].strip()
                elif line.startswith("links:"):
                    meta["links"] = line[len("links:"):].strip()
                elif line.startswith("status:"):
                    meta["status"] = line[len("status:"):].strip()
                continue
            # No frontmatter opened yet, treat as body
            continue

        # Past frontmatter
        if not found_title and line.startswith("# "):
            title = line[2:]
            found_title = True
            continue
        body_lines.append(line)

    body = "\n".join(body_lines) + "\n" if body_lines else ""
    return meta, title, body


# ── Signal validation ────────────────────────────────────────────────

def _validate_signal(filepath):
    """Validate a signal file. Returns (ok, errors_string)."""
    text = Path(filepath).read_text(errors="replace")
    errors = []

    lines = text.splitlines()
    has_open = False
    has_close = False
    in_frontmatter = False
    has_date = False
    has_tags = False
    tags_empty = True
    has_title = False
    past_frontmatter = False
    past_title = False
    lead_paragraph = ""

    for line in lines:
        if not past_frontmatter:
            if line == "---":
                if not has_open:
                    has_open = True
                    in_frontmatter = True
                    continue
                else:
                    has_close = True
                    past_frontmatter = True
                    continue
            if in_frontmatter:
                if line.startswith("date:"):
                    val = line[len("date:"):].strip()
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                        has_date = True
                elif line.startswith("tags:"):
                    val = line[len("tags:"):].strip()
                    has_tags = True
                    if val and val != "[]":
                        tags_empty = False
                continue

        # Past frontmatter
        if not has_title and line.startswith("# "):
            has_title = True
            past_title = True
            continue

        if past_title and not lead_paragraph:
            if not line or line.startswith("#"):
                continue
            lead_paragraph = line

    if not has_open or not has_close:
        errors.append("missing frontmatter delimiters (---)")
    if not has_date:
        errors.append("missing or invalid date: field (need YYYY-MM-DD)")
    if not has_tags or tags_empty:
        errors.append("tags: must have at least one tag (not empty [])")
    if not has_title:
        errors.append("missing H1 title (# ...)")
    if not lead_paragraph or len(lead_paragraph) < 20:
        errors.append("lead paragraph after title must exist and be >= 20 chars (explains why)")

    return (len(errors) == 0, "; ".join(errors) + "; " if errors else "")


# ── Commit classification ────────────────────────────────────────────

def _is_decision_commit(subject, commit_hash):
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


# ── Init ─────────────────────────────────────────────────────────────

def engram_init(dir_path):
    """Initialize .engram directory structure and index.db."""
    if not _check_fts5():
        return False
    d = Path(dir_path)
    (d / "decisions").mkdir(parents=True, exist_ok=True)
    (d / "_private" / "decisions").mkdir(parents=True, exist_ok=True)

    # Only manage .gitignore when git tracking is enabled
    if _git_tracking_enabled(dir_path):
        gi = d / ".gitignore"
        if not gi.is_file():
            gi.write_text("index.db\nbrief.md\n_private/\nconfig\n")
        else:
            existing = gi.read_text()
            lines = existing.splitlines()
            for entry in ("_private/", "brief.md", "config"):
                if entry not in lines:
                    existing += entry + "\n"
            gi.write_text(existing)

    db_path = d / "index.db"
    if not db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        conn.executescript(ENGRAM_SCHEMA_FILE.read_text())
        conn.close()
    return True


# ── Index file ───────────────────────────────────────────────────────

def _index_file(dir_path, filepath, private=0):
    """Parse a signal markdown file and insert into index.db."""
    text = Path(filepath).read_text(errors="replace")
    meta, title, body = _parse_frontmatter(text)

    if not meta["date"]:
        meta["date"] = date.today().isoformat()
    if not title:
        title = Path(filepath).stem

    sig_type = meta["type"] or "decision"
    slug = _slug(filepath)
    excerpt = _extract_excerpt(body)

    # Normalize status
    if meta["status"] not in ("active", "withdrawn"):
        meta["status"] = "active"

    # Validate — invalid overrides frontmatter status
    ok, _ = _validate_signal(filepath)
    if not ok:
        meta["status"] = "invalid"
        print(f"engram: warning: {Path(filepath).name} is incomplete (missing rationale)", file=sys.stderr)

    content = title + "\n" + body

    db_path = Path(dir_path) / "index.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO signals (type, title, content, tags, source, date, file, private, excerpt, slug, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (sig_type, title, content, meta["tags"], meta["source"], meta["date"],
         str(filepath), private, excerpt, slug, meta["status"]),
    )

    # Insert supersedes link
    if meta["supersedes"]:
        conn.execute(
            "INSERT OR IGNORE INTO links (source_file, target_file, rel_type) VALUES (?, ?, 'supersedes')",
            (slug, meta["supersedes"]),
        )

    # Insert other links
    if meta["links"]:
        for rel, target in _parse_links(meta["links"]):
            conn.execute(
                "INSERT OR IGNORE INTO links (source_file, target_file, rel_type) VALUES (?, ?, ?)",
                (slug, target, rel),
            )

    conn.commit()
    conn.close()


# ── Reindex ──────────────────────────────────────────────────────────

def engram_reindex(dir_path):
    """Destructive rebuild of index.db from signal files. Preserves meta table."""
    d = Path(dir_path)
    db_path = d / "index.db"

    # Preserve meta table data
    meta_backup = []
    if db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path))
            meta_backup = conn.execute("SELECT key, value FROM meta").fetchall()
            conn.close()
        except sqlite3.Error:
            pass

    # Recreate index from scratch
    if db_path.is_file():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(ENGRAM_SCHEMA_FILE.read_text())

    # Restore meta data
    for key, value in meta_backup:
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

    # Index public signals
    decisions_dir = d / "decisions"
    if decisions_dir.is_dir():
        for f in sorted(decisions_dir.glob("*.md")):
            _index_file(dir_path, str(f), private=0)

    # Index private signals
    private_dir = d / "_private" / "decisions"
    if private_dir.is_dir():
        for f in sorted(private_dir.glob("*.md")):
            _index_file(dir_path, str(f), private=1)


# ── Commit ingestion ─────────────────────────────────────────────────

def engram_ingest_commits(dir_path):
    """Ingest decision-worthy commits as signal files."""
    if not _git_tracking_enabled(dir_path):
        return

    # Must be in a git repo
    try:
        subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return

    d = Path(dir_path)
    db_path = d / "index.db"

    last_commit = ""
    if db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute("SELECT value FROM meta WHERE key = 'last_commit'").fetchone()
            if row:
                last_commit = row[0]
            conn.close()
        except sqlite3.Error:
            pass

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
    decisions_dir = d / "decisions"
    private_dir = d / "_private" / "decisions"

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
        source_tag = f"source: git:{commit_hash}"
        found = False
        for search_dir in (decisions_dir, private_dir):
            if search_dir.is_dir():
                for f in search_dir.glob("*.md"):
                    if source_tag in f.read_text(errors="replace"):
                        found = True
                        break
            if found:
                break
        if found:
            continue

        commit_date = date_str.split()[0] if date_str else date.today().isoformat()
        slug = _slugify(subject)
        if not slug:
            slug = f"commit-{commit_hash[:7]}"

        filepath = decisions_dir / f"{slug}.md"

        # Manual signal with same slug already exists — defer to it
        if filepath.is_file():
            continue
        if (private_dir / f"{slug}.md").is_file():
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
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_commit', ?)",
                (new_head,),
            )
            conn.commit()
            conn.close()
        except sqlite3.Error:
            pass


# ── Plan ingestion ───────────────────────────────────────────────────

def engram_ingest_plans(dir_path):
    """Ingest Claude Code plan files as decision signals."""
    d = Path(dir_path)
    db_path = d / "index.db"

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
    last_ingest = ""
    if db_path.is_file():
        try:
            conn = sqlite3.connect(str(db_path))
            row = conn.execute("SELECT value FROM meta WHERE key = 'last_plan_ingest'").fetchone()
            if row:
                last_ingest = row[0]
            conn.close()
        except sqlite3.Error:
            pass

    # Find plan files
    plan_files = list(plans_path.glob("*.md"))
    if last_ingest and db_path.is_file():
        db_mtime = db_path.stat().st_mtime
        plan_files = [f for f in plan_files if f.stat().st_mtime > db_mtime]

    if not plan_files:
        return

    decisions_dir = d / "decisions"
    today = date.today().isoformat()

    for plan_file in plan_files:
        basename = plan_file.stem

        # Dedup: skip if file with this source already exists
        source_tag = f"source: plan:{basename}"
        found = False
        if decisions_dir.is_dir():
            for f in decisions_dir.glob("*.md"):
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

        filepath = decisions_dir / f"plan-{slug}.md"
        signal = f"---\ntype: decision\ndate: {today}\nsource: plan:{basename}\n---\n\n# {title}\n\n{context}\n"
        filepath.write_text(signal)

    # Update last_plan_ingest timestamp
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_plan_ingest', ?)",
            (now,),
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


# ── Brief generation ─────────────────────────────────────────────────

def engram_brief(dir_path):
    """Generate brief.md summary of decisions."""
    d = Path(dir_path)
    db_path = d / "index.db"
    if not db_path.is_file():
        return

    conn = sqlite3.connect(str(db_path))

    # Build superseded set
    superseded_slugs = [
        row[0] for row in
        conn.execute("SELECT target_file FROM links WHERE rel_type='supersedes'").fetchall()
    ]

    superseded_count = len(superseded_slugs)

    # Build SQL exclusion for superseded slugs
    superseded_clause = ""
    superseded_params = []
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

    footer_parts = []
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

    conn.close()

    # Cap brief size
    max_lines = int(os.environ.get("ENGRAM_BRIEF_MAX_LINES", "50"))
    lines = brief.split("\n")
    if len(lines) > max_lines:
        brief = "\n".join(lines[:max_lines])
        brief += f"\n\n*... truncated to {max_lines} lines. Use @engram:query for full details.*"

    (d / "brief.md").write_text(brief + "\n")


# ── Path to keywords ────────────────────────────────────────────────

def engram_path_to_keywords(filepath):
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


# ── Query relevant signals ──────────────────────────────────────────

def engram_query_relevant(dir_path, search_terms, limit=3):
    """Search for signals matching keywords. Returns formatted string."""
    if not search_terms:
        return ""

    db_path = Path(dir_path) / "index.db"
    if not db_path.is_file():
        return ""

    # Build OR-joined FTS5 query
    terms = search_terms.split()
    if not terms:
        return ""
    fts_query = " OR ".join(terms)

    conn = sqlite3.connect(str(db_path))
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
    conn.close()

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


# ── Tag summary ─────────────────────────────────────────────────────

def engram_tag_summary(dir_path):
    """Return top topics summary string."""
    db_path = Path(dir_path) / "index.db"
    if not db_path.is_file():
        return ""

    conn = sqlite3.connect(str(db_path))

    total = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE private=0"
    ).fetchone()[0]
    if total < 5:
        conn.close()
        return ""

    rows = conn.execute(
        "SELECT j.value AS tag, COUNT(*) AS cnt "
        "FROM signals, json_each(signals.tags) j "
        "WHERE signals.private = 0 AND signals.tags != '[]' "
        "GROUP BY j.value ORDER BY cnt DESC LIMIT 8"
    ).fetchall()
    conn.close()

    if not rows:
        return ""

    parts = [f"{tag} ({cnt})" for tag, cnt in rows if tag]
    if not parts:
        return ""

    return "Top topics: " + ", ".join(parts)


# ── Find incomplete signals ─────────────────────────────────────────

def engram_find_incomplete(dir_path, limit=5):
    """Find signals with gaps. Returns pipe-delimited lines."""
    db_path = Path(dir_path) / "index.db"
    if not db_path.is_file():
        return ""

    conn = sqlite3.connect(str(db_path))
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
    conn.close()

    if not rows:
        return ""

    lines = []
    for slug, title, gaps in rows:
        gaps = gaps.rstrip(",")
        lines.append(f"{slug}|{title}|{gaps}")

    return "\n".join(lines)


# ── Resync pipeline ─────────────────────────────────────────────────

def engram_resync(dir_path):
    """Full sync: ingest commits, ingest plans, reindex, generate brief."""
    engram_ingest_commits(dir_path)
    engram_ingest_plans(dir_path)
    engram_reindex(dir_path)
    engram_brief(dir_path)


# ── Uncommitted signal summary ──────────────────────────────────────

def engram_uncommitted_summary(dir_path):
    """Report uncommitted signals if git tracking is enabled."""
    if not _git_tracking_enabled(dir_path):
        return ""

    try:
        subprocess.run(["git", "rev-parse", "--show-toplevel"],
                       capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return ""

    d = Path(dir_path)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", str(d / "decisions"), str(d / "_private" / "decisions")],
            capture_output=True, text=True, errors="replace",
        )
        lines = [l for l in result.stdout.splitlines() if l.strip()]
    except (OSError, subprocess.SubprocessError):
        return ""

    if not lines:
        return ""

    return f"{len(lines)} uncommitted signal(s) in .engram/"


# ── Validate content from stdin ──────────────────────────────────────

def _validate_content_stdin():
    """Validate signal content read from stdin. For pre-tool-use hook."""
    decoded = sys.stdin.read()
    errors = []

    lines = decoded.splitlines()

    # Check frontmatter delimiters
    delimiter_count = sum(1 for l in lines if l == "---")
    if not lines or lines[0] != "---":
        errors.append("missing opening --- frontmatter delimiter")
    if delimiter_count < 2:
        errors.append("missing closing --- frontmatter delimiter")

    # Check date field
    has_date = any(re.match(r"^date: *\d{4}-\d{2}-\d{2}", l) for l in lines)
    if not has_date:
        errors.append("missing or invalid date: field (need YYYY-MM-DD)")

    # Check tags field
    tags_line = ""
    for l in lines:
        if l.startswith("tags:"):
            tags_line = l
            break
    if not tags_line:
        errors.append("missing tags: field")
    elif "[]" in tags_line:
        errors.append("tags: is empty, add at least one tag")

    # Check H1 title
    has_title = any(l.startswith("# ") for l in lines)
    if not has_title:
        errors.append("missing H1 title (# ...)")

    # Check lead paragraph
    found_title = False
    lead = ""
    fm_count = 0
    for l in lines:
        if l == "---":
            fm_count += 1
            continue
        if fm_count < 2:
            continue
        if l.startswith("# "):
            found_title = True
            continue
        if found_title:
            if not l or l.startswith("#"):
                continue
            lead = l
            break

    if not lead or len(lead) < 20:
        errors.append("lead paragraph after title must exist and be >= 20 chars (explains why)")

    if errors:
        return "; ".join(errors) + "; "
    return ""


# ── CLI dispatch ────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 engram.py <command> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        ok = engram_init(dir_path)
        sys.exit(0 if ok else 1)

    elif cmd == "resync":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        engram_resync(dir_path)

    elif cmd == "reindex":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        engram_reindex(dir_path)

    elif cmd == "brief":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        engram_brief(dir_path)

    elif cmd == "query":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        keywords = sys.argv[3] if len(sys.argv) > 3 else ""
        limit = int(sys.argv[4]) if len(sys.argv) > 4 else 3
        result = engram_query_relevant(dir_path, keywords, limit)
        if result:
            print(result)

    elif cmd == "tag-summary":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        result = engram_tag_summary(dir_path)
        if result:
            print(result, end="")

    elif cmd == "find-incomplete":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        result = engram_find_incomplete(dir_path, limit)
        if result:
            print(result)

    elif cmd == "path-to-keywords":
        filepath = sys.argv[2] if len(sys.argv) > 2 else ""
        result = engram_path_to_keywords(filepath)
        if result:
            print(result, end="")

    elif cmd == "uncommitted-summary":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        result = engram_uncommitted_summary(dir_path)
        if result:
            print(result)

    elif cmd == "validate-content":
        errors = _validate_content_stdin()
        if errors:
            print(errors, file=sys.stderr)
            sys.exit(1)

    elif cmd == "ingest-commits":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        engram_ingest_commits(dir_path)

    elif cmd == "ingest-plans":
        dir_path = sys.argv[2] if len(sys.argv) > 2 else ".engram"
        engram_ingest_plans(dir_path)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
