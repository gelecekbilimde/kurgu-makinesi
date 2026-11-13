import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from helpers import cand
from cache import Cache  # noqa: E402
import deliver  # noqa: E402
from finder import Pick  # noqa: E402

NOW = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
KEYS = {"code", "file", "source", "id", "page_url", "creator", "licence", "credit", "width", "height", "fps",
        "duration_s", "orientation", "from_cache", "warnings"}


class Deliver(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = Cache(Path(tmp.name) / "stock")
        self.out = Path(tmp.name) / "out"

    def pick(self, source, id, **kw):
        c = cand(source=source, id=id, **kw)
        path = self.cache.clip_path(source, id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video-" + id.encode())
        return Pick(self.cache.write_sidecar(c, "q", NOW), path, False)

    def run_once(self, code, picks, query="rocket launch"):
        results = deliver.load_results(self.out)
        req = deliver.add_request(self.out, results, query, code, "horizontal", picks, [])
        deliver.save(self.out, results, [], NOW)
        return req

    def test_slugify(self):
        self.assertEqual(deliver.slugify("Ay'a iniş!"), "ay-a-inis")
        self.assertEqual(deliver.slugify("rocket launch"), "rocket-launch")
        self.assertEqual(deliver.slugify("!!!"), "stok")
        self.assertEqual(deliver.slugify("ŞÜĞÇÖİ ışık"), "sugcoi-isik")
        self.assertLessEqual(len(deliver.slugify("a" * 100)), 40)

    def test_names_and_links(self):
        p1, p2 = self.pick("pixabay", "1"), self.pick("nasa", "X")
        req = self.run_once("R12", [p1, p2])
        self.assertEqual([c["file"] for c in req["candidates"]], ["R12-1_pixabay-1.mp4", "R12-2_nasa-X.mp4"])
        self.assertEqual([c["code"] for c in req["candidates"]], ["R12-1", "R12-2"])
        self.assertEqual(os.stat(self.out / "R12-1_pixabay-1.mp4").st_ino, os.stat(p1.path).st_ino)

    def test_unsafe_id_in_file_name(self):
        req = self.run_once("R1", [self.pick("nasa", "MAF 1 ES Join_BROLL")])
        self.assertEqual(req["candidates"][0]["file"], "R1-1_nasa-MAF-1-ES-Join_BROLL.mp4")

    def test_copy_fallback(self):
        p = self.pick("pixabay", "1")
        with mock.patch("deliver.os.link", side_effect=OSError("cross-device")):
            self.run_once("R1", [p])
        f = self.out / "R1-1_pixabay-1.mp4"
        self.assertEqual(f.read_bytes(), b"video-1")
        self.assertNotEqual(os.stat(f).st_ino, os.stat(p.path).st_ino)

    def test_rerun_continues_numbering(self):
        self.run_once("R12", [self.pick("pixabay", str(i)) for i in (1, 2, 3)])
        first = self.out / "R12-1_pixabay-1.mp4"
        before = (os.stat(first).st_ino, os.stat(first).st_mtime_ns)
        req = self.run_once("R12", [self.pick("nasa", "Y")])
        self.assertEqual(req["candidates"][-1]["file"], "R12-4_nasa-Y.mp4")
        self.assertEqual(len(req["candidates"]), 4)
        self.assertEqual((os.stat(first).st_ino, os.stat(first).st_mtime_ns), before)
        self.assertEqual(len(deliver.load_results(self.out)["requests"]), 1)

    def test_rerun_after_editor_deleted_file(self):
        self.run_once("R12", [self.pick("pixabay", str(i)) for i in (1, 2, 3)])
        (self.out / "R12-2_pixabay-2.mp4").unlink()
        req = self.run_once("R12", [self.pick("nasa", "Y")])
        self.assertEqual(req["candidates"][-1]["code"], "R12-4")

    def test_delivered(self):
        self.run_once("R1", [self.pick("pixabay", "1")])
        results = deliver.load_results(self.out)
        self.assertEqual(deliver.delivered(results, "R1"), {("pixabay", "1")})
        self.assertEqual(deliver.delivered(results, "R2"), set())

    def test_same_clip_two_codes(self):
        p = self.pick("pixabay", "1")
        self.run_once("R1", [p])
        self.run_once("R2", [p], query="launch")
        for name in ("R1-1_pixabay-1.mp4", "R2-1_pixabay-1.mp4"):
            self.assertEqual(os.stat(self.out / name).st_ino, os.stat(p.path).st_ino)

    def test_kaynaklar(self):
        a = self.pick("pixabay", "1", credit="Pixabay / kullanici", page_url="https://pixabay.com/videos/id-1/")
        b = self.pick("nasa", "X", credit="NASA / Rocket Lab", page_url="https://images.nasa.gov/details/X")
        self.run_once("R1", [a, b])
        self.run_once("R2", [a], query="launch")
        lines = (self.out / "kaynaklar.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["Pixabay / kullanici: https://pixabay.com/videos/id-1/",
                                 "NASA / Rocket Lab: https://images.nasa.gov/details/X"])

    def test_results_shape(self):
        p = self.pick("pixabay", "1")
        p.from_cache = True
        results = deliver.load_results(self.out)
        deliver.add_request(self.out, results, "rocket launch", "R1", "horizontal", [p], ["R1: 1/3 aday bulundu"])
        deliver.save(self.out, results, ["pexels: PEXELS_API_KEY yok, atlandı"], NOW)
        data = json.loads((self.out / "results.json").read_text(encoding="utf-8"))
        self.assertEqual(set(data), {"created", "notes", "requests"})
        self.assertEqual(data["created"], NOW.isoformat())
        self.assertEqual(data["notes"], ["pexels: PEXELS_API_KEY yok, atlandı"])
        r = data["requests"][0]
        self.assertEqual({k: r[k] for k in ("query", "code", "orientation", "notes")},
                         {"query": "rocket launch", "code": "R1", "orientation": "horizontal",
                          "notes": ["R1: 1/3 aday bulundu"]})
        self.assertEqual(set(r["candidates"][0]), KEYS)
        self.assertTrue(r["candidates"][0]["from_cache"])

    def test_created_kept_on_rerun(self):
        self.run_once("R1", [self.pick("pixabay", "1")])
        results = deliver.load_results(self.out)
        deliver.save(self.out, results, [], datetime(2027, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(deliver.load_results(self.out)["created"], NOW.isoformat())


if __name__ == "__main__":
    unittest.main()
