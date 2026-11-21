import json
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
import designs
import manifest
import stage

WORDS = [{"text": "Bir", "start": 0, "end": 10}, {"text": "iki", "start": 10, "end": 22}]


def template():
    return manifest.load(helpers.FIXTURES / "templates" / "words-demo")


class Words(unittest.TestCase):
    def setUp(self):
        self.t = template()

    def test_words_valid(self):
        self.assertEqual(manifest.validate(self.t, {"w": WORDS})["w"], WORDS)

    def test_words_json_string(self):
        self.assertEqual(manifest.validate(self.t, {"w": json.dumps(WORDS)})["w"], WORDS)

    def fails(self, words, frames=None, expect="w"):
        with self.assertRaises(manifest.FieldError) as cm:
            manifest.validate(self.t, {"w": words}, frames=frames)
        self.assertIn(expect, " ".join(cm.exception.problems))

    def test_words_overlapping_order(self):
        self.fails([{"text": "a", "start": 10, "end": 12}, {"text": "b", "start": 5, "end": 8}])

    def test_words_end_before_start(self):
        self.fails([{"text": "a", "start": 10, "end": 10}])

    def test_words_empty_text(self):
        self.fails([{"text": " ", "start": 0, "end": 5}])

    def test_words_past_frames(self):
        self.fails(WORDS, frames=20)
        self.assertEqual(manifest.validate(self.t, {"w": WORDS}, frames=22)["w"], WORDS)

    def test_words_max_items(self):
        self.fails([{"text": str(i), "start": i, "end": i + 1} for i in range(4)])

    def test_words_malformed(self):
        self.fails("{nope")
        self.fails([{"text": "a", "start": "x", "end": 5}])
        self.fails([{"text": "a", "start": 0.5, "end": 5}])
        self.fails(["a"])


class WordsStage(unittest.TestCase):
    def test_words_in_kit_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = helpers.make_root(tmp)
            shutil.copytree(helpers.FIXTURES / "templates" / "words-demo", root / "templates" / "demo" / "words-demo")
            t = manifest.load(designs.template_dir(root, "demo", "words-demo"))
            values = manifest.validate(t, {"w": WORDS})
            dest = stage.stage(t, designs.design_dir(root, "demo"), "a", values, False, 75, 25, Path(tmp) / "s")
            self.assertIn('"w": "words"', (dest / "index.html").read_text(encoding="utf-8"))
            self.assertEqual(json.loads(json.loads((dest / "vars.json").read_text())["w"]), WORDS)

    def test_resolve_bounds_words_by_render_frames(self):
        import make_graphic
        with tempfile.TemporaryDirectory() as tmp:
            root = helpers.make_root(tmp)
            shutil.copytree(helpers.FIXTURES / "templates" / "words-demo", root / "templates" / "demo" / "words-demo")
            ctx = make_graphic.Context(root=root, archive=None, run=None, out=None)
            row = {"template": "words-demo", "frames": 25, "fields": {"w": WORDS}}
            self.assertEqual(make_graphic.resolve(row, ctx)["values"]["w"], WORDS)
            row["fields"] = {"w": [{"text": "a", "start": 0, "end": 26}]}
            with self.assertRaises(make_graphic.RequestError):
                make_graphic.resolve(row, ctx)


if __name__ == "__main__":
    unittest.main()
