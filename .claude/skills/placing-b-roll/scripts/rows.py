"""Script rows of an episode, assigned to rough-cutter chapters."""
import json
from dataclasses import dataclass, field


@dataclass
class Row:
    id: str
    key: str
    chapter: int  # 0-based, index in sections.json "chapters"
    tags: list
    visual: str
    links: list = field(default_factory=list)
    refs: list = field(default_factory=list)
    ses: str = ""
    est_s: float = 0


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load(ep):
    script = _read(ep.path("script.json"))
    chapters = _read(ep.path("sections.json"))["chapters"]
    headings = script.get("headings", [])
    out = []
    for r in script["rows"]:
        i = r.get("heading")
        title = None
        while i is not None and 0 <= i < len(headings):
            if headings[i]["level"] == 2:
                title = headings[i]["title"]
                break
            i -= 1
        if title is None or title not in chapters:
            raise ValueError(f"{r['id']}: bölüm bulunamadı ({title!r}) - sections.json'daki bölümlerle eşleşmiyor")
        out.append(Row(id=r["id"], key=r["key"], chapter=chapters.index(title), tags=list(r.get("tags", [])),
                       visual=r.get("visual", ""), links=list(r.get("links", [])), refs=list(r.get("refs", [])),
                       ses=r.get("ses", ""), est_s=r.get("est_s", 0)))
    return out


def broll_tags(row):
    """the row's tags that ask for B-roll (every tag but KAMERA)"""
    return [t for t in row.tags if t != "KAMERA"]


def is_mixed(row):
    """[KAMERA, X ...]: the presenter stays visible, the other tags are overlays (V3 only)"""
    return "KAMERA" in row.tags and bool(broll_tags(row))


def is_broll(row):
    """a row that gets B-roll: anything but a KAMERA-only row (untagged rows get a "tür yok" placeholder)"""
    return not row.tags or bool(broll_tags(row))


def broll_rows(rows, frozen):
    """B-roll rows (is_broll) of frozen chapters; frozen is the manifest's 1-based set."""
    f0 = {c - 1 for c in frozen}
    return [r for r in rows if r.chapter in f0 and is_broll(r)]
