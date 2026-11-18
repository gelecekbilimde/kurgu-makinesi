import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
import archive

PARTS = dict(template="number", template_version=1, design="starter", design_hash="abc", variant="ev",
             vertical=False, frames=150, fps=25, resolution="4k", output="fullscreen", values={"value": "1"})


class Ids(unittest.TestCase):
    def test_render_id_is_stable(self):
        self.assertEqual(archive.render_id(**PARTS), archive.render_id(**dict(PARTS)))
        self.assertEqual(len(archive.render_id(**PARTS)), 16)

    def test_render_id_changes_with_each_part(self):
        base = archive.render_id(**PARTS)
        changes = dict(template="quote", template_version=2, design="x", design_hash="abd", variant="uzay",
                       vertical=True, frames=151, fps=30, resolution="1080p", output="overlay",
                       values={"value": "2"})
        for k, v in changes.items():
            with self.subTest(part=k):
                self.assertNotEqual(archive.render_id(**{**PARTS, k: v}), base)


class Store(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.a = archive.Archive(self.d / "assets" / "graphics")
        self.file = self.d / "r.mp4"
        self.file.write_bytes(b"video")
        self.poster = self.d / "p.png"
        self.poster.write_bytes(b"poster")

    def test_store_and_lookup(self):
        self.assertIsNone(self.a.lookup("number", "abc"))
        path = self.a.store("number", "abc", {"template": "number", "x": 1}, self.file, self.poster)
        self.assertEqual(path, self.d / "assets/graphics/number/abc/render.mp4")
        self.assertEqual(self.a.lookup("number", "abc"), path)
        self.assertTrue((path.parent / "poster.png").is_file())
        self.assertEqual(json.loads((path.parent / "vars.json").read_text())["x"], 1)

    def test_tmp_dirs_are_not_entries(self):
        (self.d / "assets/graphics/number/abc.tmp").mkdir(parents=True)
        self.assertIsNone(self.a.lookup("number", "abc"))
        self.assertEqual(self.a.write_index(), [])

    def test_underscore_dirs_are_not_entries(self):
        p = self.d / "assets/graphics/_preview/demo"
        p.mkdir(parents=True)
        (p / "vars.json").write_text('{"title": "x"}')
        self.assertEqual(self.a.write_index(), [])

    def test_index_rebuilds_from_vars(self):
        self.a.store("number", "abc", {"template": "number"}, self.file, self.poster)
        self.a.store("quote", "def", {"template": "quote"}, self.file, self.poster)
        entries = self.a.write_index()
        self.assertEqual([e["id"] for e in entries], ["abc", "def"])
        idx = json.loads((self.d / "assets/graphics/index.json").read_text())
        self.assertEqual(idx[1]["file"], "quote/def/render.mp4")


if __name__ == "__main__":
    unittest.main()
