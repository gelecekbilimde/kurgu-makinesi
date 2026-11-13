import unittest

import helpers  # noqa: F401  (sets sys.path)
from fakes import FakeHttp, fixture
from sources import pixabay  # noqa: E402

CFG = {"slug": "pixabay", "url": "https://pixabay.com/api/videos/", "priority": 1, "isEnabled": True}


def make():
    http = FakeHttp({"pixabay.com/api/videos": fixture("pixabay_search.json")})
    return pixabay.Source(CFG, "KEY123", http), http


class Pixabay(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(pixabay.SLUG, "pixabay")
        self.assertTrue(pixabay.NEEDS_KEY)
        src, _ = make()
        self.assertEqual((src.slug, src.priority), ("pixabay", 1))

    def test_maps_fields(self):
        src, _ = make()
        hits = fixture("pixabay_search.json")["hits"]
        c = list(src.search("rocket launch", "horizontal"))
        by_id = {x.id: x for x in c}
        h = hits[2]  # has a real 3840x2160 large
        x = by_id[str(h["id"])]
        self.assertEqual(x.source, "pixabay")
        self.assertEqual(x.credit, "Pixabay / " + h["user"])
        self.assertEqual(x.creator, h["user"])
        self.assertEqual(x.page_url, h["pageURL"])
        self.assertIsNone(x.fps)
        self.assertEqual(x.download_url, h["videos"]["large"]["url"])
        self.assertEqual((x.width, x.height), (3840, 2160))
        self.assertEqual(x.duration_s, float(h["duration"]))
        self.assertEqual(x.licence, "Pixabay Content License")
        self.assertEqual(x.title, h["tags"])
        self.assertEqual(x.keywords, h["tags"].split(", "))

    def test_empty_large_falls_back_to_medium(self):
        src, _ = make()
        hits = fixture("pixabay_search.json")["hits"]
        by_id = {x.id: x for x in src.search("rocket launch", "horizontal")}
        for h in hits[:2]:  # hit 0: large has a url but width 0; hit 1: large url emptied
            x = by_id[str(h["id"])]
            self.assertEqual(x.download_url, h["videos"]["medium"]["url"])
            self.assertEqual(x.width, h["videos"]["medium"]["width"])

    def test_key_sent_but_secret(self):
        src, http = make()
        next(iter(src.search("rocket launch", "horizontal")))
        call = http.calls[0]
        self.assertEqual(call["params"]["key"], "KEY123")
        self.assertEqual(call["params"]["q"], "rocket launch")
        self.assertEqual(call["secret_params"], ("key",))

    def test_lazy(self):
        src, http = make()
        it = src.search("rocket launch", "horizontal")
        self.assertEqual(len(http.calls), 0)
        next(it)
        self.assertEqual(len(http.calls), 1)


if __name__ == "__main__":
    unittest.main()
