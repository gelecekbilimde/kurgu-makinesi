"""The local stock cache (assets/stock/).

Layout:
  clips/<slug>/<id>.mp4    the clip
  clips/<slug>/<id>.json   its sidecar: the source of truth for everything known about the clip
  searches/<slug>/<sha256>.json   cached API responses, reused for 24 hours
  index.json               derived from the sidecars; rebuild any time with write_index()

The sidecar schema is not stock-specific so the future archive index can hold the same records
(kind "archive"). Readers ignore fields they do not know.
"""
import hashlib
import json
import os
from pathlib import Path

SCHEMA = 1


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _add_unique(items, value):
    if value and value not in items:
        items.append(value)


class Cache:
    def __init__(self, root):
        self.root = Path(root)

    def clip_path(self, slug, id):
        return self.root / "clips" / slug / f"{id}.mp4"

    def sidecar_path(self, slug, id):
        return self.root / "clips" / slug / f"{id}.json"

    def has_clip(self, slug, id):
        return self.clip_path(slug, id).is_file() and self.sidecar_path(slug, id).is_file()

    def read_sidecar(self, slug, id):
        path = self.sidecar_path(slug, id)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def write_sidecar(self, c, query, now):
        """Create the sidecar for candidate c, or add the query to an existing one. Returns the sidecar."""
        side = self.read_sidecar(c.source, c.id)
        if side is None:
            keywords = []
            for k in c.keywords:
                _add_unique(keywords, k)
            side = {"schema": SCHEMA, "kind": "stock", "source": c.source, "id": c.id,
                    "file": f"clips/{c.source}/{c.id}.mp4", "title": c.title, "description": c.description,
                    "keywords": keywords, "width": c.width, "height": c.height, "fps": c.fps,
                    "duration_s": c.duration_s, "orientation": c.orientation, "creator": c.creator,
                    "credit": c.credit, "licence": c.licence, "page_url": c.page_url,
                    "warnings": list(c.warnings), "added": now.isoformat()}
        _add_unique(side["keywords"], query)
        _write_json(self.sidecar_path(c.source, c.id), side)
        return side

    def add_query(self, slug, id, query):
        side = self.read_sidecar(slug, id)
        if side is not None and query not in side["keywords"]:
            side["keywords"].append(query)
            _write_json(self.sidecar_path(slug, id), side)
        return side

    def read_sidecars(self):
        clips = self.root / "clips"
        if not clips.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(clips.glob("*/*.json"))]

    def _response_path(self, slug, key):
        return self.root / "searches" / slug / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")

    def get_response(self, slug, key, max_age_s, now):
        path = self._response_path(slug, key)
        if not path.is_file():
            return None
        stored = json.loads(path.read_text(encoding="utf-8"))
        if now - stored["fetched"] > max_age_s:
            return None
        return stored["data"]

    def put_response(self, slug, key, data, now):
        _write_json(self._response_path(slug, key), {"key": key, "fetched": now, "data": data})

    def write_index(self):
        entries = self.read_sidecars()
        _write_json(self.root / "index.json", {"schema": SCHEMA, "entries": entries})
        return entries

    def read_index(self):
        path = self.root / "index.json"
        if not path.is_file():
            return self.write_index() if (self.root / "clips").is_dir() else []
        return json.loads(path.read_text(encoding="utf-8"))["entries"]
