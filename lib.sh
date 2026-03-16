#!/usr/bin/env bash
# engram core library — sourced by hooks and tests
# Pure functions, no side effects at source time.
set -euo pipefail

# Resolve schema.sql relative to this file
ENGRAM_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGRAM_SCHEMA_FILE="${ENGRAM_SCHEMA_FILE:-$ENGRAM_LIB_DIR/schema.sql}"

# ── FTS5 check ────────────────────────────────────────────────────────

_check_fts5() {
  if ! sqlite3 ':memory:' "CREATE VIRTUAL TABLE _fts5_test USING fts5(x);" 2>/dev/null; then
    echo "engram: SQLite FTS5 module not available." >&2
    echo "engram: Install SQLite with FTS5 support:" >&2
    echo "engram:   macOS:  brew install sqlite && export PATH=\"\$(brew --prefix sqlite)/bin:\$PATH\"" >&2
    echo "engram:   Ubuntu: sudo apt-get install -y libsqlite3-0" >&2
    echo "engram:   Alpine: apk add sqlite" >&2
    return 1
  fi
}

# ── Init ──────────────────────────────────────────────────────────────

engram_init() {
  local dir="$1"
  _check_fts5
  mkdir -p "$dir"/{decisions,findings,issues}
  mkdir -p "$dir"/private/{decisions,findings,issues}
  if [ ! -f "$dir/.gitignore" ]; then
    printf 'index.db\nprivate/\n' > "$dir/.gitignore"
  elif ! grep -qx 'private/' "$dir/.gitignore"; then
    echo 'private/' >> "$dir/.gitignore"
  fi
  if [ ! -f "$dir/index.db" ]; then
    sqlite3 "$dir/index.db" < "$ENGRAM_SCHEMA_FILE"
  fi
}

# ── Slug helper ───────────────────────────────────────────────────────

_slugify() {
  # Lowercase, replace non-alphanum with hyphens, collapse, trim, truncate
  echo "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9]/-/g' \
    | sed 's/--*/-/g' \
    | sed 's/^-//;s/-$//' \
    | cut -c1-50
}

# ── Commit classification ────────────────────────────────────────────

# Conventional commit prefixes that represent decisions
_DECISION_PREFIXES="feat|feat!|breaking|refactor|perf"

# Prefixes that are never decisions
_SKIP_PREFIXES="fix|docs|test|tests|chore|ci|style|build|typo|wip|merge"

# Commit message patterns that indicate architectural/dependency decisions
_DECISION_PATTERNS="migrate|switch to|replace|drop|remove|add support|adopt|introduce|upgrade|deprecate|rewrite"

# Files whose presence in a commit's diff indicates a decision
_DECISION_FILES="Gemfile|package.json|Cargo.toml|go.mod|requirements.txt|Pipfile|pyproject.toml|schema.rb|structure.sql|docker-compose|Dockerfile|\.github/workflows|\.circleci|Makefile"

_is_decision_commit() {
  local subject="$1"
  local hash="$2"

  local lower_subject
  lower_subject=$(printf '%s' "$subject" | tr '[:upper:]' '[:lower:]')

  # Skip: conventional commit prefixes that aren't decisions
  if printf '%s' "$lower_subject" | grep -qE "^(${_SKIP_PREFIXES})[:(]"; then
    return 1
  fi

  # Skip: merge commits, version bumps, trivial messages
  if printf '%s' "$lower_subject" | grep -qE "^(merge branch|merge pull|bump version|wip$|wip:|fixup!|squash!)"; then
    return 1
  fi

  # Match: conventional commit prefixes that are decisions
  if printf '%s' "$lower_subject" | grep -qE "^(${_DECISION_PREFIXES})[:(]"; then
    return 0
  fi

  # Match: keyword patterns in the message
  if printf '%s' "$lower_subject" | grep -qiE "(${_DECISION_PATTERNS})"; then
    return 0
  fi

  # Match: significant file changes (schema, deps, CI, infra)
  local files_changed
  files_changed=$(git diff-tree --no-commit-id --name-only -r "$hash" 2>/dev/null || echo "")
  if printf '%s' "$files_changed" | grep -qE "(${_DECISION_FILES})"; then
    return 0
  fi

  # Default: not a decision
  return 1
}

# ── Commit ingestion ─────────────────────────────────────────────────

engram_ingest_commits() {
  local dir="$1"

  # Must be in a git repo
  git rev-parse --show-toplevel >/dev/null 2>&1 || return 0

  local last_commit=""
  if [ -f "$dir/index.db" ]; then
    last_commit=$(sqlite3 "$dir/index.db" "SELECT value FROM meta WHERE key = 'last_commit';" 2>/dev/null || echo "")
  fi

  local log_output
  if [ -z "$last_commit" ]; then
    # First run (brownfield bootstrap): last 50 commits
    log_output=$(git log -50 --format='%H|%s|%ai' 2>/dev/null || echo "")
  else
    # Incremental: commits since last ingested
    log_output=$(git log "$last_commit..HEAD" --format='%H|%s|%ai' 2>/dev/null || echo "")
  fi

  [ -z "$log_output" ] && return 0

  local new_head=""
  local count=0

  while IFS='|' read -r hash subject date_str; do
    [ -z "$hash" ] && continue

    # Track newest commit (first line of output)
    [ -z "$new_head" ] && new_head="$hash"

    # Only ingest commits that look like decisions
    if ! _is_decision_commit "$subject" "$hash"; then
      continue
    fi

    # Dedup: skip if file with this source already exists
    if grep -rql "source: git:$hash" "$dir/decisions/" 2>/dev/null; then
      continue
    fi

    local date
    date=$(echo "$date_str" | cut -d' ' -f1)
    local slug
    slug=$(_slugify "$subject")
    [ -z "$slug" ] && slug="commit-${hash:0:7}"

    local filepath="$dir/decisions/${date}-${slug}.md"

    # Avoid filename collisions
    if [ -f "$filepath" ]; then
      filepath="$dir/decisions/${date}-${slug}-${hash:0:7}.md"
    fi

    local stat
    stat=$(git show --stat --format='' "$hash" 2>/dev/null || echo "")

    cat > "$filepath" << SIGNAL
---
date: $date
source: git:$hash
---

# $subject

$stat
SIGNAL

    count=$((count + 1))
  done <<< "$log_output"

  # Update last_commit pointer (always advance, even if no decisions found)
  if [ -n "$new_head" ]; then
    sqlite3 "$dir/index.db" "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_commit', '$new_head');" 2>/dev/null || true
  fi
}

# ── Plan ingestion ────────────────────────────────────────────────────

engram_ingest_plans() {
  local dir="$1"

  # Resolve project-scoped plans directory.
  # Claude Code stores per-project data under ~/.claude/projects/<mangled-path>/
  # where <mangled-path> is the absolute CWD with / replaced by -.
  # The global ~/.claude/plans/ is shared across ALL projects and must NOT be
  # ingested — doing so leaks signals from unrelated repos.
  local plans_dir="${ENGRAM_PLANS_DIR:-}"
  if [ -z "$plans_dir" ]; then
    local project_key
    project_key=$(pwd | sed 's|/|-|g')
    plans_dir="$HOME/.claude/projects/${project_key}/plans"
  fi

  # Safety: never ingest from the global plans directory — it contains
  # plans from ALL projects and would leak unrelated signals.
  local global_plans
  global_plans=$(cd "$HOME/.claude/plans" 2>/dev/null && pwd -P 2>/dev/null || echo "")
  if [ -n "$global_plans" ]; then
    local resolved_plans
    resolved_plans=$(cd "$plans_dir" 2>/dev/null && pwd -P 2>/dev/null || echo "")
    if [ "$resolved_plans" = "$global_plans" ]; then
      return 0
    fi
  fi

  [ -d "$plans_dir" ] || return 0

  local last_ingest=""
  if [ -f "$dir/index.db" ]; then
    last_ingest=$(sqlite3 "$dir/index.db" "SELECT value FROM meta WHERE key = 'last_plan_ingest';" 2>/dev/null || echo "")
  fi

  local today
  today=$(date +%Y-%m-%d)

  # Find plan files (optionally filtered by modification time)
  local plan_files
  if [ -n "$last_ingest" ]; then
    # Find files modified since last ingest
    plan_files=$(find "$plans_dir" -name '*.md' -newer "$dir/index.db" 2>/dev/null || echo "")
  else
    plan_files=$(find "$plans_dir" -name '*.md' 2>/dev/null || echo "")
  fi

  [ -z "$plan_files" ] && return 0

  while IFS= read -r plan_file; do
    [ -z "$plan_file" ] && continue
    [ -f "$plan_file" ] || continue

    local basename
    basename=$(basename "$plan_file" .md)

    # Dedup: skip if file with this source already exists
    if [ -n "$(find "$dir/decisions" -name '*.md' 2>/dev/null)" ] && grep -rql "source: plan:$basename" "$dir/decisions/" 2>/dev/null; then
      continue
    fi

    # Extract title: first H1 heading
    local title
    title=$(grep -m1 '^# ' "$plan_file" 2>/dev/null | sed 's/^# //' || echo "")
    [ -z "$title" ] && title="$basename"

    # Extract context section (between ## Context and next ##)
    local context
    context=$(awk '/^## Context/{found=1; next} found && /^## /{exit} found{print}' "$plan_file" 2>/dev/null || echo "")

    # Skip plans with no extractable context
    [ -z "$context" ] && continue

    local slug
    slug=$(_slugify "$title")
    [ -z "$slug" ] && slug="plan-$basename"

    local filepath="$dir/decisions/${today}-plan-${slug}.md"

    cat > "$filepath" << SIGNAL
---
date: $today
source: plan:$basename
---

# $title

$context
SIGNAL

  done <<< "$plan_files"

  # Update last_plan_ingest timestamp
  sqlite3 "$dir/index.db" "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_plan_ingest', '$(date -u +%Y-%m-%dT%H:%M:%SZ)');" 2>/dev/null || true
}

# ── Reindex ───────────────────────────────────────────────────────────

engram_reindex() {
  local dir="$1"

  # Preserve meta table data before dropping
  local meta_backup=""
  if [ -f "$dir/index.db" ]; then
    meta_backup=$(sqlite3 "$dir/index.db" "SELECT key || '|' || value FROM meta;" 2>/dev/null || echo "")
  fi

  # Recreate index from scratch
  rm -f "$dir/index.db"
  sqlite3 "$dir/index.db" < "$ENGRAM_SCHEMA_FILE"

  # Restore meta data
  if [ -n "$meta_backup" ]; then
    while IFS='|' read -r key value; do
      [ -z "$key" ] && continue
      local esc_value="${value//\'/\'\'}"
      sqlite3 "$dir/index.db" "INSERT OR REPLACE INTO meta (key, value) VALUES ('$key', '$esc_value');"
    done <<< "$meta_backup"
  fi

  # Index all public signal files
  for type_dir in decisions findings issues; do
    local type_name
    case "$type_dir" in
      decisions) type_name="decision" ;;
      findings)  type_name="finding" ;;
      issues)    type_name="issue" ;;
    esac

    for f in "$dir/$type_dir"/*.md; do
      [ -f "$f" ] || continue
      _index_file "$dir" "$f" "$type_name" 0
    done
  done

  # Index all private signal files
  for type_dir in decisions findings issues; do
    local type_name
    case "$type_dir" in
      decisions) type_name="decision" ;;
      findings)  type_name="finding" ;;
      issues)    type_name="issue" ;;
    esac

    for f in "$dir/private/$type_dir"/*.md; do
      [ -f "$f" ] || continue
      _index_file "$dir" "$f" "$type_name" 1
    done
  done
}

_index_file() {
  local dir="$1"
  local filepath="$2"
  local type="$3"
  local private="${4:-0}"

  # Parse frontmatter
  local in_frontmatter=0
  local fm_date="" fm_tags="[]" fm_source=""
  local body=""
  local title=""
  local past_frontmatter=0

  while IFS= read -r line; do
    if [ "$past_frontmatter" -eq 0 ]; then
      if [ "$line" = "---" ]; then
        if [ "$in_frontmatter" -eq 0 ]; then
          in_frontmatter=1
          continue
        else
          past_frontmatter=1
          continue
        fi
      fi
      if [ "$in_frontmatter" -eq 1 ]; then
        case "$line" in
          date:*)   fm_date="${line#date:}"; fm_date="${fm_date# }";;
          source:*) fm_source="${line#source:}"; fm_source="${fm_source# }";;
          tags:*)   fm_tags="${line#tags:}"; fm_tags="${fm_tags# }";;
        esac
        continue
      fi
    fi

    # Extract title from first H1
    if [ -z "$title" ] && [[ "$line" == "# "* ]]; then
      title="${line#\# }"
      continue
    fi

    body="$body$line"$'\n'
  done < "$filepath"

  [ -z "$fm_date" ] && fm_date=$(date +%Y-%m-%d)
  [ -z "$title" ] && title=$(basename "$filepath" .md)

  # Combine title + body as content
  local content="$title"$'\n'"$body"

  # Use sed for SQL escaping (bash string replacement is unreliable with quotes)
  local esc_title esc_content esc_tags esc_source esc_file
  esc_title=$(printf '%s' "$title" | sed "s/'/''/g")
  esc_content=$(printf '%s' "$content" | sed "s/'/''/g")
  esc_tags=$(printf '%s' "$fm_tags" | sed "s/'/''/g")
  esc_source=$(printf '%s' "$fm_source" | sed "s/'/''/g")
  esc_file=$(printf '%s' "$filepath" | sed "s/'/''/g")

  sqlite3 "$dir/index.db" "INSERT INTO signals (type, title, content, tags, source, date, file, private) VALUES ('$type', '$esc_title', '$esc_content', '$esc_tags', '$esc_source', '$fm_date', '$esc_file', $private);"
}

# ── Brief generation ──────────────────────────────────────────────────

engram_brief() {
  local dir="$1"

  [ -f "$dir/index.db" ] || return 0

  local decision_count finding_count issue_count
  decision_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision' AND private=0;" 2>/dev/null || echo "0")
  finding_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='finding' AND private=0;" 2>/dev/null || echo "0")
  issue_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='issue' AND private=0;" 2>/dev/null || echo "0")

  local brief="# Decision Context ($decision_count decisions, $issue_count issues, $finding_count findings)"

  local decisions
  decisions=$(sqlite3 -separator $'\n' "$dir/index.db" "SELECT '- [' || date || '] ' || title FROM signals WHERE type='decision' AND private=0 ORDER BY date DESC LIMIT 15;" 2>/dev/null || echo "")
  if [ -n "$decisions" ]; then
    brief="$brief"$'\n\n'"## Recent Decisions"$'\n'"$decisions"
  fi

  local issues
  issues=$(sqlite3 -separator $'\n' "$dir/index.db" "SELECT '- [' || date || '] ' || title FROM signals WHERE type='issue' AND private=0 ORDER BY date DESC LIMIT 10;" 2>/dev/null || echo "")
  if [ -n "$issues" ]; then
    brief="$brief"$'\n\n'"## Open Issues"$'\n'"$issues"
  fi

  local findings
  findings=$(sqlite3 -separator $'\n' "$dir/index.db" "SELECT '- [' || date || '] ' || title FROM signals WHERE type='finding' AND private=0 ORDER BY date DESC LIMIT 10;" 2>/dev/null || echo "")
  if [ -n "$findings" ]; then
    brief="$brief"$'\n\n'"## Recent Findings"$'\n'"$findings"
  fi

  # Show private signal count if any exist
  local private_count
  private_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE private=1;" 2>/dev/null || echo "0")
  if [ "$private_count" -gt 0 ]; then
    brief="$brief"$'\n\n'"# + $private_count private signals (not shown)"
  fi

  printf '%s\n' "$brief" > "$dir/brief.md"
}

# ── Uncommitted signal summary ─────────────────────────────────────

engram_uncommitted_summary() {
  local dir="$1"
  git rev-parse --show-toplevel >/dev/null 2>&1 || return 0

  local uncommitted
  uncommitted=$(git status --porcelain "$dir/decisions" "$dir/findings" "$dir/issues" 2>/dev/null | grep -v '^$')
  [ -z "$uncommitted" ] && return 0

  local count
  count=$(echo "$uncommitted" | wc -l | tr -d ' ')
  echo "$count uncommitted signal(s) in .engram/"
}
