import os, sys, tempfile, unittest, zipfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from docx_build import build_docx  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
BLOCKS = [("p", "Heading2", "1. Açılış"), ("li", "UNFCCC (2026)"),
          ("tbl", [["TÜR", "SES"], ["STOK", "Merhaba\nikinci paragraf"]], [3000, 6000])]


class BuildDocx(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_structure(self):
        path = os.path.join(self.tmp.name, "a.docx")
        build_docx(BLOCKS, path)
        z = zipfile.ZipFile(path)
        for part in ["[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/_rels/document.xml.rels",
                     "word/styles.xml", "word/numbering.xml"]:
            self.assertIn(part, z.namelist())
        root = ET.fromstring(z.read("word/document.xml"))
        self.assertEqual(len(list(root.iter(W + "tbl"))), 1)
        self.assertEqual(len(list(root.iter(W + "tc"))), 4)
        styles = [s.get(W + "val") for s in root.iter(W + "pStyle")]
        self.assertIn("Heading2", styles)
        self.assertIn("ListParagraph", styles)
        self.assertEqual(len(list(root.iter(W + "numPr"))), 1)
        texts = "".join(t.text or "" for t in root.iter(W + "t"))
        self.assertIn("ikinci paragraf", texts)
        self.assertIn('w:styleId="Heading2"', z.read("word/styles.xml").decode())

    def test_reproducible(self):
        a, b = os.path.join(self.tmp.name, "a.docx"), os.path.join(self.tmp.name, "b.docx")
        build_docx(BLOCKS, a)
        build_docx(BLOCKS, b)
        self.assertEqual(open(a, "rb").read(), open(b, "rb").read())

    def test_sdt_and_extra_style(self):
        path = os.path.join(self.tmp.name, "c.docx")
        build_docx([("p", "Balk2", "Başlık"), ("tbl", [["TÜR"], ["\x00sdt:STOK"]], [9000])], path,
                   extra_styles={"Balk2": "heading 2"})
        z = zipfile.ZipFile(path)
        root = ET.fromstring(z.read("word/document.xml"))
        sdt = list(root.iter(W + "sdt"))
        self.assertEqual(len(sdt), 1)
        self.assertEqual("".join(t.text for t in sdt[0].iter(W + "t")), "STOK")
        self.assertIn('w:styleId="Balk2"', z.read("word/styles.xml").decode())


if __name__ == "__main__":
    unittest.main()
