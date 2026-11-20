import json, os, tempfile, unittest
from pathlib import Path

import helpers  # noqa: F401
import broll
import build


class FakeMpi:
    def __init__(self, path, type_="Video"):
        self.props = {"File Path": path, "Type": type_}

    def GetClipProperty(self, k):
        return self.props.get(k)


class FakeItem:
    def __init__(self, uid, start, dur, left, mpi, props=None, color="", speed=100.0):
        self.uid, self.start, self.dur, self.left, self.mpi = uid, start, dur, left, mpi
        self.props, self.color, self.speed = props or {"ZoomX": 1.0, "Opacity": 100.0}, color, speed

    def GetUniqueId(self):
        return self.uid

    def GetStart(self):
        return self.start

    def GetDuration(self):
        return self.dur

    def GetLeftOffset(self):
        return self.left

    def GetMediaPoolItem(self):
        return self.mpi

    def GetProperty(self):
        return dict(self.props)

    def GetClipColor(self):
        return self.color

    def GetSpeed(self):
        return {"Percentage": self.speed}


S0 = 90000


def plan_item(id_, row, start, end, file, track=2, src_in=0, kind="stock", marker=None, editor=False, uid=None):
    return {"id": id_, "row": row, "track": track, "start": start, "end": end, "file": file, "src_in": src_in,
            "src_out": src_in + end - start, "kind": kind, "code": None, "editor": editor, "deleted": False,
            "uid": uid, "props": {}, "marker": marker}


class SeenTest(unittest.TestCase):
    def test_video_item_relative_frames_and_source_range(self):
        it = FakeItem("u1", S0 + 805, 375, 10, FakeMpi("/m/a.mp4"))
        s = build.seen_item(it, S0, 2)
        self.assertEqual(s["uid"], "u1")
        self.assertEqual((s["track"], s["start"], s["end"], s["file"], s["src_in"], s["src_out"]),
                         (2, 805, 1180, os.path.realpath("/m/a.mp4"), 10, 385))
        self.assertEqual(s["props"]["ZoomX"], 1.0)
        self.assertEqual(s["props"]["ClipColor"], "")
        self.assertEqual(s["props"]["Speed"], 100.0)

    def test_still_source_range_is_zero_to_length(self):
        it = FakeItem("u2", S0 + 100, 37, 90000, FakeMpi("/m/p.png", "Still"))
        s = build.seen_item(it, S0, 3)
        self.assertEqual((s["src_in"], s["src_out"], s["start"], s["end"]), (0, 37, 100, 137))

    def test_generator_without_media_pool_item(self):
        s = build.seen_item(FakeItem("u3", S0, 50, 0, None), S0, 2)
        self.assertIsNone(s["file"])

    def test_props_survive_json_roundtrip(self):
        s = build.seen_item(FakeItem("u1", S0, 5, 0, FakeMpi("/m/a.mp4")), S0, 2)
        self.assertEqual(json.loads(json.dumps(s["props"])), s["props"])


class FrameRateTest(unittest.TestCase):
    """Source frames are in the clip's own rate; plan src_in/src_out are timeline frames (live: a 30 fps clip
    appended 0..125 gave a 104-frame item at 25 fps)."""

    def test_ratio(self):
        self.assertEqual(build.clip_ratio(FakeMpi("/m/a.mp4"), 25), 1.0)
        m = FakeMpi("/m/b.mp4")
        m.props["FPS"] = 30.0
        self.assertEqual(build.clip_ratio(m, 25), 1.2)
        m.props["FPS"] = ""
        self.assertEqual(build.clip_ratio(m, 25), 1.0)
        self.assertEqual(build.clip_ratio(FakeMpi("/m/p.png", "Still"), 25), 1.0)

    def test_append_converts_to_clip_frames(self):
        it = plan_item("R1#1", "k", 0, 189, "/m/b.mp4", src_in=125)
        spec = build.append_spec(it, "MPI", S0, still=False, ratio=1.2)
        self.assertEqual((spec["startFrame"], spec["endFrame"]), (150, 377))

    def test_seen_converts_back_to_timeline_frames(self):
        m = FakeMpi("/m/b.mp4")
        m.props["FPS"] = 30.0
        s = build.seen_item(FakeItem("u", S0 + 10, 189, 150, m), S0, 2, fps=25)
        self.assertEqual((s["src_in"], s["src_out"], s["start"], s["end"]), (125, 314, 10, 199))


class AppendTest(unittest.TestCase):
    def test_video_spec_absolute_record_frame_exclusive_end(self):
        it = plan_item("R1#1", "k", 805, 1180, "/m/a.mp4", src_in=0)
        self.assertEqual(build.append_spec(it, "MPI", S0, still=False),
                         {"mediaPoolItem": "MPI", "trackIndex": 2, "recordFrame": S0 + 805, "mediaType": 1,
                          "startFrame": 0, "endFrame": 375})

    def test_still_spec_has_no_source_range(self):
        it = plan_item("R1#2", "k", 100, 137, "/m/p.png", track=3, kind="placeholder")
        spec = build.append_spec(it, "MPI", S0, still=True)
        self.assertNotIn("startFrame", spec)
        self.assertNotIn("endFrame", spec)
        self.assertEqual((spec["trackIndex"], spec["recordFrame"]), (3, S0 + 100))
        self.assertEqual(build.still_marks(it), (0, 36))


class PlacedTest(unittest.TestCase):
    def test_stores_uid_props_and_seen_file_form(self):
        it = plan_item("R1#1", "k", 0, 50, "/m/x/../a.mp4")
        seen = {"uid": "u9", "track": 2, "start": 0, "end": 50, "file": "/m/a.mp4", "src_in": 0, "src_out": 50,
                "props": {"ZoomX": 1.0}}
        new, problems = build.placed(it, seen)
        self.assertEqual((new["uid"], new["props"], new["file"]), ("u9", {"ZoomX": 1.0}, "/m/a.mp4"))
        self.assertEqual(problems, [])

    def test_reports_a_clipped_placement(self):
        it = plan_item("R1#1", "k", 0, 50, "/m/a.mp4")
        seen = {"uid": "u9", "track": 2, "start": 20, "end": 50, "file": "/m/a.mp4", "src_in": 0, "src_out": 30,
                "props": {}}
        new, problems = build.placed(it, seen)
        self.assertTrue(problems)
        self.assertEqual(new["start"], 20)  # the plan records what is really on the timeline

    def test_nothing_placed(self):
        new, problems = build.placed(plan_item("R1#1", "k", 0, 50, "/m/a.mp4"), None)
        self.assertIsNone(new["uid"])
        self.assertTrue(problems)


class RebindTest(unittest.TestCase):
    def test_kept_item_takes_desired_id_and_marker(self):
        old = plan_item("R1#2", "k", 0, 50, "/m/p.png", kind="placeholder", marker="old text", uid="u1")
        want = plan_item("R1#1", "k", 0, 50, "/m/p.png", kind="placeholder", marker="new text")
        out = build.rebind([old], [want])
        self.assertEqual(len(out), 1)
        item, old_id = out[0]
        self.assertEqual((item["id"], item["marker"], item["uid"], old_id), ("R1#1", "new text", "u1", "R1#2"))

    def test_editor_and_editor_added_items_untouched(self):
        ed = plan_item("R1#1", "k", 0, 50, "/m/a.mp4", editor=True, uid="u1")
        added = dict(plan_item("E1", None, 0, 50, "/m/z.mp4", editor=True, uid="u2"), kind=None)
        out = build.rebind([ed, added], [plan_item("R1#1", "k", 0, 50, "/m/a.mp4")])
        self.assertEqual([(i, o) for i, o in out], [(ed, "R1#1"), (added, "E1")])


class MarkerTest(unittest.TestCase):
    def test_ranged_lavender_with_custom_data(self):
        it = plan_item("R15#2", "k", 100, 310, "/m/p.png", track=3, kind="placeholder",
                       marker="R015 YAZI: Uçak (şablon yok)")
        m = build.marker_args(it, used=set())
        self.assertEqual(m, {"frameId": 100, "color": "Lavender", "name": "R015 YAZI", "note": "R015 YAZI: Uçak (şablon yok)",
                             "duration": 210, "customData": "broll:R15#2"})

    def test_frame_taken_moves_on_and_shortens(self):
        it = plan_item("R15#3", "k", 100, 310, "/m/p.png", kind="placeholder", marker="x: y")
        m = build.marker_args(it, used={100, 101})
        self.assertEqual((m["frameId"], m["duration"]), (102, 208))

    def test_no_marker_for_non_placeholder(self):
        self.assertIsNone(build.marker_args(plan_item("R1#1", "k", 0, 50, "/m/a.mp4"), used=set()))


def placeholder_asset(tag, note, track=3):
    return {"tag": tag, "kind": "placeholder", "track": track, "note": note, "hold": None, "hold_from": None,
            "request_hash": "h", "code": None, "files": [{"file": "/m/p.png", "code": "R", "frames": None,
                                                           "credit": None}]}


class SummaryTest(unittest.TestCase):
    def test_lines(self):
        rows = {"a": {"id": "R012", "start": 0, "end": 500}, "b": {"id": "R015", "start": 600, "end": 900},
                "c": None, "gone": None}
        fetched = {"rows": {
            "a": [{"tag": "STOK", "kind": "stock", "track": 2, "files": [{"file": "/m/a.mp4", "frames": 100}]}],
            "b": [placeholder_asset("YAZI", "şablon yok: metin şablonu"),
                  placeholder_asset("GRAFİK", "arşiv", track=2)]}}
        requests = {"rows": {"b": [{"tag": "YAZI", "kind": "placeholder", "reason": "şablon yok",
                                    "need": "metin şablonu"},
                                   {"tag": "GRAFİK", "kind": "placeholder", "reason": "arşiv"}],
                             "x": [{"tag": "YAZI", "kind": "placeholder", "reason": "şablon yok",
                                    "need": "metin şablonu"}]}}
        items = [plan_item("R012#1", "a", 0, 100, "/m/a.mp4"),
                 dict(plan_item("R099#1", "vanished", 0, 10, "/m/v.mp4", editor=True))]
        ids = {"c": "R016", "gone": "R017"}
        lines = build.summary([(3, rows, items)], fetched, requests, ids)
        text = "\n".join(lines)
        self.assertIn("Yerleştirilen satırlar: R012", text)
        self.assertIn("Yer tutucular: arşiv: R015 (GRAFİK); şablon yok: R015 (YAZI)", text)
        self.assertIn("R012: stok yetmedi (400 kare boş)", text)
        self.assertIn("Bölümde bulunamadı: R016, R017", text)
        self.assertIn("R099: satırı kayboldu (1 düzenleyici öğesi)", text)
        self.assertEqual(lines[-2:], ["Gereken şablonlar:", "  - metin şablonu"])

    def test_no_needs_says_none(self):
        lines = build.summary([(3, {}, [])], {"rows": {}}, {"rows": {}}, {})
        self.assertEqual(lines[-1], "Gereken şablonlar: yok")


class MasterTest(unittest.TestCase):
    def test_order_broll_then_frozen_then_note(self):
        names = ["P ch1 A", "P ch2 B", "P ch3 C"]
        out = build.master_entries(names, existing={"P ch1 A", "P ch1 A B-roll", "P ch2 B"}, frozen={1, 2})
        self.assertEqual(out, [(1, "P ch1 A B-roll"), (2, "P ch2 B"), (3, None)])

    def test_unfrozen_chapter_timeline_not_used(self):
        self.assertEqual(build.master_entries(["P ch1 A"], existing={"P ch1 A"}, frozen=set()), [(1, None)])


class FreezeTest(unittest.TestCase):
    def test_freeze_unfreeze_edit_broll_frozen(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = helpers.make_episode(tmp, frozen=[3, 4])
            broll.main(["freeze", str(d), "4", "3"])
            m = json.loads(Path(d, "episode.json").read_text(encoding="utf-8"))
            self.assertEqual(m["broll_frozen"], [3, 4])
            self.assertEqual(m["frozen"], [3, 4])
            broll.main(["unfreeze", str(d), "3"])
            m = json.loads(Path(d, "episode.json").read_text(encoding="utf-8"))
            self.assertEqual(m["broll_frozen"], [4])


if __name__ == "__main__":
    unittest.main()
