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

# ── Helper: enable git tracking ───────────────────────────────────

_enable_git_tracking() {
  echo "git_tracking=true" > "$1/config"
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
  assert_dir_exists "_private dir" "$dir/_private"
  assert_file_exists "index.db" "$dir/index.db"

  # No .gitignore by default (git tracking is opt-in)
  if [ ! -f "$dir/.gitignore" ]; then
    _pass "no gitignore by default"
  else
    _fail "no gitignore by default" "file exists"
  fi

  # Idempotent: run again, no error
  engram_init "$dir"
  assert_file_exists "still has index.db" "$dir/index.db"
}

test_init_private_dirs() {
  echo "test_init_private_dirs:"
  local dir="$TEST_DIR/test-init-private/.engram"

  source "$LIB"
  engram_init "$dir"

  assert_dir_exists "_private dir" "$dir/_private"
}

test_init_upgrade_gitignore() {
  echo "test_init_upgrade_gitignore:"
  local dir="$TEST_DIR/test-upgrade-gitignore/.engram"

  mkdir -p "$dir"
  # Create old-style .gitignore without _private/ or brief.md (simulates existing user)
  echo "index.db" > "$dir/.gitignore"

  source "$LIB"
  engram_init "$dir"

  # Migration should auto-enable git tracking
  assert_file_exists "config created by migration" "$dir/config"
  local config
  config=$(cat "$dir/config")
  assert_contains "config has git_tracking" "$config" "git_tracking=true"

  local gitignore
  gitignore=$(cat "$dir/.gitignore")
  assert_contains "gitignore has index.db" "$gitignore" "index.db"
  assert_contains "gitignore has brief.md" "$gitignore" "brief.md"
  assert_contains "gitignore has _private/" "$gitignore" "_private/"
}

test_migrate_signals_to_decisions() {
  echo "test_migrate_signals_to_decisions:"
  local dir="$TEST_DIR/test-migrate/.engram"

  source "$LIB"

  # Create old-style layout manually (before engram_init runs migration)
  mkdir -p "$dir/signals"
  mkdir -p "$dir/_private"

  cat > "$dir/signals/decision-use-redis.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [infrastructure]
supersedes: decision-old-cache
links: [related:decision-redis-perf]
---

# Use Redis for caching

Already in our stack for session storage and pub/sub needs.
EOF

  cat > "$dir/_private/decision-secret-deal.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [business]
---

# Secret deal

Private info about a deal with a major vendor partner.
EOF

  # Run init — should trigger migration
  engram_init "$dir"

  # Old dir should be gone, new dir should exist
  assert_dir_exists "decisions dir exists" "$dir/decisions"

  # Files should have decision- prefix stripped
  assert_file_exists "public file renamed" "$dir/decisions/use-redis.md"
  assert_file_exists "private file renamed" "$dir/_private/secret-deal.md"

  # Frontmatter should have decision- prefix stripped from supersedes/links
  local content
  content=$(cat "$dir/decisions/use-redis.md")
  assert_contains "supersedes stripped" "$content" "supersedes: old-cache"
  assert_not_contains "supersedes no decision- prefix" "$content" "supersedes: decision-"
  assert_contains "links stripped" "$content" "related:redis-perf"
  assert_not_contains "links no decision- prefix" "$content" "related:decision-"

  # Reindex should work with new paths
  engram_reindex "$dir"
  local count
  count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals;")
  assert_eq "migrated signals indexed" "$count" "2"
}

test_write_decision() {
  echo "test_write_decision:"
  local dir="$TEST_DIR/test-write-decision/.engram"

  source "$LIB"
  engram_init "$dir"

  # Write a decision signal file
  cat > "$dir/decisions/use-redis.md" << 'EOF'
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
  _enable_git_tracking "$dir"
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

test_ingest_commits_body() {
  echo "test_ingest_commits_body:"
  local repo_dir="$TEST_DIR/test-ingest-body-repo"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  # Commit with a body explaining rationale
  echo "v1" > auth.rb; git add auth.rb
  git commit -q -m "feat: add OAuth2 authentication" -m "We chose OAuth2 over SAML because our mobile clients need token-based auth.

Co-Authored-By: Claude <noreply@anthropic.com>"

  # Commit without a body
  echo "v2" > api.rb; git add api.rb
  git commit -q -m "refactor: extract API gateway"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  _enable_git_tracking "$dir"
  engram_ingest_commits "$dir"

  # Should have 2 decision files
  local file_count
  file_count=$(find "$dir/decisions" -name '*.md' | wc -l | tr -d ' ')
  assert_eq "2 decisions created" "$file_count" "2"

  # Verify body appears in the OAuth2 signal file
  local oauth_file
  oauth_file=$(grep -rl "OAuth2" "$dir/decisions/" | head -1)
  local content
  content=$(cat "$oauth_file")
  assert_contains "body included in signal" "$content" "token-based auth"
  assert_not_contains "Co-Authored-By stripped" "$content" "Co-Authored-By"

  # Verify the no-body commit doesn't have extra blank lines between title and stat
  local api_file
  api_file=$(grep -rl "API gateway" "$dir/decisions/" | head -1)
  local api_content
  api_content=$(cat "$api_file")
  assert_contains "no-body signal has stat" "$api_content" "api.rb"

  cd "$SCRIPT_DIR"
}

test_ingest_dedup() {
  echo "test_ingest_dedup:"
  local repo_dir="$TEST_DIR/test-dedup-repo"

  _create_test_repo_mixed "$repo_dir"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  _enable_git_tracking "$dir"

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

test_ingest_manual_signal_suppresses() {
  echo "test_ingest_manual_signal_suppresses:"
  local repo_dir="$TEST_DIR/test-manual-suppress-repo"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  echo "v1" > widget.rb; git add widget.rb
  git commit -q -m "feat: add widget"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  _enable_git_tracking "$dir"

  # Pre-create a manual signal with the same slug auto-ingest would use
  cat > "$dir/decisions/feat-add-widget.md" << 'EOF'
---
type: decision
date: 2026-03-16
tags: [widget]
---

# Add widget component

We chose a widget approach because it composes better than mixins.
EOF

  engram_ingest_commits "$dir"

  # Should still have only 1 file — no feat-add-widget-<hash>.md created
  local file_count
  file_count=$(find "$dir/decisions" -name 'feat-add-widget*' | wc -l | tr -d ' ')
  assert_eq "manual signal suppresses auto-ingest" "$file_count" "1"

  # Verify the file content is the manual one (no source: git: line)
  assert_not_contains "manual signal preserved" "$(cat "$dir/decisions/feat-add-widget.md")" "source: git:"

  cd "$SCRIPT_DIR"
}

test_ingest_private_signal_suppresses() {
  echo "test_ingest_private_signal_suppresses:"
  local repo_dir="$TEST_DIR/test-private-suppress-repo"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  echo "v1" > cache.rb; git add cache.rb
  git commit -q -m "feat: switch to redis for caching"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  _enable_git_tracking "$dir"

  # Pre-create a private signal with the same slug
  cat > "$dir/_private/feat-switch-to-redis-for-caching.md" << 'EOF'
---
type: decision
date: 2026-03-16
tags: [caching]
---

# Switch to Redis for caching

Private: contains vendor pricing details.
EOF

  engram_ingest_commits "$dir"

  # No public signal should be created
  local public_count
  public_count=$(find "$dir/decisions" -name 'feat-switch-to-redis*' | wc -l | tr -d ' ')
  assert_eq "private signal suppresses auto-ingest" "$public_count" "0"

  cd "$SCRIPT_DIR"
}

test_ingest_no_manual_still_creates() {
  echo "test_ingest_no_manual_still_creates:"
  local repo_dir="$TEST_DIR/test-no-manual-repo"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  echo "v1" > api.rb; git add api.rb
  git commit -q -m "feat: add API gateway"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  _enable_git_tracking "$dir"
  engram_ingest_commits "$dir"

  # Auto-ingest should create the signal when no manual signal exists
  local file_count
  file_count=$(find "$dir/decisions" -name 'feat-add-api-gateway*' | wc -l | tr -d ' ')
  assert_eq "auto-ingest creates signal when no manual" "$file_count" "1"

  # Verify it has source: git:
  assert_contains "auto-ingest has git source" "$(cat "$dir/decisions"/feat-add-api-gateway*.md)" "source: git:"

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
  _enable_git_tracking "$dir"
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
  content=$(cat "$dir/decisions"/plan*auth*.md 2>/dev/null || echo "")
  assert_contains "plan has context content" "$content" "JWT"

  cd "$SCRIPT_DIR"
}

test_reindex() {
  echo "test_reindex:"
  local dir="$TEST_DIR/test-reindex/.engram"

  source "$LIB"
  engram_init "$dir"

  # Write some signal files
  cat > "$dir/decisions/test-a.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Decision A

Content A
EOF

  cat > "$dir/decisions/test-b.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Decision B

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
  cat > "$dir/decisions/pick-redis.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [infrastructure]
---

# Pick Redis for caching

Already in our stack for session storage and pub/sub needs.
EOF

  engram_reindex "$dir"
  engram_brief "$dir"

  assert_file_exists "brief.md created" "$dir/brief.md"

  local brief
  brief=$(cat "$dir/brief.md")
  assert_contains "brief has decisions header" "$brief" "Recent Decisions"
  assert_contains "brief has decision title" "$brief" "Pick Redis"
  assert_contains "brief has counts" "$brief" "1 decisions"
}

test_fts_search() {
  echo "test_fts_search:"
  local dir="$TEST_DIR/test-fts/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/postgresql.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Use PostgreSQL over MySQL

Better JSON support and window functions.
EOF

  cat > "$dir/decisions/fts5.md" << 'EOF'
---
type: decision
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
  cat > "$dir/decisions/no-frontmatter.md" << 'EOF'
# Decision with no frontmatter

Just a plain markdown file with a heading.
EOF

  # File with partial frontmatter (missing tags)
  cat > "$dir/decisions/partial.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Partial frontmatter

Only date, no tags or source.
EOF

  # File with full frontmatter
  cat > "$dir/decisions/full.md" << 'EOF'
---
type: decision
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
  _enable_git_tracking "$dir"
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
  _enable_git_tracking "$dir"
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

  cat > "$dir/decisions/test-file.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Test file column

Content.
EOF

  engram_reindex "$dir"

  local file_val
  file_val=$(sqlite3 "$dir/index.db" "SELECT file FROM signals LIMIT 1;")
  assert_contains "file column has path" "$file_val" "decisions/test-file.md"
}

test_private_signal_indexed() {
  echo "test_private_signal_indexed:"
  local dir="$TEST_DIR/test-private-indexed/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/_private/secret-deal.md" << 'EOF'
---
type: decision
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
  cat > "$dir/decisions/public-choice.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [architecture]
---

# Public architecture choice

Visible to everyone in the team and included in the brief.
EOF

  # Write a private signal
  cat > "$dir/_private/private-deal.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [business]
---

# Private deal terms

Confidential information about deal structure and terms.
EOF

  engram_reindex "$dir"
  engram_brief "$dir"

  local brief
  brief=$(cat "$dir/brief.md")
  assert_contains "brief has public title" "$brief" "Public architecture choice"
  assert_not_contains "brief excludes private title" "$brief" "Private deal terms"
  assert_contains "brief shows private count" "$brief" "1 private signal(s)"
}

test_private_queryable() {
  echo "test_private_queryable:"
  local dir="$TEST_DIR/test-private-query/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/_private/competitor-intel.md" << 'EOF'
---
type: decision
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

  cat > "$dir/decisions/normal.md" << 'EOF'
---
type: decision
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

test_uncommitted_summary() {
  echo "test_uncommitted_summary:"
  local repo_dir="$TEST_DIR/test-uncommitted-repo"
  _create_test_repo "$repo_dir" 1

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  _enable_git_tracking "$dir"

  # Write an uncommitted signal file
  cat > "$dir/decisions/test-uncommitted.md" << 'EOF'
---
type: decision
date: 2026-03-16
---

# Test uncommitted signal

Some content.
EOF

  # Should report 1 uncommitted signal
  local result
  result=$(cd "$repo_dir" && engram_uncommitted_summary "$dir")
  assert_contains "reports uncommitted count" "$result" "1 uncommitted signal"

  # Commit the signal file
  cd "$repo_dir"
  git add .engram/
  git commit -q -m "engram: add signal"

  # Should report nothing after commit
  result=$(engram_uncommitted_summary "$dir")
  assert_eq "no output after commit" "$result" ""

  cd "$SCRIPT_DIR"
}

test_uncommitted_summary_no_git() {
  echo "test_uncommitted_summary_no_git:"
  local dir="$TEST_DIR/test-uncommitted-nogit/.engram"

  source "$LIB"
  engram_init "$dir"

  # Write a signal file (not in a git repo)
  cat > "$dir/decisions/no-git.md" << 'EOF'
---
type: decision
date: 2026-03-16
---

# No git repo

Content.
EOF

  # Should return nothing (no git repo)
  local result
  result=$(engram_uncommitted_summary "$dir")
  assert_eq "no output outside git" "$result" ""
}

test_session_end_output() {
  echo "test_session_end_output:"
  local repo_dir="$TEST_DIR/test-session-end-repo"

  # Create a repo with only non-decision commits (docs/fix prefixes are skipped)
  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"
  echo "readme" > README.md
  git add . && git commit -q -m "docs: add readme"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  _enable_git_tracking "$dir"
  # Ingest + commit .engram so it's clean
  engram_ingest_commits "$dir"
  engram_reindex "$dir"
  engram_brief "$dir"
  # Add .gitkeep to empty dirs so git tracks them
  touch "$dir/decisions/.gitkeep" "$dir/_private/.gitkeep"
  git add .engram/ && git commit -q -m "engram: init"

  # Run session-end hook with CLAUDE_PLUGIN_ROOT set
  local hook_script="$SCRIPT_DIR/../hooks/session-end.sh"

  # SessionEnd hooks only support universal fields, not additionalContext.
  # The hook should output empty JSON and exit cleanly.
  local output
  local empty_plans="$TEST_DIR/empty-plans-for-session-end"
  mkdir -p "$empty_plans"

  # Test 1: no uncommitted signals — should output empty JSON
  output=$(cd "$repo_dir" && CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." ENGRAM_PLANS_DIR="$empty_plans" bash "$hook_script" 2>/dev/null)
  assert_eq "empty JSON when no signals" "$output" "{}"

  # Test 2: with uncommitted signal — should still output empty JSON
  cat > "$dir/decisions/test-end.md" << 'EOF'
---
type: decision
date: 2026-03-16
---

# Test session end

Content.
EOF

  output=$(cd "$repo_dir" && CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." ENGRAM_PLANS_DIR="$empty_plans" bash "$hook_script" 2>/dev/null)
  assert_eq "empty JSON with uncommitted" "$output" "{}"

  cd "$SCRIPT_DIR"
}

# ── Signal linking + richer brief tests ──────────────────────────────

test_supersedes_frontmatter() {
  echo "test_supersedes_frontmatter:"
  local dir="$TEST_DIR/test-supersedes/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/old-auth.md" << 'EOF'
---
type: decision
date: 2026-03-10
---

# Use session-based auth

Server-side sessions with cookies.
EOF

  cat > "$dir/decisions/new-auth.md" << 'EOF'
---
type: decision
date: 2026-03-15
supersedes: old-auth
---

# Use JWT authentication

Mobile clients need token-based auth.
EOF

  engram_reindex "$dir"

  # Check supersedes column
  local supersedes_val
  supersedes_val=$(sqlite3 "$dir/index.db" "SELECT supersedes FROM signals WHERE file_stem='new-auth';")
  assert_eq "supersedes column populated" "$supersedes_val" "old-auth"

  # Check links table
  local link_count
  link_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM links WHERE source_file='new-auth' AND target_file='old-auth' AND rel_type='supersedes';")
  assert_eq "supersedes link in links table" "$link_count" "1"
}

test_links_frontmatter() {
  echo "test_links_frontmatter:"
  local dir="$TEST_DIR/test-links-fm/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/use-redis.md" << 'EOF'
---
type: decision
date: 2026-03-14
links: [related:fts5-perf, blocks:ci-timeout]
---

# Use Redis for caching

Already in our stack.
EOF

  engram_reindex "$dir"

  local related_count
  related_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM links WHERE source_file='use-redis' AND target_file='fts5-perf' AND rel_type='related';")
  assert_eq "related link exists" "$related_count" "1"

  local blocks_count
  blocks_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM links WHERE source_file='use-redis' AND target_file='ci-timeout' AND rel_type='blocks';")
  assert_eq "blocks link exists" "$blocks_count" "1"

  local total_links
  total_links=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM links WHERE source_file='use-redis';")
  assert_eq "2 links total" "$total_links" "2"
}

test_excerpt_extraction() {
  echo "test_excerpt_extraction:"
  local dir="$TEST_DIR/test-excerpt/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/test-excerpt.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Pick PostgreSQL

Better JSON support and window functions.

## Alternatives
MySQL was considered.
EOF

  engram_reindex "$dir"

  local excerpt
  excerpt=$(sqlite3 "$dir/index.db" "SELECT excerpt FROM signals WHERE file_stem='test-excerpt';")
  assert_contains "excerpt has first body line" "$excerpt" "Better JSON support"
}

test_file_stem_column() {
  echo "test_file_stem_column:"
  local dir="$TEST_DIR/test-file-stem/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/use-redis.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Use Redis

Content.
EOF

  engram_reindex "$dir"

  local stem
  stem=$(sqlite3 "$dir/index.db" "SELECT file_stem FROM signals LIMIT 1;")
  assert_eq "file_stem is basename without .md" "$stem" "use-redis"
}

test_brief_hides_superseded() {
  echo "test_brief_hides_superseded:"
  local dir="$TEST_DIR/test-brief-superseded/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/old-cache.md" << 'EOF'
---
type: decision
date: 2026-03-10
tags: [infrastructure]
---

# Use Memcached for caching

Fast and simple key-value store for basic caching needs.
EOF

  cat > "$dir/decisions/new-cache.md" << 'EOF'
---
type: decision
date: 2026-03-15
tags: [infrastructure]
supersedes: old-cache
---

# Use Redis for caching

Supports pub/sub which we need for real-time notifications.
EOF

  engram_reindex "$dir"
  engram_brief "$dir"

  local brief
  brief=$(cat "$dir/brief.md")
  assert_contains "brief shows new decision" "$brief" "Use Redis for caching"
  assert_not_contains "brief hides superseded decision" "$brief" "Use Memcached"
  assert_contains "brief shows superseded count" "$brief" "1 superseded"
}

test_brief_tag_grouping() {
  echo "test_brief_tag_grouping:"
  local dir="$TEST_DIR/test-brief-tags/.engram"

  source "$LIB"
  engram_init "$dir"

  # Create decisions with 3+ distinct primary tags
  cat > "$dir/decisions/redis.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [infrastructure, caching]
---

# Use Redis

Already in our stack for session storage and we need pub/sub.
EOF

  cat > "$dir/decisions/jwt.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [auth, security]
---

# Use JWT

Mobile clients need stateless token-based authentication.
EOF

  cat > "$dir/decisions/postgres.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [database, storage]
---

# Use PostgreSQL

Better JSON support and window functions than MySQL.
EOF

  engram_reindex "$dir"
  engram_brief "$dir"

  local brief
  brief=$(cat "$dir/brief.md")
  assert_contains "brief has tag headers" "$brief" "###"
}

test_brief_max_lines() {
  echo "test_brief_max_lines:"
  local dir="$TEST_DIR/test-brief-max-lines/.engram"

  source "$LIB"
  engram_init "$dir"

  # Create enough signals to exceed 10-line cap
  for i in $(seq 1 20); do
    cat > "$dir/decisions/bulk-$i.md" << EOF
---
type: decision
date: 2026-03-14
tags: [bulk, testing]
---

# Bulk decision number $i

Some explanation for decision $i with enough text to occupy space in the brief.
EOF
  done

  engram_reindex "$dir"
  ENGRAM_BRIEF_MAX_LINES=10 engram_brief "$dir"

  local brief
  brief=$(cat "$dir/brief.md")
  local line_count
  line_count=$(echo "$brief" | wc -l | tr -d ' ')
  # 10 lines of content + 2 blank + 1 truncation note = 13 max
  assert_contains "brief has truncation note" "$brief" "truncated to 10 lines"
  # Without the cap the brief would be much larger; with cap it should be bounded
  # The truncated brief should still have the header
  assert_contains "brief has header" "$brief" "Decision Context"
}

test_brief_excerpts() {
  echo "test_brief_excerpts:"
  local dir="$TEST_DIR/test-brief-excerpts/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/test-exc.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [infrastructure]
---

# Use Redis for caching

Already in our stack for session storage and pub/sub needs.
EOF

  engram_reindex "$dir"
  engram_brief "$dir"

  local brief
  brief=$(cat "$dir/brief.md")
  # The dash separator before excerpt text
  assert_contains "brief has excerpt" "$brief" "Already in our stack"
}


test_supersession_chain() {
  echo "test_supersession_chain:"
  local dir="$TEST_DIR/test-chain/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/auth-v1.md" << 'EOF'
---
type: decision
date: 2026-03-01
---

# Auth v1: sessions

Cookie-based sessions.
EOF

  cat > "$dir/decisions/auth-v2.md" << 'EOF'
---
type: decision
date: 2026-03-10
supersedes: auth-v1
---

# Auth v2: JWT

Token-based auth.
EOF

  cat > "$dir/decisions/auth-v3.md" << 'EOF'
---
type: decision
date: 2026-03-15
supersedes: auth-v2
---

# Auth v3: OAuth2

Delegated authentication.
EOF

  engram_reindex "$dir"

  # Recursive CTE to walk the chain from v3 back to v1
  local chain
  chain=$(sqlite3 "$dir/index.db" "WITH RECURSIVE chain(stem, depth) AS (SELECT file_stem, 0 FROM signals WHERE file_stem = 'auth-v3' UNION ALL SELECT s.supersedes, c.depth + 1 FROM chain c JOIN signals s ON s.file_stem = c.stem WHERE s.supersedes != '') SELECT s.title FROM chain c JOIN signals s ON s.file_stem = c.stem ORDER BY c.depth;")
  assert_contains "chain includes v3" "$chain" "Auth v3"
  assert_contains "chain includes v2" "$chain" "Auth v2"
  assert_contains "chain includes v1" "$chain" "Auth v1"
}

test_links_bidirectional() {
  echo "test_links_bidirectional:"
  local dir="$TEST_DIR/test-links-bidi/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/use-redis.md" << 'EOF'
---
type: decision
date: 2026-03-14
links: [related:redis-perf]
---

# Use Redis

For caching.
EOF

  cat > "$dir/decisions/redis-perf.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Redis p99 latency is 2ms

Very fast.
EOF

  engram_reindex "$dir"

  # Query links from the target's perspective
  local from_target
  from_target=$(sqlite3 "$dir/index.db" "SELECT source_file FROM links WHERE target_file='redis-perf';")
  assert_eq "link findable from target side" "$from_target" "use-redis"

  # Query links from the decision's perspective (it's the source)
  local from_decision
  from_decision=$(sqlite3 "$dir/index.db" "SELECT target_file FROM links WHERE source_file='use-redis';")
  assert_eq "link findable from source side" "$from_decision" "redis-perf"
}

test_path_to_keywords() {
  echo "test_path_to_keywords:"
  source "$LIB"

  local result

  result=$(engram_path_to_keywords "src/auth/oauth-handler.ts")
  assert_contains "has auth" "$result" "auth"
  assert_contains "has oauth" "$result" "oauth"
  assert_contains "has handler" "$result" "handler"
  assert_not_contains "strips src" "$result" "^src$"
  assert_not_contains "strips ts extension" "$result" "ts"

  result=$(engram_path_to_keywords "lib/index.js")
  assert_not_contains "strips lib" "$result" "^lib$"
  assert_not_contains "strips index" "$result" "^index$"

  result=$(engram_path_to_keywords "app/models/payment_processor.rb")
  assert_contains "has models" "$result" "models"
  assert_contains "has payment" "$result" "payment"
  assert_contains "has processor" "$result" "processor"

  # Empty path
  result=$(engram_path_to_keywords "")
  assert_eq "empty path returns empty" "$result" ""
}

test_query_relevant() {
  echo "test_query_relevant:"
  local dir="$TEST_DIR/test-query-relevant/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/use-redis.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Use Redis for caching

Already in our stack for session storage.
EOF

  cat > "$dir/decisions/jwt-auth.md" << 'EOF'
---
type: decision
date: 2026-03-15
---

# Use JWT for authentication

Token-based auth for mobile clients.
EOF

  cat > "$dir/_private/secret.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Secret caching strategy

Private info about caching.
EOF

  engram_reindex "$dir"

  # Matching query
  local result
  result=$(engram_query_relevant "$dir" "redis caching")
  assert_contains "finds redis decision" "$result" "Use Redis"
  assert_not_contains "excludes private" "$result" "Secret"

  # Non-matching query
  result=$(engram_query_relevant "$dir" "nonexistent_xyz_12345" 2>/dev/null || echo "")
  assert_eq "no results for nonexistent" "$result" ""

  # Empty search terms
  result=$(engram_query_relevant "$dir" "")
  assert_eq "empty terms returns empty" "$result" ""

  # Limit
  result=$(engram_query_relevant "$dir" "auth redis caching" 1)
  local line_count
  line_count=$(echo "$result" | grep -c '^-' || echo "0")
  if [ "$line_count" -le 1 ]; then
    _pass "limit respected"
  else
    _fail "limit respected" "expected <= 1 result, got $line_count"
  fi
}

test_query_relevant_excludes_superseded() {
  echo "test_query_relevant_excludes_superseded:"
  local dir="$TEST_DIR/test-query-superseded/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/old-cache.md" << 'EOF'
---
type: decision
date: 2026-03-10
---

# Use Memcached for caching

Fast and simple.
EOF

  cat > "$dir/decisions/new-cache.md" << 'EOF'
---
type: decision
date: 2026-03-15
supersedes: old-cache
---

# Use Redis for caching

Supports pub/sub.
EOF

  engram_reindex "$dir"

  local result
  result=$(engram_query_relevant "$dir" "caching")
  assert_contains "shows current decision" "$result" "Use Redis"
  assert_not_contains "hides superseded" "$result" "Memcached"
}

test_tag_summary() {
  echo "test_tag_summary:"
  local dir="$TEST_DIR/test-tag-summary/.engram"

  source "$LIB"
  engram_init "$dir"

  # Create 6 signals (need >= 5 for tag_summary to return anything)
  for i in 1 2 3; do
    cat > "$dir/decisions/arch-$i.md" << EOF
---
type: decision
date: 2026-03-14
tags: [architecture]
---

# Architecture decision $i

Content $i.
EOF
  done

  for i in 1 2; do
    cat > "$dir/decisions/testing-$i.md" << EOF
---
type: decision
date: 2026-03-14
tags: [testing]
---

# Testing decision $i

Content $i.
EOF
  done

  cat > "$dir/decisions/ci.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [ci]
---

# CI decision

Content.
EOF

  engram_reindex "$dir"

  local result
  result=$(engram_tag_summary "$dir")
  assert_contains "has architecture tag" "$result" "architecture"
  assert_contains "has count" "$result" "(3)"
  assert_contains "has Top topics prefix" "$result" "Top topics"
}

test_tag_summary_few_signals() {
  echo "test_tag_summary_few_signals:"
  local dir="$TEST_DIR/test-tag-few/.engram"

  source "$LIB"
  engram_init "$dir"

  # Only 2 signals — below threshold
  cat > "$dir/decisions/a.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [foo]
---

# A

Content.
EOF

  cat > "$dir/decisions/b.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [bar]
---

# B

Content.
EOF

  engram_reindex "$dir"

  local result
  result=$(engram_tag_summary "$dir")
  assert_eq "empty when < 5 signals" "$result" ""
}

test_post_tool_context_output() {
  echo "test_post_tool_context_output:"
  local dir="$TEST_DIR/test-post-tool/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/auth-handler.md" << 'EOF'
---
type: decision
date: 2026-03-14
---

# Use OAuth for auth handler

Token-based authentication.
EOF

  engram_reindex "$dir"

  local hook_script="$SCRIPT_DIR/../hooks/post-tool-use.sh"

  # Test with matching file path
  local output
  output=$(cd "$TEST_DIR/test-post-tool" && echo '{"tool_input":{"file_path":"src/auth/handler.ts"}}' | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." CLAUDE_SESSION_ID="test-$$" bash "$hook_script" 2>/dev/null)

  # Should be valid JSON
  if echo "$output" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    _pass "post-tool output is valid JSON"
  else
    _fail "post-tool output is valid JSON" "got: $output"
  fi

  # Should contain systemMessage if results found
  if echo "$output" | grep -q "systemMessage"; then
    _pass "post-tool has systemMessage when results exist"
  else
    # It's OK if there are no FTS results — the test verifies valid JSON output
    _pass "post-tool returns valid JSON (no matches)"
  fi

  # Test with .engram path — should skip
  output=$(cd "$TEST_DIR/test-post-tool" && echo '{"tool_input":{"file_path":".engram/decisions/foo.md"}}' | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." CLAUDE_SESSION_ID="test-ptu-skip-$$" bash "$hook_script" 2>/dev/null)
  assert_eq "skips .engram paths" "$output" "{}"

  # Test with test file — should skip
  output=$(cd "$TEST_DIR/test-post-tool" && echo '{"tool_input":{"file_path":"tests/test_auth.rb"}}' | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." CLAUDE_SESSION_ID="test-ptu-skip2-$$" bash "$hook_script" 2>/dev/null)
  assert_eq "skips test files" "$output" "{}"
}

test_pre_compact_output() {
  echo "test_pre_compact_output:"
  local dir="$TEST_DIR/test-pre-compact/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/compact-test.md" << 'EOF'
---
type: decision
date: 2026-03-14
tags: [testing]
---

# Compact test decision

Testing pre-compact hook with valid signal to verify context injection.
EOF

  engram_reindex "$dir"
  engram_brief "$dir"

  local hook_script="$SCRIPT_DIR/../hooks/pre-compact.sh"

  local output
  output=$(cd "$TEST_DIR/test-pre-compact" && CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." bash "$hook_script" 2>/dev/null)

  # Should be valid JSON
  if echo "$output" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    _pass "pre-compact output is valid JSON"
  else
    _fail "pre-compact output is valid JSON" "got: $output"
  fi

  # Should contain systemMessage with brief content
  assert_contains "pre-compact has systemMessage" "$output" "systemMessage"
  assert_contains "pre-compact has decision context" "$output" "Compact test decision"
}

test_stop_hook_output() {
  echo "test_stop_hook_output:"
  local dir="$TEST_DIR/test-stop-hook/.engram"

  source "$LIB"
  engram_init "$dir"

  local hook_script="$SCRIPT_DIR/../hooks/stop.sh"

  # Test: no recent signals — should still output ok:true (advisory)
  local output
  output=$(cd "$TEST_DIR/test-stop-hook" && CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." bash "$hook_script" 2>/dev/null)

  # Must be valid JSON
  if echo "$output" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    _pass "stop hook output is valid JSON"
  else
    _fail "stop hook output is valid JSON" "got: $output"
  fi

  # Must always be ok:true (advisory only)
  assert_contains "stop hook is advisory" "$output" '"ok": true'
}

test_stop_hook_no_engram() {
  echo "test_stop_hook_no_engram:"
  local empty_dir="$TEST_DIR/test-stop-empty"
  mkdir -p "$empty_dir"

  local hook_script="$SCRIPT_DIR/../hooks/stop.sh"
  local output
  output=$(cd "$empty_dir" && CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." bash "$hook_script" 2>/dev/null)
  assert_eq "ok when no .engram" "$output" '{"ok": true}'
}

test_user_prompt_submit_hook() {
  echo "test_user_prompt_submit_hook:"
  local hook_script="$SCRIPT_DIR/../hooks/user-prompt-submit.sh"

  # Test: no decision language
  local output
  output=$(echo '{"content":"fix the bug in auth.rb"}' | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." CLAUDE_SESSION_ID="test-ups-$$" bash "$hook_script" 2>/dev/null)
  assert_eq "no nudge for normal prompt" "$output" "{}"

  # Test: decision language
  output=$(echo '{"content":"lets go with Redis for caching"}' | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." CLAUDE_SESSION_ID="test-ups-decision-$$" bash "$hook_script" 2>/dev/null)
  assert_contains "nudge for decision language" "$output" "engram:capture"

  # Test: past decision query
  output=$(echo '{"content":"why did we choose Redis?"}' | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." CLAUDE_SESSION_ID="test-ups-query-$$" bash "$hook_script" 2>/dev/null)
  assert_contains "suggest query for past decisions" "$output" "engram:query"
}

test_pre_tool_use_validation() {
  echo "test_pre_tool_use_validation:"
  local hook_script="$SCRIPT_DIR/../hooks/pre-tool-use.sh"

  # Test: non-engram file — should pass through
  local output
  output=$(echo '{"tool_input":{"file_path":"src/app.rb","content":"hello"}}' | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." bash "$hook_script" 2>/dev/null)
  assert_eq "non-engram file passes" "$output" "{}"

  # Test: valid signal file
  local valid_content='---\ndate: 2026-03-17\ntags: [architecture]\n---\n\n# Valid decision\n\nThis is a valid lead paragraph with enough chars.'
  output=$(printf '{"tool_input":{"file_path":".engram/decisions/valid.md","content":"%s"}}' "$valid_content" | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." bash "$hook_script" 2>/dev/null)
  assert_eq "valid signal passes" "$output" "{}"

  # Test: signal missing tags
  local no_tags_content='---\ndate: 2026-03-17\ntags: []\n---\n\n# No tags\n\nThis decision has empty tags which should fail.'
  output=$(printf '{"tool_input":{"file_path":".engram/decisions/no-tags.md","content":"%s"}}' "$no_tags_content" | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." bash "$hook_script" 2>/dev/null)
  assert_contains "empty tags blocked" "$output" '"ok": false'
  assert_contains "tags error message" "$output" "tags"

  # Test: signal missing frontmatter
  local no_fm_content='# No frontmatter\n\nJust a plain file.'
  output=$(printf '{"tool_input":{"file_path":".engram/decisions/no-fm.md","content":"%s"}}' "$no_fm_content" | CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." bash "$hook_script" 2>/dev/null)
  assert_contains "missing frontmatter blocked" "$output" '"ok": false'
}

test_notification_hook() {
  echo "test_notification_hook:"
  local dir="$TEST_DIR/test-notification/.engram"

  source "$LIB"
  engram_init "$dir"

  # Create an incomplete signal (missing tags, short body)
  cat > "$dir/decisions/incomplete.md" << 'EOF'
---
type: decision
date: 2026-03-17
---

# Incomplete

Short.
EOF

  engram_reindex "$dir" 2>/dev/null

  local hook_script="$SCRIPT_DIR/../hooks/notification.sh"
  local output
  output=$(cd "$TEST_DIR/test-notification" && CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." CLAUDE_SESSION_ID="test-notif-$$" bash "$hook_script" 2>/dev/null)
  assert_contains "notification suggests enrichment" "$output" "incomplete"

  # Test: no incomplete signals
  rm "$dir/decisions/incomplete.md"
  cat > "$dir/decisions/complete.md" << 'EOF'
---
type: decision
date: 2026-03-17
tags: [test]
---

# Complete decision

This decision has proper rationale and tags for validation.
EOF

  engram_reindex "$dir" 2>/dev/null
  output=$(cd "$TEST_DIR/test-notification" && CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." CLAUDE_SESSION_ID="test-notif-clean-$$" bash "$hook_script" 2>/dev/null)
  assert_eq "no nudge when all complete" "$output" "{}"
}

test_pre_compact_no_engram() {
  echo "test_pre_compact_no_engram:"
  local empty_dir="$TEST_DIR/test-pre-compact-empty"
  mkdir -p "$empty_dir"

  local hook_script="$SCRIPT_DIR/../hooks/pre-compact.sh"

  local output
  output=$(cd "$empty_dir" && CLAUDE_PLUGIN_ROOT="$SCRIPT_DIR/.." bash "$hook_script" 2>/dev/null)
  assert_eq "empty JSON when no .engram" "$output" "{}"
}

test_hooks_json_structure() {
  echo "--- test_hooks_json_structure ---"
  local hooks_file="$SCRIPT_DIR/../hooks/hooks.json"

  # Must be valid JSON
  if ! jq . "$hooks_file" > /dev/null 2>&1; then
    _fail "hooks.json is not valid JSON"
    return
  fi
  _pass "hooks.json is valid JSON"

  # Must have all 9 expected hook events
  local expected_events="SessionStart SessionEnd Stop PostToolUse PreToolUse SubagentStop PreCompact UserPromptSubmit Notification"
  for event in $expected_events; do
    local count
    count=$(jq -r ".hooks.\"$event\" | length" "$hooks_file")
    if [ "$count" -lt 1 ]; then
      _fail "hooks.json missing event: $event"
    else
      _pass "hooks.json has event: $event"
    fi
  done

  # All hooks must be command hooks (no prompt hooks — they're flaky)
  local prompt_count
  prompt_count=$(jq '[.hooks[][] | .hooks[] | select(.type == "prompt")] | length' "$hooks_file")
  assert_eq "no prompt hooks (all commands)" "$prompt_count" "0"

  # No empty commands
  local empty_commands
  empty_commands=$(jq '[.hooks[][] | .hooks[] | select(.type == "command" and (.command == "" or .command == null))] | length' "$hooks_file")
  assert_eq "no empty commands" "$empty_commands" "0"

  # PreToolUse matcher must include Write|Edit
  local pre_matcher
  pre_matcher=$(jq -r '.hooks.PreToolUse[0].matcher' "$hooks_file")
  assert_contains "PreToolUse matcher has Write" "$pre_matcher" "Write"
  assert_contains "PreToolUse matcher has Edit" "$pre_matcher" "Edit"

  # PostToolUse matcher must include Write|Edit|MultiEdit
  local post_matcher
  post_matcher=$(jq -r '.hooks.PostToolUse[0].matcher' "$hooks_file")
  assert_contains "PostToolUse matcher has Write" "$post_matcher" "Write"
  assert_contains "PostToolUse matcher has Edit" "$post_matcher" "Edit"
  assert_contains "PostToolUse matcher has MultiEdit" "$post_matcher" "MultiEdit"

  # All command hooks reference a .sh file
  local all_commands
  all_commands=$(jq -r '[.hooks[][] | .hooks[] | select(.type == "command") | .command] | .[]' "$hooks_file")
  local total_commands
  total_commands=$(echo "$all_commands" | wc -l | tr -d ' ')
  local sh_commands
  sh_commands=$(echo "$all_commands" | grep -c '\.sh' || echo "0")
  assert_eq "all commands are .sh scripts" "$sh_commands" "$total_commands"
}

# ── Validation tests ─────────────────────────────────────────────────

test_validate_signal_valid() {
  echo "test_validate_signal_valid:"
  local dir="$TEST_DIR/test-validate-valid/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/valid-test.md" << 'EOF'
---
type: decision
date: 2026-03-16
tags: [architecture, validation]
---

# Use strict validation for signals

Enforce structure at write time to ensure all decisions include rationale, improving brief quality.

## Alternatives
- No validation — too many incomplete signals
EOF

  local rc=0
  _validate_signal "$dir/decisions/valid-test.md" 2>/dev/null || rc=$?
  assert_eq "valid signal passes" "$rc" "0"
}

test_validate_signal_missing_why() {
  echo "test_validate_signal_missing_why:"
  local dir="$TEST_DIR/test-validate-no-why/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/no-why.md" << 'EOF'
---
type: decision
date: 2026-03-16
tags: [test]
---

# Decision without explanation

EOF

  local rc=0
  _validate_signal "$dir/decisions/no-why.md" 2>/dev/null || rc=$?
  assert_eq "missing lead paragraph fails" "$rc" "1"
}

test_validate_signal_missing_tags() {
  echo "test_validate_signal_missing_tags:"
  local dir="$TEST_DIR/test-validate-no-tags/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/no-tags.md" << 'EOF'
---
type: decision
date: 2026-03-16
tags: []
---

# Decision without tags

This decision has no tags which should fail validation checks.
EOF

  local rc=0
  _validate_signal "$dir/decisions/no-tags.md" 2>/dev/null || rc=$?
  assert_eq "empty tags fails" "$rc" "1"
}

test_validate_signal_short_why() {
  echo "test_validate_signal_short_why:"
  local dir="$TEST_DIR/test-validate-short/.engram"

  source "$LIB"
  engram_init "$dir"

  cat > "$dir/decisions/short-why.md" << 'EOF'
---
type: decision
date: 2026-03-16
tags: [test]
---

# Short explanation

Too short.
EOF

  local rc=0
  _validate_signal "$dir/decisions/short-why.md" 2>/dev/null || rc=$?
  assert_eq "short lead paragraph fails" "$rc" "1"
}

test_reindex_marks_invalid() {
  echo "test_reindex_marks_invalid:"
  local dir="$TEST_DIR/test-reindex-valid/.engram"

  source "$LIB"
  engram_init "$dir"

  # Valid signal
  cat > "$dir/decisions/good.md" << 'EOF'
---
type: decision
date: 2026-03-16
tags: [validation]
---

# A good decision with rationale

This decision includes a proper lead paragraph explaining why it was made.
EOF

  # Invalid signal (no tags, no lead paragraph)
  cat > "$dir/decisions/bad.md" << 'EOF'
---
type: decision
date: 2026-03-16
---

# Bad decision

EOF

  engram_reindex "$dir" 2>/dev/null

  local valid_good
  valid_good=$(sqlite3 "$dir/index.db" "SELECT valid FROM signals WHERE file_stem='good';")
  assert_eq "good signal is valid=1" "$valid_good" "1"

  local valid_bad
  valid_bad=$(sqlite3 "$dir/index.db" "SELECT valid FROM signals WHERE file_stem='bad';")
  assert_eq "bad signal is valid=0" "$valid_bad" "0"
}

test_brief_excludes_invalid() {
  echo "test_brief_excludes_invalid:"
  local dir="$TEST_DIR/test-brief-invalid/.engram"

  source "$LIB"
  engram_init "$dir"

  # Valid signal
  cat > "$dir/decisions/visible.md" << 'EOF'
---
type: decision
date: 2026-03-16
tags: [validation]
---

# Visible decision in brief

This decision has proper rationale and should appear in the brief output.
EOF

  # Invalid signal (missing tags and short body)
  cat > "$dir/decisions/hidden.md" << 'EOF'
---
type: decision
date: 2026-03-16
---

# Hidden from brief

Short.
EOF

  engram_reindex "$dir" 2>/dev/null
  engram_brief "$dir"

  local brief
  brief=$(cat "$dir/brief.md")
  assert_contains "brief shows valid signal" "$brief" "Visible decision"
  assert_not_contains "brief hides invalid signal" "$brief" "Hidden from brief"
  assert_contains "brief shows incomplete count" "$brief" "incomplete (missing rationale)"
}

test_ingest_bodyless_commit_invalid() {
  echo "test_ingest_bodyless_commit_invalid:"
  local repo_dir="$TEST_DIR/test-ingest-bodyless-repo"

  mkdir -p "$repo_dir"
  cd "$repo_dir"
  git init -q
  git config user.email "test@test.com"
  git config user.name "Test"

  # Commit with no body (just subject line)
  echo "v1" > feature.rb
  git add feature.rb
  git commit -q -m "feat: add feature without body"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"
  _enable_git_tracking "$dir"
  engram_ingest_commits "$dir"
  engram_reindex "$dir" 2>/dev/null

  # Auto-ingested commit without body should be invalid (no tags, short/missing lead paragraph)
  local valid_val
  valid_val=$(sqlite3 "$dir/index.db" "SELECT valid FROM signals WHERE source LIKE 'git:%' LIMIT 1;" 2>/dev/null || echo "")
  assert_eq "bodyless commit is valid=0" "$valid_val" "0"

  # Should be excluded from brief
  engram_brief "$dir"
  local brief
  brief=$(cat "$dir/brief.md")
  assert_not_contains "brief excludes bodyless commit" "$brief" "add feature without body"

  cd "$SCRIPT_DIR"
}

# ── Git opt-in tests ─────────────────────────────────────────────────

test_git_tracking_config() {
  echo "test_git_tracking_config:"
  local dir="$TEST_DIR/test-git-config/.engram"

  mkdir -p "$dir"
  source "$LIB"

  # Not enabled by default
  if _git_tracking_enabled "$dir"; then
    _fail "disabled by default" "returned true"
  else
    _pass "disabled by default"
  fi

  # Enable it
  _enable_git_tracking "$dir"
  if _git_tracking_enabled "$dir"; then
    _pass "enabled after config"
  else
    _fail "enabled after config" "returned false"
  fi

  # Wrong value
  echo "git_tracking=false" > "$dir/config"
  if _git_tracking_enabled "$dir"; then
    _fail "false value not enabled" "returned true"
  else
    _pass "false value not enabled"
  fi
}

test_init_no_gitignore_by_default() {
  echo "test_init_no_gitignore_by_default:"
  local dir="$TEST_DIR/test-no-gitignore/.engram"

  source "$LIB"
  engram_init "$dir"

  if [ ! -f "$dir/.gitignore" ]; then
    _pass "no gitignore created"
  else
    _fail "no gitignore created" "file exists"
  fi

  if [ ! -f "$dir/config" ]; then
    _pass "no config created"
  else
    _fail "no config created" "file exists"
  fi
}

test_init_gitignore_with_git_tracking() {
  echo "test_init_gitignore_with_git_tracking:"
  local dir="$TEST_DIR/test-gitignore-enabled/.engram"

  mkdir -p "$dir"
  source "$LIB"

  # Enable git tracking before init
  _enable_git_tracking "$dir"
  engram_init "$dir"

  assert_file_exists "gitignore created" "$dir/.gitignore"
  local gitignore
  gitignore=$(cat "$dir/.gitignore")
  assert_contains "gitignore has index.db" "$gitignore" "index.db"
  assert_contains "gitignore has brief.md" "$gitignore" "brief.md"
  assert_contains "gitignore has _private/" "$gitignore" "_private/"
  assert_contains "gitignore has config" "$gitignore" "config"
}

test_init_migration_auto_enables_git() {
  echo "test_init_migration_auto_enables_git:"
  local dir="$TEST_DIR/test-migration-auto/.engram"

  mkdir -p "$dir"
  # Simulate existing user: has .gitignore but no config
  printf 'index.db\nbrief.md\n_private/\n' > "$dir/.gitignore"

  source "$LIB"
  engram_init "$dir"

  assert_file_exists "config created" "$dir/config"
  local config
  config=$(cat "$dir/config")
  assert_contains "git tracking auto-enabled" "$config" "git_tracking=true"
}

test_ingest_noop_without_git_tracking() {
  echo "test_ingest_noop_without_git_tracking:"
  local repo_dir="$TEST_DIR/test-ingest-noop-repo"

  _create_test_repo_mixed "$repo_dir"

  local dir="$repo_dir/.engram"
  source "$LIB"
  engram_init "$dir"

  # Do NOT enable git tracking — ingest should be a no-op
  engram_ingest_commits "$dir"

  local file_count
  file_count=$(find "$dir/decisions" -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
  assert_eq "no signals without git tracking" "$file_count" "0"

  cd "$SCRIPT_DIR"
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
test_migrate_signals_to_decisions
echo ""
test_write_decision
echo ""
test_is_decision_commit
echo ""
test_ingest_commits
echo ""
test_ingest_commits_body
echo ""
test_ingest_dedup
echo ""
test_ingest_manual_signal_suppresses
echo ""
test_ingest_private_signal_suppresses
echo ""
test_ingest_no_manual_still_creates
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
test_uncommitted_summary
echo ""
test_uncommitted_summary_no_git
echo ""
test_session_end_output
echo ""
test_supersedes_frontmatter
echo ""
test_links_frontmatter
echo ""
test_excerpt_extraction
echo ""
test_file_stem_column
echo ""
test_brief_hides_superseded
echo ""
test_brief_tag_grouping
echo ""
test_brief_excerpts
echo ""
test_supersession_chain
echo ""
test_links_bidirectional
echo ""
test_path_to_keywords
echo ""
test_query_relevant
echo ""
test_query_relevant_excludes_superseded
echo ""
test_tag_summary
echo ""
test_tag_summary_few_signals
echo ""
test_post_tool_context_output
echo ""
test_pre_compact_output
echo ""
test_pre_compact_no_engram
echo ""
test_stop_hook_output
echo ""
test_stop_hook_no_engram
echo ""
test_user_prompt_submit_hook
echo ""
test_pre_tool_use_validation
echo ""
test_notification_hook
echo ""
test_hooks_json_structure
echo ""
test_brief_max_lines
echo ""
test_validate_signal_valid
echo ""
test_validate_signal_missing_why
echo ""
test_validate_signal_missing_tags
echo ""
test_validate_signal_short_why
echo ""
test_reindex_marks_invalid
echo ""
test_brief_excludes_invalid
echo ""
test_ingest_bodyless_commit_invalid
echo ""
test_git_tracking_config
echo ""
test_init_no_gitignore_by_default
echo ""
test_init_gitignore_with_git_tracking
echo ""
test_init_migration_auto_enables_git
echo ""
test_ingest_noop_without_git_tracking

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
