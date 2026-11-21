import io, json, tempfile, unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import helpers
from helpers import make_episode
import cands, shorts

W = [(100, 120, "a"), (130, 150, "b")]


def cand(pieces, teaser, **kw):
    return {"rank": 1, "title": "t", "pieces": pieces, "teaser": teaser, "reason": "", "teaser_rating": 3,
            "accepted": False, "frozen": False, "header": False, **kw}


def piece(a, b, ch=1):
    return {"chapter": ch, "start": a, "end": b}


class SnapTest(unittest.TestCase):
    def test_snap_inside_word_moves_to_gap(self):
        self.assertEqual(cands.snap(110, 140, W), (128, 123, True))

    def test_snap_never_past_gap_middle(self):
        s, e, _ = cands.snap(110, 140, [(100, 120, "a"), (122, 150, "b")])
        self.assertEqual((s, e), (121, 121))

    def test_snap_in_gap_is_padded_not_flagged(self):
        self.assertEqual(cands.snap(125, 125, W), (128, 123, False))


class CheckTest(unittest.TestCase):

    def run_check(self, cs, eligible=(1,)):
        return cands.check({"units": "frames", "candidates": cs}, {}, list(eligible), 25)

    def test_check_lengths(self):
        good = cand([piece(0, 900)], piece(100, 175))
        short = cand([piece(0, 700)], piece(100, 175))
        tiny = cand([piece(0, 900)], piece(100, 200))
        out = cand([piece(0, 900)], piece(950, 1000))
        data, notes, errs = self.run_check([good, short, tiny, out])
        self.assertEqual([c["id"] for c in data["candidates"]], ["c1", "c2", "c3", "c4"])
        self.assertNotIn("c1", errs)
        self.assertIn("pasaj 28,0 s (30–45 s olmalı)", errs["c2"])
        self.assertTrue(any(m.startswith("teaser 4,0 s") for m in errs["c3"]))
        self.assertIn("teaser pasajın dışında", errs["c4"])

    def test_unsigned_chapter_rejected(self):
        a = cand([piece(0, 900)], piece(100, 175))
        b = cand([piece(0, 900, 2)], piece(100, 175, 2))
        _, _, errs = self.run_check([a, b])
        self.assertEqual(list(errs), ["c2"])

    def test_check_assigns_stable_ids_and_keeps_existing(self):
        a, b, c = (cand([piece(0, 900)], piece(100, 175)) for _ in range(3))
        a["id"], b["id"] = "c5", "c2"
        data, _, _ = self.run_check([a, b, c])
        self.assertEqual([x["id"] for x in data["candidates"]], ["c5", "c2", "c6"])

    def test_check_snaps_pieces(self):
        words = {1: [(i * 20, i * 20 + 10, "w") for i in range(100)]}
        c = cand([piece(5, 905)], piece(105, 175))
        data, notes, _ = cands.check({"candidates": [c]}, words, [1], 25)
        p = data["candidates"][0]["pieces"][0]
        self.assertEqual((p["start"], p["end"]), (18, 893))
        self.assertTrue(notes)


class NameTest(unittest.TestCase):
    def test_timeline_name_sanitised(self):
        self.assertEqual(cands.timeline_name("COP31B", 1, "1,5°C: hedef?"), "COP31B short 1 1,5C")
        self.assertLessEqual(len(cands.timeline_name("P", 1, "x" * 200)), 80)


class CliTest(unittest.TestCase):
    def test_freeze_unfreeze_cli(self):
        with tempfile.TemporaryDirectory() as t:
            ep = make_episode(t)
            path = ep / "shorts" / "candidates.json"
            cands.save(str(path), {"units": "frames", "candidates": [{"id": "c1", "frozen": False}, {"id": "c2", "frozen": False}]})
            with redirect_stderr(io.StringIO()):
                self.assertEqual(shorts.main(["freeze", str(ep), "c2"]), 0)
                self.assertEqual([c["frozen"] for c in cands.load(str(path))["candidates"]], [False, True])
                self.assertEqual(shorts.main(["unfreeze", str(ep), "c2"]), 0)
                self.assertFalse(cands.load(str(path))["candidates"][1]["frozen"])
                self.assertNotEqual(shorts.main(["freeze", str(ep), "c9"]), 0)

    def test_candidates_cli_with_fixture_layout(self):
        with tempfile.TemporaryDirectory() as t:
            ep = make_episode(t, frozen=[1], broll_frozen=[1], clips=[{"clip": "A.MOV", "offset_f": 0, "wav": "A.wav"}])
            (ep / "script.json").write_text(json.dumps({"headings": [], "rows": []}))
            (ep / "sections.json").write_text(json.dumps({"chapters": []}))
            (ep / "shorts" / "layout").mkdir(parents=True)
            (ep / "shorts" / "layout" / "ch1.json").write_text(json.dumps(
                {"units": "frames", "timeline": "TEST ch1 X", "frames": 100, "pieces": []}))
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                rc = shorts.main(["candidates", str(ep)])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out.getvalue())["sentences"]["chapters"], {"1": []})
            self.assertTrue((ep / "shorts" / "sentences.json").exists())


if __name__ == "__main__":
    unittest.main()
