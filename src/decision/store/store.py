"""DecisionStore — manages decision files in .claude/decisions/."""

from __future__ import annotations

from pathlib import Path

from ..core.decision import Decision
from ..utils.constants import DEFAULT_QUERY_LIMIT, StrPath
from ..utils.helpers import _log
from .index import DecisionAffects, DecisionIndex, DecisionSummary, SearchResult


class DecisionStore:
    """Manages decision files in .claude/decisions/."""

    def __init__(self, decisions_dir: StrPath | None = None, *, db_dir: StrPath | None = None):
        if decisions_dir:
            self.decisions_dir = Path(decisions_dir)
        else:
            from ..utils.helpers import _discover_decisions_dir

            self.decisions_dir = _discover_decisions_dir()
        self._db_dir = db_dir
        self.__index: DecisionIndex | None = None

    @property
    def _index(self) -> DecisionIndex:
        """Lazy-initialized, cached DecisionIndex."""
        if self.__index is None:
            self.__index = DecisionIndex(self.decisions_dir, db_dir=self._db_dir)
        return self.__index

    def ensure_dir(self) -> None:
        """Create decisions directory if it doesn't exist."""
        self.decisions_dir.mkdir(parents=True, exist_ok=True)

    def list_decisions(self) -> list[Decision]:
        """List all decision files, sorted by date descending."""
        decisions: list[Decision] = []

        if self.decisions_dir.is_dir():
            for f in self.decisions_dir.glob("*.md"):
                try:
                    d = Decision.from_file(f)
                    decisions.append(d)
                except (OSError, ValueError) as exc:
                    _log(f"skipping {f.name}: {exc}")

        decisions.sort(key=lambda s: s.date, reverse=True)
        return decisions

    def query(
        self,
        keywords: str,
        limit: int = DEFAULT_QUERY_LIMIT,
        exclude_slugs: set[str] | None = None,
    ) -> str:
        """Keyword search returning formatted text for context injection.

        Use search() instead for structured SearchResult objects (e.g. CLI display).
        """
        from .query import query_relevant

        return query_relevant(self, keywords, limit, exclude_slugs=exclude_slugs)

    def validate_all(self) -> tuple[list[Decision], list[tuple[str, str]]]:
        """Validate all decision files. Returns (valid_decisions, [(filename, error), ...])."""
        valid: list[Decision] = []
        errors: list[tuple[str, str]] = []
        if not self.decisions_dir.is_dir():
            return valid, errors
        for f in sorted(self.decisions_dir.glob("*.md")):
            try:
                d = Decision.from_file(f)
            except (OSError, ValueError) as exc:
                errors.append((f.name, f"Parse error: {exc}"))
                continue
            validation_errors = d.validate()
            if validation_errors:
                for err in validation_errors:
                    errors.append((f.name, err))
            else:
                valid.append(d)
        return valid, errors

    def decision_count(self) -> int:
        """Count decision files without fully parsing them."""
        if self.decisions_dir.is_dir():
            return sum(1 for _ in self.decisions_dir.glob("*.md"))
        return 0

    def search(self, query_str: str, limit: int = DEFAULT_QUERY_LIMIT) -> list[SearchResult]:
        """FTS5 search with BM25 ranking. Falls back to empty if unavailable."""
        if self._index.available:
            return self._index.search(query_str, limit)
        return []

    def list_summaries(self) -> list[DecisionSummary]:
        """Return lightweight decision summaries from the index (no file parsing).

        Progressive loading: use this for browsing, then read full files on demand.
        Falls back to list_decisions() if FTS5 is unavailable.
        """
        if self._index.available:
            return self._index.list_summaries()
        # Fallback: parse all files
        decisions = self.list_decisions()
        return [
            DecisionSummary(
                slug=d.slug,
                title=d.title,
                date=d.date,
                description=d.description,
                tags=d.tags,
                excerpt=d.excerpt,
            )
            for d in decisions
        ]

    def decisions_with_affects(self) -> list[DecisionAffects]:
        """Return decisions with non-empty affects paths.

        Queries the FTS5 index directly — avoids parsing all decision files from disk.
        Falls back to list_decisions() if the index is unavailable.
        """
        if self._index.available:
            return self._index.decisions_with_affects()
        # Fallback: parse all files
        return [
            DecisionAffects(slug=d.name, title=d.title, date=d.date, tags=d.tags, affects=d.affects)
            for d in self.list_decisions()
            if d.affects
        ]

    def get_bodies(self, slugs: set[str]) -> dict[str, str]:
        """Return {slug: body} for the given slugs.

        Uses FTS5 index when available, falls back to file parsing.
        """
        if self._index.available:
            return self._index.get_bodies(slugs)
        result: dict[str, str] = {}
        for d in self.list_decisions():
            if d.slug in slugs:
                result[d.slug] = d.body
        return result

    def by_tag(self, tag: str) -> list[SearchResult]:
        """Find decisions with an exact tag match."""
        if self._index.available:
            return self._index.by_tag(tag)
        return []

    def all_tags(self) -> dict[str, int]:
        """Return tag -> count mapping for active decisions."""
        if self._index.available:
            return self._index.all_tags()

        # Fallback: manual counting
        from collections import Counter

        tag_counts: Counter[str] = Counter()
        for d in self.list_decisions():
            for tag in d.tags:
                tag_counts[tag] += 1
        return dict(tag_counts)
