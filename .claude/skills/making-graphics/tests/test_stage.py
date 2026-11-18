import json
import re
import tempfile
import unittest
from pathlib import Path

import helpers
import designs
import manifest
import stage


def root_attrs(html):
    tag = re.search(r"<[^>]*data-composition-id[^>]*>", html).group(0)
    return dict(re.findall(r'(data-[\w-]+)="([^"]*)"', tag))


class Stage(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = helpers.make_root(tmp.name)
        self.design = designs.design_dir(self.root, "demo")

    def do(self, name="demo", variant="a", vertical=False, frames=125, fps=25, values=None):
        t = manifest.load(designs.template_dir(self.root, "demo", name))
        values = values if values is not None else manifest.validate(t, {"value": "10^67", "bars": ["a=1", "b=2"]}
                                                                    if name == "demo" else {})
        dest = self.tmp / "stage"
        return t, stage.stage(t, self.design, variant, values, vertical, frames, fps, dest)

    def test_stage_rewrites_root(self):
        _, d = self.do(frames=125, fps=25)
        a = root_attrs((d / "index.html").read_text())
        self.assertEqual(a["data-duration"], "5")
        self.assertEqual(a["data-fps"], "25")
        self.assertEqual((a["data-width"], a["data-height"]), ("1920", "1080"))

    def test_stage_marks_background(self):
        t = manifest.load(designs.template_dir(self.root, "demo", "demo"))
        values = manifest.validate(t, {"value": "1"})
        d = stage.stage(t, self.design, "a", values, False, 25, 25, self.tmp / "s1", background=True)
        self.assertRegex((d / "index.html").read_text(), r'<html[^>]*data-background="page"')
        d = stage.stage(t, self.design, "a", values, False, 25, 25, self.tmp / "s2")
        self.assertRegex((d / "index.html").read_text(), r'<html[^>]*data-background="none"')

    def test_stage_vertical(self):
        _, d = self.do(vertical=True, frames=100, fps=50)
        a = root_attrs((d / "index.html").read_text())
        self.assertEqual((a["data-width"], a["data-height"]), ("1080", "1920"))
        self.assertEqual(a["data-duration"], "2")

    def test_stage_fractional_duration(self):
        _, d = self.do(frames=1, fps=25)
        self.assertEqual(root_attrs((d / "index.html").read_text())["data-duration"], "0.04")

    def test_stage_fixed_canvas_ignores_vertical(self):
        _, d = self.do(name="fixed", vertical=True)
        a = root_attrs((d / "index.html").read_text())
        self.assertEqual((a["data-width"], a["data-height"]), ("2400", "1800"))

    def test_stage_copies_variant_as_variant_css(self):
        _, d = self.do(variant="b")
        self.assertIn("#0f0", (d / "design" / "variant.css").read_text())
        _, d = self.do(variant=None)
        self.assertEqual((d / "design" / "variant.css").read_text(), "")

    def test_stage_unknown_variant(self):
        with self.assertRaises(designs.DesignError) as cm:
            self.do(variant="zzz")
        self.assertIn("a, b", str(cm.exception))

    def test_stage_declares_variables_from_manifest(self):
        t, d = self.do()
        html = (d / "index.html").read_text()
        m = re.search(r"<html[^>]*data-composition-variables='([^']*)'", html)
        decl = json.loads(m.group(1).replace("&apos;", "'"))
        self.assertEqual([x["id"] for x in decl], [f.name for f in t.fields])
        self.assertTrue(all(x["type"] == "string" and x["default"] == "" for x in decl))
        self.assertIn('lang="tr"', html)

    def test_stage_injects_kit_types(self):
        _, d = self.do()
        m = re.search(r'<script id="kit-types" type="application/json">(.*?)</script>',
                      (d / "index.html").read_text(), re.S)
        self.assertEqual(json.loads(m.group(1))["bars"], "list")

    def test_stage_excludes_reference_and_design_md(self):
        _, d = self.do()
        self.assertFalse((d / "design" / "reference").exists())
        self.assertFalse((d / "design" / "design.md").exists())
        self.assertTrue((d / "design" / "fonts" / "x.woff2").exists())
        self.assertTrue((d / "kit" / "hf-kit.js").exists())
        self.assertFalse((d / "template.json").exists())

    def test_vars_json_encodes_lists(self):
        _, d = self.do()
        v = json.loads((d / "vars.json").read_text())
        self.assertEqual(json.loads(v["bars"]), [{"label": "a", "value": 1.0}, {"label": "b", "value": 2.0}])
        self.assertEqual(json.loads(v["value"])["exp"], "67")
        self.assertEqual(v["explanation"], "")
        self.assertTrue(all(isinstance(x, str) for x in v.values()))


if __name__ == "__main__":
    unittest.main()
