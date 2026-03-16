#!/usr/bin/env bash
# engram v0.2 test suite
# shellcheck disable=SC1090
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib.sh
LIB="$SCRIPT_DIR/../lib.sh"
TEST_DIR=$(mktemp -d "${TMPDIR:-/tmp}/engram-test.XXXXXX")
PASS=0
FAIL=0

# Override schema file location
export ENGRAM_SCHEMA_FILE="$SCRIPT_DIR/../schema.sql"
# Override plans dir
export ENGRAM_PLANS_DIR="$TEST_DIR/plans"

cleanup() {
  rm -rf "$TEST_DIR"
}
trap cleanup EXIT

# ── Test helpers ────────────────────────────────────────────────────

_pass() {
  PASS=$((PASS + 1))
  echo "  PASS: $1"
}

_fail() {
  FAIL=$((FAIL + 1))
  echo "  FAIL: $1 — $2"
}

assert_eq() {
  if [ "$2" = "$3" ]; then
    _pass "$1"
  else
    _fail "$1" "expected '$3', got '$2'"
  fi
}

assert_contains() {
  if echo "$2" | grep -q "$3"; then
    _pass "$1"
  else
    _fail "$1" "output does not contain '$3'"
  fi
}

assert_not_contains() {
  if echo "$2" | grep -q "$3"; then
    _fail "$1" "output should not contain '$3'"
  else
    _pass "$1"
  fi
}

assert_file_exists() {
  if [ -f "$2" ]; then
    _pass "$1"
  else
    _fail "$1" "file does not exist: $2"
  fi
}

assert_dir_exists() {
  if [ -d "$2" ]; then
    _pass "$1"
  else
    _fail "$1" "directory does not exist: $2"
  fi
}

assert_file_count() {
  local count
  count=$(find "$2" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
  if [ "$count" -eq "$3" ]; then
    _pass "$1"
  else
    _fail "$1" "expected $3 files, found $count"
  fi
}

# ── Helper: create a test git repo ────────────────────────────────

_create_test_repo() {
  local repo_dir="$1"
  local num_commits="${2:-5}"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  for i in $(seq 1 "$num_commits"); do
    echo "content $i" > "file$i.txt"
    git add "file$i.txt"
    git commit -q -m "Commit $i: add file$i.txt"
  done
}

# Creates a repo with a mix of decision-worthy and trivial commits
_create_test_repo_mixed() {
  local repo_dir="$1"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  # Decision-worthy commits
  echo "v1" > Gemfile; git add Gemfile
  git commit -q -m "feat: add user authentication"

  echo "v2" > app.rb; git add app.rb
  git commit -q -m "refactor: extract payment service"

  echo "v3" > schema.sql; git add schema.sql
  git commit -q -m "migrate users to new schema"

  # Trivial commits (should be skipped)
  echo "v4" > README.md; git add README.md
  git commit -q -m "docs: update README"

  echo "v5" > app.rb; git add app.rb
  git commit -q -m "fix: handle nil email"

  echo "v6" > test.rb; git add test.rb
  git commit -q -m "test: add payment specs"

  echo "v7" > style.css; git add style.css
  git commit -q -m "chore: lint fixes"
}

# ── Tests ───────────────────────────────────────────────────────────

test_init() {
  echo "test_init:"
  local dir="$TEST_DIR/test-init/.engram"

  source "$LIB"
  engram_init "$dir"

  assert_dir_exists "decisions dir" "$dir/decisions"
  assert_dir_exists "findings dir" "$dir/findings"
  assert_dir_exists "issues dir" "$dir/issues"
  assert_file_exists "gitignore" "$dir/.gitignore"
  assert_file_exists "index.db" "$dir/index.db"

  # Verify gitignore content
  local gitignore
  gitignore=$(cat "$dir/.gitignore")
  assert_contains "gitignore contains index.db" "$gitignore" "index.db"
  assert_contains "gitignore contains private/" "$gitignore" "private/"

  # Idempotent: run again, no error
  engram_init "$dir"
  assert_file_exists "still has index.db" "$dir/index.db"
}

test_init_private_dirs() {
  echo "test_init_private_dirs:"
  local dir="$TEST_DIR/test-init-private/.engram"

  source "$LIB"
  engram_init "$dir"

  assert_dir_exists "private/decisions dir" "$dir/private/decisions"
  assert_dir_exists "private/findings dir" "$dir/private/findings"
  assert_dir_exists "private/issues dir" "$dir/private/issues"
}

test_init_upgrade_gitignore() {
  echo "test_init_upgrade_gitignore:"
  local dir="$TEST_DIR/test-upgrade-gitignore/.engram"

  mkdir -p "$dir"
  # Create old-style .gitignore without private/
  echo "index.db" > "$dir/.gitignore"

  source "$LIB"
  engram_init "$dir"

  local gitignore
  gitignore=$(cat "$dir/.gitignore")
  assert_contains "gitignore has index.db" "$gitignore" "index.db"
  assert_contains "gitignore has private/" "$gitignore" "private/"
}

test_write_decision() {
  echo "test_write_decision:"
  local dir="$TEST_DIR/test-write-decision/.engram"

  source "$LIB"
  engram_init "$dir"

  # Write a decision signal file
  cat > "$dir/decisions/2026-03-14-use-redis.md" << 'EOF'
---
date: 2026-03-14
tags: [infrastructure, caching]
---

# Use Redis for caching

Already in our stack for session storage.

## Alternatives
- Memcached — faster for simple k/v but no pub/sub

## Rationale
Redis supports pub/sub which we'll need for notifications.

## Trade-offs
Higher memory usage than Memcached.
EOF

  engram_reindex "$dir"

  local result
  result=$(sqlite3 -json "$dir/index.db" "SELECT type, title, date FROM signals WHERE type='decision';")
  assert_contains "decision indexed" "$result" "Use Redis for caching"
  assert_contains "date correct" "$result" "2026-03-14"
  assert_contains "type correct" "$result" '"type":"decision"'
}

test_write_finding() {
  echo "test_write_finding:"
  local dir="$TEST_DIR/test-write-finding/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/findings/2026-03-11-fts5-sync.md" << 'EOF'
---
date: 2026-03-11
tags: [sqlite, search]
source: manual
---

# FTS5 requires explicit sync triggers

SQLite FTS5 content= tables don't auto-update.

## Trigger
Index was returning stale results after inserts.

## Implications
Every table with FTS needs explicit triggers.
EOF

  engram_reindex "$dir"

  local result
  result=$(sqlite3 -json "$dir/index.db" "SELECT type, title FROM signals WHERE type='finding';")
  assert_contains "finding indexed" "$result" "FTS5 requires explicit sync triggers"
  assert_contains "type correct" "$result" '"type":"finding"'
}

test_write_issue() {
  echo "test_write_issue:"
  local dir="$TEST_DIR/test-write-issue/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/issues/2026-03-11-ci-slow.md" << 'EOF'
---
date: 2026-03-11
tags: [ci, testing]
---

# CI pipeline takes 45 minutes

Integration tests run serially.

## Impact
Developers avoid running full test suite locally.

## Next steps
Investigate per-worker test databases.
EOF

  engram_reindex "$dir"

  local result
  result=$(sqlite3 -json "$dir/index.db" "SELECT type, title FROM signals WHERE type='issue';")
  assert_contains "issue indexed" "$result" "CI pipeline takes 45 minutes"
  assert_contains "type correct" "$result" '"type":"issue"'
}

test_is_decision_commit() {
  echo "test_is_decision_commit:"
  local repo_dir="$TEST_DIR/test-classify-repo"
  _create_test_repo_mixed "$repo_dir"
  source "$LIB"

  # Get all commit hashes
  local hashes
  hashes=$(git log --format='%H|%s' --reverse)

  # Test each commit classification
  while IFS='|' read -r hash subject; do
    [ -z "$hash" ] && continue
    local result
    if _is_decision_commit "$subject" "$hash"; then
      result="decision"
    else
      result="skip"
    fi

    case "$subject" in
      "feat: add user authentication")    assert_eq "feat prefix → decision"    "$result" "decision" ;;
      "refactor: extract payment service") assert_eq "refactor prefix → decision" "$result" "decision" ;;
      "migrate users to new schema")      assert_eq "migrate keyword → decision" "$result" "decision" ;;
      "docs: update README")              assert_eq "docs prefix → skip"         "$result" "skip" ;;
      "fix: handle nil email")            assert_eq "fix prefix → skip"          "$result" "skip" ;;
      "test: add payment specs")          assert_eq "test prefix → skip"         "$result" "skip" ;;
      "chore: lint fixes")                assert_eq "chore prefix → skip"        "$result" "skip" ;;
    esac
  done <<< "$hashes"

  cd "$SCRIPT_DIR"
}

test_ingest_commits() {
  echo "test_ingest_commits:"
  local repo_dir="$TEST_DIR/test-ingest-repo"

  _create_test_repo_mixed "$repo_dir"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  engram_ingest_commits "$dir"

  # Should have 3 decision files (feat, refactor, migrate) out of 7 commits
  local file_count
  file_count=$(find "$dir/decisions" -name '*.md' | wc -l | tr -d ' ')
  assert_eq "3 decisions from 7 commits" "$file_count" "3"

  # Verify files have source: git:<hash>
  local has_source
  has_source=$(grep -rl "source: git:" "$dir/decisions/" | wc -l | tr -d ' ')
  assert_eq "all have git source" "$has_source" "3"

  cd "$SCRIPT_DIR"
}

test_ingest_dedup() {
  echo "test_ingest_dedup:"
  local repo_dir="$TEST_DIR/test-dedup-repo"

  _create_test_repo_mixed "$repo_dir"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"

  # Ingest twice
  engram_ingest_commits "$dir"
  local first_count
  first_count=$(find "$dir/decisions" -name '*.md' | wc -l | tr -d ' ')

  engram_ingest_commits "$dir"
  local second_count
  second_count=$(find "$dir/decisions" -name '*.md' | wc -l | tr -d ' ')

  assert_eq "no duplicates after second ingest" "$first_count" "$second_count"

  cd "$SCRIPT_DIR"
}

test_ingest_brownfield() {
  echo "test_ingest_brownfield:"
  local repo_dir="$TEST_DIR/test-brownfield-repo"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  # Create 100 commits: 60 feat (decisions) + 40 fix (skipped)
  for i in $(seq 1 100); do
    echo "content $i" > "file$i.txt"
    git add "file$i.txt"
    if [ $((i % 5)) -ne 0 ]; then
      git commit -q -m "feat: add feature $i"
    else
      git commit -q -m "fix: typo in file $i"
    fi
  done

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  engram_ingest_commits "$dir"

  # Brownfield scans last 50 commits. Of those 50, 40 are feat (decision) and 10 are fix (skip).
  local file_count
  file_count=$(find "$dir/decisions" -name '*.md' | wc -l | tr -d ' ')
  assert_eq "brownfield: only decisions from last 50" "$file_count" "40"

  cd "$SCRIPT_DIR"
}

test_ingest_plans() {
  echo "test_ingest_plans:"
  # Need a git repo context for date
  local repo_dir="$TEST_DIR/test-plans-repo"
  _create_test_repo "$repo_dir" 1

  local dir="$repo_dir/.engram"
  mkdir -p "$ENGRAM_PLANS_DIR"

  # Create a mock plan file with ## Context section
  cat > "$ENGRAM_PLANS_DIR/auth-redesign.md" << 'EOF'
# Auth Redesign

## Context
We need to move from session-based auth to JWT because our mobile
app can't maintain server-side sessions efficiently.

## Implementation
Use asymmetric keys for JWT signing...
EOF

  source "$LIB"
  engram_init "$dir"
  engram_ingest_plans "$dir"

  # Should have created a decision file from the plan
  local plan_files
  plan_files=$(grep -rl "source: plan:auth-redesign" "$dir/decisions/" 2>/dev/null | wc -l | tr -d ' ')
  assert_eq "plan ingested" "$plan_files" "1"

  # Verify content includes the context section
  local content
  content=$(cat "$dir/decisions"/*plan*auth*.md 2>/dev/null || echo "")
  assert_contains "plan has context content" "$content" "JWT"

  cd "$SCRIPT_DIR"
}

test_reindex() {
  echo "test_reindex:"
  local dir="$TEST_DIR/test-reindex/.engram"

  source "$LIB"
  engram_init "$dir"

  # Write some signal files
  cat > "$dir/decisions/2026-03-14-test-a.md" << 'EOF'
---
date: 2026-03-14
---

# Decision A

Content A
EOF

  cat > "$dir/findings/2026-03-14-test-b.md" << 'EOF'
---
date: 2026-03-14
---

# Finding B

Content B
EOF

  engram_reindex "$dir"

  local count
  count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals;")
  assert_eq "2 signals indexed" "$count" "2"

  # Delete and recreate index
  rm "$dir/index.db"
  engram_reindex "$dir"

  count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals;")
  assert_eq "2 signals after reindex" "$count" "2"
}

test_brief() {
  echo "test_brief:"
  local dir="$TEST_DIR/test-brief/.engram"

  source "$LIB"
  engram_init "$dir"

  # Write signals
  cat > "$dir/decisions/2026-03-14-pick-redis.md" << 'EOF'
---
date: 2026-03-14
---

# Pick Redis for caching

It's already in our stack.
EOF

  cat > "$dir/issues/2026-03-14-ci-slow.md" << 'EOF'
---
date: 2026-03-14
---

# CI is too slow

Takes 45 minutes.
EOF

  engram_reindex "$dir"
  engram_brief "$dir"

  assert_file_exists "brief.md created" "$dir/brief.md"

  local brief
  brief=$(cat "$dir/brief.md")
  assert_contains "brief has decisions header" "$brief" "Recent Decisions"
  assert_contains "brief has issues header" "$brief" "Open Issues"
  assert_contains "brief has decision title" "$brief" "Pick Redis"
  assert_contains "brief has issue title" "$brief" "CI is too slow"
  assert_contains "brief has counts" "$brief" "1 decisions"
}

test_fts_search() {
  echo "test_fts_search:"
  local dir="$TEST_DIR/test-fts/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/2026-03-14-postgresql.md" << 'EOF'
---
date: 2026-03-14
---

# Use PostgreSQL over MySQL

Better JSON support and window functions.
EOF

  cat > "$dir/findings/2026-03-14-fts5.md" << 'EOF'
---
date: 2026-03-14
---

# FTS5 needs sync triggers

Without triggers the index becomes stale.
EOF

  engram_reindex "$dir"

  # FTS search for PostgreSQL
  local result
  result=$(sqlite3 -json "$dir/index.db" "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid WHERE signals_fts MATCH 'PostgreSQL' ORDER BY rank LIMIT 10;")
  assert_contains "FTS finds PostgreSQL" "$result" "PostgreSQL"

  # FTS search for triggers
  result=$(sqlite3 -json "$dir/index.db" "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid WHERE signals_fts MATCH 'triggers' ORDER BY rank LIMIT 10;")
  assert_contains "FTS finds triggers" "$result" "FTS5"

  # Search for nonexistent
  result=$(sqlite3 -json "$dir/index.db" "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid WHERE signals_fts MATCH 'nonexistent_xyz_12345' ORDER BY rank LIMIT 10;" 2>/dev/null || echo "")
  assert_eq "no results for nonexistent" "$result" ""
}

test_frontmatter_parsing() {
  echo "test_frontmatter_parsing:"
  local dir="$TEST_DIR/test-frontmatter/.engram"

  source "$LIB"
  engram_init "$dir"

  # File with no frontmatter at all
  cat > "$dir/decisions/2026-03-14-no-frontmatter.md" << 'EOF'
# Decision with no frontmatter

Just a plain markdown file with a heading.
EOF

  # File with partial frontmatter (missing tags)
  cat > "$dir/decisions/2026-03-14-partial.md" << 'EOF'
---
date: 2026-03-14
---

# Partial frontmatter

Only date, no tags or source.
EOF

  # File with full frontmatter
  cat > "$dir/decisions/2026-03-14-full.md" << 'EOF'
---
date: 2026-03-14
tags: [api, auth]
source: git:abc1234
---

# Full frontmatter

Has everything.
EOF

  engram_reindex "$dir"

  local count
  count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals;")
  assert_eq "all 3 files indexed" "$count" "3"

  # Check that partial frontmatter files have defaults
  local tags
  tags=$(sqlite3 "$dir/index.db" "SELECT tags FROM signals WHERE title='Partial frontmatter';")
  assert_eq "default tags is []" "$tags" "[]"

  local source_val
  source_val=$(sqlite3 "$dir/index.db" "SELECT source FROM signals WHERE title='Partial frontmatter';")
  assert_eq "default source is empty" "$source_val" ""
}

test_meta_preserved() {
  echo "test_meta_preserved:"
  local repo_dir="$TEST_DIR/test-meta-repo"
  _create_test_repo "$repo_dir" 3

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  engram_ingest_commits "$dir"

  # Verify last_commit is stored
  local last_commit
  last_commit=$(sqlite3 "$dir/index.db" "SELECT value FROM meta WHERE key='last_commit';")
  assert_not_contains "last_commit is not empty" "EMPTY" "$last_commit"

  # Reindex should preserve meta
  engram_reindex "$dir"
  local after_reindex
  after_reindex=$(sqlite3 "$dir/index.db" "SELECT value FROM meta WHERE key='last_commit';")
  assert_eq "meta preserved after reindex" "$after_reindex" "$last_commit"

  cd "$SCRIPT_DIR"
}

test_incremental_ingest() {
  echo "test_incremental_ingest:"
  local repo_dir="$TEST_DIR/test-incremental-repo"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  # 3 initial decision-worthy commits
  for i in 1 2 3; do
    echo "v$i" > "feat$i.rb"
    git add "feat$i.rb"
    git commit -q -m "feat: add feature $i"
  done

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  engram_ingest_commits "$dir"

  local first_count
  first_count=$(find "$dir/decisions" -name '*.md' | wc -l | tr -d ' ')
  assert_eq "3 initial commits" "$first_count" "3"

  # Add 2 more decision-worthy commits
  echo "v4" > feat4.rb
  git add feat4.rb && git commit -q -m "feat: add feature 4"
  echo "v5" > feat5.rb
  git add feat5.rb && git commit -q -m "refactor: extract shared module"

  engram_ingest_commits "$dir"

  local second_count
  second_count=$(find "$dir/decisions" -name '*.md' | wc -l | tr -d ' ')
  assert_eq "5 after incremental" "$second_count" "5"

  cd "$SCRIPT_DIR"
}

test_file_column() {
  echo "test_file_column:"
  local dir="$TEST_DIR/test-file-col/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/2026-03-14-test-file.md" << 'EOF'
---
date: 2026-03-14
---

# Test file column

Content.
EOF

  engram_reindex "$dir"

  local file_val
  file_val=$(sqlite3 "$dir/index.db" "SELECT file FROM signals LIMIT 1;")
  assert_contains "file column has path" "$file_val" "decisions/2026-03-14-test-file.md"
}

test_private_signal_indexed() {
  echo "test_private_signal_indexed:"
  local dir="$TEST_DIR/test-private-indexed/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/private/decisions/2026-03-14-secret-deal.md" << 'EOF'
---
date: 2026-03-14
tags: [crm, deals]
---

# Secret deal with Acme Corp

Confidential terms discussion.
EOF

  engram_reindex "$dir"

  local private_val
  private_val=$(sqlite3 "$dir/index.db" "SELECT private FROM signals WHERE title='Secret deal with Acme Corp';")
  assert_eq "private signal has private=1" "$private_val" "1"
}

test_brief_excludes_private() {
  echo "test_brief_excludes_private:"
  local dir="$TEST_DIR/test-brief-private/.engram"

  source "$LIB"
  engram_init "$dir"

  # Write a public signal
  cat > "$dir/decisions/2026-03-14-public-choice.md" << 'EOF'
---
date: 2026-03-14
---

# Public architecture choice

Visible to everyone.
EOF

  # Write a private signal
  cat > "$dir/private/decisions/2026-03-14-private-deal.md" << 'EOF'
---
date: 2026-03-14
---

# Private deal terms

Confidential information.
EOF

  engram_reindex "$dir"
  engram_brief "$dir"

  local brief
  brief=$(cat "$dir/brief.md")
  assert_contains "brief has public title" "$brief" "Public architecture choice"
  assert_not_contains "brief excludes private title" "$brief" "Private deal terms"
  assert_contains "brief shows private count" "$brief" "1 private signals (not shown)"
}

test_private_queryable() {
  echo "test_private_queryable:"
  local dir="$TEST_DIR/test-private-query/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/private/findings/2026-03-14-competitor-intel.md" << 'EOF'
---
date: 2026-03-14
tags: [competitive]
---

# Competitor launched new product

Details about competitor's launch.
EOF

  engram_reindex "$dir"

  # FTS search should find private signals
  local result
  result=$(sqlite3 -json "$dir/index.db" "SELECT s.title FROM signals_fts fts JOIN signals s ON s.id = fts.rowid WHERE signals_fts MATCH 'competitor' ORDER BY rank LIMIT 10;")
  assert_contains "FTS finds private signal" "$result" "Competitor launched new product"
}

test_public_signals_unchanged() {
  echo "test_public_signals_unchanged:"
  local dir="$TEST_DIR/test-public-unchanged/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/2026-03-14-normal-decision.md" << 'EOF'
---
date: 2026-03-14
---

# Normal public decision

Standard decision content.
EOF

  engram_reindex "$dir"

  local private_val
  private_val=$(sqlite3 "$dir/index.db" "SELECT private FROM signals WHERE title='Normal public decision';")
  assert_eq "public signal has private=0" "$private_val" "0"
}

test_fts5_check() {
  echo "test_fts5_check:"

  source "$LIB"

  # _check_fts5 should succeed on this machine (tests already use FTS5)
  _check_fts5
  local rc=$?
  assert_eq "_check_fts5 succeeds" "$rc" "0"
}

# ── Run all tests ───────────────────────────────────────────────────

echo "=== engram v0.2 test suite ==="
echo ""

test_fts5_check
echo ""
test_init
echo ""
test_init_private_dirs
echo ""
test_init_upgrade_gitignore
echo ""
test_write_decision
echo ""
test_write_finding
echo ""
test_write_issue
echo ""
test_is_decision_commit
echo ""
test_ingest_commits
echo ""
test_ingest_dedup
echo ""
test_ingest_brownfield
echo ""
test_ingest_plans
echo ""
test_reindex
echo ""
test_brief
echo ""
test_fts_search
echo ""
test_frontmatter_parsing
echo ""
test_meta_preserved
echo ""
test_incremental_ingest
echo ""
test_file_column
echo ""
test_private_signal_indexed
echo ""
test_brief_excludes_private
echo ""
test_private_queryable
echo ""
test_public_signals_unchanged

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
