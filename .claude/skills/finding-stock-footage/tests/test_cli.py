import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import helpers  # noqa: F401  (sets sys.path)
from fakes import FakeHttp, fixture
import find_stock  # noqa: E402

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
PLAIN = "GSFC_20160909_M12368_OSIRIS_launch"
THIRD = "KSC-20230507-MH-RLS01-TROPICS_Rocket_Launch-Rocket_Lab-WON_3330130"
SPACES = "MAF_20190917_Artemis%201%20ES%20Join_BROLL"


def responses(nasa_empty=False):
    r = {"pixabay.com/api/videos": fixture("pixabay_search.json"),
         "images-api.nasa.gov/search": ({"collection": {"items": []}} if nasa_empty else fixture("nasa_search.json")),
         f"asset/{PLAIN}": fixture("nasa_asset.json"), f"{PLAIN}/metadata.json": fixture("nasa_metadata.json"),
         f"asset/{THIRD}": fixture("nasa_asset_thirdparty.json"),
         f"{THIRD}/metadata.json": fixture("nasa_metadata_thirdparty.json"),
         f"asset/{SPACES}": fixture("nasa_asset_spaces.json"),
         f"{SPACES}/metadata.json": fixture("nasa_metadata_spaces.json")}
    return r


class Cli(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.cache = self.tmp / "stock"
        self.out = self.tmp / "out"
        self.config = Path(helpers.SCRIPTS).parent / "sources.json"
        self.env = {"PIXABAY_API_KEY": "SECRETKEY", "HOME": str(self.tmp / "home")}

    def run_cli(self, *args, env=None, nasa_empty=False, pixabay_empty=False):
        resp = responses(nasa_empty)
        if pixabay_empty:
            resp["pixabay.com/api/videos"] = {"hits": []}
        pix, nasa = resp["pixabay.com/api/videos"], resp["images-api.nasa.gov/search"]
        resp["pixabay.com/api/videos"] = lambda p: {"hits": []} if p.get("q") == "xyzzy" else pix
        resp["images-api.nasa.gov/search"] = (lambda p: {"collection": {"items": []}} if p.get("q") == "xyzzy"
                                             else nasa)
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = list(args) + ["--cache", str(self.cache), "--config", str(self.config)]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = find_stock.main(argv, env=self.env if env is None else env,
                                   http_factory=lambda cache: FakeHttp(resp, cache=cache), now=NOW)
        return code, stdout.getvalue(), stderr.getvalue()

    def results(self, out=None):
        return json.loads(((out or self.out) / "results.json").read_text(encoding="utf-8"))

    def test_single_query_end_to_end(self):
        code, out, _ = self.run_cli("rocket launch", "--out", str(self.out), "--code", "R12")
        self.assertEqual(code, 0)
        req = self.results()["requests"]
        self.assertEqual(len(req), 1)
        self.assertEqual(len(req[0]["candidates"]), 3)
        self.assertEqual(len(list(self.out.glob("R12-*.mp4"))), 3)
        self.assertIn(" sn", out)
        self.assertIn("Klasör: " + str(self.out), out)
        self.assertIn("Kaynaklar: " + str(self.out / "kaynaklar.txt"), out)
        self.assertIn("R12-1  pixabay  1280x720  57 sn  yatay", out)
        self.assertIn("  ! NASA dışı içerik (Rocket Lab): kullanım hakkını kontrol et", out)

    def test_default_out_and_code(self):
        code, _, _ = self.run_cli("rocket launch")
        self.assertEqual(code, 0)
        out = self.tmp / "home" / "Downloads" / "stok" / "rocket-launch"
        self.assertTrue(list(out.glob("rocket-launch-1_*.mp4")))

    def test_rerun_uses_cache(self):
        self.run_cli("rocket launch", "--out", str(self.out), "--code", "R1")
        code, out, _ = self.run_cli("rocket launch", "--out", str(self.tmp / "out2"), "--code", "R1")
        self.assertEqual(code, 0)
        self.assertIn("önbellekten", out)

    def test_batch(self):
        batch = self.tmp / "req.json"
        batch.write_text(json.dumps([{"code": "R1", "query": "rocket launch"},
                                     {"code": "R2", "query": "rocket launch", "count": 1}]))
        code, _, _ = self.run_cli("--batch", str(batch), "--out", str(self.out))
        self.assertEqual(code, 0)
        reqs = self.results()["requests"]
        self.assertEqual([r["code"] for r in reqs], ["R1", "R2"])
        self.assertEqual(len(reqs[1]["candidates"]), 1)

    def test_batch_one_empty_row(self):
        batch = self.tmp / "req.json"
        batch.write_text(json.dumps([{"code": "R1", "query": "rocket launch"},
                                     {"code": "R2", "query": "xyzzy", "count": 2}]))
        code, out, _ = self.run_cli("--batch", str(batch), "--out", str(self.out))
        self.assertEqual(code, 0)
        reqs = self.results()["requests"]
        self.assertIn("R2: 0/2 aday bulundu", reqs[1]["notes"])

    def test_batch_needs_out(self):
        batch = self.tmp / "req.json"
        batch.write_text("[]")
        code, _, err = self.run_cli("--batch", str(batch))
        self.assertEqual(code, 1)

    def test_nothing_found(self):
        code, _, err = self.run_cli("xyzzy", "--out", str(self.out), nasa_empty=True, pixabay_empty=True)
        self.assertEqual(code, 2)
        self.assertIn("Hiç aday bulunamadı. Başka anahtar kelimeler deneyin.", err)

    def test_missing_key_still_delivers(self):
        code, out, _ = self.run_cli("rocket launch", "--out", str(self.out), env={"HOME": str(self.tmp)})
        self.assertEqual(code, 0)
        cands = self.results()["requests"][0]["candidates"]
        self.assertTrue(cands)
        self.assertEqual({c["source"] for c in cands}, {"nasa"})
        self.assertIn("pixabay: PIXABAY_API_KEY yok, atlandı", out)

    def test_key_never_printed(self):
        code, out, err = self.run_cli("rocket launch", "--out", str(self.out))
        self.assertNotIn("SECRETKEY", out + err)
        for p in list(self.out.rglob("*")) + list(self.cache.rglob("*")):
            if p.is_file() and p.suffix in (".json", ".txt"):
                self.assertNotIn("SECRETKEY", p.read_text(encoding="utf-8"))

    def test_sources_flag(self):
        code, _, _ = self.run_cli("rocket launch", "--out", str(self.out), "--sources", "nasa")
        self.assertEqual({c["source"] for c in self.results()["requests"][0]["candidates"]}, {"nasa"})

    def test_vertical(self):
        code, _, _ = self.run_cli("rocket launch", "--out", str(self.out), "--orientation", "vertical")
        self.assertEqual(self.results()["requests"][0]["orientation"], "vertical")

    def test_reindex(self):
        self.run_cli("rocket launch", "--out", str(self.out))
        (self.cache / "index.json").unlink()
        code, out, _ = self.run_cli("--reindex")
        self.assertEqual(code, 0)
        self.assertIn("3 klip dizinlendi", out)
        self.assertTrue((self.cache / "index.json").is_file())

    def test_usage_errors(self):
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(self.run_cli("rocket", "--reindex")[0], 1)


if __name__ == "__main__":
    unittest.main()
