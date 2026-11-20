import shutil, tempfile, unittest
from pathlib import Path
import helpers
from helpers import FIXTURES, make_episode
import episode, rows


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        d = make_episode(self.tmp)
        for f in ("script.json", "sections.json"):
            shutil.copy(FIXTURES / f, d / f)
        self.d = d
        self.ep = episode.Episode(d)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_chapter_by_title(self):
        rs = rows.load(self.ep)
        ch = {r.id: r.chapter for r in rs}
        self.assertEqual(ch["R001"], 0)
        self.assertEqual(ch["R002"], 0)  # level-3 heading under chapter 1
        self.assertEqual(ch["R005"], 1)
        self.assertEqual(rs[1].visual, "roket fırlatma")

    def test_unknown_chapter_raises_with_row_id(self):
        import json
        p = self.d / "sections.json"
        p.write_text(json.dumps({"chapters": ["2. Gelişme"]}), encoding="utf-8")
        with self.assertRaises(Exception) as c:
            rows.load(self.ep)
        self.assertIn("R001", str(c.exception))

    def test_broll_rows_frozen(self):
        rs = rows.load(self.ep)
        got = rows.broll_rows(rs, {1})  # 1-based in manifest
        self.assertEqual([r.id for r in got], ["R002", "R003"])
        got = rows.broll_rows(rs, {2})
        self.assertEqual([r.id for r in got], ["R005", "R006", "R007", "R008"])
        self.assertEqual(rows.broll_rows(rs, set()), [])


if __name__ == "__main__":
    unittest.main()
