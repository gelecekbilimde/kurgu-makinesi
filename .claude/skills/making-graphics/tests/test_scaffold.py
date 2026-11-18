import json
import re
import tempfile
import unittest
from pathlib import Path

import helpers
import designs
import manifest
import scaffold
import stage

STARTER_TOKENS = helpers.REPO / "graphics" / "designs" / "starter" / "tokens.css"


class NewDesign(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = helpers.make_root(tmp.name)

    def test_new_design_blank_lists_all_starter_tokens(self):
        d = scaffold.new_design(self.root, "yeni")
        blank = (d / "tokens.css").read_text()
        names = set(re.findall(r"(--[\w-]+)\s*:", STARTER_TOKENS.read_text()))
        missing = sorted(n for n in names if not re.search(re.escape(n) + r"\s*:", blank))
        self.assertEqual(missing, [])
        self.assertTrue((d / "design.md").is_file())
        self.assertTrue((d / "variants").is_dir())
        designs.design_dir(self.root, "yeni")

    def test_new_design_refuses_existing(self):
        with self.assertRaises(designs.DesignError) as cm:
            scaffold.new_design(self.root, "demo")
        self.assertIn("demo", str(cm.exception))

    def test_new_design_from_copies(self):
        d = scaffold.new_design(self.root, "kopya", from_="demo")
        self.assertEqual((d / "tokens.css").read_text(), (self.root / "designs/demo/tokens.css").read_text())
        self.assertTrue((d / "variants" / "a.css").is_file())
        self.assertFalse((d / "reference").exists())
        self.assertIn("demo", (d / "design.md").read_text())

    def test_new_design_bad_name(self):
        with self.assertRaises(designs.DesignError):
            scaffold.new_design(self.root, "../dışarı")


class NewTemplate(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = helpers.make_root(tmp.name)

    def test_new_template_is_renderable(self):
        d = scaffold.new_template(self.root, "demo", "alinti")
        t = manifest.load(d)
        self.assertEqual((t.name, t.status, t.version), ("alinti", "draft", 1))
        values = manifest.validate(t, json.loads((d / "samples.json").read_text())[0]["fields"])
        stage.stage(t, designs.design_dir(self.root, "demo"), "a", values, False, 25, 25, self.tmp / "st")

    def test_new_template_from_copies_and_resets(self):
        d = scaffold.new_template(self.root, "demo", "sabit2", from_="fixed")
        t = manifest.load(d)
        self.assertEqual((t.name, t.status, t.version), ("sabit2", "draft", 1))
        self.assertEqual(t.canvas, {"width": 2400, "height": 1800})

    def test_new_template_refuses_existing(self):
        with self.assertRaises(designs.DesignError):
            scaffold.new_template(self.root, "demo", "fixed")


if __name__ == "__main__":
    unittest.main()
