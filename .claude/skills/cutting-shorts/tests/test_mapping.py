import unittest
import helpers  # noqa: F401  (sys.path)
import mapping

LAYOUTS = {3: {"units": "frames", "timeline": "t", "frames": 1000,
               "pieces": [[0, "A.MOV", 1000, 1300], [300, "A.MOV", 2000, 2400], [700, None, 0, 300]]}}


def item(start, end, src_in, kind="stock", **kw):
    d = {"track": 2, "start": start, "end": end, "file": "f.mp4", "src_in": src_in,
         "src_out": src_in + end - start, "props": {"ZoomX": 1.0}, "kind": kind}
    d.update(kw)
    return d


def brolls(*items):
    return {3: {"units": "frames", "timeline": "t B-roll", "items": list(items)}}


def cand(pieces=((200, 500),), teaser=(220, 270)):
    return {"id": "c1", "pieces": [{"chapter": 3, "start": a, "end": b} for a, b in pieces],
            "teaser": {"chapter": 3, "start": teaser[0], "end": teaser[1]}}


def build(c=None, b=None, end_card=100):
    return mapping.short_layout(c or cand(), LAYOUTS, b or brolls(), 25, end_card)


class MappingTest(unittest.TestCase):
    def test_teaser_first_then_passage(self):
        s = build(cand(pieces=((200, 500), (600, 650))))
        self.assertEqual([(g["part"], g["rec"], g["ch_start"], g["ch_end"]) for g in s["segments"]],
                         [("teaser", 0, 220, 270), ("passage", 50, 200, 500), ("passage", 350, 600, 650)])
        self.assertEqual(s["teaser"], [0, 50])
        self.assertEqual(s["v1"][0], {"rec": 0, "clip": "A.MOV", "src_in": 1220, "src_out": 1270, "segment": 0})

    def test_piece_across_aroll_cut(self):
        s = build()  # [200,500) spans piece 0 up to 300 and piece 1 from 300
        got = [(v["rec"], v["src_in"], v["src_out"], v["segment"]) for v in s["v1"] if v["segment"] == 1]
        self.assertEqual(got, [(50, 1200, 1300, 1), (150, 2000, 2200, 1)])

    def test_generator_piece_has_no_v1_item(self):
        s = build(cand(pieces=((650, 800),)))
        self.assertEqual([(v["rec"], v["src_in"]) for v in s["v1"] if v["segment"] == 1], [(50, 2350)])

    def test_partial_overlap_keeps_source_offset(self):
        s = build(b=brolls(item(100, 300, 40)))
        (b,) = s["broll"]
        self.assertEqual((b["rec"], b["end"], b["src_in"], b["src_out"]), (50, 150, 140, 240))
        self.assertEqual(b["anchor"], {"chapter": 3, "ch_start": 200, "ch_end": 300})
        self.assertEqual(b["kind"], "stock")
        self.assertEqual(b["props"], {"ZoomX": 1.0})

    def test_no_broll_in_teaser(self):
        s = build(cand(pieces=((300, 500),), teaser=(220, 270)), b=brolls(item(210, 280, 0)))  # only over the teaser's range
        self.assertEqual(s["broll"], [])

    def test_placeholder_not_copied_listed(self):
        s = build(b=brolls(item(250, 350, 0, kind="placeholder"), item(400, 450, 0, kind="still", hold_of="x")))
        self.assertEqual([b["kind"] for b in s["broll"]], ["still"])
        self.assertEqual(s["broll"][0]["hold_of"], "x")
        self.assertEqual([(k["chapter"], k["start"], k["end"]) for k in s["skipped"]], [(3, 250, 350)])

    def test_item_over_two_pieces_copied_per_overlap(self):
        s = build(cand(pieces=((200, 250), (260, 300))), b=brolls(item(0, 400, 0)))
        self.assertEqual([(b["rec"], b["end"], b["src_in"]) for b in s["broll"]], [(50, 100, 200), (100, 140, 260)])

    def test_end_card_after_passage(self):
        s = build(end_card=75)
        self.assertEqual(s["end_card"], [350, 425])
        self.assertEqual(s["frames"], 425)

    def test_anchor_roundtrip(self):
        s = build(cand(pieces=((200, 500), (600, 650))))
        self.assertEqual(mapping.anchor_of(s, 60, 80), {"chapter": 3, "ch_start": 210, "ch_end": 230})
        self.assertEqual(mapping.anchor_of(s, 360, 380), {"chapter": 3, "ch_start": 610, "ch_end": 630})
        self.assertIsNone(mapping.anchor_of(s, 340, 360))  # spans two segments
        self.assertIsNone(mapping.anchor_of(s, 400, 410))  # end card


if __name__ == "__main__":
    unittest.main()
