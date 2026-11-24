"""Script parser for Kurgu Makinesi (.md, .txt, .rst, .html).

Extracts chapter headings (##), subsection headings (###), and B-roll /
graphics directives ([STOK], [GRAFIK], [YAZI], [KAYNAK], [ARŞİV]).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

SCRIPT_EXTENSIONS = {".md", ".txt", ".rst", ".html", ".htm"}

_CHAPTER_RE = re.compile(r"^\s*##\s+(?!#)(.+?)\s*$")
_SUBSECTION_RE = re.compile(r"^\s*###\s+(.+?)\s*$")
_HTML_H2_RE = re.compile(r"<h2[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_HTML_H3_RE = re.compile(r"<h3[^>]*>(.*?)</h3>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(
    r"\[(STOK|GRAFIK|GRAFİK|YAZI|KAYNAK|ARŞİV|ARSIV)\]\s*:?\s*(.*)",
    re.IGNORECASE,
)


@dataclass
class ScriptTag:
    """A B-roll or graphic directive found inside a chapter."""

    kind: str  # STOK, GRAFIK, YAZI, KAYNAK, ARŞİV
    description: str
    chapter_index: int
    line_number: int


@dataclass
class ChapterInfo:
    """A parsed chapter from a script file."""

    index: int  # 1-based
    title: str
    subsections: List[str] = field(default_factory=list)
    tags: List[ScriptTag] = field(default_factory=list)


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _normalize_tag_kind(raw: str) -> str:
    upper = raw.upper().replace("İ", "I")
    mapping = {
        "STOK": "STOK",
        "GRAFIK": "GRAFIK",
        "YAZI": "YAZI",
        "KAYNAK": "KAYNAK",
        "ARŞIV": "ARŞİV",
        "ARSIV": "ARŞİV",
    }
    return mapping.get(upper, upper)


def parse_script(path: str | Path) -> List[ChapterInfo]:
    """Parse chapters, subsections, and B-roll tags from a script file."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    chapters: List[ChapterInfo] = []

    if p.suffix.lower() in {".html", ".htm"}:
        # Simple sequential scan for HTML headings and tags
        lines = text.splitlines()
        current: Optional[ChapterInfo] = None
        for lineno, line in enumerate(lines, start=1):
            h2 = _HTML_H2_RE.search(line)
            if h2:
                title = _strip_html(h2.group(1))
                current = ChapterInfo(index=len(chapters) + 1, title=title)
                chapters.append(current)
                continue
            h3 = _HTML_H3_RE.search(line)
            if h3 and current is not None:
                current.subsections.append(_strip_html(h3.group(1)))
                continue
            tag = _TAG_RE.search(_strip_html(line))
            if tag and current is not None:
                current.tags.append(
                    ScriptTag(
                        kind=_normalize_tag_kind(tag.group(1)),
                        description=tag.group(2).strip(),
                        chapter_index=current.index,
                        line_number=lineno,
                    )
                )
        return chapters

    current = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        m_ch = _CHAPTER_RE.match(line)
        if m_ch:
            current = ChapterInfo(index=len(chapters) + 1, title=m_ch.group(1).strip())
            chapters.append(current)
            continue
        m_sub = _SUBSECTION_RE.match(line)
        if m_sub and current is not None:
            current.subsections.append(m_sub.group(1).strip())
            continue
        m_tag = _TAG_RE.search(line)
        if m_tag and current is not None:
            current.tags.append(
                ScriptTag(
                    kind=_normalize_tag_kind(m_tag.group(1)),
                    description=m_tag.group(2).strip(),
                    chapter_index=current.index,
                    line_number=lineno,
                )
            )

    return chapters


def discover_scripts(directory: str | Path = ".") -> List[Path]:
    """Return script files in a directory that contain at least one ## chapter."""
    root = Path(directory)
    found: List[Path] = []
    if not root.exists():
        return found
    for item in sorted(root.iterdir()):
        if item.is_file() and item.suffix.lower() in SCRIPT_EXTENSIONS:
            try:
                if parse_script(item):
                    found.append(item)
            except OSError:
                continue
    return found
