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
    def test_black_background_padded(self):
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            open(cmd[-1], "wb").close()

            class P:
                returncode = 0
                stderr = ""
            return P()

        with tempfile.TemporaryDirectory() as d:
            want = [item("graphic", file="/x/G.mp4", background="black", flag="f"),
                    item("screenshot", file="/x/S.png", background="black", start=70, end=90, src_in=0),
                    item("stock", file="/x/R.mp4")]
            got, probs = sbuild.black_backgrounds(want, d, runner=run)
            self.assertEqual(probs, [])
            self.assertEqual(got[0]["file"], os.path.join(d, "G-siyah.mp4"))
            self.assertEqual(got[1]["file"], os.path.join(d, "S-siyah.png"))
            self.assertEqual(got[2], want[2])
            self.assertEqual((got[0]["src_in"], got[0]["flag"], got[0]["background"]), (5, "f", "black"))
            self.assertIn("pad=1080:1920", " ".join(calls[0]))
            self.assertIn("-frames:v", calls[1])
            sbuild.black_backgrounds(want, d, runner=run)
            self.assertEqual(len(calls), 2)  # made once


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
