import json
import os
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (sets sys.path)
from fakes import FakeHttp
from sources import load_sources  # noqa: E402

SHIPPED = Path(helpers.SCRIPTS).parent / "sources.json"


class Loading(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def config(self, entries):
        p = self.dir / "sources.json"
        p.write_text(json.dumps({"sources": entries}))
        return p

    def entry(self, slug, priority, enabled=True, url="https://example.org/"):
        return {"slug": slug, "url": url, "priority": priority, "isEnabled": enabled}

    def test_priority_order(self):
        cfg = self.config([self.entry("pixabay", 2), self.entry("nasa", 1)])
        srcs, notes = load_sources(cfg, {"PIXABAY_API_KEY": "k"}, FakeHttp())
        self.assertEqual([s.slug for s in srcs], ["nasa", "pixabay"])
        self.assertEqual(notes, [])

    def test_disabled_skipped_silently(self):
        cfg = self.config([self.entry("pexels", 3, enabled=False), self.entry("nasa", 1)])
        srcs, notes = load_sources(cfg, {}, FakeHttp())
        self.assertEqual([s.slug for s in srcs], ["nasa"])
        self.assertEqual(notes, [])

    def test_missing_key_note(self):
        cfg = self.config([self.entry("pixabay", 1), self.entry("nasa", 2)])
        srcs, notes = load_sources(cfg, {}, FakeHttp())
        self.assertEqual([s.slug for s in srcs], ["nasa"])
        self.assertEqual(notes, ["pixabay: PIXABAY_API_KEY yok, atlandı"])

    def test_empty_key_counts_as_missing(self):
        cfg = self.config([self.entry("pixabay", 1)])
        srcs, notes = load_sources(cfg, {"PIXABAY_API_KEY": ""}, FakeHttp())
        self.assertEqual(srcs, [])

    def test_unknown_slug_note(self):
        cfg = self.config([self.entry("shutterstock", 1)])
        srcs, notes = load_sources(cfg, {}, FakeHttp())
        self.assertEqual(srcs, [])
        self.assertEqual(notes, ["shutterstock: bu kaynak için kod yok, atlandı"])

    def test_only_filter(self):
        cfg = self.config([self.entry("pixabay", 1), self.entry("nasa", 2)])
        srcs, notes = load_sources(cfg, {"PIXABAY_API_KEY": "k"}, FakeHttp(), only=["nasa"])
        self.assertEqual([s.slug for s in srcs], ["nasa"])

    def test_key_passed_to_adapter(self):
        cfg = self.config([self.entry("pixabay", 1)])
        srcs, _ = load_sources(cfg, {"PIXABAY_API_KEY": "k"}, FakeHttp())
        self.assertEqual(srcs[0].key, "k")

    def test_shipped_config(self):
        data = json.loads(SHIPPED.read_text())
        self.assertEqual(data["sources"], [
            {"slug": "pixabay", "url": "https://pixabay.com/api/videos/", "priority": 1, "isEnabled": True},
            {"slug": "nasa", "url": "https://images-api.nasa.gov", "priority": 2, "isEnabled": True},
            {"slug": "pexels", "url": "https://api.pexels.com/v1/videos/", "priority": 3, "isEnabled": False}])
        srcs, notes = load_sources(SHIPPED, {"PIXABAY_API_KEY": "k"}, FakeHttp())
        self.assertEqual([s.slug for s in srcs], ["pixabay", "nasa"])
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
