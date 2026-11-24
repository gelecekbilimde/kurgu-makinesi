#!/usr/bin/env python3
# shared/script_parser.py
"""
Shared utilities for Kurgu Makinesi rough cutting tool.
"""

import re
from pathlib import Path
from typing import List, Dict, Optional


class Script:
    """Represents a script with chapters and tags."""
    
    def __init__(self, path: str):
        self.path = Path(path)
        self.chapters: List[Dict] = []
        self.tags: set = set()
        self._content: Optional[str] = None
    
    def load(self, path: str) -> "Script":
        """Load and parse the script file."""
        content = Path(path).read_text(encoding="utf-8")
        self._content = content
        
        # Parse chapters (## headers)
        chapter_pattern = r"^##\s+(.+?)$"
        for match in re.finditer(chapter_pattern, content, re.MULTILINE):
            chapter_title = match.group(1).strip()
            self.chapters.append({
                "title": chapter_title,
                "content": ""  # Would need more complex parsing
            })
        
        # Parse tags (#tags)
        tag_pattern = r"^#[a-zA-Z0-9_-]+$"
        for match in re.finditer(tag_pattern, content, re.MULTILINE):
            self.tags.add(match.group(0).lower())
        
        return self
    
    def __str__(self) -> str:
        """String representation."""
        lines = [
            f"Script: {self.path}",
            f"  Chapters: {len(self.chapters)}",
            f"  Tags: {", ".join(sorted(self.tags)) if self.tags else "none"}"
        ]
        return "\n".join(lines)


def find_script_files(directory: str = ".") -> List[Path]:
    """Find all script files in a directory."""
    extensions = {".txt", ".md", ".rst", ".html", ".htm"}
    found = []
    
    for ext in extensions:
        pattern = f"**/*{ext}"
        found.extend(Path(directory).glob(pattern))
    
    return sorted(set(found))


def extract_chapters(content: str) -> List[Dict]:
    """Extract chapters from raw content."""
    chapters = []
    chapter_pattern = r"^##\s+(.+?)$"
    
    for match in re.finditer(chapter_pattern, content, re.MULTILINE):
        title = match.group(1).strip()
        chapters.append({"title": title})
    
    return chapters

