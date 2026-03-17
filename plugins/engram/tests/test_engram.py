#!/usr/bin/env python3
"""engram test suite — plain Python, no external deps.

Each test function creates its own .engram/ in a temp directory.
Uses real SQLite and throwaway git repos.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

# Add parent directory to path so we can import engram
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import engram

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = SCRIPT_DIR.parent / "schemas" / "schema.sql"
TEST_DIR = Path(tempfile.mkdtemp(prefix="engram-test."))
PASS = 0
FAIL = 0

# Override schema file location
os.environ["ENGRAM_SCHEMA_FILE"] = str(SCHEMA_FILE)
os.environ["ENGRAM_PLANS_DIR"] = str(TEST_DIR / "plans")
engram.ENGRAM_SCHEMA_FILE = SCHEMA_FILE

# Save original cwd
ORIG_CWD = os.getcwd()


# ── Test helpers ────────────────────────────────────────────────────

def _pass(name):
    global PASS
    PASS += 1
    print(f"  PASS: {name}")


def _fail(name, msg):
    global FAIL
    FAIL += 1
    print(f"  FAIL: {name} — {msg}")


def assert_eq(name, actual, expected):
    if actual == expected:
        _pass(name)
    else:
        _fail(name, f"expected '{expected}', got '{actual}'")


def assert_contains(name, text, substring):
    if substring in str(text):
        _pass(name)
    else:
        _fail(name, f"output does not contain '{substring}'")


def assert_not_contains(name, text, substring):
    if substring in str(text):
        _fail(name, f"output should not contain '{substring}'")
    else:
        _pass(name)


def assert_file_exists(name, path):
    if Path(path).is_file():
        _pass(name)
    else:
        _fail(name, f"file does not exist: {path}")


def assert_dir_exists(name, path):
    if Path(path).is_dir():
        _pass(name)
    else:
        _fail(name, f"directory does not exist: {path}")


def assert_file_count(name, directory, expected):
    count = len(list(Path(directory).glob("*.md")))
    if count == expected:
        _pass(name)
    else:
        _fail(name, f"expected {expected} files, found {count}")


def _enable_git_tracking(dir_path):
    Path(dir_path, "config.toml").write_text("git_tracking = true\n")


def _create_test_repo(repo_dir, num_commits=5):
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)
    for i in range(1, num_commits + 1):
        Path(f"file{i}.txt").write_text(f"content {i}")
        subprocess.run(["git", "add", f"file{i}.txt"], check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"Commit {i}: add file{i}.txt"], check=True)


def _create_test_repo_mixed(repo_dir):
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "config", "user.name", "Test"], check=True)

    # Decision-worthy commits
    Path("Gemfile").write_text("v1")
    subprocess.run(["git", "add", "Gemfile"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add user authentication"], check=True)

    Path("app.rb").write_text("v2")
    subprocess.run(["git", "add", "app.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "refactor: extract payment service"], check=True)

    Path("schema.sql").write_text("v3")
    subprocess.run(["git", "add", "schema.sql"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "migrate users to new schema"], check=True)

    # Trivial commits
    Path("README.md").write_text("v4")
    subprocess.run(["git", "add", "README.md"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "docs: update README"], check=True)

    Path("app.rb").write_text("v5")
    subprocess.run(["git", "add", "app.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fix: handle nil email"], check=True)

    Path("test.rb").write_text("v6")
    subprocess.run(["git", "add", "test.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "test: add payment specs"], check=True)

    Path("style.css").write_text("v7")
    subprocess.run(["git", "add", "style.css"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "chore: lint fixes"], check=True)


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
    print("test_fts5_check:")
    result = engram._check_fts5()
    assert_eq("_check_fts5 succeeds", result, True)


def test_init():
    print("test_init:")
    d = str(TEST_DIR / "test-init" / ".engram")
    store = engram.EngramStore(d)
    store.init()
    assert_dir_exists("decisions dir", f"{d}/decisions")
    assert_dir_exists("_private dir", f"{d}/_private/decisions")
    assert_file_exists("index.db", f"{d}/index.db")

    # No .gitignore by default
    if not Path(d, ".gitignore").is_file():
        _pass("no gitignore by default")
    else:
        _fail("no gitignore by default", "file exists")

    # Idempotent
    store.init()
    assert_file_exists("still has index.db", f"{d}/index.db")


def test_init_private_dirs():
    print("test_init_private_dirs:")
    d = str(TEST_DIR / "test-init-private" / ".engram")
    engram.EngramStore(d).init()
    assert_dir_exists("_private dir", f"{d}/_private/decisions")


def test_write_decision():
    print("test_write_decision:")
    d = str(TEST_DIR / "test-write-decision" / ".engram")
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
    assert_contains("decision indexed", result_str, "Use Redis for caching")
    assert_contains("date correct", result_str, "2026-03-14")
    assert_contains("type correct", result_str, "decision")


def test_is_decision_commit():
    print("test_is_decision_commit:")
    repo_dir = str(TEST_DIR / "test-classify-repo")
    _create_test_repo_mixed(repo_dir)

    result = subprocess.run(["git", "log", "--format=%H|%s", "--reverse"],
                            capture_output=True, text=True)
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        h, subject = line.split("|", 1)
        is_decision = engram._is_decision_commit(subject, h)
        label = "decision" if is_decision else "skip"

        if subject == "feat: add user authentication":
            assert_eq("feat prefix → decision", label, "decision")
        elif subject == "refactor: extract payment service":
            assert_eq("refactor prefix → decision", label, "decision")
        elif subject == "migrate users to new schema":
            assert_eq("migrate keyword → decision", label, "decision")
        elif subject == "docs: update README":
            assert_eq("docs prefix → skip", label, "skip")
        elif subject == "fix: handle nil email":
            assert_eq("fix prefix → skip", label, "skip")
        elif subject == "test: add payment specs":
            assert_eq("test prefix → skip", label, "skip")
        elif subject == "chore: lint fixes":
            assert_eq("chore prefix → skip", label, "skip")

    os.chdir(ORIG_CWD)


def test_ingest_commits():
    print("test_ingest_commits:")
    repo_dir = str(TEST_DIR / "test-ingest-repo")
    _create_test_repo_mixed(repo_dir)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()

    file_count = len(list(Path(d, "decisions").glob("*.md")))
    assert_eq("3 decisions from 7 commits", str(file_count), "3")

    # Verify files have source = "git:<hash>"
    has_source = sum(
        1 for f in Path(d, "decisions").glob("*.md")
        if "git:" in f.read_text()
    )
    assert_eq("all have git source", str(has_source), "3")

    os.chdir(ORIG_CWD)


def test_ingest_commits_body():
    print("test_ingest_commits_body:")
    repo_dir = str(TEST_DIR / "test-ingest-body-repo")
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
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
    assert_eq("2 decisions created", str(file_count), "2")

    # Find OAuth2 file
    oauth_file = None
    for f in Path(d, "decisions").glob("*.md"):
        if "OAuth2" in f.read_text():
            oauth_file = f
            break
    content = oauth_file.read_text() if oauth_file else ""
    assert_contains("body included in signal", content, "token-based auth")
    assert_not_contains("Co-Authored-By stripped", content, "Co-Authored-By")

    # Find API gateway file
    api_file = None
    for f in Path(d, "decisions").glob("*.md"):
        if "API gateway" in f.read_text():
            api_file = f
            break
    api_content = api_file.read_text() if api_file else ""
    assert_contains("no-body signal has stat", api_content, "api.rb")

    os.chdir(ORIG_CWD)


def test_ingest_dedup():
    print("test_ingest_dedup:")
    repo_dir = str(TEST_DIR / "test-dedup-repo")
    _create_test_repo_mixed(repo_dir)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)

    store.ingest_commits()
    first_count = len(list(Path(d, "decisions").glob("*.md")))

    store.ingest_commits()
    second_count = len(list(Path(d, "decisions").glob("*.md")))

    assert_eq("no duplicates after second ingest", str(first_count), str(second_count))

    os.chdir(ORIG_CWD)


def test_ingest_manual_signal_suppresses():
    print("test_ingest_manual_signal_suppresses:")
    repo_dir = str(TEST_DIR / "test-manual-suppress-repo")
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
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
    assert_eq("manual signal suppresses auto-ingest", str(file_count), "1")

    assert_not_contains("manual signal preserved",
                        Path(d, "decisions", "feat-add-widget.md").read_text(),
                        "source")

    os.chdir(ORIG_CWD)


def test_ingest_private_signal_suppresses():
    print("test_ingest_private_signal_suppresses:")
    repo_dir = str(TEST_DIR / "test-private-suppress-repo")
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
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
    assert_eq("private signal suppresses auto-ingest", str(public_count), "0")

    os.chdir(ORIG_CWD)


def test_ingest_no_manual_still_creates():
    print("test_ingest_no_manual_still_creates:")
    repo_dir = str(TEST_DIR / "test-no-manual-repo")
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
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
    assert_eq("auto-ingest creates signal when no manual", str(file_count), "1")

    content = list(Path(d, "decisions").glob("feat-add-api-gateway*"))[0].read_text()
    assert_contains("auto-ingest has git source", content, 'source = "git:')

    os.chdir(ORIG_CWD)


def test_ingest_brownfield():
    print("test_ingest_brownfield:")
    repo_dir = str(TEST_DIR / "test-brownfield-repo")
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
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
    assert_eq("brownfield: only decisions from last 50", str(file_count), "40")

    os.chdir(ORIG_CWD)


def test_ingest_plans():
    print("test_ingest_plans:")
    repo_dir = str(TEST_DIR / "test-plans-repo")
    _create_test_repo(repo_dir, 1)

    d = f"{repo_dir}/.engram"
    plans_dir = os.environ["ENGRAM_PLANS_DIR"]
    os.makedirs(plans_dir, exist_ok=True)

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
    assert_eq("plan ingested", str(plan_files), "1")

    content = ""
    for f in Path(d, "decisions").glob("plan*auth*"):
        content = f.read_text()
    assert_contains("plan has context content", content, "JWT")

    os.chdir(ORIG_CWD)


def test_reindex():
    print("test_reindex:")
    d = str(TEST_DIR / "test-reindex" / ".engram")
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
    assert_eq("2 signals indexed", str(count), "2")

    # Delete and recreate
    Path(d, "index.db").unlink()
    store.reindex()
    count = _db_scalar(f"{d}/index.db", "SELECT COUNT(*) FROM signals")
    assert_eq("2 signals after reindex", str(count), "2")


def test_brief():
    print("test_brief:")
    d = str(TEST_DIR / "test-brief" / ".engram")
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

    assert_file_exists("brief.md created", f"{d}/brief.md")
    brief = Path(d, "brief.md").read_text()
    assert_contains("brief has decisions header", brief, "Recent Decisions")
    assert_contains("brief has decision title", brief, "Pick Redis")
    assert_contains("brief has counts", brief, "1 decisions")


def test_fts_search():
    print("test_fts_search:")
    d = str(TEST_DIR / "test-fts" / ".engram")
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
    assert_contains("FTS finds PostgreSQL", str(result), "PostgreSQL")

    result = _db_query(db,
        "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid "
        "WHERE signals_fts MATCH 'triggers' ORDER BY rank LIMIT 10")
    assert_contains("FTS finds triggers", str(result), "FTS5")

    result = _db_query(db,
        "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid "
        "WHERE signals_fts MATCH 'nonexistent_xyz_12345' ORDER BY rank LIMIT 10")
    assert_eq("no results for nonexistent", str(result), "[]")


def test_frontmatter_parsing():
    print("test_frontmatter_parsing:")
    d = str(TEST_DIR / "test-frontmatter" / ".engram")
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
    assert_eq("all 3 files indexed", str(count), "3")

    tags = _db_scalar(f"{d}/index.db", "SELECT tags FROM signals WHERE title='Partial frontmatter'")
    assert_eq("default tags is []", tags, "[]")

    source = _db_scalar(f"{d}/index.db", "SELECT source FROM signals WHERE title='Partial frontmatter'")
    assert_eq("default source is empty", source, "")


def test_meta_preserved():
    print("test_meta_preserved:")
    repo_dir = str(TEST_DIR / "test-meta-repo")
    _create_test_repo(repo_dir, 3)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)
    store.ingest_commits()

    last_commit = _db_scalar(f"{d}/index.db", "SELECT value FROM meta WHERE key='last_commit'")
    assert_not_contains("last_commit is not empty", "EMPTY", str(last_commit))

    store.reindex()
    after_reindex = _db_scalar(f"{d}/index.db", "SELECT value FROM meta WHERE key='last_commit'")
    assert_eq("meta preserved after reindex", after_reindex, last_commit)

    os.chdir(ORIG_CWD)


def test_incremental_ingest():
    print("test_incremental_ingest:")
    repo_dir = str(TEST_DIR / "test-incremental-repo")
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
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
    assert_eq("3 initial commits", str(first_count), "3")

    Path("feat4.rb").write_text("v4")
    subprocess.run(["git", "add", "feat4.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: add feature 4"], check=True)

    Path("feat5.rb").write_text("v5")
    subprocess.run(["git", "add", "feat5.rb"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "refactor: extract shared module"], check=True)

    store.ingest_commits()
    second_count = len(list(Path(d, "decisions").glob("*.md")))
    assert_eq("5 after incremental", str(second_count), "5")

    os.chdir(ORIG_CWD)


def test_file_column():
    print("test_file_column:")
    d = str(TEST_DIR / "test-file-col" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "test-file.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n# Test file column\n\nContent.\n"
    )

    store.reindex()

    file_val = _db_scalar(f"{d}/index.db", "SELECT file FROM signals LIMIT 1")
    assert_contains("file column has path", file_val, "decisions/test-file.md")


def test_private_signal_indexed():
    print("test_private_signal_indexed:")
    d = str(TEST_DIR / "test-private-indexed" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "_private", "decisions", "secret-deal.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"crm\", \"deals\"]\n+++\n\n"
        "# Secret deal with Acme Corp\n\nConfidential terms discussion.\n"
    )

    store.reindex()

    private_val = _db_scalar(f"{d}/index.db",
        "SELECT private FROM signals WHERE title='Secret deal with Acme Corp'")
    assert_eq("private signal has private=1", str(private_val), "1")


def test_brief_excludes_private():
    print("test_brief_excludes_private:")
    d = str(TEST_DIR / "test-brief-private" / ".engram")
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
    assert_contains("brief has public title", brief, "Public architecture choice")
    assert_not_contains("brief excludes private title", brief, "Private deal terms")
    assert_contains("brief shows private count", brief, "1 private signal(s)")


def test_private_queryable():
    print("test_private_queryable:")
    d = str(TEST_DIR / "test-private-query" / ".engram")
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
    assert_contains("FTS finds private signal", str(result), "Competitor launched new product")


def test_public_signals_unchanged():
    print("test_public_signals_unchanged:")
    d = str(TEST_DIR / "test-public-unchanged" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "normal.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Normal public decision\n\nStandard decision content.\n"
    )

    store.reindex()

    private_val = _db_scalar(f"{d}/index.db",
        "SELECT private FROM signals WHERE title='Normal public decision'")
    assert_eq("public signal has private=0", str(private_val), "0")


def test_uncommitted_summary():
    print("test_uncommitted_summary:")
    repo_dir = str(TEST_DIR / "test-uncommitted-repo")
    _create_test_repo(repo_dir, 1)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()
    _enable_git_tracking(d)

    Path(d, "decisions", "test-uncommitted.md").write_text(
        "+++\ndate = 2026-03-16\n+++\n\n"
        "# Test uncommitted signal\n\nSome content.\n"
    )

    os.chdir(repo_dir)
    result = store.uncommitted_summary()
    assert_contains("reports uncommitted count", result, "1 uncommitted signal")

    subprocess.run(["git", "add", ".engram/"], check=True)
    subprocess.run(["git", "commit", "-q", "-m", "engram: add signal"], check=True)

    result = store.uncommitted_summary()
    assert_eq("no output after commit", result, "")

    os.chdir(ORIG_CWD)


def test_uncommitted_summary_no_git():
    print("test_uncommitted_summary_no_git:")
    d = str(TEST_DIR / "test-uncommitted-nogit" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "no-git.md").write_text(
        "+++\ndate = 2026-03-16\n+++\n\n# No git repo\n\nContent.\n"
    )

    result = store.uncommitted_summary()
    assert_eq("no output outside git", result, "")


def test_session_end_output():
    print("test_session_end_output:")
    repo_dir = str(TEST_DIR / "test-session-end-repo")
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
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

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")
    empty_plans = str(TEST_DIR / "empty-plans-for-session-end")
    os.makedirs(empty_plans, exist_ok=True)

    output = subprocess.run(
        ["bash", dispatch, "SessionEnd"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "ENGRAM_PLANS_DIR": empty_plans},
        cwd=repo_dir,
    ).stdout.strip()
    assert_eq("empty JSON when no signals", output, "{}")

    Path(d, "decisions", "test-end.md").write_text(
        "+++\ndate = 2026-03-16\n+++\n\n# Test session end\n\nContent.\n"
    )

    output = subprocess.run(
        ["bash", dispatch, "SessionEnd"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "ENGRAM_PLANS_DIR": empty_plans},
        cwd=repo_dir,
    ).stdout.strip()
    assert_eq("empty JSON with uncommitted", output, "{}")

    os.chdir(ORIG_CWD)


def test_supersedes_frontmatter():
    print("test_supersedes_frontmatter:")
    d = str(TEST_DIR / "test-supersedes" / ".engram")
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
    assert_eq("supersedes link in links table", str(link_count), "1")


def test_links_frontmatter():
    print("test_links_frontmatter:")
    d = str(TEST_DIR / "test-links-fm" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "use-redis.md").write_text(
        "+++\ndate = 2026-03-14\nlinks = [\"related:fts5-perf\", \"related:ci-timeout\"]\n+++\n\n"
        "# Use Redis for caching\n\nAlready in our stack.\n"
    )

    store.reindex()

    related_count = _db_scalar(f"{d}/index.db",
        "SELECT COUNT(*) FROM links WHERE source_file='use-redis' AND target_file='fts5-perf' AND rel_type='related'")
    assert_eq("related link exists", str(related_count), "1")

    total_links = _db_scalar(f"{d}/index.db",
        "SELECT COUNT(*) FROM links WHERE source_file='use-redis'")
    assert_eq("2 links total", str(total_links), "2")


def test_excerpt_extraction():
    print("test_excerpt_extraction:")
    d = str(TEST_DIR / "test-excerpt" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "test-excerpt.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Pick PostgreSQL\n\nBetter JSON support and window functions.\n\n"
        "## Alternatives\nMySQL was considered.\n"
    )

    store.reindex()

    excerpt = _db_scalar(f"{d}/index.db", "SELECT excerpt FROM signals WHERE slug='test-excerpt'")
    assert_contains("excerpt has first body line", excerpt, "Better JSON support")


def test_slug_column():
    print("test_slug_column:")
    d = str(TEST_DIR / "test-slug" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "use-redis.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n# Use Redis\n\nContent.\n"
    )

    store.reindex()

    slug_val = _db_scalar(f"{d}/index.db", "SELECT slug FROM signals LIMIT 1")
    assert_eq("slug is basename without .md", slug_val, "use-redis")


def test_brief_hides_superseded():
    print("test_brief_hides_superseded:")
    d = str(TEST_DIR / "test-brief-superseded" / ".engram")
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
    assert_contains("brief shows new decision", brief, "Use Redis for caching")
    assert_not_contains("brief hides superseded decision", brief, "Use Memcached")
    assert_contains("brief shows superseded count", brief, "1 superseded")


def test_brief_tag_grouping():
    print("test_brief_tag_grouping:")
    d = str(TEST_DIR / "test-brief-tags" / ".engram")
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
    assert_contains("brief has tag headers", brief, "###")


def test_brief_max_lines():
    print("test_brief_max_lines:")
    d = str(TEST_DIR / "test-brief-max-lines" / ".engram")
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
    assert_contains("brief has truncation note", brief, "truncated to 10 lines")
    assert_contains("brief has header", brief, "Decision Context")


def test_brief_excerpts():
    print("test_brief_excerpts:")
    d = str(TEST_DIR / "test-brief-excerpts" / ".engram")
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
    assert_contains("brief has excerpt", brief, "Already in our stack")


def test_supersession_chain():
    print("test_supersession_chain:")
    d = str(TEST_DIR / "test-chain" / ".engram")
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
    assert_contains("chain includes v3", chain_str, "Auth v3")
    assert_contains("chain includes v2", chain_str, "Auth v2")
    assert_contains("chain includes v1", chain_str, "Auth v1")


def test_links_bidirectional():
    print("test_links_bidirectional:")
    d = str(TEST_DIR / "test-links-bidi" / ".engram")
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
    assert_eq("link findable from target side", from_target, "use-redis")

    from_decision = _db_scalar(f"{d}/index.db",
        "SELECT target_file FROM links WHERE source_file='use-redis'")
    assert_eq("link findable from source side", from_decision, "redis-perf")


def test_path_to_keywords():
    print("test_path_to_keywords:")

    result = engram.engram_path_to_keywords("src/auth/oauth-handler.ts")
    assert_contains("has auth", result, "auth")
    assert_contains("has oauth", result, "oauth")
    assert_contains("has handler", result, "handler")
    # "src" is a noise word
    words = result.split()
    if "src" not in words:
        _pass("strips src")
    else:
        _fail("strips src", "still contains src")
    if "ts" not in words:
        _pass("strips ts extension")
    else:
        _fail("strips ts extension", "still contains ts")

    result = engram.engram_path_to_keywords("lib/index.js")
    words = result.split()
    if "lib" not in words:
        _pass("strips lib")
    else:
        _fail("strips lib", "still contains lib")
    if "index" not in words:
        _pass("strips index")
    else:
        _fail("strips index", "still contains index")

    result = engram.engram_path_to_keywords("app/models/payment_processor.rb")
    assert_contains("has models", result, "models")
    assert_contains("has payment", result, "payment")
    assert_contains("has processor", result, "processor")

    result = engram.engram_path_to_keywords("")
    assert_eq("empty path returns empty", result, "")


def test_query_relevant():
    print("test_query_relevant:")
    d = str(TEST_DIR / "test-query-relevant" / ".engram")
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
    assert_contains("finds redis decision", result, "Use Redis")
    assert_not_contains("excludes private", result, "Secret")

    result = store.query_relevant("nonexistent_xyz_12345")
    assert_eq("no results for nonexistent", result, "")

    result = store.query_relevant("")
    assert_eq("empty terms returns empty", result, "")

    result = store.query_relevant("auth redis caching", limit=1)
    line_count = len([l for l in result.splitlines() if l.startswith("-")])
    if line_count <= 1:
        _pass("limit respected")
    else:
        _fail("limit respected", f"expected <= 1 result, got {line_count}")


def test_query_relevant_excludes_superseded():
    print("test_query_relevant_excludes_superseded:")
    d = str(TEST_DIR / "test-query-superseded" / ".engram")
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
    assert_contains("shows current decision", result, "Use Redis")
    assert_not_contains("hides superseded", result, "Memcached")


def test_tag_summary():
    print("test_tag_summary:")
    d = str(TEST_DIR / "test-tag-summary" / ".engram")
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
    assert_contains("has architecture tag", result, "architecture")
    assert_contains("has count", result, "(3)")
    assert_contains("has Top topics prefix", result, "Top topics")


def test_tag_summary_few_signals():
    print("test_tag_summary_few_signals:")
    d = str(TEST_DIR / "test-tag-few" / ".engram")
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
    assert_eq("empty when < 5 signals", result, "")


def test_post_tool_context_output():
    print("test_post_tool_context_output:")
    d = str(TEST_DIR / "test-post-tool" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "auth-handler.md").write_text(
        "+++\ndate = 2026-03-14\n+++\n\n"
        "# Use OAuth for auth handler\n\nToken-based authentication.\n"
    )

    store.reindex()

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")
    test_cwd = str(TEST_DIR / "test-post-tool")

    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Write","tool_input":{"file_path":"src/auth/handler.ts"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()

    try:
        json.loads(output)
        _pass("post-tool output is valid JSON")
    except (json.JSONDecodeError, ValueError):
        _fail("post-tool output is valid JSON", f"got: {output}")

    if "systemMessage" in output:
        _pass("post-tool has systemMessage when results exist")
    else:
        _pass("post-tool returns valid JSON (no matches)")

    # Skip .engram paths
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Write","tool_input":{"file_path":".engram/decisions/foo.md"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-ptu-skip-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert_eq("skips .engram paths", output, "{}")

    # Skip test files
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Write","tool_input":{"file_path":"tests/test_auth.rb"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-ptu-skip2-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert_eq("skips test files", output, "{}")


def test_pre_compact_output():
    print("test_pre_compact_output:")
    d = str(TEST_DIR / "test-pre-compact" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "compact-test.md").write_text(
        "+++\ndate = 2026-03-14\ntags = [\"testing\"]\n+++\n\n"
        "# Compact test decision\n\nTesting pre-compact hook with valid signal to verify context injection.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nTest coverage.\n"
    )

    store.reindex()
    store.brief()

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")
    test_cwd = str(TEST_DIR / "test-pre-compact")

    output = subprocess.run(
        ["bash", dispatch, "PreCompact"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
        cwd=test_cwd,
    ).stdout.strip()

    try:
        json.loads(output)
        _pass("pre-compact output is valid JSON")
    except (json.JSONDecodeError, ValueError):
        _fail("pre-compact output is valid JSON", f"got: {output}")

    assert_contains("pre-compact has systemMessage", output, "systemMessage")
    assert_contains("pre-compact has decision context", output, "Compact test decision")


def test_stop_hook_output():
    print("test_stop_hook_output:")
    d = str(TEST_DIR / "test-stop-hook" / ".engram")
    engram.EngramStore(d).init()

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")
    test_cwd = str(TEST_DIR / "test-stop-hook")

    output = subprocess.run(
        ["bash", dispatch, "Stop"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-stop-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()

    try:
        json.loads(output)
        _pass("stop hook output is valid JSON")
    except (json.JSONDecodeError, ValueError):
        _fail("stop hook output is valid JSON", f"got: {output}")

    assert_contains("stop hook is advisory", output, '"ok": true')


def test_stop_hook_no_engram():
    print("test_stop_hook_no_engram:")
    empty_dir = str(TEST_DIR / "test-stop-empty")
    os.makedirs(empty_dir, exist_ok=True)

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")

    output = subprocess.run(
        ["bash", dispatch, "Stop"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-stop-empty-{os.getpid()}"},
        cwd=empty_dir,
    ).stdout.strip()
    assert_eq("ok when no .engram", output, '{"ok": true}')


def test_user_prompt_submit_hook():
    print("test_user_prompt_submit_hook:")
    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")

    output = subprocess.run(
        ["bash", dispatch, "UserPromptSubmit"],
        input='{"tool_input":{"content":"fix the bug in auth.rb"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-ups-{os.getpid()}"},
    ).stdout.strip()
    assert_eq("no nudge for normal prompt", output, "{}")

    output = subprocess.run(
        ["bash", dispatch, "UserPromptSubmit"],
        input='{"tool_input":{"content":"lets go with Redis for caching"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-ups-decision-{os.getpid()}"},
    ).stdout.strip()
    assert_contains("nudge for decision language", output, "engram:capture")

    output = subprocess.run(
        ["bash", dispatch, "UserPromptSubmit"],
        input='{"tool_input":{"content":"why did we choose Redis?"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-ups-query-{os.getpid()}"},
    ).stdout.strip()
    assert_contains("suggest query for past decisions", output, "engram:query")


def test_pre_tool_use_validation():
    print("test_pre_tool_use_validation:")
    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")

    # Non-engram file
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Write","tool_input":{"file_path":"src/app.rb","content":"hello"}}',
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("non-engram file passes", output, "{}")

    # Valid signal
    valid_content = "+++\ndate = 2026-03-17\ntags = [\"architecture\"]\n+++\n\n# Valid decision\n\nThis is a valid lead paragraph with enough chars.\n\n## Alternatives\n- None\n\n## Rationale\nValid."
    input_json = json.dumps({"tool_name": "Write", "tool_input": {"file_path": ".engram/decisions/valid.md", "content": valid_content}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("valid signal passes", output, "{}")

    # Missing tags
    no_tags_content = "+++\ndate = 2026-03-17\ntags = []\n+++\n\n# No tags\n\nThis decision has empty tags which should fail."
    input_json = json.dumps({"tool_name": "Write", "tool_input": {"file_path": ".engram/decisions/no-tags.md", "content": no_tags_content}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_contains("empty tags blocked", output, '"ok": false')
    assert_contains("tags error message", output, "tags")

    # Missing frontmatter
    no_fm_content = "# No frontmatter\n\nJust a plain file."
    input_json = json.dumps({"tool_name": "Write", "tool_input": {"file_path": ".engram/decisions/no-fm.md", "content": no_fm_content}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_contains("missing frontmatter blocked", output, '"ok": false')


def test_notification_hook():
    print("test_notification_hook:")
    d = str(TEST_DIR / "test-notification" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "incomplete.md").write_text(
        "+++\ndate = 2026-03-17\n+++\n\n# Incomplete\n\nShort.\n"
    )

    store.reindex()

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")
    test_cwd = str(TEST_DIR / "test-notification")

    output = subprocess.run(
        ["bash", dispatch, "Notification"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-notif-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert_contains("notification suggests enrichment", output, "incomplete")

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
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-notif-clean-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert_eq("no nudge when all complete", output, "{}")


def test_pre_compact_no_engram():
    print("test_pre_compact_no_engram:")
    empty_dir = str(TEST_DIR / "test-pre-compact-empty")
    os.makedirs(empty_dir, exist_ok=True)

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")

    output = subprocess.run(
        ["bash", dispatch, "PreCompact"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
        cwd=empty_dir,
    ).stdout.strip()
    assert_eq("empty JSON when no .engram", output, "{}")


def test_hooks_json_structure():
    print("--- test_hooks_json_structure ---")
    hooks_file = SCRIPT_DIR.parent / "hooks" / "hooks.json"

    try:
        data = json.loads(hooks_file.read_text())
        _pass("hooks.json is valid JSON")
    except (json.JSONDecodeError, ValueError):
        _fail("hooks.json is not valid JSON", "")
        return

    expected_events = ["SessionStart", "SessionEnd", "Stop", "PostToolUse", "PreToolUse",
                       "SubagentStop", "PreCompact", "UserPromptSubmit", "Notification"]
    for event in expected_events:
        hooks = data.get("hooks", {}).get(event, [])
        if len(hooks) >= 1:
            _pass(f"hooks.json has event: {event}")
        else:
            _fail(f"hooks.json missing event: {event}", "")

    # All hooks must be command hooks
    prompt_count = 0
    for event_hooks in data.get("hooks", {}).values():
        for entry in event_hooks:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "prompt":
                    prompt_count += 1
    assert_eq("no prompt hooks (all commands)", str(prompt_count), "0")

    # No empty commands
    empty_commands = 0
    for event_hooks in data.get("hooks", {}).values():
        for entry in event_hooks:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command" and not hook.get("command"):
                    empty_commands += 1
    assert_eq("no empty commands", str(empty_commands), "0")

    # PreToolUse matcher
    pre_matcher = data["hooks"]["PreToolUse"][0].get("matcher", "")
    assert_contains("PreToolUse matcher has Write", pre_matcher, "Write")
    assert_contains("PreToolUse matcher has Edit", pre_matcher, "Edit")

    # PostToolUse matcher
    post_matcher = data["hooks"]["PostToolUse"][0].get("matcher", "")
    assert_contains("PostToolUse matcher has Write", post_matcher, "Write")
    assert_contains("PostToolUse matcher has Edit", post_matcher, "Edit")
    assert_contains("PostToolUse matcher has MultiEdit", post_matcher, "MultiEdit")

    # All command hooks reference dispatch.sh
    all_commands = []
    for event_hooks in data.get("hooks", {}).values():
        for entry in event_hooks:
            for hook in entry.get("hooks", []):
                if hook.get("type") == "command":
                    all_commands.append(hook.get("command", ""))
    total = len(all_commands)
    dispatch_count = sum(1 for c in all_commands if "dispatch.sh" in c)
    assert_eq("all commands use dispatch.sh", str(dispatch_count), str(total))


def test_validate_signal_valid():
    print("test_validate_signal_valid:")
    d = str(TEST_DIR / "test-validate-valid" / ".engram")
    engram.EngramStore(d).init()

    Path(d, "decisions", "valid-test.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"architecture\", \"validation\"]\n+++\n\n"
        "# Use strict validation for signals\n\n"
        "Enforce structure at write time to ensure all decisions include rationale, improving brief quality.\n\n"
        "## Alternatives\n- No validation — too many incomplete signals\n\n"
        "## Rationale\nEnsures all decisions include the why.\n"
    )

    ok, _ = engram.Signal.from_file(f"{d}/decisions/valid-test.md").validate()
    assert_eq("valid signal passes", str(int(ok)), "1")


def test_validate_signal_missing_why():
    print("test_validate_signal_missing_why:")
    d = str(TEST_DIR / "test-validate-no-why" / ".engram")
    engram.EngramStore(d).init()

    Path(d, "decisions", "no-why.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"test\"]\n+++\n\n"
        "# Decision without explanation\n\n"
    )

    ok, _ = engram.Signal.from_file(f"{d}/decisions/no-why.md").validate()
    assert_eq("missing lead paragraph fails", str(int(ok)), "0")


def test_validate_signal_missing_tags():
    print("test_validate_signal_missing_tags:")
    d = str(TEST_DIR / "test-validate-no-tags" / ".engram")
    engram.EngramStore(d).init()

    Path(d, "decisions", "no-tags.md").write_text(
        "+++\ndate = 2026-03-16\ntags = []\n+++\n\n"
        "# Decision without tags\n\nThis decision has no tags which should fail validation checks.\n"
    )

    ok, _ = engram.Signal.from_file(f"{d}/decisions/no-tags.md").validate()
    assert_eq("empty tags fails", str(int(ok)), "0")


def test_validate_signal_short_why():
    print("test_validate_signal_short_why:")
    d = str(TEST_DIR / "test-validate-short" / ".engram")
    engram.EngramStore(d).init()

    Path(d, "decisions", "short-why.md").write_text(
        "+++\ndate = 2026-03-16\ntags = [\"test\"]\n+++\n\n"
        "# Short explanation\n\nToo short.\n"
    )

    ok, _ = engram.Signal.from_file(f"{d}/decisions/short-why.md").validate()
    assert_eq("short lead paragraph fails", str(int(ok)), "0")


def test_reindex_marks_invalid():
    print("test_reindex_marks_invalid:")
    d = str(TEST_DIR / "test-reindex-valid" / ".engram")
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
    assert_eq("good signal is active", status_good, "active")

    status_bad = _db_scalar(f"{d}/index.db", "SELECT status FROM signals WHERE slug='bad'")
    assert_eq("bad signal is invalid", status_bad, "invalid")


def test_brief_excludes_invalid():
    print("test_brief_excludes_invalid:")
    d = str(TEST_DIR / "test-brief-invalid" / ".engram")
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
    assert_contains("brief shows valid signal", brief, "Visible decision")
    assert_not_contains("brief hides invalid signal", brief, "Hidden from brief")
    assert_contains("brief shows incomplete count", brief, "incomplete (missing rationale)")


def test_ingest_bodyless_commit_invalid():
    print("test_ingest_bodyless_commit_invalid:")
    repo_dir = str(TEST_DIR / "test-ingest-bodyless-repo")
    os.makedirs(repo_dir, exist_ok=True)
    os.chdir(repo_dir)
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
    assert_eq("bodyless commit is invalid", str(status_val), "invalid")

    store.brief()
    brief = Path(d, "brief.md").read_text()
    assert_not_contains("brief excludes bodyless commit", brief, "add feature without body")

    os.chdir(ORIG_CWD)


def test_resync():
    print("test_resync:")
    d = str(TEST_DIR / "test-resync" / ".engram")

    saved_plans = os.environ.get("ENGRAM_PLANS_DIR", "")
    empty_plans = str(TEST_DIR / "test-resync" / "empty-plans")
    os.makedirs(empty_plans, exist_ok=True)
    os.environ["ENGRAM_PLANS_DIR"] = empty_plans

    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "resync-test.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"testing\"]\n+++\n\n"
        "# Test resync pipeline\n\nVerify that engram_resync runs ingest, reindex, and brief in one call.\n\n"
        "## Alternatives\n- Manual steps\n\n## Rationale\nSingle-call convenience.\n"
    )

    store.resync()

    assert_file_exists("index.db exists after resync", f"{d}/index.db")

    count = _db_scalar(f"{d}/index.db", "SELECT COUNT(*) FROM signals WHERE type='decision'")
    assert_eq("signal indexed after resync", str(count), "1")

    assert_file_exists("brief.md exists after resync", f"{d}/brief.md")
    brief = Path(d, "brief.md").read_text()
    assert_contains("brief has decision", brief, "Test resync pipeline")

    os.environ["ENGRAM_PLANS_DIR"] = saved_plans


def test_git_tracking_config():
    print("test_git_tracking_config:")
    d = str(TEST_DIR / "test-git-config" / ".engram")
    os.makedirs(d, exist_ok=True)

    store = engram.EngramStore(d)

    if not store.git_tracking:
        _pass("disabled by default")
    else:
        _fail("disabled by default", "returned true")

    _enable_git_tracking(d)
    if store.git_tracking:
        _pass("enabled after config")
    else:
        _fail("enabled after config", "returned false")

    Path(d, "config.toml").write_text("git_tracking = false\n")
    if not store.git_tracking:
        _pass("false value not enabled")
    else:
        _fail("false value not enabled", "returned true")


def test_init_no_gitignore_by_default():
    print("test_init_no_gitignore_by_default:")
    d = str(TEST_DIR / "test-no-gitignore" / ".engram")
    engram.EngramStore(d).init()

    if not Path(d, ".gitignore").is_file():
        _pass("no gitignore created")
    else:
        _fail("no gitignore created", "file exists")

    if Path(d, "config.toml").is_file():
        _pass("config.toml created")
    else:
        _fail("config.toml created", "file missing")


def test_init_gitignore_with_git_tracking():
    print("test_init_gitignore_with_git_tracking:")
    d = str(TEST_DIR / "test-gitignore-enabled" / ".engram")
    os.makedirs(d, exist_ok=True)

    _enable_git_tracking(d)
    engram.EngramStore(d).init()

    assert_file_exists("gitignore created", f"{d}/.gitignore")
    gitignore = Path(d, ".gitignore").read_text()
    assert_contains("gitignore has index.db", gitignore, "index.db")
    assert_contains("gitignore has brief.md", gitignore, "brief.md")
    assert_contains("gitignore has _private/", gitignore, "_private/")
    assert_contains("gitignore has config", gitignore, "config")


def test_ingest_noop_without_git_tracking():
    print("test_ingest_noop_without_git_tracking:")
    repo_dir = str(TEST_DIR / "test-ingest-noop-repo")
    _create_test_repo_mixed(repo_dir)

    d = f"{repo_dir}/.engram"
    store = engram.EngramStore(d)
    store.init()

    # Do NOT enable git tracking
    store.ingest_commits()

    file_count = len(list(Path(d, "decisions").glob("*.md")))
    assert_eq("no signals without git tracking", str(file_count), "0")

    os.chdir(ORIG_CWD)


def test_find_incomplete():
    print("test_find_incomplete:")
    d = str(TEST_DIR / "test-find-incomplete" / ".engram")
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
    assert_contains("finds incomplete signal", result, "incomplete")
    assert_contains("reports tags gap", result, "tags")
    assert_contains("reports sections gap", result, "sections")
    assert_contains("reports links gap", result, "links")


def test_find_incomplete_empty():
    print("test_find_incomplete_empty:")
    d = str(TEST_DIR / "test-find-inc-empty" / ".engram")
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
    assert_eq("no incomplete signals", result, "")


def test_find_incomplete_source_classification():
    print("test_find_incomplete_source_classification:")
    d = str(TEST_DIR / "test-find-inc-source" / ".engram")
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
    assert_contains("finds agent-written", result, "agent-written")
    assert_contains("finds auto-ingested", result, "auto-ingested")

    # Agent-written signals should report sections as a gap
    agent_line = [l for l in result.splitlines() if "agent-written" in l][0]
    assert_contains("agent-written has sections gap", agent_line, "sections")

    # Auto-ingested signals should NOT report sections as a gap
    auto_line = [l for l in result.splitlines() if "auto-ingested" in l][0]
    assert_not_contains("auto-ingested skips sections gap", auto_line, "sections")

    agent_source = _db_scalar(f"{d}/index.db",
        "SELECT source FROM signals WHERE slug='agent-written'")
    assert_eq("agent-written has empty source", agent_source, "")

    git_source = _db_scalar(f"{d}/index.db",
        "SELECT source FROM signals WHERE slug='auto-ingested'")
    assert_contains("auto-ingested has git source", git_source, "git:")


def test_stop_hook_backfill_nudge():
    print("test_stop_hook_backfill_nudge:")
    d = str(TEST_DIR / "test-stop-backfill" / ".engram")
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

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")
    test_cwd = str(TEST_DIR / "test-stop-backfill")

    output = subprocess.run(
        ["bash", dispatch, "Stop"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-stop-bf-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert_contains("stop hook nudges backfill", output, "backfill")
    assert_contains("stop hook is advisory", output, '"ok": true')


def test_notification_backfill_nudge():
    print("test_notification_backfill_nudge:")
    d = str(TEST_DIR / "test-notif-backfill" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "incomplete-notif.md").write_text(
        "+++\ndate = 2026-03-17\n+++\n\n"
        "# Incomplete for notification test\n\nShort.\n"
    )

    store.reindex()

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")
    test_cwd = str(TEST_DIR / "test-notif-backfill")

    output = subprocess.run(
        ["bash", dispatch, "Notification"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-notif-bf-{os.getpid()}"},
        cwd=test_cwd,
    ).stdout.strip()
    assert_contains("notification nudges backfill", output, "backfill")


def test_status_withdrawn_indexed():
    print("test_status_withdrawn_indexed:")
    d = str(TEST_DIR / "test-status-indexed" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "old-feature.md").write_text(
        "+++\ndate = 2026-03-10\ntags = [\"feature\"]\nstatus = \"withdrawn\"\n+++\n\n"
        "# Add visualize skill\n\nFeature was planned but never implemented, withdrawing this decision.\n"
    )

    store.reindex()

    status_val = _db_scalar(f"{d}/index.db", "SELECT status FROM signals WHERE slug='old-feature'")
    assert_eq("status column stores withdrawn", status_val, "withdrawn")

    Path(d, "decisions", "active-feature.md").write_text(
        "+++\ndate = 2026-03-11\ntags = [\"feature\"]\n+++\n\n"
        "# Keep this feature active\n\nThis decision is current and should default to active status.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nActive feature.\n"
    )

    store.reindex()

    active_val = _db_scalar(f"{d}/index.db", "SELECT status FROM signals WHERE slug='active-feature'")
    assert_eq("status defaults to active", active_val, "active")


def test_brief_hides_withdrawn():
    print("test_brief_hides_withdrawn:")
    d = str(TEST_DIR / "test-brief-withdrawn" / ".engram")
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
    assert_contains("brief shows active decision", brief, "Use PostgreSQL")
    assert_not_contains("brief hides withdrawn decision", brief, "dashboard visualization")
    assert_contains("brief shows withdrawn count", brief, "1 withdrawn")


def test_query_relevant_excludes_withdrawn():
    print("test_query_relevant_excludes_withdrawn:")
    d = str(TEST_DIR / "test-query-withdrawn" / ".engram")
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
    assert_contains("shows active decision", result, "Use S3")
    assert_not_contains("hides withdrawn", result, "local disk")


def test_pre_commit_gate():
    print("test_pre_commit_gate:")
    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")

    # ── No .engram directory → allow ──
    no_engram_dir = str(TEST_DIR / "test-pre-commit-gate-no-engram")
    Path(no_engram_dir).mkdir(parents=True, exist_ok=True)
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git commit -m \\"test\\""}}',
        capture_output=True, text=True, cwd=no_engram_dir,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("no engram dir allows commit", output, "{}")

    # ── Non-commit command → allow ──
    d = str(TEST_DIR / "test-pre-commit-gate" / ".engram")
    store = engram.EngramStore(d)
    store.init()
    store.reindex()

    test_cwd = str(TEST_DIR / "test-pre-commit-gate")
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git status"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("non-commit command allowed", output, "{}")

    # ── git commit with no recent decision → nudge (not block) ──
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git commit -m \\"feat: add feature\\""}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_contains("nudges on commit without decision", output, "No decision signal")
    assert_contains("nudge mentions capture", output, "/engram:capture")

    # ── git commit --amend → allow (bypass) ──
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git commit --amend -m \\"fix\\""}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("amend allowed", output, "{}")

    # ── Write a decision signal, then commit → allow ──
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
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("allows commit with recent decision", output, "{}")


def test_pre_delete_guard():
    print("test_pre_delete_guard:")
    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")

    # Setup: create .engram with a signal
    d = str(TEST_DIR / "test-pre-delete-guard" / ".engram")
    store = engram.EngramStore(d)
    store.init()
    Path(d, "decisions", "keep-me.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n# Keep me\n\nThis should not be deleted.\n"
    )
    test_cwd = str(TEST_DIR / "test-pre-delete-guard")

    # rm on signal file → block
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"rm .engram/decisions/keep-me.md"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_contains("blocks rm on signal file", output, '"decision": "block"')
    assert_contains("mentions append-only", output, "append-only")

    # rm -rf on .engram → block
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"rm -rf .engram"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_contains("blocks rm -rf on .engram", output, '"decision": "block"')

    # git checkout -- on signal → block
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git checkout -- .engram/decisions/keep-me.md"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_contains("blocks git checkout on signal", output, '"decision": "block"')

    # git restore on signal → block
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git restore .engram/decisions/keep-me.md"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_contains("blocks git restore on signal", output, '"decision": "block"')

    # Non-engram rm → allow
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"rm src/old-file.py"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("allows rm on non-engram file", output, "{}")

    # Non-destructive git command → allow
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git status"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("allows non-destructive commands", output, "{}")


def test_pre_tool_use_edit_guard():
    print("test_pre_tool_use_edit_guard:")
    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")

    # Edit that deletes content from signal → block
    input_json = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": ".engram/decisions/test.md", "old_string": "## Rationale\n\nThis is important.", "new_string": ""}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_contains("blocks content deletion edit", output, '"decision": "block"')
    assert_contains("mentions append-only", output, "append-only")

    # Edit that modifies content (non-empty new_string) → allow
    input_json = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": ".engram/decisions/test.md", "old_string": "tags = []", "new_string": "tags = [\"architecture\"]"}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("allows content-modifying edit", output, "{}")

    # Edit on non-engram file → allow (no old_string check)
    input_json = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/app.rb", "old_string": "old", "new_string": "new"}})
    output = subprocess.run(
        ["bash", dispatch, "PreToolUse"],
        input=input_json,
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("allows edit on non-engram file", output, "{}")


def test_subagent_stop_context():
    print("test_subagent_stop_context:")

    # Setup: create .engram with brief
    d = str(TEST_DIR / "test-subagent-context" / ".engram")
    store = engram.EngramStore(d)
    store.init()
    Path(d, "decisions", "test-decision.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Test decision for subagent\n\nSubagents should see this decision in their context.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nTest context.\n"
    )
    store.reindex()
    store.brief()

    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")
    test_cwd = str(TEST_DIR / "test-subagent-context")

    # Use unique session ID to avoid dedup
    output = subprocess.run(
        ["bash", dispatch, "SubagentStop"],
        input="{}",
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent),
             "CLAUDE_SESSION_ID": f"test-subagent-{id(test_subagent_stop_context)}"},
    ).stdout.strip()

    parsed = json.loads(output)
    assert_contains("subagent gets brief context", parsed.get("systemMessage", ""), "Decision Context")
    assert_contains("subagent gets decision title", parsed.get("systemMessage", ""), "Test decision for subagent")
    assert_contains("subagent gets capture nudge", parsed.get("systemMessage", ""), "/engram:capture")


def test_post_push_resync():
    print("test_post_push_resync:")
    dispatch = str(SCRIPT_DIR.parent / "hooks" / "dispatch.sh")

    # No .engram → pass through
    no_engram_dir = str(TEST_DIR / "test-post-push-no-engram")
    Path(no_engram_dir).mkdir(parents=True, exist_ok=True)
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}',
        capture_output=True, text=True, cwd=no_engram_dir,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("no engram dir passes through", output, "{}")

    # Non-push command → pass through
    d = str(TEST_DIR / "test-post-push" / ".engram")
    store = engram.EngramStore(d)
    store.init()
    test_cwd = str(TEST_DIR / "test-post-push")

    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git status"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    assert_eq("non-push command passes through", output, "{}")

    # git push → resync message
    Path(d, "decisions", "push-test.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Push test\n\nThis should be resynced after push.\n\n"
        "## Alternatives\n- None\n\n## Rationale\nTest.\n"
    )
    output = subprocess.run(
        ["bash", dispatch, "PostToolUse"],
        input='{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}',
        capture_output=True, text=True, cwd=test_cwd,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(SCRIPT_DIR.parent)},
    ).stdout.strip()
    parsed = json.loads(output)
    assert_contains("push triggers resync message", parsed.get("systemMessage", ""), "resynced")


# ── Timestamp tests ──────────────────────────────────────────────────

def test_timestamps_indexed():
    print("test_timestamps_indexed:")
    d = str(TEST_DIR / "test-timestamps" / ".engram")
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
    assert_not_contains("created_at populated", "EMPTY", str(created))
    assert_not_contains("updated_at populated", "EMPTY", str(updated))
    assert_contains("created_at is ISO format", str(created), "T")
    assert_contains("updated_at is ISO format", str(updated), "T")


def test_created_at_from_frontmatter():
    print("test_created_at_from_frontmatter:")
    d = str(TEST_DIR / "test-created-fm" / ".engram")
    store = engram.EngramStore(d)
    store.init()

    Path(d, "decisions", "fm-ts.md").write_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\ncreated_at = \"2026-01-15T10:30:00+00:00\"\n+++\n\n"
        "# Frontmatter timestamp\n\nThe created_at from frontmatter should take precedence.\n\n"
        "## Alternatives\n- Use mtime\n\n## Rationale\nExplicit creation date.\n"
    )

    store.reindex()

    created = _db_scalar(f"{d}/index.db", "SELECT created_at FROM signals WHERE slug='fm-ts'")
    assert_contains("created_at from frontmatter", str(created), "2026-01-15")


# ── Section validation tests ────────────────────────────────────────

def test_validate_missing_sections():
    print("test_validate_missing_sections:")
    sig = engram.Signal.from_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Missing both sections\n\nThis signal has no Rationale or Alternatives sections.\n"
    )
    ok, errors = sig.validate()
    assert_eq("fails validation", ok, False)
    assert_contains("mentions Rationale", errors, "## Rationale")
    assert_contains("mentions Alternatives", errors, "## Alternatives")


def test_validate_partial_sections():
    print("test_validate_partial_sections:")
    sig = engram.Signal.from_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Has Alternatives only\n\nThis signal has Alternatives but no Rationale.\n\n"
        "## Alternatives\n- Option A\n"
    )
    ok, errors = sig.validate()
    assert_eq("fails validation", ok, False)
    assert_contains("mentions Rationale", errors, "## Rationale")
    assert_not_contains("does not mention Alternatives", errors, "## Alternatives")


# ── Compaction tests ────────────────────────────────────────────────

def test_compact_archives_old_signal():
    print("test_compact_archives_old_signal:")
    d = f"{TEST_DIR}/compact-old"
    engram_dir = f"{d}/.engram"
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
    assert_eq("one archived", archived, 1)
    assert_eq("original removed", sig_path.is_file(), False)
    assert_file_exists("moved to archive", str(Path(engram_dir) / "archive" / "decisions" / "old-decision.md"))


def test_compact_keeps_recent_signal():
    print("test_compact_keeps_recent_signal:")
    d = f"{TEST_DIR}/compact-recent"
    engram_dir = f"{d}/.engram"
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
    assert_eq("none archived", archived, 0)
    assert_file_exists("still exists", str(sig_path))


def test_compact_keeps_pinned_signal():
    print("test_compact_keeps_pinned_signal:")
    d = f"{TEST_DIR}/compact-pinned"
    engram_dir = f"{d}/.engram"
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
    assert_eq("none archived", archived, 0)
    assert_file_exists("still exists", str(sig_path))


def test_compact_keeps_referenced_signal():
    print("test_compact_keeps_referenced_signal:")
    d = f"{TEST_DIR}/compact-referenced"
    engram_dir = f"{d}/.engram"
    store = engram.EngramStore(engram_dir)
    store.init()

    # Write two old signals — one references the other via supersedes
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
    assert_eq("one archived (unreferenced only)", archived, 1)
    assert_file_exists("old-referenced still exists", str(old_path))
    assert_eq("newer-decision archived", newer_path.is_file(), False)


def test_compact_brief_excludes_archived():
    print("test_compact_brief_excludes_archived:")
    d = f"{TEST_DIR}/compact-brief"
    engram_dir = f"{d}/.engram"
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
    assert_contains("has active", brief_text, "Active decision")
    assert_not_contains("no archived", brief_text, "Archived decision")


# ── Section depth validation tests ─────────────────────────────────

def test_validate_empty_rationale_section():
    print("test_validate_empty_rationale_section:")
    sig = engram.Signal.from_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Decision with empty rationale\n\nThis is a test decision.\n\n"
        "## Alternatives\n- Option A\n\n"
        "## Rationale\n\n"
    )
    ok, errors = sig.validate()
    assert_eq("fails validation", ok, False)
    assert_contains("mentions empty section", errors, "empty")


def test_validate_empty_alternatives_section():
    print("test_validate_empty_alternatives_section:")
    sig = engram.Signal.from_text(
        "+++\ndate = 2026-03-17\ntags = [\"test\"]\n+++\n\n"
        "# Decision with empty alternatives\n\nThis is a test decision.\n\n"
        "## Alternatives\n\n"
        "## Rationale\nChosen for good reasons.\n"
    )
    ok, errors = sig.validate()
    assert_eq("fails validation", ok, False)
    assert_contains("mentions empty section", errors, "empty")


# ── Run all tests ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== engram v0.2 test suite (Python) ===\n")

    tests = [
        test_fts5_check,
        test_init,
        test_init_private_dirs,
        test_write_decision,
        test_is_decision_commit,
        test_ingest_commits,
        test_ingest_commits_body,
        test_ingest_dedup,
        test_ingest_manual_signal_suppresses,
        test_ingest_private_signal_suppresses,
        test_ingest_no_manual_still_creates,
        test_ingest_brownfield,
        test_ingest_plans,
        test_reindex,
        test_brief,
        test_fts_search,
        test_frontmatter_parsing,
        test_meta_preserved,
        test_incremental_ingest,
        test_file_column,
        test_private_signal_indexed,
        test_brief_excludes_private,
        test_private_queryable,
        test_public_signals_unchanged,
        test_uncommitted_summary,
        test_uncommitted_summary_no_git,
        test_session_end_output,
        test_supersedes_frontmatter,
        test_links_frontmatter,
        test_excerpt_extraction,
        test_slug_column,
        test_brief_hides_superseded,
        test_brief_tag_grouping,
        test_brief_max_lines,
        test_brief_excerpts,
        test_supersession_chain,
        test_links_bidirectional,
        test_path_to_keywords,
        test_query_relevant,
        test_query_relevant_excludes_superseded,
        test_tag_summary,
        test_tag_summary_few_signals,
        test_post_tool_context_output,
        test_pre_compact_output,
        test_pre_compact_no_engram,
        test_stop_hook_output,
        test_stop_hook_no_engram,
        test_user_prompt_submit_hook,
        test_pre_tool_use_validation,
        test_notification_hook,
        test_hooks_json_structure,
        test_validate_signal_valid,
        test_validate_signal_missing_why,
        test_validate_signal_missing_tags,
        test_validate_signal_short_why,
        test_reindex_marks_invalid,
        test_brief_excludes_invalid,
        test_ingest_bodyless_commit_invalid,
        test_git_tracking_config,
        test_init_no_gitignore_by_default,
        test_init_gitignore_with_git_tracking,
        test_ingest_noop_without_git_tracking,
        test_resync,
        test_find_incomplete,
        test_find_incomplete_empty,
        test_find_incomplete_source_classification,
        test_stop_hook_backfill_nudge,
        test_notification_backfill_nudge,
        test_status_withdrawn_indexed,
        test_brief_hides_withdrawn,
        test_query_relevant_excludes_withdrawn,
        test_pre_commit_gate,
        test_pre_delete_guard,
        test_pre_tool_use_edit_guard,
        test_subagent_stop_context,
        test_post_push_resync,
        test_timestamps_indexed,
        test_created_at_from_frontmatter,
        test_validate_missing_sections,
        test_validate_partial_sections,
        test_compact_archives_old_signal,
        test_compact_keeps_recent_signal,
        test_compact_keeps_pinned_signal,
        test_compact_keeps_referenced_signal,
        test_compact_brief_excludes_archived,
        test_validate_empty_rationale_section,
        test_validate_empty_alternatives_section,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            _fail(test.__name__, f"EXCEPTION: {e}")
        print()

    # Cleanup
    os.chdir(ORIG_CWD)
    shutil.rmtree(str(TEST_DIR), ignore_errors=True)

    print(f"=== Results: {PASS} passed, {FAIL} failed ===")
    sys.exit(0 if FAIL == 0 else 1)
