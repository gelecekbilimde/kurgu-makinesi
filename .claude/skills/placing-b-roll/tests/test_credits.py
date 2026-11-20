import os, tempfile, unittest
import helpers  # noqa: F401
import credits, plan
from test_plan import asset, f, fetched, item


class CreditsTest(unittest.TestCase):
    def setUp(self):
        self.rows = {"k": {"id": "R1", "start": 0, "end": 200}, "g": {"id": "R2", "start": 200, "end": 500},
                     "s": {"id": "R3", "start": 500, "end": 600}}
        self.fe = fetched(
            k=[asset("stock", [f("a.mp4", 120, "Video: Ali / Pixabay"), f("b.mp4", 120, "NASA"),
                               f("c.mp4", 120, "Unused / Pexels")])],
            g=[asset("graphic", [f("G2-1.mp4", 200, "IEA 2024; NASA")], tag="GRAFİK",
                     hold="/m/G2-1-hold.png", hold_from=140)],
            s=[asset("kaynak", [f("R3.png", None, "https://example.org/a")], tag="KAYNAK")])
        self.items = plan.desired(self.rows, self.fe)

    def test_timeline_order_unused_excluded_duplicates_once(self):
        self.assertEqual(credits.collect(self.items, self.fe),
                         ["Video: Ali / Pixabay", "NASA", "IEA 2024", "https://example.org/a"])

    def test_deleted_items_excluded(self):
        items = [dict(i, editor=True, deleted=True, file=None) if i["file"] == "/m/a.mp4" else i
                 for i in self.items]
        self.assertNotIn("Video: Ali / Pixabay", credits.collect(items, self.fe))

    def test_editor_added_item_with_known_file_included(self):
        e = item("E1", None, 700, 800, "/m/c.mp4", editor=True, uid="x")
        unknown = item("E2", None, 800, 900, "/elsewhere/own.mp4", editor=True, uid="y")
        self.assertEqual(credits.collect(self.items + [e, unknown], self.fe)[-1], "Unused / Pexels")

    def test_editor_placed_candidate_of_an_earlier_fetch_is_credited(self):
        """live (Task 9): the editor dragged R015-2 from the row bin; it came from an earlier query of the row,
        so fetched.json no longer lists it, but the stock tool's results.json does."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "stok"))
            os.makedirs(os.path.join(d, "grafik"))
            with open(os.path.join(d, "stok", "results.json"), "w", encoding="utf-8") as fh:
                fh.write('{"requests": [{"candidates": [{"file": "old.mp4", "credit": "Pixabay / bellergy"}]}]}')
            with open(os.path.join(d, "grafik", "results.json"), "w", encoding="utf-8") as fh:
                fh.write('{"renders": [{"file": "G9-1.mp4", "sources": ["IEA", "ESA"]}]}')
            tools = credits.tool_credits(d)
            old = os.path.realpath(os.path.join(d, "stok", "old.mp4"))
            g = os.path.realpath(os.path.join(d, "grafik", "G9-1.mp4"))
            e = [item("E1", None, 700, 800, old, editor=True, uid="x"),
                 item("E2", None, 800, 900, g, editor=True, uid="y")]
            self.assertEqual(credits.collect(self.items + e, self.fe, tools)[-3:],
                             ["Pixabay / bellergy", "IEA", "ESA"])
            self.assertEqual(credits.tool_credits(os.path.join(d, "missing")), {})

    def test_write(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "broll", "kaynaklar.txt")
            credits.write(p, ["NASA", "Çağ / Pixabay"])
            with open(p, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "NASA\nÇağ / Pixabay\n")


if __name__ == "__main__":
    unittest.main()
