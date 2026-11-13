import unittest

import helpers  # noqa: F401  (sets sys.path)
from fakes import FakeHttp, fixture
from sources import pexels  # noqa: E402

CFG = {"slug": "pexels", "url": "https://api.pexels.com/v1/videos/", "priority": 3, "isEnabled": False}


def make():
    http = FakeHttp({"api.pexels.com/v1/videos/search": fixture("pexels_search.json")})
    return pexels.Source(CFG, "PEXKEY", http), http


class Pexels(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(pexels.SLUG, "pexels")
        self.assertTrue(pexels.NEEDS_KEY)

    def test_maps_fields(self):
        src, _ = make()
        c = {x.id: x for x in src.search("forest", "horizontal")}
        x = c["1448735"]
        self.assertEqual(x.credit, "Pexels / Ruvim Miksanskiy")
        self.assertEqual(x.creator, "Ruvim Miksanskiy")
        self.assertEqual(x.page_url, "https://www.pexels.com/video/video-of-forest-1448735/")
        self.assertEqual(x.title, "video of forest")
        self.assertEqual(x.licence, "Pexels License")
        # 4096 wide is over the 3840 limit and the hls entry is not mp4: the 2048x1080 file wins
        self.assertEqual((x.width, x.height), (2048, 1080))
        self.assertTrue(x.download_url.endswith(".mp4"))
        self.assertEqual(x.fps, 25.0)
        self.assertEqual(x.duration_s, 32.0)
        v = c["8536521"]
        self.assertEqual((v.width, v.height, v.orientation), (2160, 3840, "vertical"))

    def test_orientation_param(self):
        src, http = make()
        list(src.search("rocket", "vertical"))
        self.assertEqual(http.calls[0]["params"]["orientation"], "portrait")
        src, http = make()
        list(src.search("rocket", "horizontal"))
        self.assertEqual(http.calls[0]["params"]["orientation"], "landscape")
        self.assertEqual(http.calls[0]["params"]["query"], "rocket")
        self.assertEqual(http.calls[0]["params"]["per_page"], 20)

    def test_auth_header_not_in_params(self):
        src, http = make()
        list(src.search("rocket", "horizontal"))
        self.assertEqual(http.calls[0]["headers"], {"Authorization": "PEXKEY"})
        self.assertNotIn("PEXKEY", repr(http.calls[0]["params"]))
        self.assertEqual(http.calls[0]["url"], "https://api.pexels.com/v1/videos/search")


if __name__ == "__main__":
    unittest.main()
