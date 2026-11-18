import tempfile
import unittest

import helpers
import designs


class Designs(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = helpers.make_root(tmp.name)

    def test_config_reads_active_design(self):
        self.assertEqual(designs.Config(self.root).design, "demo")

    def test_unknown_design_lists_known(self):
        with self.assertRaises(designs.DesignError) as cm:
            designs.design_dir(self.root, "yok")
        self.assertIn("demo", str(cm.exception))
        self.assertIn("other", str(cm.exception))

    def test_variants_and_default(self):
        d = designs.design_dir(self.root, "demo")
        self.assertEqual(designs.variants(d), ["a", "b"])
        self.assertEqual(designs.default_variant(d), "a")
        self.assertIsNone(designs.default_variant(designs.design_dir(self.root, "other")))

    def test_design_hash_ignores_docs(self):
        d = designs.design_dir(self.root, "demo")
        h = designs.design_hash(d)
        (d / "design.md").write_text("changed")
        (d / "reference" / "r.html").write_text("changed")
        self.assertEqual(designs.design_hash(d), h)
        (d / "tokens.css").write_text(":root { --ink: #000; }")
        self.assertNotEqual(designs.design_hash(d), h)

    def test_templates_listed(self):
        names = [t.name for t in designs.templates(self.root, "demo")]
        self.assertEqual(names, ["demo", "fixed"])

    def test_unknown_template_lists_known(self):
        with self.assertRaises(designs.DesignError) as cm:
            designs.template_dir(self.root, "demo", "yok")
        self.assertIn("fixed", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
