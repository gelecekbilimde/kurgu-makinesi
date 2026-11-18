import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import helpers  # noqa: F401
import deliver

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


class Deliver(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.out = self.d / "out"
        self.src = self.d / "render.mp4"
        self.src.write_bytes(b"one")

    def add(self, code="G1", sources=()):
        results = deliver.load_results(self.out)
        e = deliver.add(self.out, results, code, {"template": "t", "sources": list(sources)}, self.src)
        deliver.save(self.out, results, [], NOW)
        return e

    def test_slugify_folds_turkish(self):
        self.assertEqual(deliver.slugify("Güneş Işığı Ölçümü"), "gunes-isigi-olcumu")
        self.assertEqual(deliver.slugify("!!!"), "grafik")

    def test_deliver_numbering_continues(self):
        self.assertEqual(self.add()["file"], "G1-1.mp4")
        self.src.unlink()
        self.src.write_bytes(b"two")
        self.assertEqual(self.add()["file"], "G1-2.mp4")
        self.assertEqual((self.out / "G1-1.mp4").read_bytes(), b"one")
        self.assertEqual((self.out / "G1-2.mp4").read_bytes(), b"two")
        self.assertEqual(self.add(code="G2")["code"], "G2-1")

    def test_never_overwrites_foreign_file(self):
        self.out.mkdir()
        (self.out / "G1-1.mp4").write_bytes(b"editor's")
        self.assertEqual(self.add()["file"], "G1-2.mp4")
        self.assertEqual((self.out / "G1-1.mp4").read_bytes(), b"editor's")

    def test_kaynaklar_dedup(self):
        self.add(sources=["NASA, 2024"])
        self.add(sources=["NASA, 2024", "ESA"])
        self.assertEqual((self.out / "kaynaklar.txt").read_text(), "NASA, 2024\nESA\n")

    def test_results_shape(self):
        self.add()
        r = json.loads((self.out / "results.json").read_text())
        self.assertEqual(set(r), {"created", "notes", "renders"})
        self.assertEqual(r["renders"][0]["code"], "G1-1")


if __name__ == "__main__":
    unittest.main()
