import os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
sys.path.insert(0, PKG)
import script_doc  # noqa: E402

TEMPLATE = os.path.join(PKG, "script-template.docx")


class Template(unittest.TestCase):
    def test_template_parses(self):
        s = script_doc.parse(TEMPLATE)
        self.assertIsNotNone(s, "script-template.docx must be an A/V script")
        self.assertEqual([h["level"] for h in s["headings"]], [2, 3])
        self.assertEqual(len(s["rows"]), 2)                    # the H3 table's empty row is skipped
        self.assertEqual(s["rows"][0]["tags"], ["GRAFİK"])
        self.assertEqual(s["rows"][1]["tags"], ["KAMERA"])
        self.assertTrue(any("[GRAFİK]" in f for f in s["front"]))       # the tag reminder line
        self.assertEqual(s["rows"][0]["refs"], ["K1"])
        self.assertEqual([r["warnings"] for r in s["rows"]], [[], []])
        self.assertEqual(len(s["kaynakca"]), 1)
        self.assertEqual(s["header"], {"Başlık": "", "Sunucu": "", "Yazar": "", "Tarih": "", "Durum": "taslak"})
        text = " ".join(b[2] if b[0] == "p" else " ".join(c for r in b[1] for c in r) for b in script_doc.read_blocks(TEMPLATE))
        self.assertNotIn("Doğrulama", text)
        self.assertNotIn("—", text)
        blocks = script_doc.read_blocks(TEMPLATE)
        self.assertEqual([b[1][0] for b in blocks if b[0] == "tbl"], [["Başlık", ""]] + [["GÖRÜNTÜ", "SES"]] * 2)
        self.assertFalse(any(b[0] == "p" and "Tahmini" in b[2] for b in blocks))

    def test_rebuild_is_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = os.path.join(tmp, "before.docx")
            shutil.copy(TEMPLATE, before)
            subprocess.run([sys.executable, os.path.join(PKG, "build_template.py")], check=True, capture_output=True)
            with open(before, "rb") as a, open(TEMPLATE, "rb") as b:
                self.assertEqual(a.read(), b.read())


if __name__ == "__main__":
    unittest.main()
