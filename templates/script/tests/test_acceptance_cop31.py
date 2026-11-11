"""Spec acceptance on the real COP31 episode (local only: episodes/ is gitignored).

COP31's old-style script.txt is converted to the A/V template, read back with script_doc, and fed
to the rough cutter's unmodified sections.py: the chapters must come out identical. """
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PKG))
sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(PKG, "tools"))
import script_doc  # noqa: E402

EP = os.path.join(REPO, "episodes/cop31")
SRC = os.path.join(REPO, "demo/cop/raw/COP31_YouTube_Senaryosu.docx")
SECTIONS = os.path.join(REPO, ".claude/skills/rough-cutting-a-roll/scripts/sections.py")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@unittest.skipUnless(os.path.exists(os.path.join(EP, "sections.json")) and os.path.exists(SRC), "COP31 files not present")
class Cop31(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ep = os.path.join(self.tmp.name, "ep")
        os.makedirs(self.ep)
        m = read_json(os.path.join(EP, "episode.json"))
        m["script"] = "script.txt"
        with open(os.path.join(self.ep, "episode.json"), "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)
        for d in ("plans", "transcripts"):
            os.symlink(os.path.join(EP, d), os.path.join(self.ep, d))

    def sections(self, script_txt):
        with open(os.path.join(self.ep, "script.txt"), "w", encoding="utf-8") as f:
            f.write(script_txt)
        subprocess.run([sys.executable, SECTIONS, self.ep], check=True, capture_output=True)
        return read_json(os.path.join(self.ep, "sections.json"))

    def expected(self):
        e = read_json(os.path.join(EP, "sections.json"))
        return {k: e[k] for k in ("chapters", "headings", "pieces")}

    def test_baseline_reproduces(self):
        with open(os.path.join(EP, "script.txt"), encoding="utf-8") as f:
            got = self.sections(f.read())
        self.assertEqual({k: got[k] for k in ("chapters", "headings", "pieces")}, self.expected())

    def test_av_template_same_sections(self):
        from legacy_to_av import legacy_to_av
        docx = os.path.join(self.tmp.name, "cop31-av.docx")
        legacy_to_av(SRC, docx)
        s = script_doc.parse(docx)
        self.assertIsNotNone(s)
        # front matter survives as-is: the corrections table stays a 3-column table before chapter 1
        blocks = script_doc.read_blocks(docx)
        first = next(i for i, b in enumerate(blocks) if b[0] == "p" and b[2].startswith("1. Açılış"))
        tables = [b[1] for b in blocks[:first] if b[0] == "tbl"]
        self.assertEqual(tables[0][0], ["Orijinal ifade", "Sorun", "Yeni metinde"])
        self.assertEqual(s["header"], {})
        self.assertEqual([r["tags"] for r in s["rows"] if r["tags"] != ["KAMERA"]], [["GRAFİK"]] * 9)
        got = self.sections(script_doc.to_legacy_txt(s))
        self.assertEqual({k: got[k] for k in ("chapters", "headings", "pieces")}, self.expected())



if __name__ == "__main__":
    unittest.main()
