#!/usr/bin/env python3
"""Script parsing for Kurgu Makinesi: '## ' chapter headings (with their text) and '#tag' lines."""

import re
from pathlib import Path
from typing import Dict, List

_CHAPTER = re.compile(r"^##[ \t]+(.+?)[ \t]*$")
_TAG = re.compile(r"^#[a-zA-Z0-9_-]+$")
SCRIPT_EXTENSIONS = {".txt", ".md", ".rst", ".html", ".htm"}


def extract_chapters(content: str) -> List[Dict]:
    """[{'title', 'content'}]: each '## title' line starts a chapter; its content is the lines up to the next
    chapter, with '#tag' lines left out."""
    chapters: List[Dict] = []
    body: List[str] = []
    for line in content.splitlines():
        m = _CHAPTER.match(line)
        if m:
            if chapters:
                chapters[-1]["content"] = "\n".join(body).strip()
            chapters.append({"title": m.group(1), "content": ""})
            body = []
        elif chapters and not _TAG.match(line.strip()):
            body.append(line)
    if chapters:
        chapters[-1]["content"] = "\n".join(body).strip()
    return chapters


class Script:
    """A script with chapters and tags."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.chapters: List[Dict] = []
        self.tags: set = set()

    def load(self, path: str = None) -> "Script":
        content = Path(path or self.path).read_text(encoding="utf-8")
        self.chapters = extract_chapters(content)
        self.tags = {line.strip().lower() for line in content.splitlines() if _TAG.match(line.strip())}
        return self

    @property
    def titles(self) -> List[str]:
        return [c["title"] for c in self.chapters]

    def __str__(self) -> str:
        tags = ", ".join(sorted(self.tags)) if self.tags else "none"
        return f"Script: {self.path}\n  Chapters: {len(self.chapters)}\n  Tags: {tags}"


def find_script_files(directory: str = ".") -> List[Path]:
    """Script files under a directory (.git and hidden folders skipped)."""
    found = set()
    for ext in SCRIPT_EXTENSIONS:
        for p in Path(directory).glob(f"**/*{ext}"):
            if not any(part.startswith(".") for part in p.relative_to(directory).parts):
                found.add(p)
    return sorted(found)
