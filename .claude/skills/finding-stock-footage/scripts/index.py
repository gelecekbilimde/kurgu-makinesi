"""Search over clip index entries (sidecar dicts). Knows nothing about APIs, so the archive index can reuse it."""
import re


def tokens(text):
    return set(re.findall(r"\w+", text.casefold()))


def match(entries, query, orientation=None):
    """Entries whose title + keywords contain every query word; wanted orientation first, then newest."""
    wanted = tokens(query)
    if not wanted:
        return []
    found = [e for e in entries if wanted <= tokens(" ".join([e.get("title", "")] + list(e.get("keywords", []))))]
    found.sort(key=lambda e: (e.get("source", ""), e.get("id", "")))
    found.sort(key=lambda e: e.get("added", ""), reverse=True)
    found.sort(key=lambda e: orientation is not None and e.get("orientation") != orientation)
    return found
