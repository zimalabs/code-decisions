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

# ── Config ────────────────────────────────────────────────────────────

_git_tracking_enabled() {
  local dir="$1"
  [ -f "$dir/config" ] && grep -qx 'git_tracking=true' "$dir/config"
}

# ── Init ──────────────────────────────────────────────────────────────

engram_init() {
  local dir="$1"
  _check_fts5
  mkdir -p "$dir"/decisions
  mkdir -p "$dir"/_private/decisions

  # Only manage .gitignore when git tracking is enabled
  if _git_tracking_enabled "$dir"; then
    if [ ! -f "$dir/.gitignore" ]; then
      printf 'index.db\nbrief.md\n_private/\nconfig\n' > "$dir/.gitignore"
    else
      for entry in '_private/' 'brief.md' 'config'; do
        grep -qx "$entry" "$dir/.gitignore" || echo "$entry" >> "$dir/.gitignore"
      done
    fi
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

_slug() {
  basename "$1" .md
}

_extract_excerpt() {
  echo "$1" | { grep -v '^$' || true; } | { grep -v '^#' || true; } | head -1 | cut -c1-120
}

_normalize_tags() {
  # Convert YAML-style [a, b, c] to valid JSON ["a","b","c"]
  local raw="$1"
  case "$raw" in
    '[]'|'') echo '[]'; return ;;
    *'"'*) echo "$raw"; return ;;
  esac
  local inner="${raw#\[}"; inner="${inner%\]}"
  local result="["
  local first=1
  while IFS= read -r tag; do
    tag="${tag# }"; tag="${tag% }"
    [ -z "$tag" ] && continue
    [ "$first" -eq 1 ] && first=0 || result="$result,"
    result="$result\"$tag\""
  done <<< "$(echo "$inner" | tr ',' '\n')"
  result="$result]"
  echo "$result"
}

_parse_links() {
  local str="$1"
  str="${str#\[}"; str="${str%\]}"
  echo "$str" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while IFS=: read -r rel target; do
    [ -n "$rel" ] && [ -n "$target" ] && printf '%s|%s\n' "$rel" "$target"
  done
}

# ── Signal validation ────────────────────────────────────────────────

_validate_signal() {
  local filepath="$1"
  local errors=""

  local in_frontmatter=0
  local has_open=0 has_close=0
  local has_date=0 has_tags=0 tags_empty=1
  local has_title=0
  local lead_paragraph=""
  local past_frontmatter=0 past_title=0

  while IFS= read -r line; do
    if [ "$past_frontmatter" -eq 0 ]; then
      if [ "$line" = "---" ]; then
        if [ "$has_open" -eq 0 ]; then
          has_open=1
          in_frontmatter=1
          continue
        else
          has_close=1
          past_frontmatter=1
          continue
        fi
      fi
      if [ "$in_frontmatter" -eq 1 ]; then
        case "$line" in
          date:*)
            local date_val="${line#date:}"; date_val="${date_val# }"
            if printf '%s' "$date_val" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'; then
              has_date=1
            fi
            ;;
          tags:*)
            local tags_val="${line#tags:}"; tags_val="${tags_val# }"
            has_tags=1
            case "$tags_val" in
              '[]'|'') tags_empty=1 ;;
              *) tags_empty=0 ;;
            esac
            ;;
        esac
        continue
      fi
    fi

    # Past frontmatter: look for title and lead paragraph
    if [ "$has_title" -eq 0 ] && [[ "$line" == "# "* ]]; then
      has_title=1
      past_title=1
      continue
    fi

    if [ "$past_title" -eq 1 ] && [ -z "$lead_paragraph" ]; then
      # Skip blank lines and headings
      [ -z "$line" ] && continue
      [[ "$line" == "#"* ]] && continue
      lead_paragraph="$line"
    fi
  done < "$filepath"

  if [ "$has_open" -eq 0 ] || [ "$has_close" -eq 0 ]; then
    errors="${errors}missing frontmatter delimiters (---); "
  fi
  if [ "$has_date" -eq 0 ]; then
    errors="${errors}missing or invalid date: field (need YYYY-MM-DD); "
  fi
  if [ "$has_tags" -eq 0 ] || [ "$tags_empty" -eq 1 ]; then
    errors="${errors}tags: must have at least one tag (not empty []); "
  fi
  if [ "$has_title" -eq 0 ]; then
    errors="${errors}missing H1 title (# ...); "
  fi
  if [ -z "$lead_paragraph" ] || [ "${#lead_paragraph}" -lt 20 ]; then
    errors="${errors}lead paragraph after title must exist and be >= 20 chars (explains why); "
  fi

  if [ -n "$errors" ]; then
    echo "engram: invalid signal $(basename "$filepath"): $errors" >&2
    return 1
  fi
  return 0
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

  # Git tracking must be explicitly enabled
  _git_tracking_enabled "$dir" || return 0

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

    # Dedup: skip if file with this source already exists (public or private)
    if grep -rql "source: git:$hash" "$dir/decisions/" 2>/dev/null; then
      continue
    fi
    if grep -rql "source: git:$hash" "$dir/_private/decisions/" 2>/dev/null; then
      continue
    fi

    local date
    date=$(echo "$date_str" | cut -d' ' -f1)
    local slug
    slug=$(_slugify "$subject")
    [ -z "$slug" ] && slug="commit-${hash:0:7}"

    local filepath="$dir/decisions/${slug}.md"

    # Manual signal with same slug already exists — defer to it
    if [ -f "$filepath" ]; then
      continue
    fi
    if [ -f "$dir/_private/decisions/${slug}.md" ]; then
      continue
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

    local filepath="$dir/decisions/plan-${slug}.md"

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
  for f in "$dir/decisions"/*.md; do
    [ -f "$f" ] || continue
    _index_file "$dir" "$f" 0
  done

  # Index private signals
  for f in "$dir/_private/decisions"/*.md; do
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
  local fm_type="" fm_date="" fm_tags="[]" fm_source="" fm_supersedes="" fm_links="" fm_status="active"
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
          tags:*)       fm_tags="${line#tags:}"; fm_tags="${fm_tags# }"
                        fm_tags=$(_normalize_tags "$fm_tags");;
          supersedes:*) fm_supersedes="${line#supersedes:}"; fm_supersedes="${fm_supersedes# }";;
          links:*)      fm_links="${line#links:}"; fm_links="${fm_links# }";;
          status:*)     fm_status="${line#status:}"; fm_status="${fm_status# }";;
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

  # Derive type: frontmatter > default to decision
  local type="$fm_type"
  [ -z "$type" ] && type="decision"

  # Compute derived fields
  local slug
  slug=$(_slug "$filepath")
  local excerpt
  excerpt=$(_extract_excerpt "$body")

  # Normalize status (default to 'active' if unrecognized)
  case "$fm_status" in
    active|withdrawn) ;;
    *) fm_status="active" ;;
  esac

  # Validate signal — invalid overrides frontmatter status
  if ! _validate_signal "$filepath" 2>/dev/null; then
    fm_status="invalid"
    echo "engram: warning: $(basename "$filepath") is incomplete (missing rationale)" >&2
  fi

  # Combine title + body as content
  local content="$title"$'\n'"$body"

  # Use sed for SQL escaping (bash string replacement is unreliable with quotes)
  local esc_title esc_content esc_tags esc_source esc_file esc_excerpt esc_slug
  esc_title=$(printf '%s' "$title" | sed "s/'/''/g")
  esc_content=$(printf '%s' "$content" | sed "s/'/''/g")
  esc_tags=$(printf '%s' "$fm_tags" | sed "s/'/''/g")
  esc_source=$(printf '%s' "$fm_source" | sed "s/'/''/g")
  esc_file=$(printf '%s' "$filepath" | sed "s/'/''/g")
  esc_excerpt=$(printf '%s' "$excerpt" | sed "s/'/''/g")
  esc_slug=$(printf '%s' "$slug" | sed "s/'/''/g")

  sqlite3 "$dir/index.db" "INSERT INTO signals (type, title, content, tags, source, date, file, private, excerpt, slug, status) VALUES ('$type', '$esc_title', '$esc_content', '$esc_tags', '$esc_source', '$fm_date', '$esc_file', $private, '$esc_excerpt', '$esc_slug', '$fm_status');"

  # Insert links
  if [ -n "$fm_supersedes" ]; then
    local esc_supersedes
    esc_supersedes=$(printf '%s' "$fm_supersedes" | sed "s/'/''/g")
    sqlite3 "$dir/index.db" "INSERT OR IGNORE INTO links (source_file, target_file, rel_type) VALUES ('$esc_slug', '$esc_supersedes', 'supersedes');"
  fi

  if [ -n "$fm_links" ]; then
    _parse_links "$fm_links" | while IFS='|' read -r rel target; do
      [ -z "$rel" ] || [ -z "$target" ] && continue
      local esc_rel esc_target
      esc_rel=$(printf '%s' "$rel" | sed "s/'/''/g")
      esc_target=$(printf '%s' "$target" | sed "s/'/''/g")
      sqlite3 "$dir/index.db" "INSERT OR IGNORE INTO links (source_file, target_file, rel_type) VALUES ('$esc_slug', '$esc_target', '$esc_rel');"
    done
  fi
}

# ── Brief generation ──────────────────────────────────────────────────

engram_brief() {
  local dir="$1"

  [ -f "$dir/index.db" ] || return 0

  # Build superseded set (slugs that have been superseded by another signal)
  local superseded_set
  superseded_set=$(sqlite3 "$dir/index.db" "SELECT target_file FROM links WHERE rel_type='supersedes';" 2>/dev/null || echo "")

  # Build SQL IN clause for superseded slugs
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
    superseded_in="AND slug NOT IN ($items)"
  fi

  local superseded_count
  if [ -n "$superseded_set" ]; then
    superseded_count=$(echo "$superseded_set" | grep -c . || echo "0")
  else
    superseded_count=0
  fi

  local decision_count
  decision_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision' AND private=0 AND status='active';" 2>/dev/null || echo "0")

  local invalid_count
  invalid_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision' AND private=0 AND status='invalid';" 2>/dev/null || echo "0")

  local withdrawn_count
  withdrawn_count=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE type='decision' AND private=0 AND status='withdrawn';" 2>/dev/null || echo "0")

  local brief="# Decision Context ($decision_count decisions)"

  # ── Decisions: tag-grouped with excerpts, excluding superseded ──
  local distinct_tags
  distinct_tags=$(sqlite3 "$dir/index.db" "SELECT COUNT(DISTINCT j.value) FROM signals, json_each(signals.tags) j WHERE signals.type='decision' AND signals.private=0 AND signals.status='active' AND signals.tags != '[]' $superseded_in;" 2>/dev/null || echo "0")

  if [ "$distinct_tags" -ge 3 ]; then
    # Tag-grouped decisions
    local tag_groups
    tag_groups=$(sqlite3 -separator '|' "$dir/index.db" "SELECT COALESCE(json_extract(s.tags, '\$[0]'), '') as primary_tag, GROUP_CONCAT('- [' || s.date || '] ' || s.title || CASE WHEN s.excerpt != '' THEN ' — ' || s.excerpt ELSE '' END || CASE WHEN l.target_file IS NOT NULL THEN ' (supersedes: ' || l.target_file || ')' ELSE '' END, CHAR(10)) FROM signals s LEFT JOIN links l ON l.source_file = s.slug AND l.rel_type = 'supersedes' WHERE s.type='decision' AND s.private=0 AND s.status='active' $superseded_in GROUP BY primary_tag ORDER BY MAX(s.date) DESC LIMIT 15;" 2>/dev/null || echo "")
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
    decisions=$(sqlite3 -separator $'\n' "$dir/index.db" "SELECT '- [' || s.date || '] ' || s.title || CASE WHEN s.excerpt != '' THEN ' — ' || s.excerpt ELSE '' END || CASE WHEN l.target_file IS NOT NULL THEN ' (supersedes: ' || l.target_file || ')' ELSE '' END FROM signals s LEFT JOIN links l ON l.source_file = s.slug AND l.rel_type = 'supersedes' WHERE s.type='decision' AND s.private=0 AND s.status='active' $superseded_in ORDER BY s.date DESC LIMIT 15;" 2>/dev/null || echo "")
    if [ -n "$decisions" ]; then
      brief="$brief"$'\n\n'"## Recent Decisions"$'\n'"$decisions"
    fi
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
  if [ "$withdrawn_count" -gt 0 ]; then
    [ -n "$footer_parts" ] && footer_parts="$footer_parts, "
    footer_parts="${footer_parts}$withdrawn_count withdrawn signal(s)"
  fi
  if [ "$invalid_count" -gt 0 ]; then
    [ -n "$footer_parts" ] && footer_parts="$footer_parts, "
    footer_parts="${footer_parts}$invalid_count signal(s) incomplete (missing rationale)"
  fi
  if [ -n "$footer_parts" ]; then
    brief="$brief"$'\n\n'"*+ $footer_parts not shown*"
  fi

  # Cap brief size to stay within context budget (~2-4K tokens)
  local max_lines="${ENGRAM_BRIEF_MAX_LINES:-50}"
  local line_count
  line_count=$(printf '%s\n' "$brief" | wc -l | tr -d ' ')
  if [ "$line_count" -gt "$max_lines" ]; then
    brief=$(printf '%s\n' "$brief" | head -n "$max_lines")
    brief="$brief"$'\n\n'"*... truncated to $max_lines lines. Use @engram:query for full details.*"
  fi

  printf '%s\n' "$brief" > "$dir/brief.md"
}

# ── Path to keywords ──────────────────────────────────────────────

engram_path_to_keywords() {
  local filepath="$1"
  # Strip extension
  local base="${filepath%.*}"
  # Split on / - _ . and filter noise words
  local words
  words=$(printf '%s' "$base" | tr '/' '\n' | tr '-' '\n' | tr '_' '\n' | tr '.' '\n' | tr '[:upper:]' '[:lower:]')
  local noise="src lib app index test spec the and is of to in for a an"
  local seen="" result=""
  while IFS= read -r word; do
    [ -z "$word" ] && continue
    # Skip noise words
    case " $noise " in
      *" $word "*) continue ;;
    esac
    # Deduplicate
    case " $seen " in
      *" $word "*) continue ;;
    esac
    seen="$seen $word"
    [ -n "$result" ] && result="$result "
    result="$result$word"
  done <<< "$words"
  printf '%s' "$result"
}

# ── Query relevant signals ───────────────────────────────────────

engram_query_relevant() {
  local dir="$1"
  local search_terms="$2"
  local limit="${3:-3}"

  [ -z "$search_terms" ] && return 0
  [ -f "$dir/index.db" ] || return 0

  # Build OR-joined FTS5 query
  local fts_query=""
  for term in $search_terms; do
    [ -n "$fts_query" ] && fts_query="$fts_query OR "
    local esc_term
    esc_term=$(printf '%s' "$term" | sed "s/'/''/g")
    fts_query="$fts_query$esc_term"
  done

  [ -z "$fts_query" ] && return 0

  # Exclude private and superseded signals
  local results
  results=$(sqlite3 -separator '|' "$dir/index.db" "SELECT s.date, s.title, s.excerpt FROM signals_fts fts JOIN signals s ON s.id = fts.rowid WHERE signals_fts MATCH '$fts_query' AND s.private = 0 AND s.status = 'active' AND s.slug NOT IN (SELECT target_file FROM links WHERE rel_type = 'supersedes') ORDER BY rank LIMIT $limit;" 2>/dev/null || echo "")

  [ -z "$results" ] && return 0

  while IFS='|' read -r date title excerpt; do
    [ -z "$title" ] && continue
    if [ -n "$excerpt" ]; then
      printf -- '- [%s] %s — %s\n' "$date" "$title" "$excerpt"
    else
      printf -- '- [%s] %s\n' "$date" "$title"
    fi
  done <<< "$results"
}

# ── Tag summary ──────────────────────────────────────────────────

engram_tag_summary() {
  local dir="$1"

  [ -f "$dir/index.db" ] || return 0

  # Check minimum signal count
  local total
  total=$(sqlite3 "$dir/index.db" "SELECT COUNT(*) FROM signals WHERE private=0;" 2>/dev/null || echo "0")
  [ "$total" -lt 5 ] && return 0

  # Extract individual tags from JSON arrays and count them
  local tag_counts
  tag_counts=$(sqlite3 "$dir/index.db" "
    SELECT j.value AS tag, COUNT(*) AS cnt
    FROM signals, json_each(signals.tags) j
    WHERE signals.private = 0 AND signals.tags != '[]'
    GROUP BY j.value ORDER BY cnt DESC LIMIT 8;
  " 2>/dev/null | awk -F'|' '{print $2, $1}')

  [ -z "$tag_counts" ] && return 0

  local parts=""
  while read -r cnt tag; do
    [ -z "$tag" ] && continue
    [ -n "$parts" ] && parts="$parts, "
    parts="$parts$tag ($cnt)"
  done <<< "$tag_counts"

  [ -z "$parts" ] && return 0
  printf 'Top topics: %s' "$parts"
}

# ── Find incomplete signals ───────────────────────────────────────

engram_find_incomplete() {
  local dir="$1"
  local limit="${2:-5}"

  [ -f "$dir/index.db" ] || return 0

  # Find signals with gaps: missing tags, missing body sections, or no links.
  # Output: slug|title|gap_types (pipe-delimited, one per line)
  sqlite3 -separator '|' "$dir/index.db" "
    SELECT s.slug, s.title,
      CASE WHEN s.tags = '[]' OR s.tags = '' THEN 'tags,' ELSE '' END
      || CASE WHEN s.content NOT LIKE '%## Rationale%' AND s.content NOT LIKE '%## Alternatives%' THEN 'sections,' ELSE '' END
      || CASE WHEN l.source_file IS NULL AND l2.target_file IS NULL THEN 'links,' ELSE '' END
      AS gap_types
    FROM signals s
    LEFT JOIN links l ON l.source_file = s.slug
    LEFT JOIN links l2 ON l2.target_file = s.slug
    WHERE (s.tags = '[]' OR s.tags = ''
      OR (s.content NOT LIKE '%## Rationale%' AND s.content NOT LIKE '%## Alternatives%')
      OR (l.source_file IS NULL AND l2.target_file IS NULL))
    GROUP BY s.slug
    ORDER BY s.date DESC
    LIMIT $limit;
  " 2>/dev/null | while IFS='|' read -r stem title gaps; do
    # Trim trailing comma from gap_types
    gaps="${gaps%,}"
    printf '%s|%s|%s\n' "$stem" "$title" "$gaps"
  done
}

# ── Full sync pipeline ─────────────────────────────────────────────

engram_resync() {
  local dir="$1"
  engram_ingest_commits "$dir"
  engram_ingest_plans "$dir"
  engram_reindex "$dir"
  engram_brief "$dir"
}

# ── Uncommitted signal summary ─────────────────────────────────────

engram_uncommitted_summary() {
  local dir="$1"

  # Git tracking must be explicitly enabled
  _git_tracking_enabled "$dir" || return 0

  git rev-parse --show-toplevel >/dev/null 2>&1 || return 0

  local uncommitted
  uncommitted=$(git status --porcelain "$dir/decisions" "$dir/_private/decisions" 2>/dev/null | grep -v '^$')
  [ -z "$uncommitted" ] && return 0

  local count
  count=$(echo "$uncommitted" | wc -l | tr -d ' ')
  echo "$count uncommitted signal(s) in .engram/"
}
