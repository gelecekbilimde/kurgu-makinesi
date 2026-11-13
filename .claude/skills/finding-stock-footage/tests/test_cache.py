import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from helpers import cand  # noqa: F401  (sets sys.path)
from cache import Cache  # noqa: E402

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)


class Model(unittest.TestCase):
    def test_orientation(self):
        self.assertEqual(cand(width=1920, height=1080).orientation, "horizontal")
        self.assertEqual(cand(width=1080, height=1920).orientation, "vertical")
        self.assertEqual(cand(width=1080, height=1080).orientation, "square")
        self.assertEqual(cand(width=1080, height=1920).long_side, 1920)


class CacheTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.cache = Cache(self.root)

    def test_sidecar_roundtrip(self):
        self.cache.write_sidecar(cand(id="42"), "rocket launch", NOW)
        side = self.cache.read_sidecars()
        self.assertEqual(len(side), 1)
        s = side[0]
        self.assertEqual(s["schema"], 1)
        self.assertEqual(s["kind"], "stock")
        self.assertEqual(s["file"], "clips/pixabay/42.mp4")
        self.assertIn("rocket launch", s["keywords"])
        for key in ("source", "id", "title", "description", "keywords", "width", "height", "fps", "duration_s",
                    "orientation", "creator", "credit", "licence", "page_url", "warnings", "third_party", "added"):
            self.assertIn(key, s)

    def test_sidecar_adds_query(self):
        self.cache.write_sidecar(cand(id="42"), "launch", NOW)
        self.cache.write_sidecar(cand(id="42"), "rocket", NOW)
        self.cache.add_query("pixabay", "42", "launch")
        kw = self.cache.read_sidecars()[0]["keywords"]
        self.assertIn("launch", kw)
        self.assertIn("rocket", kw)
        self.assertEqual(len(kw), len(set(kw)))

    def test_has_clip_needs_both_files(self):
        p = self.cache.clip_path("nasa", "X")
        p.parent.mkdir(parents=True)
        p.write_bytes(b"v")
        self.assertFalse(self.cache.has_clip("nasa", "X"))
        self.cache.write_sidecar(cand(source="nasa", id="X"), "q", NOW)
        self.assertTrue(self.cache.has_clip("nasa", "X"))

    def test_response_cache_age(self):
        self.cache.put_response("pixabay", "https://x?q=a", {"hits": [1]}, now=0)
        self.assertEqual(self.cache.get_response("pixabay", "https://x?q=a", 86400, now=86399), {"hits": [1]})
        self.assertIsNone(self.cache.get_response("pixabay", "https://x?q=a", 86400, now=86401))
        self.assertIsNone(self.cache.get_response("pixabay", "https://x?q=b", 86400, now=1))

    def test_index_rebuilt_from_sidecars(self):
        self.cache.write_sidecar(cand(id="1"), "q", NOW)
        self.cache.write_sidecar(cand(id="2"), "q", NOW)
        idx = self.root / "index.json"
        if idx.exists():
            idx.unlink()
        entries = self.cache.write_index()
        self.assertEqual(len(entries), 2)
        self.assertEqual(len(json.loads(idx.read_text())["entries"]), 2)
        self.assertFalse([f for f in os.listdir(self.root) if f.endswith(".tmp")])


if __name__ == "__main__":
    unittest.main()
