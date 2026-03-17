#!/usr/bin/env python3
"""engram test suite — pytest style.

Each test function creates its own .engram/ via tmp_path.
Uses real SQLite and throwaway git repos.
"""

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import engram

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "plugin" / "schemas" / "schema.sql"
PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugin"
DISPATCH = PLUGIN_DIR / "hooks" / "dispatch.sh"

# Override schema file location
os.environ["ENGRAM_SCHEMA_FILE"] = str(SCHEMA_FILE)
engram.ENGRAM_SCHEMA_FILE = SCHEMA_FILE


# ── Test helpers ────────────────────────────────────────────────────


def _enable_git_tracking(dir_path):
    Path(dir_path, "config.toml").write_text("git_tracking = true\n")


def _create_test_repo(repo_dir, num_commits=5):
    os.makedirs(repo_dir, exist_ok=True)
    subprocess.run(["git", "init", "-q"], check=True, cwd=repo_dir)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True, cwd=repo_dir)
    subprocess.run(["git", "config", "user.name", "Test"], check=True, cwd=repo_dir)
    for i in range(1, num_commits + 1):
        Path(repo_dir, f"file{i}.txt").write_text(f"content {i}")
        subprocess.run(["git", "add", f"file{i}.txt"], check=True, cwd=repo_dir)
        subprocess.run(["git", "commit", "-q", "-m", f"Commit {i}: add file{i}.txt"], check=True, cwd=repo_dir)


def _create_test_repo_mixed(repo_dir):
    os.makedirs(repo_dir, exist_ok=True)
    subprocess.run(["git", "init", "-q"], check=True, cwd=repo_dir)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True, cwd=repo_dir)
    subprocess.run(["git", "config", "user.name", "Test"], check=True, cwd=repo_dir)

    # Decision-worthy commits
    Path(repo_dir, "Gemfile").write_text("v1")
    subprocess.run(["git", "add", "Gemfile"], check=True, cwd=repo_dir)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add user authentication"], check=True, cwd=repo_dir)

    Path(repo_dir, "app.rb").write_text("v2")
    subprocess.run(["git", "add", "app.rb"], check=True, cwd=repo_dir)
    subprocess.run(["git", "commit", "-q", "-m", "refactor: extract payment service"], check=True, cwd=repo_dir)

    Path(repo_dir, "schema.sql").write_text("v3")
    subprocess.run(["git", "add", "schema.sql"], check=True, cwd=repo_dir)
    subprocess.run(["git", "commit", "-q", "-m", "migrate users to new schema"], check=True, cwd=repo_dir)

    # Trivial commits
    Path(repo_dir, "README.md").write_text("v4")
    subprocess.run(["git", "add", "README.md"], check=True, cwd=repo_dir)
    subprocess.run(["git", "commit", "-q", "-m", "docs: update README"], check=True, cwd=repo_dir)

    Path(repo_dir, "app.rb").write_text("v5")
    subprocess.run(["git", "add", "app.rb"], check=True, cwd=repo_dir)
    subprocess.run(["git", "commit", "-q", "-m", "fix: handle nil email"], check=True, cwd=repo_dir)

    Path(repo_dir, "test.rb").write_text("v6")
    subprocess.run(["git", "add", "test.rb"], check=True, cwd=repo_dir)
    subprocess.run(["git", "commit", "-q", "-m", "test: add payment specs"], check=True, cwd=repo_dir)

    Path(repo_dir, "style.css").write_text("v7")
    subprocess.run(["git", "add", "style.css"], check=True, cwd=repo_dir)
    subprocess.run(["git", "commit", "-q", "-m", "chore: lint fixes"], check=True, cwd=repo_dir)


def _db_query(db_path, sql, params=()):
    conn = sqlite3.connect(str(db_path))
    result = conn.execute(sql, params).fetchall()
    conn.close()
    return result


def _db_scalar(db_path, sql, params=()):
    rows = _db_query(db_path, sql, params)
    return rows[0][0] if rows else None


# ── Tests ───────────────────────────────────────────────────────────

def test_fts5_check():
    result = engram._check_fts5()
    assert result == True


def test_init(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()
    assert Path(d, "decisions").is_dir()
    assert Path(d, "_private", "decisions").is_dir()
    assert Path(d, "index.db").is_file()

    # No .gitignore by default
    assert not Path(d, ".gitignore").is_file()

    # Idempotent
    store.init()
    assert Path(d, "index.db").is_file()


def test_init_private_dirs(tmp_path):
    d = str(tmp_path / ".engram")
    engram.EngramStore(d).init()
    assert Path(d, "_private", "decisions").is_dir()


def test_write_decision(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "use-redis.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"infrastructure\", \"caching\"]\n+++\n\n"
        "# Use Redis for caching\n\nAlready in our stack for session storage.\n\n"
        "## Alternatives\n- Memcached — faster for simple k/v but no pub/sub\n\n"
        "## Rationale\nRedis supports pub/sub which we'll need for notifications.\n\n"
        "## Trade-offs\nHigher memory usage than Memcached.\n"
    )

    store.reindex()

    result = _db_query(f"{d}/index.db", "SELECT type, title, date FROM signals WHERE type='decision'")
    result_str = str(result)
    assert "Use Redis for caching" in result_str
    assert "2026-03-14" in result_str
    assert "decision" in result_str


def test_is_decision_commit(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    _create_test_repo_mixed(repo_dir)
    monkeypatch.chdir(repo_dir)

    result = subprocess.run(["git", "log", "--format=%H|%s", "--reverse"],
                            capture_output=True, text=True)
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        h, subject = line.split("|", 1)
        is_decision = engram._is_decision_commit(subject, h)
        label = "decision" if is_decision else "skip"

        if subject == "feat: add user authentication":
            assert label == "decision"
        elif subject == "refactor: extract payment service":
            assert label == "decision"
        elif subject == "migrate users to new schema":
            assert label == "decision"
        elif subject == "docs: update README":
            assert label == "skip"
        elif subject == "fix: handle nil email":
            assert label == "skip"
        elif subject == "test: add payment specs":
            assert label == "skip"
        elif subject == "chore: lint fixes":
            assert label == "skip"


def test_ingest_commits(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    _create_test_repo_mixed(repo_dir)
    monkeypatch.chdir(repo_dir)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()

    file_count = len(list(Path(d, "decisions").glob("*.md")))
    assert str(file_count) == "3"

    # Verify files have source = "git:<hash>"
    has_source = sum(
        1 for f in Path(d, "decisions").glob("*.md")
        if "git:" in f.read_text()
    )
    assert str(has_source) == "3"


def test_ingest_commits_body(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    os.makedirs(repo_dir, exist_ok=True)
    monkeypatch.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)

    Path("auth.rb").write_text("v1")
    subprocess.run(["git", "add", "auth.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add OAuth2 authentication",
                     "-m", "We chose OAuth2 over SAML because our mobile clients need token-based auth.\n\nCo-Authored-By: Claude <noreply@anthropic.com>"], check=True)

    Path("api.rb").write_text("v2")
    subprocess.run(["git", "add", "api.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "refactor: extract API gateway"], check=True)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()

    file_count = len(list(Path(d, "decisions").glob("*.md")))
    assert str(file_count) == "2"

    # Find OAuth2 file
    oauth_file = None
    for f in Path(d, "decisions").glob("*.md"):
        if "OAuth2" in f.read_text():
            oauth_file = f
            break
    content = oauth_file.read_text() if oauth_file else ""
    assert "token-based auth" in str(content)
    assert "Co-Authored-By" not in str(content)

    # Find API gateway file
    api_file = None
    for f in Path(d, "decisions").glob("*.md"):
        if "API gateway" in f.read_text():
            api_file = f
            break
    api_content = api_file.read_text() if api_file else ""
    assert "api.rb" in str(api_content)


def test_ingest_dedup(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    _create_test_repo_mixed(repo_dir)
    monkeypatch.chdir(repo_dir)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)

    store.ingest_commits()
    first_count = len(list(Path(d, "decisions").glob("*.md")))

    store.ingest_commits()
    second_count = len(list(Path(d, "decisions").glob("*.md")))

    assert str(first_count) == str(second_count)


def test_ingest_manual_signal_suppresses(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    os.makedirs(repo_dir, exist_ok=True)
    monkeypatch.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)

    Path("widget.rb").write_text("v1")
    subprocess.run(["git", "add", "widget.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add widget"], check=True)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)

    Path(d, "decisions", "feat-add-widget.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"widget\"]\n+++\n\n"
        "# Add widget component\n\nWe chose a widget approach because it composes better than mixins.\n"
    )

    store.ingest_commits()

    file_count = len(list(Path(d, "decisions").glob("feat-add-widget*")))
    assert str(file_count) == "1"

    assert "source" not in str(Path(d, "decisions", "feat-add-widget.md").read_text())


def test_ingest_private_signal_suppresses(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    os.makedirs(repo_dir, exist_ok=True)
    monkeypatch.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)

    Path("cache.rb").write_text("v1")
    subprocess.run(["git", "add", "cache.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: switch to redis for caching"], check=True)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)

    Path(d, "_private", "decisions", "feat-switch-to-redis-for-caching.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"caching\"]\n+++\n\n"
        "# Switch to Redis for caching\n\nPrivate: contains vendor pricing details.\n"
    )

    store.ingest_commits()

    public_count = len(list(Path(d, "decisions").glob("feat-switch-to-redis*")))
    assert str(public_count) == "0"


def test_ingest_no_manual_still_creates(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    os.makedirs(repo_dir, exist_ok=True)
    monkeypatch.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)

    Path("api.rb").write_text("v1")
    subprocess.run(["git", "add", "api.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add API gateway"], check=True)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()

    file_count = len(list(Path(d, "decisions").glob("feat-add-api-gateway*")))
    assert str(file_count) == "1"

    content = list(Path(d, "decisions").glob("feat-add-api-gateway*"))[0].read_text()
    assert 'source = "git:' in str(content)


def test_ingest_brownfield(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    os.makedirs(repo_dir, exist_ok=True)
    monkeypatch.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)

    for i in range(1, 101):
        Path(f"file{i}.txt").write_text(f"content {i}")
        subprocess.run(["git", "add", f"file{i}.txt"], check=True)
        if i % 5 != 0:
            subprocess.run(["git", "commit", "-q", "-m", f"feat: add feature {i}"], check=True)
        else:
            subprocess.run(["git", "commit", "-q", "-m", f"fix: typo in file {i}"], check=True)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()

    file_count = len(list(Path(d, "decisions").glob("*.md")))
    assert str(file_count) == "40"


def test_ingest_plans(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    _create_test_repo(repo_dir, 1)
    monkeypatch.chdir(repo_dir)

    d = f"{repo_dir}/.engram"
    plans_dir = str(tmp_path / "plans")
    os.makedirs(plans_dir, exist_ok=True)
    monkeypatch.setenv("ENGRAM_PLANS_DIR", plans_dir)

    Path(plans_dir, "auth-redesign.md").write_text(
        "# Auth Redesign\n\n## Context\n"
        "We need to move from session-based auth to JWT because our mobile\n"
        "app can't maintain server-side sessions efficiently.\n\n"
        "## Implementation\nUse asymmetric keys for JWT signing...\n"
    )

    store = engram.EngramStore(d)
    store.init()
    store.ingest_plans()

    plan_files = sum(
        1 for f in Path(d, "decisions").glob("*.md")
        if "plan:auth-redesign" in f.read_text()
    )
    assert str(plan_files) == "1"

    content = ""
    for f in Path(d, "decisions").glob("plan*auth*"):
        content = f.read_text()
    assert "JWT" in str(content)


def test_reindex(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "test-a.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n# Decision A\n\nContent A\n"
    )
    Path(d, "decisions", "test-b.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n# Decision B\n\nContent B\n"
    )

    store.reindex()

    count = _db_scalar(f"{d}/index.db", "SELECT COUNT(*) FROM signals")
    assert str(count) == "2"

    # Delete and recreate
    Path(d, "index.db").unlink()
    store.reindex()
    count = _db_scalar(f"{d}/index.db", "SELECT COUNT(*) FROM signals")
    assert str(count) == "2"


def test_brief(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "pick-redis.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"infrastructure\"]\n+++\n\n"
        "# Pick Redis for caching\n\nAlready in our stack for session storage and pub/sub needs.\n\n"
        "## Alternatives\n- Memcached — no pub/sub\n\n"
        "## Rationale\nRedis supports pub/sub for notifications.\n"
    )

    store.reindex()
    store.brief()

    assert Path(d, "brief.md").is_file()
    brief = Path(d, "brief.md").read_text()
    assert "Recent Decisions" in str(brief)
    assert "Pick Redis" in str(brief)
    assert "1 decisions" in str(brief)


def test_fts_search(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "postgresql.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Use PostgreSQL over MySQL\n\nBetter JSON support and window functions.\n"
    )
    Path(d, "decisions", "fts5.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# FTS5 needs sync triggers\n\nWithout triggers the index becomes stale.\n"
    )

    store.reindex()

    db = f"{d}/index.db"
    result = _db_query(db,
        "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid "
        "WHERE signals_fts MATCH 'PostgreSQL' ORDER BY rank LIMIT 10")
    assert "PostgreSQL" in str(result)

    result = _db_query(db,
        "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid "
        "WHERE signals_fts MATCH 'triggers' ORDER BY rank LIMIT 10")
    assert "FTS5" in str(result)

    result = _db_query(db,
        "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid "
        "WHERE signals_fts MATCH 'nonexistent_xyz_12345' ORDER BY rank LIMIT 10")
    assert str(result) == "[]"


def test_frontmatter_parsing(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "no-frontmatter.md").write_text(
        "# Decision with no frontmatter\n\nJust a plain markdown file with a heading.\n"
    )
    Path(d, "decisions", "partial.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Partial frontmatter\n\nOnly date, no tags or source.\n"
    )
    Path(d, "decisions", "full.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"api\", \"auth\"]\nsource = \"git:abc1234\"\n+++\n\n"
        "# Full frontmatter\n\nHas everything.\n"
    )

    store.reindex()

    count = _db_scalar(f"{d}/index.db", "SELECT COUNT(*) FROM signals")
    assert str(count) == "3"

    tags = _db_scalar(f"{d}/index.db", "SELECT tags FROM signals WHERE title='Partial frontmatter'")
    assert tags == "[]"

    source = _db_scalar(f"{d}/index.db", "SELECT source FROM signals WHERE title='Partial frontmatter'")
    assert source == ""


def test_meta_preserved(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    _create_test_repo(repo_dir, 3)
    monkeypatch.chdir(repo_dir)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()

    last_commit = _db_scalar(f"{d}/index.db", "SELECT value FROM meta WHERE key='last_commit'")
    assert "EMPTY" not in str(last_commit)

    store.reindex()
    after_reindex = _db_scalar(f"{d}/index.db", "SELECT value FROM meta WHERE key='last_commit'")
    assert after_reindex == last_commit


def test_incremental_ingest(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    os.makedirs(repo_dir, exist_ok=True)
    monkeypatch.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)

    for i in range(1, 4):
        Path(f"feat{i}.rb").write_text(f"v{i}")
        subprocess.run(["git", "add", f"feat{i}.rb"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"feat: add feature {i}"], check=True)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()

    first_count = len(list(Path(d, "decisions").glob("*.md")))
    assert str(first_count) == "3"

    Path("feat4.rb").write_text("v4")
    subprocess.run(["git", "add", "feat4.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add feature 4"], check=True)

    Path("feat5.rb").write_text("v5")
    subprocess.run(["git", "add", "feat5.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "refactor: extract shared module"], check=True)

    store.ingest_commits()
    second_count = len(list(Path(d, "decisions").glob("*.md")))
    assert str(second_count) == "5"


def test_file_column(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "test-file.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n# Test file column\n\nContent.\n"
    )

    store.reindex()

    file_val = _db_scalar(f"{d}/index.db", "SELECT file FROM signals LIMIT 1")
    assert "decisions/test-file.md" in str(file_val)


def test_private_signal_indexed(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "_private", "decisions", "secret-deal.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"crm\", \"deals\"]\n+++\n\n"
        "# Secret deal with Acme Corp\n\nConfidential terms discussion.\n"
    )

    store.reindex()

    private_val = _db_scalar(f"{d}/index.db",
        "SELECT private FROM signals WHERE title='Secret deal with Acme Corp'")
    assert str(private_val) == "1"


def test_brief_excludes_private(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "public-choice.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"architecture\"]\n+++\n\n"
        "# Public architecture choice\n\nVisible to everyone in the team and included in the brief.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nBest option.\n"
    )
    Path(d, "_private", "decisions", "private-deal.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"business\"]\n+++\n\n"
        "# Private deal terms\n\nConfidential information about deal structure and terms.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nBest option.\n"
    )

    store.reindex()
    store.brief()

    brief = Path(d, "brief.md").read_text()
    assert "Public architecture choice" in str(brief)
    assert "Private deal terms" not in str(brief)
    assert "1 private signal(s)" in str(brief)


def test_private_queryable(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "_private", "decisions", "competitor-intel.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"competitive\"]\n+++\n\n"
        "# Competitor launched new product\n\nDetails about competitor's launch.\n"
    )

    store.reindex()

    result = _db_query(f"{d}/index.db",
        "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid "
        "WHERE signals_fts MATCH 'competitor' ORDER BY rank LIMIT 10")
    assert "Competitor launched new product" in str(result)


def test_public_signals_unchanged(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "normal.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Normal public decision\n\nStandard decision content.\n"
    )

    store.reindex()

    private_val = _db_scalar(f"{d}/index.db",
        "SELECT private FROM signals WHERE title='Normal public decision'")
    assert str(private_val) == "0"


def test_uncommitted_summary(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    _create_test_repo(repo_dir, 1)
    monkeypatch.chdir(repo_dir)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)

    Path(d, "decisions", "test-uncommitted.md").write_text(
        "+++\ndate = 2026-03-16\n+++\n\n"
        "# Test uncommitted signal\n\nSome content.\n"
    )

    result = store.uncommitted_summary()
    assert "1 uncommitted signal" in str(result)

    subprocess.run(["git", "add", ".engram/"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "engram: add signal"], check=True)

    result = store.uncommitted_summary()
    assert result == ""


def test_uncommitted_summary_no_git(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "no-git.md").write_text(
        "+++\ndate = 2026-03-16\n+++\n\n# No git repo\n\nContent.\n"
    )

    result = store.uncommitted_summary()
    assert result == ""


def test_session_end_output(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    os.makedirs(repo_dir, exist_ok=True)
    monkeypatch.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)
    Path("README.md").write_text("readme")
    subprocess.run(["git", "add", "."], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "docs: add readme"], check=True)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()
    store.reindex()
    store.brief()

    # Add .gitkeep
    Path(d, "decisions", ".gitkeep").touch()
    Path(d, "_private", "decisions", ".gitkeep").touch()
    subprocess.run(["git", "add", ".engram/"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "engram: init"], check=True)

    dispatch = str(DISPATCH)
    empty_plans = str(tmp_path / "empty-plans")
    os.makedirs(empty_plans, exist_ok=True)

    output = subprocess.run(
        ["bash", dispatch, "SessionEnd"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "ENGRAM_PLANS_DIR": empty_plans},
        cwd=repo_dir,
    ).stdout.strip()
    assert output == "{}"

    Path(d, "decisions", "test-end.md").write_text(
        "+++\ndate = 2026-03-16\n+++\n\n# Test session end\n\nContent.\n"
    )

    output = subprocess.run(
        ["bash", dispatch, "SessionEnd"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "ENGRAM_PLANS_DIR": empty_plans},
        cwd=repo_dir,
    ).stdout.strip()
    assert output == "{}"


def test_supersedes_frontmatter(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "old-auth.md").write_text(
        "+++\ndate = 2026-03-10\n+++\n\n"
        "# Use session-based auth\n\nServer-side sessions with cookies.\n"
    )
    Path(d, "decisions", "new-auth.md").write_text(
        "+++\ndate = 2026-03-15\nsupersedes = \"old-auth\"\n+++\n\n"
        "# Use JWT authentication\n\nMobile clients need token-based auth.\n"
    )

    store.reindex()

    link_count = _db_scalar(f"{d}/index.db",
        "SELECT COUNT(*) FROM links WHERE source_file='new-auth' AND target_file='old-auth' AND rel_type='supersedes'")
    assert str(link_count) == "1"


def test_links_frontmatter(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "use-redis.md").write_text(
        "+++\ndate = 2026-03-14\nlinks = [\"related:fts5-perf\", \"related:ci-timeout\"]\n+++\n\n"
        "# Use Redis for caching\n\nAlready in our stack.\n"
    )

    store.reindex()

    related_count = _db_scalar(f"{d}/index.db",
        "SELECT COUNT(*) FROM links WHERE source_file='use-redis' AND target_file='fts5-perf' AND rel_type='related'")
    assert str(related_count) == "1"

    total_links = _db_scalar(f"{d}/index.db",
        "SELECT COUNT(*) FROM links WHERE source_file='use-redis'")
    assert str(total_links) == "2"


def test_excerpt_extraction(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "test-excerpt.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Pick PostgreSQL\n\nBetter JSON support and window functions.\n\n"
        "## Alternatives\nMySQL was considered.\n"
    )

    store.reindex()

    excerpt = _db_scalar(f"{d}/index.db", "SELECT excerpt FROM signals WHERE slug='test-excerpt'")
    assert "Better JSON support" in str(excerpt)


def test_slug_column(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "use-redis.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n# Use Redis\n\nContent.\n"
    )

    store.reindex()

    slug_val = _db_scalar(f"{d}/index.db", "SELECT slug FROM signals LIMIT 1")
    assert slug_val == "use-redis"


def test_brief_hides_superseded(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "old-cache.md").write_text(
        "+++\ndate = 2026-03-10\ntags = [\"infrastructure\"]\n+++\n\n"
        "# Use Memcached for caching\n\nFast and simple key-value store for basic caching needs.\n\n"
        "## Alternatives\n- Redis\n\n## Rationale\nSimple k/v.\n"
    )
    Path(d, "decisions", "new-cache.md").write_text(
        "+++\ndate = 2026-03-15\ntags = [\"infrastructure\"]\nsupersedes = \"old-cache\"\n+++\n\n"
        "# Use Redis for caching\n\nSupports pub/sub which we need for real-time notifications.\n\n"
        "## Alternatives\n- Memcached\n\n## Rationale\nPub/sub support.\n"
    )

    store.reindex()
    store.brief()

    brief = Path(d, "brief.md").read_text()
    assert "Use Redis for caching" in str(brief)
    assert "Use Memcached" not in str(brief)
    assert "1 superseded" in str(brief)


def test_brief_tag_grouping(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "redis.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"infrastructure\", \"caching\"]\n+++\n\n"
        "# Use Redis\n\nAlready in our stack for session storage and we need pub/sub.\n\n"
        "## Alternatives\n- Memcached\n\n## Rationale\nPub/sub support.\n"
    )
    Path(d, "decisions", "jwt.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"auth\", \"security\"]\n+++\n\n"
        "# Use JWT\n\nMobile clients need stateless token-based authentication.\n\n"
        "## Alternatives\n- Sessions\n\n## Rationale\nStateless auth for mobile.\n"
    )
    Path(d, "decisions", "postgres.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"database\", \"storage\"]\n+++\n\n"
        "# Use PostgreSQL\n\nBetter JSON support and window functions than MySQL.\n\n"
        "## Alternatives\n- MySQL\n\n## Rationale\nJSON and window functions.\n"
    )

    store.reindex()
    store.brief()

    brief = Path(d, "brief.md").read_text()
    assert "###" in str(brief)


def test_brief_max_lines(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    for i in range(1, 21):
        Path(d, "decisions", f"bulk-{i}.md").write_text(
            f"+++\ndate = 2026-03-14\ntags = [\"bulk\", \"testing\"]\n+++\n\n"
            f"# Bulk decision number {i}\n\nSome explanation for decision {i} with enough text to occupy space in the brief.\n\n"
            f"## Alternatives\n- None\n\n## Rationale\nBulk test.\n"
        )

    store.reindex()
    os.environ["ENGRAM_BRIEF_MAX_LINES"] = "10"
    store.brief()
    os.environ.pop("ENGRAM_BRIEF_MAX_LINES", None)

    brief = Path(d, "brief.md").read_text()
    assert "truncated to 10 lines" in str(brief)
    assert "Decision Context" in str(brief)


def test_brief_excerpts(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "test-exc.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"infrastructure\"]\n+++\n\n"
        "# Use Redis for caching\n\nAlready in our stack for session storage and pub/sub needs.\n\n"
        "## Alternatives\n- Memcached\n\n## Rationale\nPub/sub support.\n"
    )

    store.reindex()
    store.brief()

    brief = Path(d, "brief.md").read_text()
    assert "Already in our stack" in str(brief)


def test_supersession_chain(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "auth-v1.md").write_text(
        "+++\ndate = 2026-03-01\n+++\n\n# Auth v1: sessions\n\nCookie-based sessions.\n"
    )
    Path(d, "decisions", "auth-v2.md").write_text(
        "+++\ndate = 2026-03-10\nsupersedes = \"auth-v1\"\n+++\n\n# Auth v2: JWT\n\nToken-based auth.\n"
    )
    Path(d, "decisions", "auth-v3.md").write_text(
        "+++\ndate = 2026-03-15\nsupersedes = \"auth-v2\"\n+++\n\n# Auth v3: OAuth2\n\nDelegated authentication.\n"
    )

    store.reindex()

    chain = _db_query(f"{d}/index.db",
        "WITH RECURSIVE chain(stem, depth) AS ("
        "SELECT 'auth-v3', 0 UNION ALL "
        "SELECT l.target_file, c.depth + 1 FROM chain c JOIN links l ON l.source_file = c.stem AND l.rel_type = 'supersedes'"
        ") SELECT s.title FROM chain c JOIN signals s ON s.slug = c.stem ORDER BY c.depth")
    chain_str = str(chain)
    assert "Auth v3" in chain_str
    assert "Auth v2" in chain_str
    assert "Auth v1" in chain_str


def test_links_bidirectional(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "use-redis.md").write_text(
        "+++\ndate = 2026-03-14\nlinks = [\"related:redis-perf\"]\n+++\n\n"
        "# Use Redis\n\nFor caching.\n"
    )
    Path(d, "decisions", "redis-perf.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Redis p99 latency is 2ms\n\nVery fast.\n"
    )

    store.reindex()

    from_target = _db_scalar(f"{d}/index.db",
        "SELECT source_file FROM links WHERE target_file='redis-perf'")
    assert from_target == "use-redis"

    from_decision = _db_scalar(f"{d}/index.db",
        "SELECT target_file FROM links WHERE source_file='use-redis'")
    assert from_decision == "redis-perf"


def test_path_to_keywords():
    result = engram.engram_path_to_keywords("src/auth/oauth-handler.ts")
    assert "auth" in str(result)
    assert "oauth" in str(result)
    assert "handler" in str(result)
    # "src" is a noise word
    words = result.split()
    assert "src" not in words
    assert "ts" not in words

    result = engram.engram_path_to_keywords("lib/index.js")
    words = result.split()
    assert "lib" not in words
    assert "index" not in words

    result = engram.engram_path_to_keywords("app/models/payment_processor.rb")
    assert "models" in str(result)
    assert "payment" in str(result)
    assert "processor" in str(result)

    result = engram.engram_path_to_keywords("")
    assert result == ""


def test_query_relevant(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "use-redis.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"infrastructure\"]\n+++\n\n"
        "# Use Redis for caching\n\nAlready in our stack for session storage and pub/sub needs.\n\n"
        "## Alternatives\n- Memcached\n\n## Rationale\nPub/sub.\n"
    )
    Path(d, "decisions", "jwt-auth.md").write_text(
        "+++\ndate = 2026-03-15\ntags = [\"auth\"]\n+++\n\n"
        "# Use JWT for authentication\n\nToken-based auth for mobile clients that need stateless sessions.\n\n"
        "## Alternatives\n- Sessions\n\n## Rationale\nStateless.\n"
    )
    Path(d, "_private", "decisions", "secret.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"caching\"]\n+++\n\n"
        "# Secret caching strategy\n\nPrivate info about caching that should not be visible in queries.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nPrivate.\n"
    )

    store.reindex()

    result = store.query_relevant("redis caching")
    assert "Use Redis" in str(result)
    assert "Secret" not in str(result)

    result = store.query_relevant("nonexistent_xyz_12345")
    assert result == ""

    result = store.query_relevant("")
    assert result == ""

    result = store.query_relevant("auth redis caching", limit=1)
    line_count = len([l for l in result.splitlines() if l.startswith("-")])
    assert line_count <= 1


def test_query_relevant_excludes_superseded(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "old-cache.md").write_text(
        "+++\ndate = 2026-03-10\ntags = [\"infrastructure\"]\n+++\n\n"
        "# Use Memcached for caching\n\nFast and simple key-value store for basic caching needs.\n\n"
        "## Alternatives\n- Redis\n\n## Rationale\nSimple.\n"
    )
    Path(d, "decisions", "new-cache.md").write_text(
        "+++\ndate = 2026-03-15\ntags = [\"infrastructure\"]\nsupersedes = \"old-cache\"\n+++\n\n"
        "# Use Redis for caching\n\nSupports pub/sub which we need for real-time notifications.\n\n"
        "## Alternatives\n- Memcached\n\n## Rationale\nPub/sub.\n"
    )

    store.reindex()

    result = store.query_relevant("caching")
    assert "Use Redis" in str(result)
    assert "Memcached" not in str(result)


def test_tag_summary(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    for i in range(1, 4):
        Path(d, "decisions", f"arch-{i}.md").write_text(
            f"+++\ndate = 2026-03-14\ntags = [\"architecture\"]\n+++\n\n"
            f"# Architecture decision {i}\n\nContent {i} with enough explanation.\n\n"
            f"## Alternatives\n- None\n\n## Rationale\nBest option.\n"
        )
    for i in range(1, 3):
        Path(d, "decisions", f"testing-{i}.md").write_text(
            f"+++\ndate = 2026-03-14\ntags = [\"testing\"]\n+++\n\n"
            f"# Testing decision {i}\n\nContent {i} with enough explanation.\n\n"
            f"## Alternatives\n- None\n\n## Rationale\nBest option.\n"
        )
    Path(d, "decisions", "ci.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"ci\"]\n+++\n\n# CI decision\n\nContent with enough explanation here.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nBest option.\n"
    )

    store.reindex()

    result = store.tag_summary()
    assert "architecture" in str(result)
    assert "(3)" in str(result)
    assert "Top topics" in str(result)


def test_tag_summary_few_signals(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "a.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"foo\"]\n+++\n\n# A\n\nContent.\n"
    )
    Path(d, "decisions", "b.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"bar\"]\n+++\n\n# B\n\nContent.\n"
    )

    store.reindex()

    result = store.tag_summary()
    assert result == ""


def test_post_tool_context_output(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "auth-handler.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Use OAuth for auth handler\n\nToken-based authentication.\n"
    )

    store.reindex()

    dispatch = str(DISPATCH)
    test_cwd = str(tmp_path)

    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Write","tool_input":{"file_path":"src/auth/handler.ts"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()

    json.loads(output)  # valid JSON

    # Skip .engram paths
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Write","tool_input":{"file_path":".engram/decisions/foo.md"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-ptu-skip-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert output == "{}"

    # Skip test files
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Write","tool_input":{"file_path":"tests/test_auth.rb"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-ptu-skip2-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert output == "{}"


def test_pre_compact_output(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "compact-test.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"testing\"]\n+++\n\n"
        "# Compact test decision\n\nTesting pre-compact hook with valid signal to verify context injection.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nTest coverage.\n"
    )

    store.reindex()
    store.brief()

    dispatch = str(DISPATCH)
    test_cwd = str(tmp_path)

    output = subprocess.run(
        ["bash", dispatch, "PreCompact"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
        cwd=test_cwd,
    ).stdout.strip()

    json.loads(output)  # valid JSON
    assert "systemMessage" in output
    assert "Compact test decision" in str(output)


def test_stop_hook_output(tmp_path):
    d = str(tmp_path / ".engram")
    engram.EngramStore(d).init()

    dispatch = str(DISPATCH)
    test_cwd = str(tmp_path)

    output = subprocess.run(
        ["bash", dispatch, "Stop"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-stop-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()

    json.loads(output)  # valid JSON
    assert '"ok": true' in str(output)


def test_stop_hook_no_engram(tmp_path):
    empty_dir = str(tmp_path / "empty")
    os.makedirs(empty_dir, exist_ok=True)

    dispatch = str(DISPATCH)

    output = subprocess.run(
        ["bash", dispatch, "Stop"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-stop-empty-{os.getpid()}"},
        cwd=empty_dir,
    ).stdout.strip()
    assert output == '{"ok": true}'


def test_user_prompt_submit_hook():
    dispatch = str(DISPATCH)

    output = subprocess.run(
        ["bash", dispatch, "UserPromptSubmit"],
        input='{"tool_input":{"content":"fix the bug in auth.rb"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-ups-{os.getpid()}"},
    ).stdout.strip()
    assert output == "{}"

    output = subprocess.run(
        ["bash", dispatch, "UserPromptSubmit"],
        input='{"tool_input":{"content":"lets go with Redis for caching"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-ups-decision-{os.getpid()}"},
    ).stdout.strip()
    assert "engram:capture" in str(output)

    output = subprocess.run(
        ["bash", dispatch, "UserPromptSubmit"],
        input='{"tool_input":{"content":"why did we choose Redis?"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-ups-query-{os.getpid()}"},
    ).stdout.strip()
    assert "engram:query" in str(output)


def test_pre_tool_use_validation():
    dispatch = str(DISPATCH)

    # Non-engram file
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Write","tool_input":{"file_path":"src/app.rb","content":"hello"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # Valid signal
    valid_content = "+++\ndate = 2026-03-17\ntags = [\"architecture\"]\n+++\n\n# Valid decision\n\nThis is a valid lead paragraph with enough chars.\n\n## Alternatives\n- None\n\n## Rationale\nValid."
    input_json = json.dumps({"tool_name": "Write", "tool_input": {"file_path": ".engram/decisions/valid.md", "content": valid_content}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # Missing tags
    no_tags_content = "+++\ndate = 2026-03-17\ntags = []\n+++\n\n# No tags\n\nThis decision has empty tags which should fail."
    input_json = json.dumps({"tool_name": "Write", "tool_input": {"file_path": ".engram/decisions/no-tags.md", "content": no_tags_content}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert '"ok": false' in str(output)
    assert "tags" in str(output)

    # Missing frontmatter
    no_fm_content = "# No frontmatter\n\nJust a plain file."
    input_json = json.dumps({"tool_name": "Write", "tool_input": {"file_path": ".engram/decisions/no-fm.md", "content": no_fm_content}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert '"ok": false' in str(output)


def test_notification_hook(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "incomplete.md").write_text(
        "+++\ndate = 2026-03-17\n+++\n\n# Incomplete\n\nShort.\n"
    )

    store.reindex()

    dispatch = str(DISPATCH)
    test_cwd = str(tmp_path)

    output = subprocess.run(
        ["bash", dispatch, "Notification"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-notif-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert "incomplete" in str(output)

    # Remove incomplete, add complete
    Path(d, "decisions", "incomplete.md").unlink()
    Path(d, "decisions", "complete.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Complete decision\n\nThis decision has proper rationale and tags for validation.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nComplete.\n"
    )

    store.reindex()
    output = subprocess.run(
        ["bash", dispatch, "Notification"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-notif-clean-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert output == "{}"


def test_pre_compact_no_engram(tmp_path):
    empty_dir = str(tmp_path / "empty")
    os.makedirs(empty_dir, exist_ok=True)

    dispatch = str(DISPATCH)

    output = subprocess.run(
        ["bash", dispatch, "PreCompact"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
        cwd=empty_dir,
    ).stdout.strip()
    assert output == "{}"


def test_hooks_json_structure():
    hooks_file = PLUGIN_DIR / "hooks" / "hooks.json"

    data = json.loads(hooks_file.read_text())

    expected_events = ["SessionStart", "SessionEnd", "Stop", "PostToolUse", "PreToolUse",
                       "SubagentStop", "PreCompact", "UserPromptSubmit", "Notification"]
    for event in expected_events:
        hooks = data.get("hooks", {}).get(event, [])
        assert len(hooks) >= 1, f"hooks.json missing event: {event}"

    # All hooks must be command hooks
    prompt_count = 0
    for event_hooks in data.get("hooks", {}).values():
        for entry in event_hooks:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "prompt":
                    prompt_count += 1
    assert str(prompt_count) == "0"

    # No empty commands
    empty_commands = 0
    for event_hooks in data.get("hooks", {}).values():
        for entry in event_hooks:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command" and not hook.get("command"):
                    empty_commands += 1
    assert str(empty_commands) == "0"

    # PreToolUse matcher
    pre_matcher = data["hooks"]["PreToolUse"][0].get("matcher", "")
    assert "Write" in str(pre_matcher)
    assert "Edit" in str(pre_matcher)

    # PostToolUse matcher
    post_matcher = data["hooks"]["PostToolUse"][0].get("matcher", "")
    assert "Write" in str(post_matcher)
    assert "Edit" in str(post_matcher)
    assert "MultiEdit" in str(post_matcher)

    # All command hooks reference dispatch.sh
    all_commands = []
    for event_hooks in data.get("hooks", {}).values():
        for entry in event_hooks:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command":
                    all_commands.append(hook.get("command", ""))
    total = len(all_commands)
    dispatch_count = sum(1 for c in all_commands if "dispatch.sh" in c)
    assert str(dispatch_count) == str(total)


def test_validate_signal_valid(tmp_path):
    d = str(tmp_path / ".engram")
    engram.EngramStore(d).init()

    Path(d, "decisions", "valid-test.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"architecture\", \"validation\"]\n+++\n\n"
        "# Use strict validation for signals\n\n"
        "Enforce structure at write time to ensure all decisions include rationale, improving brief quality.\n\n"
        "## Alternatives\n- No validation — too many incomplete signals\n\n"
        "## Rationale\nEnsures all decisions include the why.\n"
    )

    ok, _ = engram.Signal.from_file(f"{d}/decisions/valid-test.md").validate()
    assert str(int(ok)) == "1"


def test_validate_signal_missing_why(tmp_path):
    d = str(tmp_path / ".engram")
    engram.EngramStore(d).init()

    Path(d, "decisions", "no-why.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"test\"]\n+++\n\n"
        "# Decision without explanation\n\n"
    )

    ok, _ = engram.Signal.from_file(f"{d}/decisions/no-why.md").validate()
    assert str(int(ok)) == "0"


def test_validate_signal_missing_tags(tmp_path):
    d = str(tmp_path / ".engram")
    engram.EngramStore(d).init()

    Path(d, "decisions", "no-tags.md").write_text(
        "+++\ndate = 2026-03-16\ntags = []\n+++\n\n"
        "# Decision without tags\n\nThis decision has no tags which should fail validation checks.\n"
    )

    ok, _ = engram.Signal.from_file(f"{d}/decisions/no-tags.md").validate()
    assert str(int(ok)) == "0"


def test_validate_signal_short_why(tmp_path):
    d = str(tmp_path / ".engram")
    engram.EngramStore(d).init()

    Path(d, "decisions", "short-why.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"test\"]\n+++\n\n"
        "# Short explanation\n\nToo short.\n"
    )

    ok, _ = engram.Signal.from_file(f"{d}/decisions/short-why.md").validate()
    assert str(int(ok)) == "0"


def test_reindex_marks_invalid(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "good.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"validation\"]\n+++\n\n"
        "# A good decision with rationale\n\n"
        "This decision includes a proper lead paragraph explaining why it was made.\n\n"
        "## Alternatives\n- None considered\n\n"
        "## Rationale\nBest option available.\n"
    )
    Path(d, "decisions", "bad.md").write_text(
        "+++\ndate = 2026-03-16\n+++\n\n# Bad decision\n\n"
    )

    store.reindex()

    status_good = _db_scalar(f"{d}/index.db", "SELECT status FROM signals WHERE slug='good'")
    assert status_good == "active"

    status_bad = _db_scalar(f"{d}/index.db", "SELECT status FROM signals WHERE slug='bad'")
    assert status_bad == "invalid"


def test_brief_excludes_invalid(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "visible.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"validation\"]\n+++\n\n"
        "# Visible decision in brief\n\n"
        "This decision has proper rationale and should appear in the brief output.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nBest option.\n"
    )
    Path(d, "decisions", "hidden.md").write_text(
        "+++\ndate = 2026-03-16\n+++\n\n# Hidden from brief\n\nShort.\n"
    )

    store.reindex()
    store.brief()

    brief = Path(d, "brief.md").read_text()
    assert "Visible decision" in str(brief)
    assert "Hidden from brief" not in str(brief)
    assert "incomplete (missing rationale)" in str(brief)


def test_ingest_bodyless_commit_invalid(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    os.makedirs(repo_dir, exist_ok=True)
    monkeypatch.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)

    Path("feature.rb").write_text("v1")
    subprocess.run(["git", "add", "feature.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add feature without body"], check=True)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()
    store.reindex()

    status_val = _db_scalar(f"{d}/index.db",
        "SELECT status FROM signals WHERE source LIKE 'git:%' LIMIT 1")
    assert str(status_val) == "invalid"

    store.brief()
    brief = Path(d, "brief.md").read_text()
    assert "add feature without body" not in str(brief)


def test_resync(tmp_path, monkeypatch):
    d = str(tmp_path / ".engram")

    empty_plans = str(tmp_path / "empty-plans")
    os.makedirs(empty_plans, exist_ok=True)
    monkeypatch.setenv("ENGRAM_PLANS_DIR", empty_plans)

    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "resync-test.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"testing\"]\n+++\n\n"
        "# Test resync pipeline\n\nVerify that engram_resync runs ingest, reindex, and brief in one call.\n\n"
        "## Alternatives\n- Manual steps\n\n## Rationale\nSingle-call convenience.\n"
    )

    store.resync()

    assert Path(d, "index.db").is_file()

    count = _db_scalar(f"{d}/index.db", "SELECT COUNT(*) FROM signals WHERE type='decision'")
    assert str(count) == "1"

    assert Path(d, "brief.md").is_file()
    brief = Path(d, "brief.md").read_text()
    assert "Test resync pipeline" in str(brief)


def test_git_tracking_config(tmp_path):
    d = str(tmp_path / ".engram")
    os.makedirs(d, exist_ok=True)

    store = engram.EngramStore(d)

    assert not store.git_tracking

    _enable_git_tracking(d)
    assert store.git_tracking

    Path(d, "config.toml").write_text("git_tracking = false\n")
    assert not store.git_tracking


def test_init_no_gitignore_by_default(tmp_path):
    d = str(tmp_path / ".engram")
    engram.EngramStore(d).init()

    assert not Path(d, ".gitignore").is_file()
    assert Path(d, "config.toml").is_file()


def test_init_gitignore_with_git_tracking(tmp_path):
    d = str(tmp_path / ".engram")
    os.makedirs(d, exist_ok=True)

    _enable_git_tracking(d)
    engram.EngramStore(d).init()

    assert Path(d, ".gitignore").is_file()
    gitignore = Path(d, ".gitignore").read_text()
    assert "index.db" in str(gitignore)
    assert "brief.md" in str(gitignore)
    assert "_private/" in str(gitignore)
    assert "config" in str(gitignore)


def test_ingest_noop_without_git_tracking(tmp_path, monkeypatch):
    repo_dir = str(tmp_path / "repo")
    _create_test_repo_mixed(repo_dir)
    monkeypatch.chdir(repo_dir)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()

    # Do NOT enable git tracking
    store.ingest_commits()

    file_count = len(list(Path(d, "decisions").glob("*.md")))
    assert str(file_count) == "0"


def test_find_incomplete(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "complete.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"architecture\"]\nlinks = [\"related:other\"]\n+++\n\n"
        "# Complete decision\n\nThis decision has proper rationale and tags for validation.\n\n"
        "## Rationale\n\nWe chose this because it was the best option.\n\n"
        "## Alternatives\n\n- Option B was considered but rejected.\n"
    )
    Path(d, "decisions", "incomplete.md").write_text(
        "+++\ndate = 2026-03-17\n+++\n\n"
        "# Incomplete decision\n\nThis decision is missing tags, rationale, and links.\n"
    )

    store.reindex()

    result = store.find_incomplete()
    assert "incomplete" in str(result)
    assert "tags" in str(result)
    assert "sections" in str(result)
    assert "links" in str(result)


def test_find_incomplete_empty(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "done.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\nlinks = [\"related:other\"]\n+++\n\n"
        "# Done decision\n\nThis decision has everything it needs and should not appear.\n\n"
        "## Alternatives\n- None considered\n\n"
        "## Rationale\n\nGood reasons.\n"
    )

    store.reindex()

    result = store.find_incomplete()
    assert result == ""


def test_find_incomplete_source_classification(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "agent-written.md").write_text(
        "+++\ndate = 2026-03-17\n+++\n\n"
        "# Agent written decision\n\nThis was written by the agent during the session.\n"
    )
    Path(d, "decisions", "auto-ingested.md").write_text(
        "+++\ndate = 2026-03-17\nsource = \"git:abc123\"\n+++\n\n"
        "# Auto ingested from commit\n\nImported from git history automatically.\n"
    )

    store.reindex()

    result = store.find_incomplete()
    assert "agent-written" in str(result)
    assert "auto-ingested" in str(result)

    # Agent-written signals should report sections as a gap
    agent_line = [l for l in result.splitlines() if "agent-written" in l][0]
    assert "sections" in str(agent_line)

    # Auto-ingested signals should NOT report sections as a gap
    auto_line = [l for l in result.splitlines() if "auto-ingested" in l][0]
    assert "sections" not in str(auto_line)

    agent_source = _db_scalar(f"{d}/index.db",
        "SELECT source FROM signals WHERE slug='agent-written'")
    assert agent_source == ""

    git_source = _db_scalar(f"{d}/index.db",
        "SELECT source FROM signals WHERE slug='auto-ingested'")
    assert "git:" in str(git_source)


def test_stop_hook_backfill_nudge(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "incomplete-stop.md").write_text(
        "+++\ndate = 2026-03-17\n+++\n\n"
        "# Incomplete for stop test\n\nShort.\n"
    )

    store.reindex()

    import time
    time.sleep(1)
    Path(d, "decisions", "incomplete-stop.md").touch()

    dispatch = str(DISPATCH)
    test_cwd = str(tmp_path)

    output = subprocess.run(
        ["bash", dispatch, "Stop"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-stop-bf-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert "backfill" in str(output)
    assert '"ok": true' in str(output)


def test_notification_backfill_nudge(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "incomplete-notif.md").write_text(
        "+++\ndate = 2026-03-17\n+++\n\n"
        "# Incomplete for notification test\n\nShort.\n"
    )

    store.reindex()

    dispatch = str(DISPATCH)
    test_cwd = str(tmp_path)

    output = subprocess.run(
        ["bash", dispatch, "Notification"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-notif-bf-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert "backfill" in str(output)


def test_status_withdrawn_indexed(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "old-feature.md").write_text(
        "+++\ndate = 2026-03-10\ntags = [\"feature\"]\nstatus = \"withdrawn\"\n+++\n\n"
        "# Add visualize skill\n\nFeature was planned but never implemented, withdrawing this decision.\n"
    )

    store.reindex()

    status_val = _db_scalar(f"{d}/index.db", "SELECT status FROM signals WHERE slug='old-feature'")
    assert status_val == "withdrawn"

    Path(d, "decisions", "active-feature.md").write_text(
        "+++\ndate = 2026-03-11\ntags = [\"feature\"]\n+++\n\n"
        "# Keep this feature active\n\nThis decision is current and should default to active status.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nActive feature.\n"
    )

    store.reindex()

    active_val = _db_scalar(f"{d}/index.db", "SELECT status FROM signals WHERE slug='active-feature'")
    assert active_val == "active"


def test_brief_hides_withdrawn(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "active-choice.md").write_text(
        "+++\ndate = 2026-03-15\ntags = [\"architecture\"]\n+++\n\n"
        "# Use PostgreSQL for storage\n\nRelational model fits our query patterns well and we need ACID.\n\n"
        "## Alternatives\n- MongoDB\n\n## Rationale\nACID compliance.\n"
    )
    Path(d, "decisions", "withdrawn-choice.md").write_text(
        "+++\ndate = 2026-03-10\ntags = [\"feature\"]\nstatus = \"withdrawn\"\n+++\n\n"
        "# Add dashboard visualization\n\nFeature was planned but never built, no longer relevant to direction.\n"
    )

    store.reindex()
    store.brief()

    brief = Path(d, "brief.md").read_text()
    assert "Use PostgreSQL" in str(brief)
    assert "dashboard visualization" not in str(brief)
    assert "1 withdrawn" in str(brief)


def test_query_relevant_excludes_withdrawn(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "active-storage.md").write_text(
        "+++\ndate = 2026-03-15\ntags = [\"storage\"]\n+++\n\n"
        "# Use S3 for file storage\n\nScalable object storage for user uploads and attachments.\n\n"
        "## Alternatives\n- Local disk\n\n## Rationale\nScalability.\n"
    )
    Path(d, "decisions", "withdrawn-storage.md").write_text(
        "+++\ndate = 2026-03-10\ntags = [\"storage\"]\nstatus = \"withdrawn\"\n+++\n\n"
        "# Use local disk for file storage\n\nWas planned but never implemented, switching to cloud storage.\n\n"
        "## Alternatives\n- S3\n\n## Rationale\nSimplicity.\n"
    )

    store.reindex()

    result = store.query_relevant("storage")
    assert "Use S3" in str(result)
    assert "local disk" not in str(result)


def test_pre_commit_gate(tmp_path):
    dispatch = str(DISPATCH)

    # No .engram directory -> allow
    no_engram_dir = str(tmp_path / "no-engram")
    Path(no_engram_dir).mkdir(parents=True, exist_ok=True)
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git commit -m \\"test\\""}}',
        capture_output=True, text=True, cwd=no_engram_dir,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # Non-commit command -> allow
    d = str(tmp_path / "gate" / ".engram")
    store = engram.EngramStore(d)
    store.init()
    store.reindex()

    test_cwd = str(tmp_path / "gate")
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git status"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # git commit with no recent decision -> nudge (not block)
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git commit -m \\"feat: add feature\\""}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert "No decision signal" in str(output)
    assert "/engram:capture" in str(output)

    # git commit --amend -> allow (bypass)
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git commit --amend -m \\"fix\\""}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # Write a decision signal, then commit -> allow
    import time
    time.sleep(0.1)  # ensure mtime is newer than index.db
    Path(d, "decisions", "new-feature.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"feature\"]\n+++\n\n"
        "# Add new feature\n\nThis feature improves the user experience significantly.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nUX improvement.\n"
    )
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git commit -m \\"feat: add feature\\""}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"


def test_pre_delete_guard(tmp_path):
    dispatch = str(DISPATCH)

    # Setup: create .engram with a signal
    d = str(tmp_path / "guard" / ".engram")
    store = engram.EngramStore(d)
    store.init()
    Path(d, "decisions", "keep-me.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n# Keep me\n\nThis should not be deleted.\n"
    )
    test_cwd = str(tmp_path / "guard")

    # rm on signal file -> block
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"rm .engram/decisions/keep-me.md"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert '"decision": "block"' in str(output)
    assert "append-only" in str(output)

    # rm -rf on .engram -> block
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"rm -rf .engram"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert '"decision": "block"' in str(output)

    # git checkout -- on signal -> block
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git checkout -- .engram/decisions/keep-me.md"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert '"decision": "block"' in str(output)

    # git restore on signal -> block
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git restore .engram/decisions/keep-me.md"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert '"decision": "block"' in str(output)

    # Non-engram rm -> allow
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"rm src/old-file.py"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # Non-destructive git command -> allow
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git status"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"


def test_pre_tool_use_edit_guard():
    dispatch = str(DISPATCH)

    # Edit that deletes content from signal -> block
    input_json = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": ".engram/decisions/test.md", "old_string": "## Rationale\n\nThis is important.", "new_string": ""}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert '"decision": "block"' in str(output)
    assert "append-only" in str(output)

    # Edit that modifies content (non-empty new_string) -> allow
    input_json = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": ".engram/decisions/test.md", "old_string": "tags = []", "new_string": "tags = [\"architecture\"]"}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # Edit on non-engram file -> allow (no old_string check)
    input_json = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/app.rb", "old_string": "old", "new_string": "new"}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"


def test_subagent_stop_context(tmp_path):
    # Setup: create .engram with brief
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()
    Path(d, "decisions", "test-decision.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Test decision for subagent\n\nSubagents should see this decision in their context.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nTest context.\n"
    )
    store.reindex()
    store.brief()

    dispatch = str(DISPATCH)
    test_cwd = str(tmp_path)

    # Use unique session ID to avoid dedup
    output = subprocess.run(
        ["bash", dispatch, "SubagentStop"],
        input="{}",
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR),
             "CLAUDE_SESSION_ID": f"test-subagent-{id(test_subagent_stop_context)}"},
    ).stdout.strip()

    parsed = json.loads(output)
    assert "Decision Context" in str(parsed.get("systemMessage", ""))
    assert "Test decision for subagent" in str(parsed.get("systemMessage", ""))
    assert "/engram:capture" in str(parsed.get("systemMessage", ""))


def test_post_push_resync(tmp_path):
    dispatch = str(DISPATCH)

    # No .engram -> pass through
    no_engram_dir = str(tmp_path / "no-engram")
    Path(no_engram_dir).mkdir(parents=True, exist_ok=True)
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}',
        capture_output=True, text=True, cwd=no_engram_dir,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # Non-push command -> pass through
    d = str(tmp_path / "push" / ".engram")
    store = engram.EngramStore(d)
    store.init()
    test_cwd = str(tmp_path / "push")

    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git status"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    assert output == "{}"

    # git push -> resync message
    Path(d, "decisions", "push-test.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Push test\n\nThis should be resynced after push.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nTest.\n"
    )
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_DIR)},
    ).stdout.strip()
    parsed = json.loads(output)
    assert "resynced" in str(parsed.get("systemMessage", ""))


# ── Timestamp tests ──────────────────────────────────────────────────

def test_timestamps_indexed(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "ts-test.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Timestamp test\n\nThis signal should have timestamps populated at index time.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nTest.\n"
    )

    store.reindex()

    created = _db_scalar(f"{d}/index.db", "SELECT created_at FROM signals WHERE slug='ts-test'")
    updated = _db_scalar(f"{d}/index.db", "SELECT updated_at FROM signals WHERE slug='ts-test'")
    assert "EMPTY" not in str(created)
    assert "EMPTY" not in str(updated)
    assert "T" in str(created)
    assert "T" in str(updated)


def test_created_at_from_frontmatter(tmp_path):
    d = str(tmp_path / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "fm-ts.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\ncreated_at = \"2026-01-15T10:30:00+00:00\"\n+++\n\n"
        "# Frontmatter timestamp\n\nThe created_at from frontmatter should take precedence.\n\n"
        "## Alternatives\n- Use mtime\n\n## Rationale\nExplicit creation date.\n"
    )

    store.reindex()

    created = _db_scalar(f"{d}/index.db", "SELECT created_at FROM signals WHERE slug='fm-ts'")
    assert "2026-01-15" in str(created)


# ── Section validation tests ────────────────────────────────────────

def test_validate_missing_sections():
    sig = engram.Signal.from_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Missing both sections\n\nThis signal has no Rationale or Alternatives sections.\n"
    )
    ok, errors = sig.validate()
    assert ok == False
    assert "## Rationale" in str(errors)
    assert "## Alternatives" in str(errors)


def test_validate_partial_sections():
    sig = engram.Signal.from_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Has Alternatives only\n\nThis signal has Alternatives but no Rationale.\n\n"
        "## Alternatives\n- Option A\n"
    )
    ok, errors = sig.validate()
    assert ok == False
    assert "## Rationale" in str(errors)
    assert "## Alternatives" not in str(errors)


# ── Compaction tests ────────────────────────────────────────────────

def test_compact_archives_old_signal(tmp_path):
    engram_dir = str(tmp_path / ".engram")
    store = engram.EngramStore(engram_dir)
    store.init()

    # Write a signal with an old date
    sig_path = Path(engram_dir) / "decisions" / "old-decision.md"
    sig_path.write_text(
        "+++\ndate = 2025-01-01\ntags = [\"test\"]\n+++\n\n"
        "# Old decision\n\nThis is old and should be archived.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nIt was old.\n"
    )

    store.reindex()

    # compact with 0-day threshold to force archival
    archived = store.compact(max_age_days=0)
    assert archived == 1
    assert sig_path.is_file() == False
    assert Path(engram_dir, "archive", "decisions", "old-decision.md").is_file()


def test_compact_keeps_recent_signal(tmp_path):
    engram_dir = str(tmp_path / ".engram")
    store = engram.EngramStore(engram_dir)
    store.init()

    from datetime import date
    today = date.today().isoformat()
    sig_path = Path(engram_dir) / "decisions" / "recent-decision.md"
    sig_path.write_text(
        f"+++\ndate = {today}\ntags = [\"test\"]\n+++\n\n"
        "# Recent decision\n\nThis is recent and should stay.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nIt is new.\n"
    )

    store.reindex()
    archived = store.compact(max_age_days=90)
    assert archived == 0
    assert sig_path.is_file()


def test_compact_keeps_pinned_signal(tmp_path):
    engram_dir = str(tmp_path / ".engram")
    store = engram.EngramStore(engram_dir)
    store.init()

    sig_path = Path(engram_dir) / "decisions" / "pinned-decision.md"
    sig_path.write_text(
        "+++\ndate = 2025-01-01\ntags = [\"test\"]\npin = true\n+++\n\n"
        "# Pinned decision\n\nThis is old but pinned so it stays.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nIt is pinned.\n"
    )

    store.reindex()
    archived = store.compact(max_age_days=0)
    assert archived == 0
    assert sig_path.is_file()


def test_compact_keeps_referenced_signal(tmp_path):
    engram_dir = str(tmp_path / ".engram")
    store = engram.EngramStore(engram_dir)
    store.init()

    # Write two old signals -- one references the other via supersedes
    old_path = Path(engram_dir) / "decisions" / "old-referenced.md"
    old_path.write_text(
        "+++\ndate = 2025-01-01\ntags = [\"test\"]\n+++\n\n"
        "# Old referenced\n\nThis is old but referenced by another signal.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nIt is referenced.\n"
    )

    newer_path = Path(engram_dir) / "decisions" / "newer-decision.md"
    newer_path.write_text(
        "+++\ndate = 2025-02-01\ntags = [\"test\"]\nsupersedes = \"old-referenced\"\n+++\n\n"
        "# Newer decision\n\nThis supersedes the old one.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nIt replaces old.\n"
    )

    store.reindex()
    archived = store.compact(max_age_days=0)
    # newer-decision gets archived (it's old, not referenced)
    # old-referenced stays (it's a target of a supersedes link)
    assert archived == 1
    assert old_path.is_file()
    assert newer_path.is_file() == False


def test_compact_brief_excludes_archived(tmp_path):
    engram_dir = str(tmp_path / ".engram")
    store = engram.EngramStore(engram_dir)
    store.init()

    from datetime import date, timedelta
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # Write a signal that will stay active (use tomorrow to survive age=0 cutoff)
    active_path = Path(engram_dir) / "decisions" / "active-decision.md"
    active_path.write_text(
        f"+++\ndate = {tomorrow}\ntags = [\"test\"]\n+++\n\n"
        "# Active decision\n\nThis stays in the brief.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nIt is active.\n"
    )

    # Write an old signal that will be archived
    old_path = Path(engram_dir) / "decisions" / "archived-decision.md"
    old_path.write_text(
        "+++\ndate = 2025-01-01\ntags = [\"test\"]\n+++\n\n"
        "# Archived decision\n\nThis should not appear in brief.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nIt is old.\n"
    )

    # Compact, then reindex and brief
    store.reindex()
    store.compact(max_age_days=0)
    store.reindex()
    store.brief()

    brief_text = Path(engram_dir, "brief.md").read_text()
    assert "Active decision" in str(brief_text)
    assert "Archived decision" not in str(brief_text)


# ── Section depth validation tests ─────────────────────────────────

def test_validate_empty_rationale_section():
    sig = engram.Signal.from_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Decision with empty rationale\n\nThis is a test decision.\n\n"
        "## Alternatives\n- Option A\n\n"
        "## Rationale\n\n"
    )
    ok, errors = sig.validate()
    assert ok == False
    assert "empty" in str(errors)


def test_validate_empty_alternatives_section():
    sig = engram.Signal.from_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Decision with empty alternatives\n\nThis is a test decision.\n\n"
        "## Alternatives\n\n"
        "## Rationale\nChosen for good reasons.\n"
    )
    ok, errors = sig.validate()
    assert ok == False
    assert "empty" in str(errors)
