import unittest

import helpers  # noqa: F401  (sys.path)
import mapping
import plan
import splan

LAYOUTS = {3: {"units": "frames", "timeline": "t", "frames": 3000,
               "pieces": [[0, "A.MOV", 1000, 4000]]}}
CAM = "/raw/A.MOV"
SHOT = "/b/stills/R009-kaynak.png"
GRAPH = "/b/grafik/G012-1.mp4"
HOLD = "/b/stills/G012-1-hold-50.png"
VGRAPH = "/s/c1/grafik/G012-v-1.mp4"
VHOLD = "/s/c1/stills/G012-v-1-hold-50.png"


def bitem(start, end, kind, file, track=2, **kw):
    d = {"track": track, "start": start, "end": end, "file": file, "src_in": 0, "src_out": end - start,
         "props": {"Pan": 0.0, "Tilt": 0.0, "ZoomX": 1.0, "ZoomY": 1.0, "ZoomGang": True, "Speed": 100.0},
         "kind": kind}
    d.update(kw)
    return d


def layout(items=(), pieces=((200, 500), (700, 900)), teaser=(220, 270)):
    cand = {"id": "c1", "pieces": [{"chapter": 3, "start": a, "end": b} for a, b in pieces],
            "teaser": {"chapter": 3, "start": teaser[0], "end": teaser[1]}}
    brolls = {3: {"units": "frames", "timeline": "t B-roll", "items": list(items)}}
    return mapping.short_layout(cand, LAYOUTS, brolls, 25, 75)


def crops(lay):
    t = {"ZoomX": 3.160494, "ZoomY": 3.160494, "Pan": -5.333, "Tilt": 0.0}
    return {"units": "frames", "timeline": [1080, 1920],
            "items": [dict(v, camera=CAM, src_size=[3840, 2160], transform=t) for v in lay["v1"]]}


def assets(lay, replace=None, graphics=None):
    teaser, end_card = lay["teaser"], lay["end_card"]
    passage = [teaser[1], end_card[0]]
    own = graphics if graphics is not None else [
        {"role": "watermark", "file": "/s/c1/grafik/watermark-1.png", "range": passage, "placeholder": False,
         "vertical": False},
        {"role": "teaser-caption", "file": "/s/c1/grafik/teaser-caption-1.mov", "range": list(teaser),
         "placeholder": False, "vertical": True},
        {"role": "end-card", "file": "/s/c1/stills/end-card.png", "range": list(end_card), "placeholder": True,
         "vertical": True}]
    return {"units": "frames", "id": "c1", "end_card_frames": 75, "cues": [],
            "teaser_cutout": [{"file": "/s/c1/teaser-cutout.mov", "rec": 0, "end": teaser[1]}],
            "graphics": own, "replace": replace or {}, "needed": []}


def desired(items=(), replace=None, graphics=None):
    lay = layout(items)
    return lay, splan.desired(lay, assets(lay, replace, graphics), crops(lay))


def by_kind(items, kind):
    return [i for i in items if i["kind"] == kind]


FIT = {"ZoomX": 1.0, "ZoomY": 1.0, "Pan": 0.0, "Tilt": 0.0}


class DesiredTest(unittest.TestCase):
    def test_tracks_by_kind(self):
        lay, items = desired([bitem(300, 400, "stock", "/b/stok/a.mp4", src_size=[1920, 1080]),
                              bitem(300, 350, "graphic", "/b/grafik/y.mp4", track=3)])
        tracks = {i["kind"]: i["track"] for i in items}
        self.assertEqual(tracks, {"camera": 1, "stock": 2, "graphic": 3, "teaser-caption": 4,
                                  "teaser-cutout": 5, "watermark": 6, "end-card": 2})
        wm = by_kind(items, "watermark")[0]
        self.assertEqual((wm["start"], wm["end"]), (lay["teaser"][1], lay["end_card"][0]))
        header = {"role": "header", "file": "/s/c1/grafik/header-1.mov", "range": [50, 550],
                  "placeholder": False, "vertical": True}
        _, items = desired(graphics=[header])
        self.assertEqual(by_kind(items, "header")[0]["track"], 7)
        for i in items:  # the B-roll skill's item shape, plus anchor
            for k in ("id", "row", "track", "start", "end", "file", "src_in", "src_out", "kind", "code", "editor",
                      "deleted", "uid", "props", "marker", "anchor"):
                self.assertIn(k, i)
        self.assertEqual(len({i["id"] for i in items}), len(items))

    def test_ids_stable_across_builds(self):
        _, a = desired([bitem(300, 400, "stock", "/b/stok/a.mp4", src_size=[1920, 1080])])
        _, b = desired([bitem(210, 260, "stock", "/b/stok/z.mp4", src_size=[1920, 1080]),
                        bitem(300, 400, "stock", "/b/stok/a.mp4", src_size=[1920, 1080])])
        ids = {(i["file"], i["src_in"]): i["id"] for i in b}
        for i in a:
            self.assertEqual(ids[(i["file"], i["src_in"])], i["id"])

    def test_v1_carries_crop(self):
        lay, items = desired()
        cams = by_kind(items, "camera")
        self.assertEqual(len(cams), 3)  # teaser + two pieces
        for c in cams:
            self.assertEqual(c["track"], 1)
            self.assertEqual(c["file"], CAM)
            self.assertEqual(c["props"], {"ZoomX": 3.160494, "ZoomY": 3.160494, "Pan": -5.333, "Tilt": 0.0})
        self.assertEqual([(c["start"], c["end"], c["src_in"]) for c in cams],
                         [(0, 50, 1220), (50, 350, 1200), (350, 550, 1700)])
        self.assertEqual(cams[1]["anchor"], {"chapter": 3, "ch_start": 200, "ch_end": 500})

    def test_stock_centre_crop_fill(self):
        _, items = desired([bitem(300, 400, "stock", "/b/stok/a.mp4", src_size=[1920, 1080]),
                            bitem(400, 450, "stock", "/b/stok/b.mp4", src_size=[1440, 1080]),
                            bitem(450, 480, "stock", "/b/stok/c.mp4")])
        s, sq, unknown = by_kind(items, "stock")
        self.assertEqual(s["props"], {"ZoomX": 3.160494, "ZoomY": 3.160494, "Pan": 0.0, "Tilt": 0.0})
        self.assertIsNone(s.get("flag"))
        self.assertEqual((sq["props"]["ZoomX"], sq.get("flag")), (2.370370, None))
        self.assertEqual(unknown["props"], s["props"])  # size unknown: 16:9 assumed, and said so
        self.assertIn("boyutu bilinmiyor", unknown["flag"])
        self.assertEqual((s["start"], s["end"], s["anchor"]), (150, 250, {"chapter": 3, "ch_start": 300,
                                                                          "ch_end": 400}))

    def test_stock_overlay_not_filled(self):
        zoomed = bitem(330, 360, "stock", "/b/stok/z.mp4", track=3, src_size=[1920, 1080])
        zoomed["props"] = dict(zoomed["props"], ZoomX=0.5, ZoomY=0.5)
        _, items = desired([bitem(300, 330, "stock", "/b/stok/a.mp4", track=3, src_size=[1920, 1080]), zoomed])
        for o in by_kind(items, "stock"):
            self.assertEqual((o["track"], o["props"], o.get("background")), (3, FIT, None))
            self.assertTrue(o["flag"])

    def test_screenshot_fit_width_flagged(self):
        _, items = desired([bitem(300, 400, "kaynak", SHOT)])
        s = by_kind(items, "screenshot")[0]
        self.assertEqual((s["track"], s["props"], s["background"]), (2, FIT, "black"))
        self.assertTrue(s["flag"])

    def test_non_vertical_fullscreen_fit_and_flag(self):
        _, items = desired([bitem(300, 350, "graphic", GRAPH), bitem(350, 400, "still", HOLD, hold_of=GRAPH)])
        for g in items:
            if g["file"] in (GRAPH, HOLD):
                self.assertEqual((g["track"], g["props"], g["background"]), (2, FIT, "black"))
                self.assertTrue(g["flag"])
        # re-rendered vertical (Task 8 `replace`): the vertical file, fills the frame, no flag
        _, items = desired([bitem(300, 350, "graphic", GRAPH), bitem(350, 400, "still", HOLD, hold_of=GRAPH)],
                           replace={GRAPH: VGRAPH, HOLD: VHOLD})
        got = [(g["file"], g["props"], g.get("background"), g.get("flag"))
               for g in items if g["kind"] in ("graphic", "still")]
        self.assertEqual(got, [(VGRAPH, FIT, None, None), (VHOLD, FIT, None, None)])
        # an own graphic from a non-vertical template, full-screen (end card)
        end = {"role": "end-card", "file": "/s/c1/grafik/end-card-1.png", "range": [550, 625],
               "placeholder": False, "vertical": False}
        _, items = desired(graphics=[end])
        e = by_kind(items, "end-card")[0]
        self.assertEqual((e["track"], e["props"], e["background"]), (2, FIT, "black"))
        self.assertTrue(e["flag"])

    def test_overlay_fit_without_background(self):
        _, items = desired([bitem(300, 350, "graphic", GRAPH, track=3)])
        g = by_kind(items, "graphic")[0]
        self.assertEqual((g["track"], g["props"], g.get("background")), (3, FIT, None))
        self.assertTrue(g["flag"])
        wm = by_kind(items, "watermark")[0]  # Task 8: 1920x1080 still from a non-vertical template
        self.assertEqual((wm["props"], wm.get("background")), (FIT, None))
        self.assertTrue(wm["flag"])
        for k in ("teaser-caption", "teaser-cutout", "end-card"):  # vertical: fills the frame, no flag
            i = by_kind(items, k)[0]
            self.assertEqual((i["props"], i.get("background"), i.get("flag")), (FIT, None, None))

    def test_editor_transformed_item_flagged(self):
        zoomed = bitem(300, 400, "stock", "/b/stok/a.mp4", src_size=[1920, 1080])
        zoomed["props"] = dict(zoomed["props"], ZoomX=1.4, ZoomY=1.4, Pan=120.0)
        _, items = desired([zoomed, bitem(400, 450, "kaynak", SHOT, props={"ZoomX": 1.2, "ZoomY": 1.2}),
                            bitem(450, 480, "stock", "/b/stok/b.mp4", src_size=[1920, 1080])])
        a, shot, b = (next(i for i in items if i["file"] == f) for f in ("/b/stok/a.mp4", SHOT, "/b/stok/b.mp4"))
        centre = {"ZoomX": 3.160494, "ZoomY": 3.160494, "Pan": 0.0, "Tilt": 0.0}
        self.assertEqual((a["props"], b["props"], shot["props"]), (centre, centre, centre))
        self.assertTrue(a["flag"])
        self.assertTrue(shot["flag"])
        self.assertIsNone(b.get("flag"))

    def test_upper_editor_track_kept_above_ours(self):
        _, items = desired([bitem(300, 350, "editor", "/b/x.png", track=4)])
        e = next(i for i in items if i["file"] == "/b/x.png")
        self.assertEqual(e["track"], 8)
        self.assertTrue(e["flag"])

    def test_missing_crop_stops(self):
        lay = layout()
        with self.assertRaises(ValueError):
            splan.desired(lay, assets(lay), {"items": []})


class FlagsTest(unittest.TestCase):
    def test_markers_teaser_joins_reason(self):
        lay, items = desired([bitem(300, 350, "graphic", GRAPH, track=3),
                              bitem(800, 850, "placeholder", "/b/stills/p.png")])
        ms = splan.flags(items, lay, {"id": "c1", "reason": "çarpıcı bir rakam"})
        for m in ms:
            self.assertEqual(m["color"], "Fuchsia")
            self.assertTrue(m["customData"].startswith("short:c1:"))
            self.assertGreaterEqual(m["duration"], 1)
        by_frame = {m["frame"]: m for m in ms}
        self.assertEqual(len(by_frame), len(ms))  # one marker per frame (Resolve refuses a second one)
        first = by_frame[0]
        self.assertEqual(first["duration"], 50)  # ranged over the teaser
        self.assertIn("çarpıcı bir rakam", first["note"])
        self.assertEqual(by_frame[350]["duration"], 1)  # the join between the two pieces
        self.assertEqual(by_frame[350]["customData"], "short:c1:join:2")
        g = by_frame[150]  # flagged overlay, ranged over the item
        self.assertEqual((g["duration"], g["customData"]), (50, "short:c1:flag:1"))
        flagged = [m for m in ms if m["customData"].startswith("short:c1:flag:")]
        self.assertEqual(len(flagged), 1)  # Ruling 7: the watermark gets a summary line, no marker
        self.assertEqual(by_frame[50]["customData"], "short:c1:join:1")  # teaser -> passage
        lines = splan.flag_lines("c1", items)
        self.assertEqual(len(lines), 2)
        self.assertTrue(any("watermark#1" in x for x in lines))
        ph = by_frame[450]  # the placeholder left in the chapter, not copied
        self.assertEqual((ph["duration"], ph["customData"]), (50, "short:c1:placeholder:1"))

    def test_flag_on_a_join_keeps_the_join(self):
        lay, items = desired([bitem(700, 760, "graphic", GRAPH, track=3)])  # starts on the piece join (350)
        ms = splan.flags(items, lay, {"id": "c1", "reason": "r"})
        m = next(m for m in ms if m["frame"] == 350)
        self.assertEqual(m["duration"], 60)
        self.assertIn("ek yeri", m["note"])
        self.assertIn("Ek yeri", m["name"])

    def test_editor_items_not_flagged(self):
        lay, items = desired([bitem(300, 350, "graphic", GRAPH, track=3)])
        items = [dict(i, editor=True) if i["kind"] == "graphic" else i for i in items]
        ms = splan.flags(items, lay, {"id": "c1", "reason": "r"})
        self.assertFalse(any(m["frame"] == 150 for m in ms))


def placed(items, n0=0):
    """The plan as build leaves it: uids and the props read back right after placing."""
    return [dict(i, uid=f"u{n}", props=dict(i["props"], Opacity=100.0)) for n, i in enumerate(items, n0)]


def seen_of(items):
    return [{k: i[k] for k in ("uid", "track", "start", "end", "file", "src_in", "src_out", "props")}
            for i in items]


class ReadbackTest(unittest.TestCase):
    def test_editor_item_kept_by_readback(self):
        lay, items = desired([bitem(300, 400, "stock", "/b/stok/a.mp4", src_size=[1920, 1080]),
                              bitem(400, 450, "stock", "/b/stok/b.mp4", src_size=[1920, 1080])])
        last = placed(items)
        seen = seen_of(last)
        moved = next(s for s in seen if s["file"] == "/b/stok/a.mp4")
        moved["start"] += 10
        moved["end"] += 10
        seen = [s for s in seen if s["file"] != "/b/stok/b.mp4"]  # deleted
        cur = splan.readback(last, seen, lay["segments"])
        keep, remove, add = plan.actions(cur, items)
        self.assertEqual((remove, add), ([], []))
        a = next(i for i in keep if i["uid"] == moved["uid"])
        self.assertEqual((a["editor"], a["start"]), (True, 160))
        self.assertEqual(a["anchor"], {"chapter": 3, "ch_start": 310, "ch_end": 410})  # re-anchored where it sits
        b = next(i for i in keep if i.get("deleted"))
        self.assertEqual((b["editor"], b["file"]), (True, None))
        # the next read-back leaves both as they are
        again = splan.readback(keep, [s for s in seen], lay["segments"])
        self.assertEqual(plan.actions(again, items)[1:], ([], []))

    def test_editor_added_item_anchored(self):
        lay, items = desired()
        last = placed(items)
        extra = {"uid": "x1", "track": 3, "start": 100, "end": 120, "file": "/e/logo.png", "src_in": 0,
                 "src_out": 20, "props": FIT}
        cur = splan.readback(last, seen_of(last) + [extra], lay["segments"])
        e = next(i for i in cur if i["uid"] == "x1")
        self.assertEqual((e["editor"], e["anchor"]), (True, {"chapter": 3, "ch_start": 250, "ch_end": 270}))

    def test_editor_item_over_a_join_anchored_and_checked(self):
        lay, items = desired()
        last = placed(items)
        over = {"uid": "x1", "track": 3, "start": 330, "end": 380, "file": "/e/logo.png", "src_in": 0,
                "src_out": 50, "props": FIT}  # across the piece join at 350
        card = dict(over, uid="x2", start=540, end=600)  # last piece into the end card (550)
        cur = splan.readback(last, seen_of(last) + [over, card], lay["segments"])
        e = next(i for i in cur if i["uid"] == "x1")
        self.assertEqual(e["anchor"], {"pieces": [{"chapter": 3, "ch_start": 480, "ch_end": 500},
                                                  {"chapter": 3, "ch_start": 700, "ch_end": 730}]})
        c = next(i for i in cur if i["uid"] == "x2")
        self.assertEqual(c["anchor"], {"pieces": [{"chapter": 3, "ch_start": 890, "ch_end": 900},
                                                  {"end_card": 0, "frames": 50}]})
        self.assertEqual(splan.stale_anchors([e, c], lay), [])
        self.assertEqual(splan.stale_anchors([e, c], layout(pieces=((200, 500), (700, 910)))), [c])  # card moved
        self.assertEqual(splan.stale_anchors([e, c], layout(pieces=((200, 510), (700, 900)))), [e, c])

    def test_stale_anchor_flagged_not_moved(self):
        lay, items = desired([bitem(300, 400, "stock", "/b/stok/a.mp4", src_size=[1920, 1080])])
        a = dict(next(i for i in items if i["kind"] == "stock"), editor=True)
        same = layout(pieces=((200, 500), (700, 950)))  # later piece longer: a still sits on its words
        self.assertEqual(splan.stale_anchors([a], same), [])
        shifted = layout(pieces=((250, 500), (700, 900)), teaser=(260, 310))  # first piece starts later: its words moved
        stale = splan.stale_anchors([a], shifted)
        self.assertEqual(stale, [a])
        self.assertEqual((stale[0]["start"], stale[0]["end"]), (150, 250))  # never moved
        gone = layout(pieces=((700, 900),), teaser=(720, 770))  # its words left the passage
        self.assertEqual(splan.stale_anchors([a], gone), [a])
        ms, lines = splan.stale_notes("c1", stale)
        self.assertEqual((ms[0]["frame"], ms[0]["duration"], ms[0]["color"]), (150, 100, "Fuchsia"))
        self.assertTrue(ms[0]["customData"].startswith("short:c1:"))
        self.assertEqual(len(lines), 1)


CUES = [{"start": 50, "end": 80, "text": "Birinci satır\nikinci"}, {"start": 80, "end": 120, "text": "üçüncü"}]


def placed_cues(lay):
    return [dict(c, uid=f"s{n}") for n, c in enumerate(splan.cues({"cues": CUES}, lay))]


def seen_cues(cues):
    return [{"uid": c["uid"], "start": c["start"], "end": c["end"], "text": c["text"].replace("\n", " ")}
            for c in cues]


class SubtitleTest(unittest.TestCase):
    def test_untouched_cues_are_ours(self):
        lay = layout()
        last = placed_cues(lay)
        keep, ours = splan.subtitle_readback(last, seen_cues(last), lay["segments"], CUES)
        self.assertEqual((keep, ours), ([], last))
        self.assertFalse(splan.subtitles_stale(keep + ours, CUES))

    def test_edited_cue_kept(self):
        lay = layout()
        last = placed_cues(lay)
        seen = seen_cues(last)
        seen[0]["text"] = "Birinci satır düzeltildi"
        seen[1]["start"] += 2  # moved
        keep, ours = splan.subtitle_readback(last, seen, lay["segments"], CUES)
        self.assertEqual(ours, [])
        self.assertEqual([(c["uid"], c["editor"], c["text"], c["start"]) for c in keep],
                         [("s0", True, "Birinci satır\ndüzeltildi", 50), ("s1", True, "üçüncü", 82)])
        again = splan.subtitle_readback(keep, seen, lay["segments"], CUES)
        self.assertEqual(again, (keep, []))
        # same desired cues: nothing stale, the edited ones are never rewritten
        self.assertFalse(splan.subtitles_stale(keep + ours, CUES))
        self.assertFalse(splan.subtitles_stale(keep + ours, CUES[:1]))  # the dropped cue is the editor's now
        self.assertTrue(splan.subtitles_stale(keep + ours, CUES + [{"start": 300, "end": 330, "text": "yeni"}]))

    def test_deleted_cue_not_refilled(self):
        lay = layout()
        last = placed_cues(lay)
        keep, ours = splan.subtitle_readback(last, seen_cues(last)[1:], lay["segments"], CUES)
        self.assertEqual([(c["uid"], c["editor"], c["deleted"]) for c in keep], [(None, True, True)])
        self.assertEqual([c["uid"] for c in ours], ["s1"])
        self.assertFalse(splan.subtitles_stale(keep + ours, CUES))
        keep2, ours2 = splan.subtitle_readback(keep + ours, seen_cues(last)[1:], lay["segments"], CUES)
        self.assertEqual((keep2, ours2), (keep, ours))

    def test_editor_added_cue_and_cue_without_uid(self):
        lay = layout()
        last = [dict(c, uid=None) for c in placed_cues(lay)]
        seen = seen_cues([dict(c, uid=f"r{n}") for n, c in enumerate(last)])
        seen.append({"uid": "new", "start": 200, "end": 220, "text": "eklendi"})
        keep, ours = splan.subtitle_readback(last, seen, lay["segments"], CUES)
        self.assertEqual([c["uid"] for c in ours], ["r0", "r1"])  # matched by frames and text, uid learnt
        self.assertEqual([(c["uid"], c["editor"], c["text"]) for c in keep], [("new", True, "eklendi")])
        self.assertFalse(splan.subtitles_stale(keep + ours, CUES))


    def test_cues_anchored_and_edited_cue_reanchored(self):
        lay = layout()
        last = placed_cues(lay)
        self.assertEqual(last[0]["anchor"], {"chapter": 3, "ch_start": 200, "ch_end": 230})
        seen = seen_cues(last)
        seen[1]["start"], seen[1]["end"] = 90, 130
        keep, _ = splan.subtitle_readback(last, seen, lay["segments"], CUES)
        self.assertEqual(keep[0]["anchor"], {"chapter": 3, "ch_start": 240, "ch_end": 280})
        self.assertEqual(splan.stale_anchors(keep, lay), [])
        self.assertEqual(splan.stale_anchors(keep, layout(pieces=((210, 500), (700, 900)))), keep)

    def test_reimport_round_trip(self):
        lay = layout()
        last = placed_cues(lay)
        new = [{"start": 50, "end": 90, "text": "yeni birinci"}, {"start": 90, "end": 120, "text": "üçüncü"}]
        self.assertTrue(splan.subtitles_stale(last, new))  # build adds the re-import marker
        # the editor deletes the old cues and imports captions.srt: new uids
        seen = [{"uid": f"n{k}", "start": c["start"], "end": c["end"], "text": c["text"]} for k, c in enumerate(new)]
        keep, ours = splan.subtitle_readback(last, seen, lay["segments"], new)
        self.assertEqual([(c["uid"], c["editor"]) for c in ours], [("n0", False), ("n1", False)])
        self.assertTrue(all(c["deleted"] for c in keep))
        self.assertFalse(splan.subtitles_stale(keep + ours, new))
        keep2, ours2 = splan.subtitle_readback(keep + ours, seen, lay["segments"], new)  # next build
        self.assertEqual([c["uid"] for c in ours2], ["n0", "n1"])
        self.assertFalse(splan.subtitles_stale(keep2 + ours2, new))


class PlanFileTest(unittest.TestCase):
    def test_roundtrip_and_missing(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "shorts", "plan.json")
            self.assertEqual(splan.load(p), {"units": "frames", "shorts": {}})
            data = {"units": "frames", "shorts": {"c1": {"timeline": "uid", "timeline_name": "T short 1 x",
                                                         "items": [], "subtitles": [], "segments": []}}}
            splan.save(p, data)
            self.assertEqual(splan.load(p), data)


if __name__ == "__main__":
    unittest.main()
