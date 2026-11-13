import unittest

import helpers  # noqa: F401  (sets sys.path)
from fakes import FakeHttp, fixture
from model import SourceError
from sources import nasa  # noqa: E402

CFG = {"slug": "nasa", "url": "https://images-api.nasa.gov", "priority": 2, "isEnabled": True}
PLAIN = "GSFC_20160909_M12368_OSIRIS_launch"
THIRD = "KSC-20230507-MH-RLS01-TROPICS_Rocket_Launch-Rocket_Lab-WON_3330130"
SPACES = "MAF_20190917_Artemis%201%20ES%20Join_BROLL"


def responses(**over):
    r = {"images-api.nasa.gov/search": fixture("nasa_search.json"),
         f"asset/{PLAIN}": fixture("nasa_asset.json"), f"{PLAIN}/metadata.json": fixture("nasa_metadata.json"),
         f"asset/{THIRD}": fixture("nasa_asset_thirdparty.json"),
         f"{THIRD}/metadata.json": fixture("nasa_metadata_thirdparty.json"),
         f"asset/{SPACES}": fixture("nasa_asset_spaces.json"),
         f"{SPACES}/metadata.json": fixture("nasa_metadata_spaces.json")}
    r.update(over)
    return r


def run(**over):
    http = FakeHttp(responses(**over))
    return {c.id: c for c in nasa.Source(CFG, None, http).search("rocket launch", "horizontal")}, http


class CreditRule(unittest.TestCase):
    def test_credit_rule(self):
        cases = [({}, ("NASA", False)),
                 ({"XMP:Credit": ""}, ("NASA", False)),
                 ({"XMP:Credit": "NASA/JPL-Caltech"}, ("NASA/JPL-Caltech", False)),
                 ({"XMP:Credit": "NASA/Bill Ingalls"}, ("NASA/Bill Ingalls", False)),
                 ({"XMP:Credit": "KSC"}, ("NASA / KSC", False)),
                 ({"XMP:Credit": "JPL"}, ("NASA / JPL", False)),
                 ({"XMP:Credit": "Rocket Lab"}, ("NASA / Rocket Lab", True)),
                 ({"XMP:Credit": "ESA"}, ("NASA / ESA", True)),
                 ({"XMP:Creator": ["SpaceX"]}, ("NASA / SpaceX", True)),
                 ({"XMP:Creator": "nasa"}, ("nasa", False))]
        for meta, want in cases:
            self.assertEqual(nasa.credit_for(meta), want, meta)

    def test_center_must_be_a_word(self):
        self.assertTrue(nasa.credit_for({"XMP:Credit": "Mars Society"})[1])  # "Mars" is not "MSFC"/"ARC"
        self.assertTrue(nasa.credit_for({"XMP:Credit": "Archer Aviation"})[1])  # contains "arc" but not as a word


class Adapter(unittest.TestCase):
    def test_contract(self):
        self.assertEqual(nasa.SLUG, "nasa")
        self.assertFalse(nasa.NEEDS_KEY)

    def test_third_party_candidate_has_warning(self):
        c = run()[0][THIRD]
        self.assertEqual(c.credit, "NASA / Rocket Lab")
        self.assertIn("NASA dışı içerik (Rocket Lab): kullanım hakkını kontrol et", c.warnings)

    def test_plain_candidate(self):
        c = run()[0][PLAIN]
        self.assertEqual(c.credit, "NASA")
        self.assertEqual(c.warnings, [])
        self.assertEqual(c.page_url, f"https://images.nasa.gov/details/{PLAIN}")
        self.assertEqual(c.licence, "NASA Images and Media Usage Guidelines")
        self.assertTrue(c.title)
        self.assertTrue(c.keywords)

    def test_dimensions_fps_duration(self):
        c = run()[0][THIRD]
        self.assertEqual((c.width, c.height, c.fps, c.duration_s), (1920, 1080, 50.0, 30.0))
        self.assertTrue(c.download_url.endswith("~orig.mp4"))

    def test_duration_formats(self):
        self.assertEqual(nasa.parse_duration("0:00:30"), 30.0)
        self.assertEqual(nasa.parse_duration("0:01:02.5"), 62.5)
        self.assertEqual(nasa.parse_duration("12.5 s"), 12.5)
        self.assertEqual(nasa.parse_duration(7), 7.0)
        self.assertIsNone(nasa.parse_duration("bilinmiyor"))

    def test_spaces_in_urls_are_quoted(self):
        c = run()[0]["MAF_20190917_Artemis 1 ES Join_BROLL"]
        self.assertTrue(c.download_url.startswith("https://"))
        self.assertNotIn(" ", c.download_url)
        self.assertIn("%20", c.download_url)
        self.assertEqual(c.width, 3840)

    def test_oversized_orig_uses_large(self):
        meta = dict(fixture("nasa_metadata_spaces.json"), **{"QuickTime:ImageWidth": 7680, "QuickTime:ImageHeight": 4320})
        c = run(**{f"{SPACES}/metadata.json": meta})[0]["MAF_20190917_Artemis 1 ES Join_BROLL"]
        self.assertTrue(c.download_url.endswith("~large.mp4"))
        self.assertEqual((c.width, c.height), (1920, 1080))

    def test_missing_orig_or_metadata_skipped(self):
        no_mp4 = {"collection": {"items": [{"href": "http://images-assets.nasa.gov/video/x/metadata.json"}]}}
        got, _ = run(**{f"asset/{THIRD}": no_mp4, f"{PLAIN}/metadata.json": SourceError("nasa", "HTTP 404")})
        self.assertNotIn(THIRD, got)
        self.assertNotIn(PLAIN, got)
        self.assertIn("MAF_20190917_Artemis 1 ES Join_BROLL", got)

    def test_metadata_without_size_or_duration_skipped(self):
        got, _ = run(**{f"{THIRD}/metadata.json": {"XMP:Credit": "Rocket Lab"}})
        self.assertNotIn(THIRD, got)

    def test_lazy(self):
        http = FakeHttp(responses())
        it = nasa.Source(CFG, None, http).search("rocket launch", "horizontal")
        next(it)
        self.assertEqual(len(http.calls), 3)  # search, asset list, metadata
        self.assertEqual(http.calls[0]["params"], {"q": "rocket launch", "media_type": "video", "page_size": 20})


if __name__ == "__main__":
    unittest.main()
