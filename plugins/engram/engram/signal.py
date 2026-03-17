"""Signal dataclass — parsed representation of a signal markdown file."""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from ._constants import StrPath
from ._frontmatter import _FM_FIELDS, _split_frontmatter
from ._helpers import _parse_links


@dataclasses.dataclass
class Signal:
    """Parsed representation of a signal markdown file."""
    title: str = ""
    body: str = ""
    sig_type: str = "decision"
    date: str = ""
    tags: str = "[]"
    source: str = ""
    supersedes: str = ""
    links: str = ""
    status: str = "active"
    _has_frontmatter: bool = dataclasses.field(default=True, repr=False)

    @classmethod
    def from_text(cls, text: str) -> Signal:
        """Parse markdown with YAML frontmatter into a Signal."""
        meta: dict[str, str] = {
            "type": "",
            "date": "",
            "tags": "[]",
            "source": "",
            "supersedes": "",
            "links": "",
            "status": "active",
        }

        fm_lines, content_lines = _split_frontmatter(text)
        has_fm = bool(fm_lines) or text.splitlines()[:1] == ["---"]

        for line in fm_lines:
            key, _, val = line.partition(":")
            if key in _FM_FIELDS:
                meta[key] = _FM_FIELDS[key](val)

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

        return cls(
            title=title,
            body=body,
            sig_type=meta["type"] or "decision",
            date=meta["date"],
            tags=meta["tags"],
            source=meta["source"],
            supersedes=meta["supersedes"],
            links=meta["links"],
            status=meta["status"],
            _has_frontmatter=has_fm,
        )

    @classmethod
    def from_file(cls, filepath: StrPath) -> Signal:
        """Read and parse a signal file."""
        text = Path(filepath).read_text(errors="replace")
        return cls.from_text(text)

    @property
    def excerpt(self) -> str:
        """First non-empty, non-heading line of body, truncated to 120 chars."""
        for line in self.body.splitlines():
            if line and not line.startswith("#"):
                return line[:120]
        return ""

    @property
    def content(self) -> str:
        """Title + newline + body."""
        return self.title + "\n" + self.body

    def validate(self) -> tuple[bool, str]:
        """Validate signal fields. Returns (ok, errors_string)."""
        errors = []

        if not self._has_frontmatter:
            errors.append("missing frontmatter delimiters (---)")
        else:
            # Check date
            if not self.date or not re.match(r"^\d{4}-\d{2}-\d{2}$", self.date):
                errors.append("missing or invalid date: field (need YYYY-MM-DD)")

            # Check tags
            if not self.tags or self.tags == "[]":
                errors.append("tags: must have at least one tag (not empty [])")

        # Check title and lead paragraph
        if not self.title:
            errors.append("missing H1 title (# ...)")

        lead_paragraph = ""
        for line in self.body.splitlines():
            if not lead_paragraph:
                if not line or line.startswith("#"):
                    continue
                lead_paragraph = line

        if not lead_paragraph or len(lead_paragraph) < 20:
            errors.append("lead paragraph after title must exist and be >= 20 chars (explains why)")

        return (len(errors) == 0, "; ".join(errors) + "; " if errors else "")

    def parsed_links(self) -> list[tuple[str, str]]:
        """Parse links field into list of (rel, target)."""
        return _parse_links(self.links)
