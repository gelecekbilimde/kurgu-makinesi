"""Real API calls. Skipped unless STOCK_LIVE=1 (run after `source ~/.bashrc` for the Pixabay key)."""
import os
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (sets sys.path)
from cache import Cache  # noqa: E402
from http_client import Http  # noqa: E402
from sources import nasa, pixabay  # noqa: E402

LIVE = os.environ.get("STOCK_LIVE") == "1"


@unittest.skipUnless(LIVE, "set STOCK_LIVE=1 to call the real APIs")
class Live(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = Cache(Path(tmp.name) / "stock")
        self.http = Http(self.cache)

    def test_nasa_search(self):
        src = nasa.Source({"url": "https://images-api.nasa.gov", "priority": 2}, None, self.http)
        c = next(iter(src.search("rocket launch", "horizontal")))
        self.assertGreater(c.width, 0)
        self.assertGreater(c.height, 0)
        self.assertGreater(c.duration_s, 0)
        self.assertTrue(c.download_url.startswith("https://"))

    @unittest.skipUnless(os.environ.get("PIXABAY_API_KEY"), "PIXABAY_API_KEY not set")
    def test_pixabay_search_and_download(self):
        key = os.environ["PIXABAY_API_KEY"]
        src = pixabay.Source({"url": "https://pixabay.com/api/videos/", "priority": 1}, key, self.http)
        self.assertIsNotNone(next(iter(src.search("rocket launch", "horizontal"))))
        raw = self.http.get_json("pixabay", "https://pixabay.com/api/videos/",
                                 {"key": key, "q": "rocket launch", "per_page": 20, "safesearch": "true"},
                                 secret_params=("key",))
        tiny = raw["hits"][0]["videos"]["tiny"]["url"]
        dest = self.cache.clip_path("pixabay", "live")
        self.http.download("pixabay", tiny, dest)
        self.assertGreater(dest.stat().st_size, 10_000)
        for p in self.cache.root.rglob("*.json"):
            self.assertNotIn(key, p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
