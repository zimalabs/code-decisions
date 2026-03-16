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
  mkdir -p "$dir"/signals
  mkdir -p "$dir"/_private
  if [ ! -f "$dir/.gitignore" ]; then
    printf 'index.db\nbrief.md\n_private/\n' > "$dir/.gitignore"
  else
    for entry in '_private/' 'brief.md'; do
      grep -qx "$entry" "$dir/.gitignore" || echo "$entry" >> "$dir/.gitignore"
    done
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

# ── Signal helpers ───────────────────────────────────────────────────

_file_stem() {
  basename "$1" .md
}

_extract_excerpt() {
  echo "$1" | grep -v '^$' | grep -v '^#' | head -1 | cut -c1-120
}

_parse_links() {
  local str="$1"
  str="${str#\[}"; str="${str%\]}"
  echo "$str" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while IFS=: read -r rel target; do
    [ -n "$rel" ] && [ -n "$target" ] && printf '%s|%s\n' "$rel" "$target"
  done
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
    if grep -rql "source: git:$hash" "$dir/signals/" 2>/dev/null; then
      continue
    fi

    local date
    date=$(echo "$date_str" | cut -d' ' -f1)
    local slug
    slug=$(_slugify "$subject")
    [ -z "$slug" ] && slug="commit-${hash:0:7}"

    local filepath="$dir/signals/decision-${slug}.md"

    # Avoid filename collisions
    if [ -f "$filepath" ]; then
      filepath="$dir/signals/decision-${slug}-${hash:0:7}.md"
    fi

    local stat
    stat=$(git show --stat --format='' "$hash" 2>/dev/null || echo "")

    # Extract commit body, strip Co-Authored-By trailers and trailing blank lines
    local body
    body=$(git log -1 --format='%b' "$hash" 2>/dev/null | grep -iv '^Co-Authored-By:' | sed -e '/./,$!d' -e :a -e '/^\n*$/{$d;N;ba' -e '}')

    if [ -n "$body" ]; then
      cat > "$filepath" << SIGNAL
---
type: decision
date: $date
source: git:$hash
---

# $subject

$body

$stat
SIGNAL
    else
      cat > "$filepath" << SIGNAL
---
type: decision
date: $date
source: git:$hash
---

# $subject

$stat
SIGNAL
    fi

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
    if [ -n "$(find "$dir/signals" -name '*.md' 2>/dev/null)" ] && grep -rql "source: plan:$basename" "$dir/signals/" 2>/dev/null; then
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

    local filepath="$dir/signals/decision-plan-${slug}.md"

    cat > "$filepath" << SIGNAL
---
type: decision
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

  # Index public signals
  for f in "$dir/signals"/*.md; do
    [ -f "$f" ] || continue
    _index_file "$dir" "$f" 0
  done

  # Index private signals
  for f in "$dir/_private"/*.md; do
    [ -f "$f" ] || continue
    _index_file "$dir" "$f" 1
  done
}

_index_file() {
  local dir="$1"
  local filepath="$2"
  local private="${3:-0}"

  # Parse frontmatter
  local in_frontmatter=0
  local fm_type="" fm_date="" fm_tags="[]" fm_source="" fm_supersedes="" fm_status="" fm_links=""
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
          type:*)       fm_type="${line#type:}"; fm_type="${fm_type# }";;
          date:*)       fm_date="${line#date:}"; fm_date="${fm_date# }";;
          source:*)     fm_source="${line#source:}"; fm_source="${fm_source# }";;
          tags:*)       fm_tags="${line#tags:}"; fm_tags="${fm_tags# }";;
          supersedes:*) fm_supersedes="${line#supersedes:}"; fm_supersedes="${fm_supersedes# }";;
          status:*)     fm_status="${line#status:}"; fm_status="${fm_status# }";;
          links:*)      fm_links="${line#links:}"; fm_links="${fm_links# }";;
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

  # Derive type: frontmatter > filename prefix > default
  local type="$fm_type"
  if [ -z "$type" ]; then
    local fname
    fname=$(basename "$filepath")
    case "$fname" in
      decision-*) type="decision" ;;
      finding-*)  type="finding" ;;
      issue-*)    type="issue" ;;
      *)          type="decision" ;;
    esac
  fi

  # Compute derived fields
  local file_stem
  file_stem=$(_file_stem "$filepath")
  local excerpt
  excerpt=$(_extract_excerpt "$body")

  # Combine title + body as content
  local content="$title"$'\n'"$body"

  # Use sed for SQL escaping (bash string replacement is unreliable with quotes)
  local esc_title esc_content esc_tags esc_source esc_file esc_excerpt esc_supersedes esc_status esc_file_stem
  esc_title=$(printf '%s' "$title" | sed "s/'/''/g")
  esc_content=$(printf '%s' "$content" | sed "s/'/''/g")
  esc_tags=$(printf '%s' "$fm_tags" | sed "s/'/''/g")
  esc_source=$(printf '%s' "$fm_source" | sed "s/'/''/g")
  esc_file=$(printf '%s' "$filepath" | sed "s/'/''/g")
  esc_excerpt=$(printf '%s' "$excerpt" | sed "s/'/''/g")
  esc_supersedes=$(printf '%s' "$fm_supersedes" | sed "s/'/''/g")
  esc_status=$(printf '%s' "$fm_status" | sed "s/'/''/g")
  esc_file_stem=$(printf '%s' "$file_stem" | sed "s/'/''/g")

  sqlite3 "$dir/index.db" "INSERT INTO signals (type, title, content, tags, source, date, file, private, excerpt, status, supersedes, file_stem) VALUES ('$type', '$esc_title', '$esc_content', '$esc_tags', '$esc_source', '$fm_date', '$esc_file', $private, '$esc_excerpt', '$esc_status', '$esc_supersedes', '$esc_file_stem');"

  # Insert links
  if [ -n "$fm_supersedes" ]; then
    sqlite3 "$dir/index.db" "INSERT OR IGNORE INTO links (source_file, target_file, rel_type) VALUES ('$esc_file_stem', '$esc_supersedes', 'supersedes');"
  fi

  if [ -n "$fm_links" ]; then
    _parse_links "$fm_links" | while IFS='|' read -r rel target; do
      [ -z "$rel" ] || [ -z "$target" ] && continue
      local esc_rel esc_target
      esc_rel=$(printf '%s' "$rel" | sed "s/'/''/g")
      esc_target=$(printf '%s' "$target" | sed "s/'/''/g")
      sqlite3 "$dir/index.db" "INSERT OR IGNORE INTO links (source_file, target_file, rel_type) VALUES ('$esc_file_stem', '$esc_target', '$esc_rel');"
    done
  fi
}

# ── Brief generation ──────────────────────────────────────────────────

engram_brief() {
  local dir="$1"

  [ -f "$dir/index.db" ] || return 0

  # Build superseded set (file_stems that have been superseded by another signal)
  local superseded_set
  superseded_set=$(sqlite3 "$dir/index.db" "SELECT supersedes FROM signals WHERE supersedes != '' AND private=0;" 2>/dev/null || echo "")

  # Build SQL IN clause for superseded stems
  local superseded_in=""
  if [ -n "$superseded_set" ]; then
    local items=""
    while IFS= read -r stem; do
      [ -z "$stem" ] && continue
      local esc_stem
      esc_stem=$(printf '%s' "$stem" | sed "s/'/''/g")
      [ -n "$items" ] && items="$items,"
      items="$items'$esc_stem'"
    done <<< "$superseded_set"
    superseded_in="AND file_stem NOT IN ($items)"
  fi

  local superseded_count
  if [ -n "$superseded_set" ]; then
    superseded_count=$(echo "$superseded_set" | grep -c . || echo "0")
  else
    superseded_count=0
  fi

  local decision_count finding_count issue_count
  decision_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision' AND private=0;" 2>/dev/null || echo "0")
  finding_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='finding' AND private=0;" 2>/dev/null || echo "0")
  issue_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='issue' AND private=0;" 2>/dev/null || echo "0")

  local brief="# Decision Context ($decision_count decisions, $issue_count issues, $finding_count findings)"

  # ── Decisions: tag-grouped with excerpts, excluding superseded ──
  local distinct_tags
  distinct_tags=$(sqlite3 "$dir/index.db" "SELECT COUNT(DISTINCT CASE WHEN tags != '[]' AND tags != '' THEN REPLACE(REPLACE(SUBSTR(tags, 1, INSTR(tags||',', ',')-1), '[', ''), ']', '') ELSE NULL END) FROM signals WHERE type='decision' AND private=0 $superseded_in;" 2>/dev/null || echo "0")

  if [ "$distinct_tags" -ge 3 ]; then
    # Tag-grouped decisions
    local tag_groups
    tag_groups=$(sqlite3 -separator '|' "$dir/index.db" "SELECT REPLACE(REPLACE(SUBSTR(tags, 1, INSTR(tags||',', ',')-1), '[', ''), ']', '') as primary_tag, GROUP_CONCAT('- [' || date || '] ' || title || CASE WHEN excerpt != '' THEN ' — ' || excerpt ELSE '' END || CASE WHEN supersedes != '' THEN ' (supersedes: ' || supersedes || ')' ELSE '' END, CHAR(10)) FROM signals WHERE type='decision' AND private=0 $superseded_in GROUP BY primary_tag ORDER BY MAX(date) DESC LIMIT 15;" 2>/dev/null || echo "")
    if [ -n "$tag_groups" ]; then
      brief="$brief"$'\n\n'"## Recent Decisions"
      while IFS='|' read -r tag entries; do
        [ -z "$entries" ] && continue
        if [ -n "$tag" ] && [ "$tag" != "[]" ]; then
          brief="$brief"$'\n'"### $tag"$'\n'"$entries"
        else
          brief="$brief"$'\n'"$entries"
        fi
      done <<< "$tag_groups"
    fi
  else
    # Chronological decisions with excerpts
    local decisions
    decisions=$(sqlite3 -separator $'\n' "$dir/index.db" "SELECT '- [' || date || '] ' || title || CASE WHEN excerpt != '' THEN ' — ' || excerpt ELSE '' END || CASE WHEN supersedes != '' THEN ' (supersedes: ' || supersedes || ')' ELSE '' END FROM signals WHERE type='decision' AND private=0 $superseded_in ORDER BY date DESC LIMIT 15;" 2>/dev/null || echo "")
    if [ -n "$decisions" ]; then
      brief="$brief"$'\n\n'"## Recent Decisions"$'\n'"$decisions"
    fi
  fi

  # ── Issues: split open/resolved ──
  local open_issues
  open_issues=$(sqlite3 -separator $'\n' "$dir/index.db" "SELECT '- [' || date || '] ' || title || CASE WHEN excerpt != '' THEN ' — ' || excerpt ELSE '' END FROM signals WHERE type='issue' AND private=0 AND status != 'resolved' $superseded_in ORDER BY date DESC LIMIT 10;" 2>/dev/null || echo "")
  if [ -n "$open_issues" ]; then
    brief="$brief"$'\n\n'"## Open Issues"$'\n'"$open_issues"
  fi

  local resolved_count
  resolved_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='issue' AND private=0 AND (status = 'resolved' OR (file_stem IN (SELECT supersedes FROM signals WHERE supersedes != '')));" 2>/dev/null || echo "0")
  if [ "$resolved_count" -gt 0 ]; then
    brief="$brief"$'\n'"*$resolved_count resolved issue(s) not shown*"
  fi

  # ── Findings: with excerpts, excluding superseded ──
  local findings
  findings=$(sqlite3 -separator $'\n' "$dir/index.db" "SELECT '- [' || date || '] ' || title || CASE WHEN excerpt != '' THEN ' — ' || excerpt ELSE '' END FROM signals WHERE type='finding' AND private=0 $superseded_in ORDER BY date DESC LIMIT 10;" 2>/dev/null || echo "")
  if [ -n "$findings" ]; then
    brief="$brief"$'\n\n'"## Recent Findings"$'\n'"$findings"
  fi

  # ── Footer ──
  local private_count
  private_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE private=1;" 2>/dev/null || echo "0")
  local footer_parts=""
  if [ "$private_count" -gt 0 ]; then
    footer_parts="$private_count private signal(s)"
  fi
  if [ "$superseded_count" -gt 0 ]; then
    [ -n "$footer_parts" ] && footer_parts="$footer_parts, "
    footer_parts="${footer_parts}$superseded_count superseded signal(s)"
  fi
  if [ -n "$footer_parts" ]; then
    brief="$brief"$'\n\n'"*+ $footer_parts not shown*"
  fi

  printf '%s\n' "$brief" > "$dir/brief.md"
}

# ── Uncommitted signal summary ─────────────────────────────────────

engram_uncommitted_summary() {
  local dir="$1"
  git rev-parse --show-toplevel >/dev/null 2>&1 || return 0

  local uncommitted
  uncommitted=$(git status --porcelain "$dir/signals" "$dir/_private" 2>/dev/null | grep -v '^$')
  [ -z "$uncommitted" ] && return 0

  local count
  count=$(echo "$uncommitted" | wc -l | tr -d ' ')
  echo "$count uncommitted signal(s) in .engram/"
}
