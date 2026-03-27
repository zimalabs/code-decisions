#!/usr/bin/env bash
# Thin dispatcher — pipes stdin to the Python policy engine.
# Usage: bash dispatch.sh <event>
set -euo pipefail

event="${1:-unknown}"

_log_error() {
    local logdir="$HOME/.claude/logs"
    mkdir -p "$logdir" 2>/dev/null
    printf '%s decision: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$logdir/decision.log" 2>/dev/null
}

err_handler() {
    local code=$?
    local msg="$event hook failed (exit $code)"
    printf '{"error":"decision plugin: %s. Check logs at ~/.claude/logs/decision.log, or reinstall: /plugin install decisions@zimalabs"}\n' \
        "$msg" >&2
    _log_error "$msg"
    exit 0
}
trap err_handler ERR
trap 'exit 0' SIGINT SIGTERM

if [[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
    printf '{"error":"decision plugin: plugin environment not configured. Check logs at ~/.claude/logs/decision.log, or reinstall: /plugin install decisions@zimalabs"}\n' >&2
    exit 0
fi

if [[ ! -d "${CLAUDE_PLUGIN_ROOT}/decision" ]]; then
    printf '{"error":"decision plugin: plugin files not found. Check logs at ~/.claude/logs/decision.log, or reinstall: /plugin install decisions@zimalabs"}\n' >&2
    exit 0
fi

if ! command -v python3 &>/dev/null; then
    printf '{"error":"decision plugin: python3 is required but not found. Install Python 3 from https://python.org"}\n' >&2
    exit 0
fi

export PYTHONPATH="${CLAUDE_PLUGIN_ROOT}"
input=$(cat)

# Fast-path: skip Python for trivially short UserPromptSubmit messages
# (e.g. "yes", "ok", "continue") — no policy will match on <15 chars.
# Uses total JSON length as a cheap proxy to avoid spawning any process.
# A 15-char content value needs ~40+ bytes of JSON wrapper, so 60 is safe.
if [[ "$event" == "UserPromptSubmit" && ${#input} -lt 60 ]]; then
    printf '{}\n'
    exit 0
fi

# Fast-path: skip Python for UserPromptSubmit unless the message contains
# "/decision", a decision query pattern, or decision language.
if [[ "$event" == "UserPromptSubmit" ]]; then
    _run_python=false
    if grep -q '/decision' <<< "$input" 2>/dev/null; then _run_python=true; fi
    if grep -qiE '(why did we|what did we decide|what was decided|did we decide|what did we choose|why do we|remind me.*(decision|chose|decid))' <<< "$input" 2>/dev/null; then _run_python=true; fi
    # Capture-nudge decision language (requires technical signal like backticks or CamelCase)
    if grep -qiE '(let.?s go with|let.?s use|we decided|switching to|going with|the decision is|we.?ll use|agreed on|settled on|i chose|opting for|went with|committing to|ruling out)' <<< "$input" 2>/dev/null; then _run_python=true; fi
    if [[ "$_run_python" == "false" ]]; then
        printf '{}\n'
        exit 0
    fi
fi

# Fast-path: skip Python for PostToolUse when the file_path matches skip
# patterns (test files, config, docs, memory).
# Patterns are generated from SKIP_FILE_PATTERNS in constants.py — see the
# test_skip_patterns_in_sync test in test_dispatch_integration.py.
# Extract file_path from JSON to avoid false positives from code content.
if [[ "$event" == "PostToolUse" ]]; then
    # Extract file_path value from JSON — grep for "file_path":"..." pattern
    _fp=$(printf '%s' "$input" | grep -oE '"file_path"\s*:\s*"[^"]*"' | head -1 | sed 's/.*"file_path"\s*:\s*"//;s/"$//')
    if [[ -n "$_fp" ]]; then
        # BEGIN SKIP_PATTERNS (generated — keep in sync with constants.py, verified by test_skip_patterns_in_sync)
        _skip=false
        for pat in /memory/ /decisions/ _test. .test. /tests/ /test/ /spec/ tests/ test/ spec/ README.md CHANGELOG.md CLAUDE.md MEMORY.md /docs/ /doc/ .json .yaml .yml \
                   .toml .lock .png .jpg .jpeg .gif .svg .ico .webp LICENSE Makefile /assets/ /static/ /public/ /vendor/ .woff .woff2 .ttf .eot; do
        # END SKIP_PATTERNS
            if [[ "$_fp" == *"$pat"* ]]; then _skip=true; break; fi
        done
        if [[ "$_skip" == "true" ]]; then printf '{}\n'; exit 0; fi

        # Dedup: skip Python if this file_path was already dispatched this session.
        # related-context deduplicates in Python, but this avoids spawning Python at all.
        _dedup="/tmp/decision-dispatch-${CLAUDE_SESSION_ID:-$$}"
        if grep -qxF "$_fp" "$_dedup" 2>/dev/null; then
            printf '{}\n'
            exit 0
        fi
        printf '%s\n' "$_fp" >> "$_dedup" 2>/dev/null
    fi
fi

_t0=$SECONDS
printf '%s' "$input" | python3 -m decision policy "$@"
_elapsed=$(( SECONDS - _t0 ))
if [[ "$_elapsed" -gt 0 ]]; then
    _log_error "slow: ${event} took ${_elapsed}s"
fi
