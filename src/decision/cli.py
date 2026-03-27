"""CLI commands for the decision plugin.

User-facing: search, show, list, tags, stats, validate, undo, coverage, tree, enrich, help.
Internal: policy (hook dispatch, hidden from help).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core.decision import Decision


def _json_out(data: object) -> None:
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2))


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="decision", description="Decision memory CLI")
    sub = parser.add_subparsers(dest="command")

    # search
    p_search = sub.add_parser("search", help="Search decisions (FTS5 + BM25)")
    p_search.add_argument("keywords", nargs="+", help="Search keywords")
    p_search.add_argument("--json", action="store_true", dest="as_json")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.add_argument("--group", action="store_true", help="Group results by tag")

    # show
    p_show = sub.add_parser("show", help="Display full decision")
    p_show.add_argument("slug", help="Decision slug (supports partial matching)")

    # list
    p_list = sub.add_parser("list", help="Browse decisions")
    p_list.add_argument("--tag", default="")
    p_list.add_argument("--json", action="store_true", dest="as_json")

    # tags
    p_tags = sub.add_parser("tags", help="List tags with counts")
    p_tags.add_argument("--json", action="store_true", dest="as_json")

    # stats
    p_stats = sub.add_parser("stats", help="Health check")
    p_stats.add_argument("--json", action="store_true", dest="as_json")
    p_stats.add_argument("--health", action="store_true", help="Deep analysis: staleness, orphaned affects")

    # validate
    sub.add_parser("validate", help="Check all decision files for errors")

    # undo
    p_undo = sub.add_parser("undo", help="Revert a decision")
    p_undo.add_argument("slug", nargs="?", default=None, help="Decision slug (omit for most recent)")

    # coverage
    p_coverage = sub.add_parser("coverage", help="Show decision coverage across the codebase")
    p_coverage.add_argument("--json", action="store_true", dest="as_json")

    # tree
    p_tree = sub.add_parser("tree", help="Show decisions grouped by codebase area")
    p_tree.add_argument("--json", action="store_true", dest="as_json")

    # enrich
    p_enrich = sub.add_parser("enrich", help="Analyze a decision for enrichment opportunities")
    p_enrich.add_argument("slug", help="Decision slug")
    p_enrich.add_argument("--json", action="store_true", dest="as_json")

    # dismiss
    sub.add_parser("dismiss", help="Suppress nudges for this session")

    # help
    sub.add_parser("help", help="Show this message")

    # policy (internal, not shown in help)
    p_policy = sub.add_parser("policy")
    p_policy.add_argument("event", nargs="?", default="")
    p_policy.add_argument("--trace", action="store_true")

    return parser


# ── Commands ─────────────────────────────────────────────────────────


def _cmd_search(args: argparse.Namespace) -> None:
    """Search decisions with FTS5 + BM25 ranking."""
    from .store import DecisionStore
    from .store.query import _relevance_label

    query_str = " ".join(args.keywords)
    store = DecisionStore()
    results = store.search(query_str, args.limit)

    if args.as_json:
        _json_out([dataclasses.asdict(r) for r in results])
        return

    if not results:
        print(f'No results for "{query_str}".')
        return

    use_grouping = args.group

    if use_grouping:
        # Group by primary tag
        groups: dict[str, list] = {}
        for r in results:
            primary = r.tags[0] if r.tags else "(untagged)"
            groups.setdefault(primary, []).append(r)

        for tag, group in groups.items():
            print(f"  {tag} ({len(group)}):")
            for r in group:
                rel = _relevance_label(r.rank, is_fts=True)
                print(f"    [{r.date}] {r.title} {rel}")
                if r.excerpt:
                    print(f"             {r.excerpt}")
            print()
    else:
        for r in results:
            tags = ", ".join(r.tags) if r.tags else ""
            rel = _relevance_label(r.rank, is_fts=True)
            print(f"  [{r.date}] {r.title} {rel}")
            if r.excerpt:
                print(f"           {r.excerpt}")
            if tags:
                print(f"           tags: {tags}")
            print()

    print(f'{len(results)} result(s) for "{query_str}"')


def _render_decision(path: Path) -> None:
    """Render a decision file in a human-friendly format."""
    from .core.decision import Decision

    text = path.read_text()
    d = Decision.from_text(text)

    # Metadata header
    print(f"# {d.title}" if d.title else f"# {d.name}")
    print()
    parts = []
    if d.date:
        parts.append(d.date)
    if d.tags:
        parts.append(f"tags: {', '.join(d.tags)}")
    if parts:
        print("  ".join(parts))
    if d.description:
        print(f"  {d.description}")
    if d.affects:
        print(f"  affects: {', '.join(d.affects)}")
    print()

    # Body (skip leading blank lines)
    body = d.body.strip()
    if body:
        print(body)
        print()


def _find_decision_file(decisions_dir: Path, slug: str) -> Path | None:
    """Find a decision file by slug with partial matching.

    Returns the file Path on exact or unambiguous prefix match.
    Prints error and exits on ambiguous or not-found.
    Returns None only if decisions_dir doesn't exist.
    """
    if not decisions_dir.is_dir():
        print(f"Decision not found: {slug}", file=sys.stderr)
        return None

    # Exact match
    exact = decisions_dir / f"{slug}.md"
    if exact.is_file():
        return exact

    # Prefix match
    matches = [f for f in decisions_dir.glob("*.md") if f.stem.startswith(slug)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f'Ambiguous slug "{slug}". Matches:', file=sys.stderr)
        for m in sorted(matches):
            print(f"  {m.stem}", file=sys.stderr)
        sys.exit(1)

    # Substring suggestions
    all_slugs = sorted(f.stem for f in decisions_dir.glob("*.md"))
    similar = [s for s in all_slugs if slug in s]
    if similar:
        print(f"Decision not found: {slug}", file=sys.stderr)
        print("Similar:", file=sys.stderr)
        for s in similar[:5]:
            print(f"  {s}", file=sys.stderr)
    else:
        print(f"Decision not found: {slug}", file=sys.stderr)
        print(f"Try: python3 -m decision search {slug}", file=sys.stderr)
    return None


def _cmd_show(args: argparse.Namespace | None = None) -> None:
    """Display a full decision by slug (supports partial matching)."""
    from .utils.helpers import _discover_decisions_dir

    if args is None:
        parser = _build_parser()
        args = parser.parse_args()

    decisions_dir = _discover_decisions_dir()
    target = _find_decision_file(decisions_dir, args.slug)
    if target is None:
        sys.exit(1)
    _render_decision(target)


def _cmd_undo(args: argparse.Namespace) -> None:
    """Revert a decision by slug or most recent."""
    import subprocess

    from .utils.helpers import _discover_decisions_dir

    decisions_dir = _discover_decisions_dir()
    if not decisions_dir.is_dir():
        print("No decisions directory found.", file=sys.stderr)
        sys.exit(1)

    if args.slug:
        target = _find_decision_file(decisions_dir, args.slug)
        if target is None:
            sys.exit(1)
    else:
        # Most recent by mtime
        files = sorted(decisions_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            print("No decisions to undo.", file=sys.stderr)
            sys.exit(1)
        target = files[0]

    slug = target.stem

    # Check if file is tracked by git
    try:
        result = subprocess.run(
            ["git", "ls-files", str(target)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_tracked = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        git_tracked = ""

    if git_tracked:
        # Existing file edited — restore from git
        result = subprocess.run(["git", "checkout", "--", str(target)], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print(f"Failed to restore {slug}: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        print(f"Restored: {slug} (from git)")
    else:
        # New file — delete it
        target.unlink()
        print(f"Deleted: {slug}")


def _cmd_list(args: argparse.Namespace) -> None:
    """List decisions from index (progressive loading — no file parsing)."""
    from .store import DecisionStore

    store = DecisionStore()
    summaries = store.list_summaries()

    if not summaries:
        if args.as_json:
            _json_out([])
            return
        print("No decisions found.")
        return

    tag_filter = args.tag.lower()

    filtered = []
    for d in summaries:
        if tag_filter and tag_filter not in [t.lower() for t in d.tags]:
            continue
        filtered.append(d)

    if args.as_json:
        _json_out(
            [
                {
                    "slug": d.slug,
                    "title": d.title,
                    "date": d.date,
                    "tags": d.tags,
                }
                for d in filtered
            ]
        )
        return

    if not filtered:
        print("No matching decisions.")
        return

    for d in filtered:
        tags = ", ".join(d.tags) if d.tags else ""
        print(f"  [{d.date}] {d.title}")
        if tags:
            print(f"           tags: {tags}")

    print(f"\n{len(filtered)} decision(s)")


def _cmd_tags(args: argparse.Namespace) -> None:
    """List tags with counts."""
    from .store import DecisionStore

    store = DecisionStore()
    tags = store.all_tags()

    if args.as_json:
        _json_out(tags)
        return

    if not tags:
        print("No tags found.")
        return

    # Sort by count descending, then name ascending
    for tag, count in sorted(tags.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {tag}: {count}")


def _cmd_stats(args: argparse.Namespace) -> None:
    """Health check: counts, coverage, index status."""
    from .store import DecisionStore

    store = DecisionStore()
    decisions = store.list_decisions()
    tags = store.all_tags()

    total = len(decisions)

    cutoff = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
    recent = sum(1 for d in decisions if d.date >= cutoff)

    unique_tags = len(tags)
    tagged = sum(1 for d in decisions if d.tags)
    untagged = total - tagged

    with_affects = sum(1 for d in decisions if d.affects)
    without_affects = total - with_affects

    index_available = store._index.available if total > 0 else False

    if args.as_json:
        _json_out(
            {
                "total": total,
                "recent_30d": recent,
                "unique_tags": unique_tags,
                "tagged": tagged,
                "untagged": untagged,
                "with_affects": with_affects,
                "without_affects": without_affects,
                "index_available": index_available,
            }
        )
        return

    print(f"Decisions: {total}")
    print(f"Recent (30d): {recent}")
    print(f"Tags: {unique_tags} unique, {tagged} tagged, {untagged} untagged")
    affects_note = ""
    if without_affects > 0 and total > 0:
        affects_note = f" — {without_affects} missing affects (won't auto-surface)"
    print(f"Affects: {with_affects}/{total} decisions are proximity-triggered{affects_note}")
    if without_affects > 0:
        missing = [d.slug for d in decisions if not d.affects][:5]
        suffix = ", ..." if without_affects > 5 else ""
        print(f"  Missing affects: {', '.join(missing)}{suffix}")
    idx_status = "FTS5 available (synced)" if index_available else "not available"
    print(f"Index: {idx_status}")

    if getattr(args, "health", False) and decisions:
        _cmd_health(decisions)


def _cmd_health(decisions: list[Decision]) -> None:
    """Deep health analysis: staleness detection + orphaned affects paths."""
    import subprocess

    from .utils.constants import STALENESS_COMMIT_THRESHOLD
    from .utils.helpers import _log

    stale: list[tuple[str, int]] = []
    orphaned: list[tuple[str, list[str]]] = []

    for dec in decisions:
        if not dec.affects or not dec.date:
            continue

        # Check staleness: significant commits to affected files since decision date
        affects_args = [p for p in dec.affects if "*" not in p and "?" not in p]
        if affects_args:
            try:
                result = subprocess.run(
                    ["git", "log", f"--since={dec.date}", "--oneline", "--"] + affects_args,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                commit_count = len(result.stdout.strip().splitlines()) if result.stdout.strip() else 0
                if commit_count >= STALENESS_COMMIT_THRESHOLD:
                    stale.append((dec.slug, commit_count))
            except Exception as exc:
                _log(f"staleness check failed for {dec.slug}: {exc}")
                continue

        # Check orphaned affects paths
        dead = []
        for p in dec.affects:
            if "*" in p or "?" in p:
                continue
            check_path = Path(p)
            if p.endswith("/"):
                if not check_path.is_dir():
                    dead.append(p)
            elif not check_path.is_file():
                dead.append(p)
        if dead:
            orphaned.append((dec.slug, dead))

    if stale:
        print(f"\nPotentially stale ({len(stale)}):")
        for slug, commits in sorted(stale, key=lambda x: -x[1])[:10]:
            print(f"  {slug} — {commits} commits to affected files since capture")
    else:
        print("\nNo stale decisions detected.")

    if orphaned:
        print(f"\nOrphaned affects ({len(orphaned)}):")
        for slug, paths in orphaned[:10]:
            print(f"  {slug} — {', '.join(paths)}")

    # Surfacing analytics from cross-session history
    _print_surfacing_analytics(decisions)


def _print_surfacing_analytics(decisions: list[Decision]) -> None:
    """Show which decisions are surfaced often, rarely, or never."""
    from .utils.helpers import _state_dir

    path = _state_dir() / "surfacing_history.json"
    if not path.is_file():
        print("\nSurfacing analytics: no data yet (accumulates across sessions).")
        return

    try:
        history: dict[str, int] = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return

    all_slugs = {d.slug for d in decisions if d.affects}
    never_surfaced = sorted(all_slugs - set(history))
    frequent = sorted(
        [(s, c) for s, c in history.items() if s in all_slugs and c > 10],
        key=lambda x: -x[1],
    )

    print(f"\nSurfacing analytics ({len(history)} data points):")
    if never_surfaced:
        shown = never_surfaced[:5]
        more = f" (and {len(never_surfaced) - 5} more)" if len(never_surfaced) > 5 else ""
        print(f"  Never surfaced: {', '.join(shown)}{more}")
        print("    → Consider broadening affects or adding directory prefixes")
    if frequent:
        for slug, count in frequent[:5]:
            print(f"  Frequently surfaced: {slug} ({count}x)")
        print("    → Consider narrowing affects if this causes noise")
    if not never_surfaced and not frequent:
        print("  All decisions surfacing at healthy rates.")


def _cmd_validate(_args: argparse.Namespace) -> None:
    """Check all decision files for parse and validation errors."""
    from .store import DecisionStore

    store = DecisionStore()
    valid, errors = store.validate_all()

    if not errors:
        print(f"All {len(valid)} decision files are valid.")
        return

    print(f"{len(errors)} error(s) in decision files:\n")
    current_file = ""
    for filename, err in errors:
        if filename != current_file:
            print(f"  {filename}:")
            current_file = filename
        print(f"    - {err}")
    print()
    print(f"{len(valid)} valid, {len(set(f for f, _ in errors))} with errors")
    sys.exit(1)


def _cmd_dismiss(_args: argparse.Namespace) -> None:
    """Suppress all nudges for the rest of this session."""
    from .policy.engine import SessionState

    state = SessionState()
    state.mark_nudges_dismissed()
    print("Nudges dismissed for this session.")


def _cmd_help() -> None:
    """Print usage for user-facing commands."""
    print("Usage: python3 -m decision <command> [args...]\n")
    print("Commands:")
    print("  search <keywords> [--json] [--limit N]  Search decisions (FTS5 + BM25)")
    print("  show <slug>                             Display full decision")
    print("  list [--tag <tag>] [--json]             Browse decisions")
    print("  tags [--json]                           List tags with counts")
    print("  stats [--json] [--health]               Health check (staleness, surfacing analytics)")
    print("  validate                                Check decision files for errors")
    print("  undo [slug]                             Revert a decision")
    print("  dismiss                                 Suppress nudges for this session")
    print("  help                                    Show this message")
    print("\nDiagnostic:")
    print("  enrich <slug> [--json]                  Analyze a decision for enrichment opportunities")
    print("  tree [--json]                           Show decisions grouped by codebase area")
    print("  coverage [--json]                       Show decision coverage across the codebase")


def _cmd_policy(args: argparse.Namespace | None = None) -> None:
    """Evaluate policies for a hook event, or list all policies."""
    from .policy.defs import ALL_POLICIES
    from .policy.engine import PolicyEngine, SessionState

    # Support direct calls from tests that patch sys.argv
    if args is None:
        parser = _build_parser()
        args = parser.parse_args()

    event = args.event or ""

    if not event:
        engine = PolicyEngine()
        for p in ALL_POLICIES:
            engine.register(p)
        print(json.dumps(engine.list_policies(), indent=2))
        return

    trace_flag = args.trace

    input_text = sys.stdin.read()
    try:
        input_data = json.loads(input_text) if input_text.strip() else {}
    except json.JSONDecodeError:
        input_data = {}

    engine = PolicyEngine()
    for p in ALL_POLICIES:
        engine.register(p)

    if trace_flag:
        engine.trace_enabled = True

    state = SessionState()
    result = engine.evaluate(event, input_data, state)
    state.flush_activity()

    if trace_flag:
        parsed = json.loads(result) if result else {}
        print(json.dumps({"result": parsed, "trace": engine.last_trace}, indent=2))
    else:
        print(result)


def _cmd_coverage(args: argparse.Namespace) -> None:
    """Show decision coverage across the codebase."""
    import subprocess

    from .policy.related_context import _affects_match
    from .store import DecisionStore
    from .utils.constants import SKIP_FILE_PATTERNS

    store = DecisionStore()
    decisions_data = store.decisions_with_affects()

    # Get tracked source files via git
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        all_files = result.stdout.strip().split("\n") if result.stdout.strip() else []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("Could not list files (git not available).", file=sys.stderr)
        sys.exit(1)

    # Filter to source files (exclude tests, config, docs, decisions)
    source_files = [
        f for f in all_files if f and not any(pat in f for pat in SKIP_FILE_PATTERNS) and not f.endswith(".md")
    ]

    if not source_files:
        print("No source files found.")
        return

    covered: list[tuple[str, list[str]]] = []
    uncovered: list[str] = []
    for f in source_files:
        matching = [title for _, title, _, _, affects in decisions_data if _affects_match(affects, f)]
        if matching:
            covered.append((f, matching))
        else:
            uncovered.append(f)

    total = len(source_files)
    pct = round(len(covered) / total * 100) if total else 0

    if getattr(args, "as_json", False):
        _json_out(
            {
                "total_files": total,
                "covered": len(covered),
                "uncovered": len(uncovered),
                "coverage_pct": pct,
                "uncovered_dirs": _group_by_dir(uncovered),
            }
        )
        return

    print(f"Decision coverage: {len(covered)}/{total} source files ({pct}%)")

    if uncovered:
        by_dir = _group_by_dir(uncovered)
        print("\nUncovered directories:")
        for d, count in sorted(by_dir.items(), key=lambda x: -x[1]):
            print(f"  {d}/ ({count} files)")


def _group_by_dir(files: list[str]) -> dict[str, int]:
    """Group file paths by parent directory, return dir → count."""
    from collections import defaultdict
    from pathlib import PurePosixPath

    by_dir: defaultdict[str, int] = defaultdict(int)
    for f in files:
        d = str(PurePosixPath(f).parent)
        by_dir[d] += 1
    return dict(by_dir)


# ── Enrich command ───────────────────────────────────────────────────


def _cmd_enrich(args: argparse.Namespace) -> None:
    """Analyze a decision for enrichment opportunities."""
    import re

    from .core.decision import Decision
    from .store.store import DecisionStore
    from .utils.helpers import _discover_decisions_dir

    decisions_dir = _discover_decisions_dir()
    target = _find_decision_file(decisions_dir, args.slug)
    if target is None:
        sys.exit(1)

    dec = Decision.from_file(target)
    store = DecisionStore(decisions_dir)

    findings: dict[str, list[str]] = {
        "conflicts": [],
        "reasoning_gaps": [],
        "missing_affects": [],
        "suggestions": [],
    }

    # 1. Contradiction check
    try:
        from .utils.contradiction import find_contradictions
        from .utils.similarity import find_overlapping_decisions

        overlaps = find_overlapping_decisions(dec, store, threshold=2.0, max_results=5)
        if overlaps:
            overlap_slugs = {s for s, _, _ in overlaps}
            bodies = store.get_bodies(overlap_slugs)
            affects_data: dict[str, list[str]] = {}
            for slug, _t, _d, _tags, affects in store.decisions_with_affects():
                if slug in overlap_slugs:
                    affects_data[slug] = affects

            for slug, title, _score in overlaps:
                body = bodies.get(slug, "")
                if body:
                    score = find_contradictions(dec.body, body, dec.affects, affects_data.get(slug, []))
                    if score >= 0.5:
                        findings["conflicts"].append(f"{slug} ({title}) — score {score:.2f}")
    except Exception:
        pass

    # 2. Reasoning depth check
    content_lines = [ln for ln in dec.body.splitlines() if ln and not ln.startswith("#")]
    content_text = " ".join(content_lines)

    has_reasoning = bool(Decision._REASONING_RE.search(dec.body))
    alternatives_re = re.compile(
        r"\b(instead of|rather than|alternative|considered|rejected|ruled out|over)\b",
        re.IGNORECASE,
    )
    has_alternatives = bool(alternatives_re.search(dec.body))

    if not has_reasoning:
        findings["reasoning_gaps"].append("No reasoning language (because, trade-off, chose)")
    if not has_alternatives:
        findings["reasoning_gaps"].append("No alternatives mentioned (instead of, rejected, ruled out)")
    if len(content_text) < 100:
        findings["reasoning_gaps"].append(f"Body is thin ({len(content_text)} chars of content)")

    # 3. Missing affects
    if not dec.affects:
        findings["missing_affects"].append("No affects paths — decision won't auto-surface")
        # Suggest from sibling decisions with shared tags
        if dec.tags:
            from .utils.affects import suggest_affects_from_tags

            suggested = suggest_affects_from_tags(dec.tags, store)
            if suggested:
                for s in suggested[:5]:
                    findings["missing_affects"].append(f"Suggested: {s}")
    else:
        # Check for stale paths
        for p in dec.affects:
            if "*" in p or "?" in p:
                continue
            check = Path(p)
            if p.endswith("/"):
                if not check.is_dir():
                    findings["missing_affects"].append(f"Stale path: {p}")
            elif not check.is_file():
                findings["missing_affects"].append(f"Stale path: {p}")

        # Suggest additional affects from siblings
        if dec.tags:
            from .utils.affects import suggest_additional_affects

            additional = suggest_additional_affects(dec.affects, dec.tags, store)
            if additional:
                for s in additional[:3]:
                    findings["suggestions"].append(f"Consider adding affects: {s}")

    # 4. Generate suggestions
    if findings["conflicts"]:
        findings["suggestions"].append("Review conflicting decisions for consistency")
    if findings["reasoning_gaps"]:
        findings["suggestions"].append("Expand the reasoning: what you rejected, trade-offs, constraints")
    if not dec.affects:
        findings["suggestions"].append("Add affects paths so the decision auto-surfaces when editing related code")

    # Output
    if getattr(args, "as_json", False):
        _json_out(findings)
        return

    has_any = any(v for v in findings.values())
    if not has_any:
        print(f"Decision `{dec.slug}` looks well-formed — no enrichment needed.")
        return

    print(f"Enrichment analysis for `{dec.slug}`:\n")
    if findings["conflicts"]:
        print("Conflicts:")
        for c in findings["conflicts"]:
            print(f"  ⚠ {c}")
        print()
    if findings["reasoning_gaps"]:
        print("Reasoning gaps:")
        for g in findings["reasoning_gaps"]:
            print(f"  - {g}")
        print()
    if findings["missing_affects"]:
        print("Affects:")
        for a in findings["missing_affects"]:
            print(f"  - {a}")
        print()
    if findings["suggestions"]:
        print("Suggestions:")
        for s in findings["suggestions"]:
            print(f"  → {s}")


# ── Tree command ─────────────────────────────────────────────────────


def _cmd_tree(args: argparse.Namespace) -> None:
    """Show decisions grouped by codebase area (based on affects paths)."""
    from collections import defaultdict
    from pathlib import PurePosixPath

    from .store.store import DecisionStore

    store = DecisionStore()

    # Build area → decisions mapping
    area_decisions: defaultdict[str, list[tuple[str, str, list[str]]]] = defaultdict(list)
    slugs_with_affects: set[str] = set()

    for slug, _title, date, tags, affects in store.decisions_with_affects():
        slugs_with_affects.add(slug)
        areas_seen: set[str] = set()
        for a in affects:
            a = a.lstrip("./")
            if a.endswith("/"):
                area = a.rstrip("/") + "/"
            elif "*" in a or "?" in a:
                # Glob: use directory part
                area = str(PurePosixPath(a).parent) + "/"
            else:
                area = str(PurePosixPath(a).parent) + "/"
            if area not in areas_seen:
                areas_seen.add(area)
                area_decisions[area].append((slug, date, tags))

    # Collect decisions without affects
    no_affects: list[tuple[str, str, list[str]]] = []
    for summary in store.list_summaries():
        if summary.slug not in slugs_with_affects:
            no_affects.append((summary.slug, summary.date, summary.tags))

    if getattr(args, "as_json", False):
        data: dict[str, object] = {
            "areas": {
                area: [{"slug": s, "date": d, "tags": t} for s, d, t in entries]
                for area, entries in sorted(area_decisions.items())
            },
        }
        if no_affects:
            data["no_affects"] = [{"slug": s, "date": d, "tags": t} for s, d, t in no_affects]
        _json_out(data)
        return

    if not area_decisions and not no_affects:
        print("No decisions found.")
        return

    for area in sorted(area_decisions):
        entries = sorted(area_decisions[area], key=lambda x: x[1])
        n = len(entries)
        print(f"{area:<30s} {n} decision{'s' if n != 1 else ''}")
        for slug, date, tags in entries:
            tag_str = "  ".join(f"#{t}" for t in tags)
            print(f"  {slug:<28s} {date}  {tag_str}")
        print()

    if no_affects:
        n = len(no_affects)
        print(f"{'(no affects)':<30s} {n} decision{'s' if n != 1 else ''}")
        for slug, date, tags in sorted(no_affects, key=lambda x: x[1]):
            tag_str = "  ".join(f"#{t}" for t in tags)
            print(f"  {slug:<28s} {date}  {tag_str}")


# ── Dispatch ─────────────────────────────────────────────────────────

_CommandFn = Callable[[argparse.Namespace], None]

_COMMAND_DISPATCH: dict[str, _CommandFn] = {
    "search": _cmd_search,
    "show": _cmd_show,
    "list": _cmd_list,
    "tags": _cmd_tags,
    "stats": _cmd_stats,
    "validate": _cmd_validate,
    "undo": _cmd_undo,
    "coverage": _cmd_coverage,
    "tree": _cmd_tree,
    "enrich": _cmd_enrich,
    "dismiss": _cmd_dismiss,
    "help": lambda _args: _cmd_help(),
    "policy": _cmd_policy,
}


def main() -> None:
    if len(sys.argv) < 2:
        _cmd_help()
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd in ("--version", "-V"):
        from decision._version import __version__

        print(f"decision {__version__}")
        sys.exit(0)

    if cmd not in _COMMAND_DISPATCH:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print("Run 'python3 -m decision help' for available commands.", file=sys.stderr)
        sys.exit(1)

    # search requires at least one keyword — check before argparse to give clean error
    if cmd == "search" and len(sys.argv) < 3:
        print("Usage: python3 -m decision search <keywords> [--json] [--limit N]", file=sys.stderr)
        sys.exit(1)

    # show requires a slug
    if cmd == "show" and len(sys.argv) < 3:
        print("Usage: python3 -m decision show <slug>", file=sys.stderr)
        sys.exit(1)

    parser = _build_parser()
    args = parser.parse_args()
    _COMMAND_DISPATCH[cmd](args)
