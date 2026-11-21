"""Pure glue of `shorts_resolve.py build` (sbuild.py) and the read step's source sizes, against fakes."""
import os
import tempfile
import unittest

import helpers  # noqa: F401
import sbuild
import shorts_resolve as sr


class Mpi:
    def __init__(self, path="/x/a.mp4", type_="Video", fps=25.0):
        self.props = {"File Path": path, "Type": type_, "FPS": fps}

    def GetClipProperty(self, k):
        return self.props.get(k)


def item(kind="stock", track=2, start=10, end=60, file="/x/a.mp4", src_in=5, props=None, **kw):
    return dict({"id": f"{kind}#1", "row": kind, "track": track, "start": start, "end": end, "file": file,
                 "src_in": src_in, "src_out": src_in + end - start, "kind": kind, "editor": False,
                 "deleted": False, "uid": None, "props": props or {}}, **kw)


class AppendSpecTest(unittest.TestCase):
    def test_append_spec_video_only(self):
        spec = sbuild.append_spec(item(), Mpi(), 90000, False)
        self.assertEqual(spec["mediaType"], 1)
        self.assertEqual((spec["trackIndex"], spec["recordFrame"], spec["startFrame"], spec["endFrame"]),
                         (2, 90010, 5, 55))

    def test_camera_keeps_its_audio(self):
        spec = sbuild.append_spec(item("camera", track=1), Mpi(), 90000, False)
        self.assertNotIn("mediaType", spec)
        self.assertEqual(spec["trackIndex"], 1)

    def test_clip_rate(self):
        spec = sbuild.append_spec(item(src_in=10, end=60), Mpi(fps=50.0), 90000, False, 2.0)
        self.assertEqual((spec["startFrame"], spec["endFrame"]), (20, 120))

    def test_still_takes_no_source_range(self):
        spec = sbuild.append_spec(item("screenshot", file="/x/s.png"), Mpi("/x/s.png", "Still"), 90000, True)
        self.assertNotIn("startFrame", spec)
        self.assertEqual(spec["mediaType"], 1)

    def test_still_range_normalised(self):
        got = sbuild.still_range(item("still", file="/x/G-hold-262.PNG", src_in=40, start=100, end=130))
        self.assertEqual((got["src_in"], got["src_out"]), (0, 30))
        vid = item(src_in=40)
        self.assertIs(sbuild.still_range(vid), vid)


class TransformTest(unittest.TestCase):
    def test_transform_order(self):
        calls = sbuild.transform_calls({"Tilt": 0.0, "Pan": -5.333, "ZoomY": 3.160494, "ZoomX": 3.160494,
                                        "Opacity": 50.0})
        self.assertEqual([k for k, _ in calls], ["ZoomX", "ZoomY", "Pan", "Tilt"])
        self.assertEqual(dict(calls)["Pan"], -5.333)

    def test_apply_and_verify(self):
        class It:
            def __init__(self, sticky=None):
                self.p, self.calls, self.sticky = {"ZoomX": 1.0, "ZoomY": 1.0, "Pan": 0.0, "Tilt": 0.0}, [], sticky

            def SetProperty(self, k, v):
                self.calls.append(k)
                if k != self.sticky:
                    self.p[k] = v
                return True

            def GetProperty(self, k=None):
                return self.p[k] if k else dict(self.p)

        it = It()
        self.assertEqual(sbuild.apply_transform(it, {"ZoomX": 2.0, "ZoomY": 2.0, "Pan": 3.0, "Tilt": 0.0}, "x#1"),
                         [])
        self.assertEqual(it.calls, ["ZoomX", "ZoomY", "Pan", "Tilt"])
        probs = sbuild.apply_transform(It("Pan"), {"ZoomX": 2.0, "ZoomY": 2.0, "Pan": 3.0, "Tilt": 0.0}, "x#1")
        self.assertEqual(len(probs), 1)
        self.assertIn("Pan", probs[0])

    def test_transform_differs(self):
        want = {"ZoomX": 3.160494, "Pan": -5.333}
        self.assertFalse(sbuild.transform_differs(want, {"ZoomX": 3.1604940001, "Pan": -5.333, "Opacity": 1}))
        self.assertTrue(sbuild.transform_differs(want, {"ZoomX": 3.160494, "Pan": 0.0}))


class NameTest(unittest.TestCase):
    def test_refuses_long_form_name(self):
        for name in ("COP31B ch3 COP31'in ana gündem maddeleri", "COP31B ch4 Türkiye ve COP31 B-roll",
                     "COP31B B-roll", "COP31B", "COP31B short adayları", "COP31 short 1 x", "COP31B shortx 1"):
            self.assertFalse(sbuild.is_ours(name, "COP31B"), name)

            class Tl:
                def GetName(self, n=name):
                    return n
            with self.assertRaises(sbuild.NotOurs):
                sbuild.assert_ours(Tl(), "COP31B")
        self.assertTrue(sbuild.is_ours("COP31B short 2 Fosil yakıt yol haritası ve ETS", "COP31B"))
        self.assertTrue(sbuild.is_ours("COP31B short 10", "COP31B"))

    def test_rename_when_title_changed(self):
        old = "COP31B short 2 Fosil yakıt"
        self.assertEqual(sbuild.rename_to(old, "COP31B short 1 Fosil yakıt", "COP31B"), "COP31B short 1 Fosil yakıt")
        self.assertEqual(sbuild.rename_to(old, "COP31B short 2 ETS", "COP31B"), "COP31B short 2 ETS")
        self.assertIsNone(sbuild.rename_to(old, old, "COP31B"))
        with self.assertRaises(sbuild.NotOurs):
            sbuild.rename_to("COP31B ch3 X", "COP31B short 1 X", "COP31B")


class TodoTest(unittest.TestCase):
    CANDS = [
        {"id": "c1", "accepted": True, "frozen": False, "pieces": [{"chapter": 3}], "teaser": {"chapter": 3}},
        {"id": "c2", "accepted": True, "frozen": True, "pieces": [{"chapter": 3}], "teaser": {"chapter": 3}},
        {"id": "c3", "accepted": False, "frozen": False, "pieces": [{"chapter": 3}], "teaser": {"chapter": 3}},
        {"id": "c4", "accepted": True, "frozen": False, "pieces": [{"chapter": 5}], "teaser": {"chapter": 5}},
    ]

    def test_frozen_short_skipped(self):
        todo, lines, bad = sbuild.todo(self.CANDS, [], [3, 4])
        self.assertEqual([c["id"] for c in todo], ["c1"])
        self.assertTrue(any(ln.startswith("c2:") and "dondurulmuş" in ln for ln in lines))
        self.assertTrue(any(ln.startswith("c4:") and "imzalı" in ln for ln in lines))
        self.assertFalse(any(ln.startswith("c3:") for ln in lines))  # not accepted, not asked for: silent
        self.assertTrue(bad)

    def test_no_teaser_skipped(self):
        cands = [{"id": "c5", "accepted": True, "frozen": False, "pieces": [{"chapter": 3}], "teaser": None},
                 {"id": "c6", "accepted": True, "frozen": False, "pieces": [{"chapter": 3}]}]
        todo, lines, bad = sbuild.todo(cands, [], [3])
        self.assertEqual(todo, [])
        self.assertEqual(len([ln for ln in lines if "teaser yok: önce check" in ln]), 2)
        self.assertTrue(bad)

    def test_named_ids(self):
        todo, lines, bad = sbuild.todo(self.CANDS, ["c2", "c3"], [3, 4])
        self.assertEqual(todo, [])
        self.assertTrue(any(ln.startswith("c3:") and "kabul" in ln for ln in lines))
        self.assertTrue(bad)
        todo, lines, bad = sbuild.todo(self.CANDS, ["c9"], [3, 4])
        self.assertEqual((todo, bad), ([], True))


class CollideTest(unittest.TestCase):
    def test_collides_with_kept_items_on_same_track(self):
        mine = item(track=2, start=10, end=60)
        editor = dict(item(track=2, start=50, end=80), id="E1", editor=True, uid="u1")
        other_track = dict(item(track=3, start=10, end=60), uid="u2")
        gone = dict(item(track=2, start=10, end=60), editor=True, deleted=True, uid=None)
        self.assertEqual(sbuild.collides(mine, [editor, other_track, gone])["id"], "E1")
        self.assertIsNone(sbuild.collides(mine, [other_track, gone]))
        self.assertIsNone(sbuild.collides(mine, [dict(editor, start=60)]))


class BackgroundTest(unittest.TestCase):
    class Run:
        """ffmpeg fake: writes its output (the temp file); fail=True writes part of it and exits 1."""

        def __init__(self):
            self.calls, self.fail = [], False

        def __call__(self, cmd, **kw):
            self.calls.append(cmd)
            with open(cmd[-1], "wb") as f:
                f.write(b"half" if self.fail else b"padded")

            class P:
                returncode = 1 if self.fail else 0
                stderr = "killed" if self.fail else ""
            return P()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.out = os.path.join(self.d, "siyah")
        for name in ("G.mp4", "S.png"):
            with open(os.path.join(self.d, name), "wb") as f:
                f.write(b"v1")

    def tearDown(self):
        self.tmp.cleanup()

    def src(self, name):
        return os.path.join(self.d, name)

    def test_black_background_padded(self):
        run = self.Run()
        want = [item("graphic", file=self.src("G.mp4"), background="black", flag="f"),
                item("screenshot", file=self.src("S.png"), background="black", start=70, end=90, src_in=0),
                item("stock", file="/x/R.mp4")]
        got, probs = sbuild.black_backgrounds(want, self.out, runner=run)
        self.assertEqual(probs, [])
        self.assertRegex(os.path.basename(got[0]["file"]), r"^G-[0-9a-f]{8}-siyah\.mp4$")
        self.assertRegex(os.path.basename(got[1]["file"]), r"^S-[0-9a-f]{8}-siyah\.png$")
        self.assertEqual(got[2], want[2])
        self.assertEqual((got[0]["src_in"], got[0]["flag"], got[0]["background"]), (5, "f", "black"))
        self.assertIn("pad=1080:1920", " ".join(run.calls[0]))
        self.assertIn("-frames:v", run.calls[1])
        self.assertEqual(sorted(os.listdir(self.out)), sorted(os.path.basename(g["file"]) for g in got[:2]))
        sbuild.black_backgrounds(want, self.out, runner=run)
        self.assertEqual(len(run.calls), 2)  # made once

    def test_rerendered_source_gets_a_new_copy(self):  # (a)
        run = self.Run()
        want = [item("graphic", file=self.src("G.mp4"), background="black")]
        first = sbuild.black_backgrounds(want, self.out, runner=run)[0][0]["file"]
        with open(self.src("G.mp4"), "wb") as f:
            f.write(b"re-rendered, longer")
        second = sbuild.black_backgrounds(want, self.out, runner=run)[0][0]["file"]
        self.assertNotEqual(first, second)
        self.assertEqual(len(run.calls), 2)

    def test_failed_ffmpeg_leaves_nothing_to_place(self):  # (b)
        run = self.Run()
        run.fail = True
        want = [item("graphic", file=self.src("G.mp4"), background="black")]
        got, probs = sbuild.black_backgrounds(want, self.out, runner=run)
        self.assertEqual(got, want)  # the original, unpadded
        self.assertEqual(len(probs), 1)
        self.assertEqual(os.listdir(self.out), [])  # no truncated copy, no temp file
        run.fail = False
        got, probs = sbuild.black_backgrounds(want, self.out, runner=run)
        self.assertEqual(probs, [])
        with open(got[0]["file"], "rb") as f:
            self.assertEqual(f.read(), b"padded")

    def test_same_stem_elsewhere_gets_its_own_copy(self):  # (c)
        os.makedirs(os.path.join(self.d, "b"))
        with open(os.path.join(self.d, "b", "G.mp4"), "wb") as f:
            f.write(b"v1")
        run = self.Run()
        got, _ = sbuild.black_backgrounds(
            [item("graphic", file=self.src("G.mp4"), background="black"),
             item("graphic", file=os.path.join(self.d, "b", "G.mp4"), background="black", start=70, end=90)],
            self.out, runner=run)
        self.assertNotEqual(got[0]["file"], got[1]["file"])
        self.assertEqual(len(run.calls), 2)

    def test_missing_source_reported(self):
        want = [item("graphic", file=self.src("yok.mp4"), background="black")]
        got, probs = sbuild.black_backgrounds(want, self.out, runner=self.Run())
        self.assertEqual((got, len(probs)), (want, 1))


class CreateTimelineTest(unittest.TestCase):
    class Mp:
        def __init__(self, rate):
            self.rate, self.deleted = rate, []

        def GetRootFolder(self):
            return "root"

        def SetCurrentFolder(self, f):
            return True

        def CreateEmptyTimeline(self, name):
            mp = self

            class Tl:
                def __init__(self):
                    self.s = {}

                def GetName(self):
                    return name

                def SetSetting(self, k, v):
                    self.s[k] = v
                    return True

                def GetSetting(self, k):
                    return mp.rate if k == "timelineFrameRate" else self.s.get(k)
            return Tl()

        def DeleteTimelines(self, tls):
            self.deleted += tls
            return True

    def test_frame_rate_read_back(self):
        mp = self.Mp(25.0)
        self.assertIsNotNone(sbuild.create_timeline(mp, "f", "TEST short 1 x", 25, "TEST"))
        mp = self.Mp(24.0)
        with self.assertRaises(sbuild.sync.Problem):
            sbuild.create_timeline(mp, "f", "TEST short 1 x", 25, "TEST")
        self.assertEqual(len(mp.deleted), 1)


class MarkersTest(unittest.TestCase):
    class Tl:
        def __init__(self, markers, name="TEST short 1 x"):
            self.m, self.name = dict(markers), name

        def GetName(self):
            return self.name

        def GetMarkers(self):
            return dict(self.m)

        def DeleteMarkerAtFrame(self, f):
            return self.m.pop(f, None) is not None

        def AddMarker(self, f, color, name, note, dur, cd):
            if f in self.m:
                return False
            self.m[f] = {"color": color, "name": name, "note": note, "duration": dur, "customData": cd}
            return True

    def test_only_our_markers_replaced(self):
        tl = self.Tl({0: {"color": "Fuchsia", "customData": "short:c1:reason", "duration": 1},
                      30: {"color": "Fuchsia", "customData": "short:c1:flag:3", "duration": 5},
                      40: {"color": "Yellow", "customData": "", "duration": 1},
                      50: {"color": "Fuchsia", "customData": "short:c10:flag:1", "duration": 1}})
        ms = [{"frame": 0, "color": "Fuchsia", "name": "Neden", "note": "n", "duration": 1,
               "customData": "short:c1:reason"},
              {"frame": 40, "color": "Fuchsia", "name": "Kontrol", "note": "k", "duration": 10,
               "customData": "short:c1:flag:1"},
              {"frame": 95, "color": "Fuchsia", "name": "Son", "note": "s", "duration": 20,
               "customData": "short:c1:flag:2"},
              {"frame": 100, "color": "Fuchsia", "name": "Dış", "note": "d", "duration": 1,
               "customData": "short:c1:flag:3"}]
        probs = sbuild.set_markers(tl, "c1", ms, 100, "TEST")
        self.assertEqual(tl.m[40]["color"], "Yellow")  # the editor's marker stays
        self.assertEqual(tl.m[41]["customData"], "short:c1:flag:1")  # moved on and shortened
        self.assertEqual(tl.m[41]["duration"], 9)
        self.assertEqual(tl.m[95]["duration"], 5)  # clamped to the timeline end
        self.assertNotIn(30, tl.m)  # old numbering gone
        self.assertEqual(tl.m[50]["customData"], "short:c10:flag:1")  # another short's prefix is not ours
        self.assertEqual(len(probs), 1)  # frame 100 is past the end

    def test_refuses_long_form(self):
        with self.assertRaises(sbuild.NotOurs):
            sbuild.set_markers(self.Tl({}, "TEST ch1 x"), "c1", [], 100, "TEST")


class PlaceTest(unittest.TestCase):
    """sbuild.place against a fake timeline whose append can drop the video of a camera clip."""

    class It:
        n = 0

        def __init__(self, kind, track, start, dur, mpi, left=0):
            PlaceTest.It.n += 1
            self.left = left
            self.uid, self.kind, self.track, self.start, self.dur, self.mpi = f"u{PlaceTest.It.n}", kind, track, start, dur, mpi
            self.p = {"ZoomX": 1.0, "ZoomY": 1.0, "Pan": 0.0, "Tilt": 0.0}

        def GetUniqueId(self):
            return self.uid

        def GetMediaPoolItem(self):
            return self.mpi

        def GetStart(self):
            return self.start

        def GetDuration(self):
            return self.dur

        def GetLeftOffset(self):
            return self.left

        def GetProperty(self, k=None):
            return self.p[k] if k else dict(self.p)

        def SetProperty(self, k, v):
            self.p[k] = v
            return True

        def GetClipColor(self):
            return ""

        def GetSpeed(self):
            return 100.0

        def GetLinkedItems(self):
            return []

        def GetTrackTypeAndIndex(self):
            return [self.kind, self.track]

    class Tl:
        def __init__(self, uid="t1", name="TEST short 1 x"):
            self.uid, self.name, self.items, self.deleted = uid, name, [], []

        def GetName(self):
            return self.name

        def GetUniqueId(self):
            return self.uid

        def GetStartFrame(self):
            return 90000

        def GetTrackCount(self, kind):
            return 2 if kind == "video" else 1

        def GetItemListInTrack(self, kind, k):
            return [i for i in self.items if (i.kind, i.track) == (kind, k)]

        def DeleteClips(self, its):
            self.deleted += its
            self.items = [i for i in self.items if i not in its]
            return True

    class Mp:
        def __init__(self, tl, video=True):
            self.tl, self.video, self.specs = tl, video, []

        def AppendToTimeline(self, specs):
            self.specs += specs
            spec = specs[0]
            dur = spec["endFrame"] - spec["startFrame"]
            if self.video:
                self.tl.items.append(PlaceTest.It("video", spec["trackIndex"], spec["recordFrame"], dur,
                                                  spec["mediaPoolItem"], spec["startFrame"]))
            self.tl.items.append(PlaceTest.It("audio", 1, spec["recordFrame"], dur, spec["mediaPoolItem"]))
            return [object()]

    class Project:
        def __init__(self, tl):
            self.tl = tl

        def GetCurrentTimeline(self):
            return self.tl

    def test_camera_audio_removed_when_its_video_does_not_land(self):
        """Final review minor: no orphan audio left behind by a camera append whose video didn't land."""
        tl = self.Tl()
        mp = self.Mp(tl, video=False)
        cam = item("camera", track=1, start=0, end=50, src_in=100, file="/cam/A.MOV", props={"Pan": 5.0})
        rec, probs = sbuild.place(mp, tl, 90000, 25, cam, Mpi("/cam/A.MOV"), "TEST", self.Project(tl))
        self.assertIsNone(rec["uid"])
        self.assertTrue(probs)
        self.assertEqual(tl.items, [])
        self.assertEqual([d.kind for d in tl.deleted], ["audio"])

    def test_camera_with_video_keeps_its_audio(self):
        tl = self.Tl()
        mp = self.Mp(tl)
        cam = item("camera", track=1, start=0, end=50, src_in=100, file="/cam/A.MOV", props={"Pan": 5.0})
        rec, probs = sbuild.place(mp, tl, 90000, 25, cam, Mpi("/cam/A.MOV"), "TEST", self.Project(tl))
        self.assertEqual(probs, [])
        self.assertIsNotNone(rec["uid"])
        self.assertEqual(sorted(i.kind for i in tl.items), ["audio", "video"])
        self.assertEqual(rec["props"]["Pan"], 5.0)

    def test_refuses_to_append_when_another_timeline_is_current(self):
        """Final review minor: the current timeline is re-checked (uid) before every append."""
        tl = self.Tl()
        mp = self.Mp(tl)
        other = self.Tl("t2", "TEST ch1 Bir")
        with self.assertRaises(sbuild.NotOurs):
            sbuild.place(mp, tl, 90000, 25, item(), Mpi(), "TEST", self.Project(other))
        self.assertEqual(mp.specs, [])
        self.assertEqual(tl.items, [])


class ReadSizeTest(unittest.TestCase):
    def test_parse_resolution(self):
        self.assertEqual(sr.parse_resolution("1920x1080"), [1920, 1080])
        self.assertEqual(sr.parse_resolution(" 2560 x 1440 "), [2560, 1440])
        for bad in (None, "", "x", "0x0", "abcxdef"):
            self.assertIsNone(sr.parse_resolution(bad))

    def test_read_items_src_size(self):
        seen = [{"uid": "1", "track": 2, "start": 0, "end": 10, "file": "/x/stok/R1-1.mp4", "src_in": 0,
                 "src_out": 10, "props": {}},
                {"uid": "2", "track": 2, "start": 10, "end": 20, "file": "/x/e.mp4", "src_in": 0, "src_out": 10,
                 "props": {}}]
        got = sr.read_items(seen, {"rows": {}}, sizes={"1": [2560, 1440], "2": None})
        self.assertEqual(got[0]["src_size"], [2560, 1440])
        self.assertNotIn("src_size", got[1])


if __name__ == "__main__":
    unittest.main()
