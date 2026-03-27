"""Decision dataclass — parsed representation of a decision markdown file."""

from __future__ import annotations

import dataclasses
import datetime
import re
from pathlib import Path

from ..utils.constants import (
    EXCERPT_MAX_LEN,
    MIN_LEAD_PARAGRAPH,
    SLUG_MAX_LEN,
    StrPath,
)
from ..utils.frontmatter import _split_yaml_frontmatter
from ..utils.helpers import _parse_list_field


@dataclasses.dataclass(slots=True)
class Decision:
    """Parsed representation of a decision markdown file (YAML frontmatter).

    Frontmatter fields: name, description, date, tags, status, affects.
    Body: H1 title + markdown content explaining why.
    """

    title: str = ""
    body: str = ""
    name: str = ""
    description: str = ""
    date: str = ""
    tags: list[str] = dataclasses.field(default_factory=list)
    affects: list[str] = dataclasses.field(default_factory=list)
    has_frontmatter: bool = dataclasses.field(default=True, repr=False)
    file_path: str = dataclasses.field(default="", repr=False)

    @classmethod
    def from_text(cls, text: str) -> Decision:
        """Parse markdown with YAML frontmatter into a Decision."""
        fm, content_lines = _split_yaml_frontmatter(text)
        has_fm = bool(fm) or text.splitlines()[:1] == ["---"]

        title = ""
        body_lines = []
        found_title = False
        for line in content_lines:
            if not found_title and line.startswith("# "):
                title = line[2:]
                found_title = True
                continue
            body_lines.append(line)

        body = "\n".join(body_lines) + "\n" if body_lines else ""

        tags = _parse_list_field(fm.get("tags", []))
        affects = _parse_list_field(fm.get("affects", []))

        return cls(
            title=title,
            body=body,
            name=str(fm.get("name", "")),
            description=str(fm.get("description", "")),
            date=str(fm.get("date", "")),
            tags=tags,
            affects=affects,
            has_frontmatter=has_fm,
        )

    @classmethod
    def from_file(cls, filepath: StrPath) -> Decision:
        """Read and parse a decision file."""
        text = Path(filepath).read_text(errors="replace")
        d = cls.from_text(text)
        d.file_path = str(filepath)
        return d

    @property
    def slug(self) -> str:
        """Derive slug from file_path if set, else from name."""
        if self.file_path:
            return Path(self.file_path).stem
        return self.name

    _REASONING_RE = re.compile(
        r"\b(because|instead of|rather than|trade.?off|downside|alternative"
        r"|chose|over|ruled out|opted|picked|decided|rejected)\b",
        re.IGNORECASE,
    )

    @property
    def excerpt(self) -> str:
        """First non-empty, non-heading line of body, truncated."""
        for line in self.body.splitlines():
            if line and not line.startswith("#"):
                return line[:EXCERPT_MAX_LEN]
        return ""

    @property
    def reasoning_excerpt(self) -> str:
        """First sentence containing reasoning language, or fallback to excerpt."""
        for line in self.body.splitlines():
            if not line or line.startswith("#"):
                continue
            if self._REASONING_RE.search(line):
                return line[:EXCERPT_MAX_LEN]
        return self.excerpt

    def validate(self) -> list[str]:
        """Validate decision fields. Returns list of error strings (empty = valid)."""
        errors: list[str] = []

        if not self.has_frontmatter:
            errors.append("Add YAML frontmatter delimiters (`---`) at the top and bottom of the metadata block")
        else:
            if not self.name:
                errors.append('Add a `name` field — the decision\'s unique slug (e.g. `name: "use-redis-for-caching"`)')
            elif len(self.name) > SLUG_MAX_LEN:
                errors.append(
                    f"`name` is {len(self.name)} characters — keep it under {SLUG_MAX_LEN}"
                    f' (e.g. `name: "use-redis-for-caching"`)'
                )
            elif re.search(r'[/\\<>:"|?*\x00-\x1f]', self.name):
                errors.append(
                    f'`name` "{self.name}" contains invalid filename characters'
                    " — use only alphanumeric, hyphens, and underscores"
                )
            if not self.description:
                errors.append(
                    'Add a `description` field — a one-line summary (e.g. `description: "Use Redis for caching"`)'
                )

            # Check date: format AND semantic validity
            if not self.date or not re.match(r"^\d{4}-\d{2}-\d{2}$", self.date):
                errors.append('Add a `date` field in YYYY-MM-DD format (e.g. `date: "2026-03-23"`)')
            else:
                try:
                    datetime.date.fromisoformat(self.date)
                except ValueError:
                    errors.append(f"The date `{self.date}` isn't a valid calendar date — check the month and day")

            # Check tags
            if not self.tags:
                errors.append('Add at least one tag to help with search and browsing (e.g. `tags:\\n  - "caching"`)')

            # Reject invalid affects paths
            for p in self.affects:
                if Path(p).is_absolute():
                    errors.append(f'`affects` path "{p}" is absolute — use paths relative to the repo root')
                    break
                if ".." in Path(p).parts:
                    errors.append(f'`affects` path "{p}" contains `..` — use paths relative to the repo root')
                    break

        # Check title and lead paragraph
        if not self.title:
            errors.append(
                "Add a title line starting with `# ` after the frontmatter (e.g. `# Use Redis for session caching`)"
            )

        lead_paragraph = ""
        for line in self.body.splitlines():
            if not lead_paragraph:
                if not line or line.startswith("#"):
                    continue
                lead_paragraph = line

        if not lead_paragraph or len(lead_paragraph) < MIN_LEAD_PARAGRAPH:
            errors.append(
                f"Add a lead paragraph after the title explaining *why* (at least {MIN_LEAD_PARAGRAPH} characters)"
            )

        return errors
