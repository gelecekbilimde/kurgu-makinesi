import unittest
import helpers  # noqa: F401
import cands, review

OFFS = {3: 0, 4: 1000}
FRAMES = {3: 1000, 4: 800}
W = [(100 + 20 * i, 110 + 20 * i, "w") for i in range(100)]  # words 10 frames long, gaps 10 frames


def cand(cid="c1", accepted=False, **kw):
    c = {"id": cid, "rank": 1, "title": "Başlık", "pieces": [{"chapter": 3, "start": 100, "end": 900}],
         "teaser": {"chapter": 3, "start": 200, "end": 260}, "reason": "neden", "teaser_rating": 4,
         "accepted": accepted, "frozen": False, "header": False}
    c.update(kw)
    return c


def mk(cid, suffix, frame, dur, color="Fuchsia"):
    return {"frameId": frame, "color": color, "duration": dur, "customData": f"short:{cid}:{suffix}"}


class ReviewTest(unittest.TestCase):
    def test_offsets_cumulative(self):
        self.assertEqual(review.offsets({3: 9201, 4: 7168}, [3, 4]), {3: 0, 4: 9201})
        self.assertEqual(review.offsets({3: 10, 4: 5}, [4, 3]), {4: 0, 3: 5})

    def test_marker_per_piece_and_teaser(self):
        c = cand(pieces=[{"chapter": 3, "start": 100, "end": 400}, {"chapter": 4, "start": 50, "end": 500}])
        ms = review.markers({"candidates": [c]}, OFFS)
        self.assertEqual([m["customData"] for m in ms], ["short:c1:p0", "short:c1:p1", "short:c1:t"])
        self.assertEqual([m["frameId"] for m in ms], [100, 1050, 200])
        self.assertEqual([m["duration"] for m in ms], [300, 450, 60])
        self.assertEqual(ms[0]["name"], "1. Başlık")
        self.assertEqual(ms[2]["name"], "1. Başlık · teaser")
        self.assertEqual(ms[0]["note"], "neden\nteaser: 4")
        self.assertTrue(all(m["color"] == "Fuchsia" for m in ms))

    def test_green_means_accepted(self):
        ms = review.markers({"candidates": [cand(accepted=True)]}, OFFS)
        self.assertTrue(all(m["color"] == "Green" for m in ms))
        back, _ = review.read_back({"candidates": [cand()]}, [mk("c1", "p0", 100, 800, "Green")], OFFS, FRAMES)
        self.assertTrue(back["candidates"][0]["accepted"])

    def test_deleted_markers_unaccept(self):
        back, _ = review.read_back({"candidates": [cand(accepted=True)]}, [], OFFS, FRAMES)
        c = back["candidates"][0]
        self.assertFalse(c["accepted"])
        self.assertEqual(c["pieces"], [{"chapter": 3, "start": 100, "end": 900}])

    def test_moved_marker_new_range_and_chapter(self):
        back, _ = review.read_back({"candidates": [cand()]}, [mk("c1", "p0", 1100, 700, "Green")], OFFS, FRAMES)
        self.assertEqual(back["candidates"][0]["pieces"], [{"chapter": 4, "start": 100, "end": 800}])

    def test_marker_across_chapter_edge_clamped(self):
        back, notes = review.read_back({"candidates": [cand()]}, [mk("c1", "p0", 400, 900, "Green")], OFFS, FRAMES)
        self.assertEqual(back["candidates"][0]["pieces"], [{"chapter": 3, "start": 400, "end": 1000}])
        self.assertTrue(any("sınır" in n for n in notes))
        # last chapter: clamped with chapter_frames
        back, notes = review.read_back({"candidates": [cand()]}, [mk("c1", "p0", 1500, 900, "Green")], OFFS, FRAMES)
        self.assertEqual(back["candidates"][0]["pieces"], [{"chapter": 4, "start": 500, "end": 800}])

    def test_accept_resnaps_resized_marker(self):
        # resized to end at 345, inside the word [340, 350)
        back, _ = review.read_back({"candidates": [cand(pieces=[{"chapter": 3, "start": 100, "end": 900}])]},
                                   [mk("c1", "p0", 100, 245, "Green")], OFFS, FRAMES)
        self.assertEqual(back["candidates"][0]["pieces"][0]["end"], 345)
        out, notes, _ = cands.check(back, {3: W}, [3, 4], 25)
        self.assertEqual(out["candidates"][0]["pieces"][0]["end"], 333)  # back to the gap before the word [340, 350): 330 + POST_F
        self.assertTrue(any("kelime içindeydi" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
