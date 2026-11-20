"""sync.py against a fake Resolve timeline/media pool: plan.json must always match the timeline."""
import itertools
import unittest

import helpers  # noqa: F401
import build
import plan
import sync

TL_FPS = 25
S0 = 90000
_uids = itertools.count(1)


class Mpi:
    def __init__(self, path, type_="Video", fps=25.0):
        self.props = {"File Path": path, "Type": type_, "FPS": fps}
        self.marks = None

    def GetClipProperty(self, k):
        return self.props.get(k)

    def GetName(self):
        return self.props["File Path"].rsplit("/", 1)[-1]

    def SetMarkInOut(self, a, b):
        self.marks = (a, b)

    def ClearMarkInOut(self):
        self.marks = None


class Item:
    def __init__(self, mpi, track, start, dur, left):
        self.uid, self.mpi, self.track, self.start, self.dur, self.left = f"u{next(_uids)}", mpi, track, start, dur, left

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
        return {"ZoomX": 1.0}

    def GetClipColor(self):
        return ""

    def GetSpeed(self):
        return {"Percentage": 0.0 if build.is_still(self.mpi) else 100.0}

    def GetTrackTypeAndIndex(self):
        return ["video", self.track]


class Timeline:
    def __init__(self):
        self.items, self.markers, self.delete_fails = [], {}, False

    def GetStartFrame(self):
        return S0

    def GetTrackCount(self, kind):
        return 3

    def GetItemListInTrack(self, kind, k):
        return sorted((i for i in self.items if i.track == k), key=lambda i: i.start)

    def DeleteClips(self, items):
        if self.delete_fails:
            return False
        self.items = [i for i in self.items if i not in items]
        return True

    def GetMarkers(self):
        return dict(self.markers)

    def AddMarker(self, f, color, name, note, dur, custom=""):
        if f in self.markers:
            return False
        self.markers[f] = {"color": color, "name": name, "note": note, "duration": dur, "customData": custom}
        return True

    def GetMarkerByCustomData(self, cd):
        return next((m for m in self.markers.values() if m["customData"] == cd), {})

    def DeleteMarkerByCustomData(self, cd):
        n = len(self.markers)
        self.markers = {f: m for f, m in self.markers.items() if m["customData"] != cd}
        return len(self.markers) < n


class Folder:
    def __init__(self, name):
        self.name, self.subs, self.clips = name, [], []

    def GetName(self):
        return self.name

    def GetSubFolderList(self):
        return list(self.subs)

    def GetClipList(self):
        return list(self.clips)


class MediaPool:
    """files: path -> (type, fps). Appends to self.tl like Resolve: source frames in the clip's rate, a still's
    length from mark in/out, an append over an item cut to the free part, the return value optionally empty."""

    def __init__(self, tl, files):
        self.tl, self.files, self.root, self.cur = tl, files, Folder("root"), None
        self.return_nothing, self.fail_import, self.fail_folder, self.raise_on_append = False, set(), False, None
        self.appends = 0

    def GetRootFolder(self):
        return self.root

    def SetCurrentFolder(self, f):
        self.cur = f
        return True

    def AddSubFolder(self, parent, name):
        if self.fail_folder:
            raise RuntimeError("Resolve: AddSubFolder failed")
        f = Folder(name)
        parent.subs.append(f)
        return f

    def ImportMedia(self, paths):
        out = []
        for p in paths:
            if p in self.fail_import:
                continue
            type_, fps = self.files[p]
            m = Mpi(p, type_, fps)
            self.cur.clips.append(m)
            out.append(m)
        return out

    def AppendToTimeline(self, specs):
        self.appends += 1
        if self.raise_on_append == self.appends:
            raise RuntimeError("Resolve went away")
        got = []
        for s in specs:
            m, track, start = s["mediaPoolItem"], s["trackIndex"], s["recordFrame"]
            if build.is_still(m):
                dur, left = m.marks[1] - m.marks[0] + 1, S0
            else:
                ratio = m.GetClipProperty("FPS") / TL_FPS
                dur, left = round((s["endFrame"] - s["startFrame"]) / ratio), s["startFrame"]
            end = start + dur
            for o in self.tl.items:  # cut to the free part
                if o.track == track and o.start < end and start < o.start + o.dur:
                    if o.start <= start:
                        start = o.start + o.dur
                    else:
                        end = o.start
            if end > start:
                it = Item(m, track, start, end - start, left)
                self.tl.items.append(it)
                got.append(it)
        return [] if self.return_nothing else got


def stock(id_, row, start, end, file, src_in=0):
    return {"id": id_, "row": row, "track": 2, "start": start, "end": end, "file": file, "src_in": src_in,
            "src_out": src_in + end - start, "kind": "stock", "code": None, "editor": False, "deleted": False,
            "uid": None, "props": {}, "marker": None}


def holder(id_, row, start, end, file, text):
    return dict(stock(id_, row, start, end, file), track=3, kind="placeholder", marker=text)


class Rig:
    def __init__(self, files):
        self.tl = Timeline()
        self.mp = MediaPool(self.tl, files)
        self.top = Folder("P B-roll")
        self.mp.root.subs.append(self.top)
        self.media = sync.Media(self.mp, self.top)
        self.ch_bin = sync.subfolder(self.mp, self.top, "ch3")
        self.saved = []

    def save(self, items):
        self.saved = [dict(i) for i in items]

    def run(self, last, desired):
        return sync.sync_items(self.tl, self.mp, self.media, self.ch_bin, TL_FPS, last, desired, self.save)

    def in_sync(self, items):
        """every V2/V3 uid on the timeline is in the plan and every placed plan item is on the timeline"""
        on_tl = {i.uid for i in self.tl.items}
        in_plan = {i["uid"] for i in items if i.get("uid") and not i.get("deleted")}
        return on_tl == in_plan


FILES = {"/m/a.mp4": ("Video", 25.0), "/m/b.mp4": ("Video", 25.0), "/m/c.mp4": ("Video", 25.0),
         "/m/p.png": ("Still", 25.0), "/m/slow.mp4": ("Video", 24.0), "/m/ntsc.mp4": ("Video", 24000 / 1001)}


class SyncTest(unittest.TestCase):
    def test_build_twice_second_is_noop(self):
        r = Rig(FILES)
        want = [stock("R1#1", "k", 0, 100, "/m/a.mp4"), holder("R1#2", "k", 0, 100, "/m/p.png", "R1 YAZI: x")]
        items, c, probs = r.run([], want)
        self.assertEqual((c["added"], c["removed"], probs), (2, 0, []))
        self.assertEqual(len(r.tl.markers), 1)
        items2, c2, probs2 = r.run(items, want)
        self.assertEqual((c2["added"], c2["removed"], c2["kept"], probs2), (0, 0, 2, []))
        self.assertTrue(r.in_sync(items2))

    def test_append_return_value_not_trusted(self):
        r = Rig(FILES)
        r.mp.return_nothing = True
        items, c, probs = r.run([], [stock("R1#1", "k", 0, 100, "/m/a.mp4")])
        self.assertEqual((c["added"], probs), (1, []))
        self.assertTrue(r.in_sync(items))


class RateRoundingTest(unittest.TestCase):
    """clips slower than the timeline: round(round(x * r) / r) != x must not re-place them on every build"""

    def check(self, path):
        r = Rig(FILES)
        want = [stock("R1#1", "k", 0, 189, path), stock("R1#2", "k", 189, 202, path, src_in=13)]
        items, c, probs = r.run([], want)
        self.assertEqual((c["added"], probs), (2, []))
        items2, c2, probs2 = r.run(items, want)
        self.assertEqual((c2["added"], c2["removed"], c2["editor"], probs2), (0, 0, 0, []))
        items3, c3, _ = r.run(items2, want)
        self.assertEqual((c3["added"], c3["removed"]), (0, 0))
        self.assertTrue(r.in_sync(items3))

    def test_ratio_096(self):
        self.check("/m/slow.mp4")

    def test_ratio_ntsc_film(self):
        self.check("/m/ntsc.mp4")

    def test_placed_records_planned_values_with_seen_snapshot(self):
        it = stock("R1#1", "k", 0, 189, "/m/slow.mp4")
        seen = {"uid": "u", "track": 2, "start": 0, "end": 188, "file": "/m/slow.mp4", "src_in": 0, "src_out": 188,
                "props": {}}
        rec, probs = build.placed(it, seen)
        self.assertEqual((rec["end"], rec["src_out"], rec["seen"]["end"], probs), (189, 189, 188, []))
        self.assertFalse(plan.readback([rec], [seen])[0]["editor"])
        trimmed = dict(seen, end=150, src_out=150)
        back = plan.readback([rec], [trimmed])[0]
        self.assertTrue(back["editor"])
        self.assertEqual(back["end"], 150)
        self.assertNotIn("seen", back)


class FailureTest(unittest.TestCase):
    def test_failed_delete_keeps_items_and_their_markers(self):
        r = Rig(FILES)
        old = [stock("R1#1", "k", 0, 100, "/m/a.mp4"), holder("R1#2", "k", 0, 100, "/m/p.png", "R1 YAZI: x")]
        items, _, _ = r.run([], old)
        new = [stock("R1#1", "k", 0, 100, "/m/b.mp4")]  # the request changed: a.mp4 and the placeholder go
        r.tl.delete_fails = True
        items2, c, probs = r.run(items, new)
        self.assertEqual((c["added"], c["removed"]), (0, 0))
        self.assertTrue(any("silinemeyen" in p for p in probs))
        self.assertTrue(r.in_sync(items2))
        self.assertTrue(r.in_sync(r.saved))
        self.assertEqual(len(r.tl.markers), 1)  # the placeholder is still there, so is its marker
        self.assertFalse(any(i["id"].startswith("E") for i in items2))
        r.tl.delete_fails = False
        items3, c3, probs3 = r.run(items2, new)
        self.assertEqual((c3["added"], c3["removed"], probs3), (1, 2, []))
        self.assertEqual([i["file"] for i in items3], ["/m/b.mp4"])
        self.assertEqual(r.tl.markers, {})
        self.assertTrue(r.in_sync(items3))

    def test_exception_during_bin_import_is_a_problem_and_plan_is_saved(self):
        r = Rig(FILES)
        want = [stock("R1#1", "k", 0, 100, "/m/a.mp4")]
        items, _, _ = r.run([], want)
        r.mp.fail_folder = True
        fetched = {"rows": {"k": [{"kind": "stock", "files": [{"file": "/m/a.mp4"}, {"file": "/m/c.mp4"}]}]}}
        probs = sync.file_candidates(r.mp, r.media, r.ch_bin, {"k": {"id": "R1", "start": 0, "end": 100}},
                                     fetched, items)
        self.assertEqual(len(probs), 1)
        self.assertIn("R1 adayları", probs[0])
        self.assertTrue(r.in_sync(r.saved))

    def test_failed_import_is_a_problem_others_still_placed(self):
        r = Rig(FILES)
        r.mp.fail_import = {"/m/b.mp4"}
        items, c, probs = r.run([], [stock("R1#1", "k", 0, 100, "/m/b.mp4"), stock("R2#1", "j", 200, 300, "/m/a.mp4")])
        self.assertEqual(c["added"], 1)
        self.assertTrue(any("içe aktarılamadı" in p for p in probs))
        self.assertTrue(r.in_sync(items))

    def test_exception_mid_placement_leaves_saved_plan_matching_timeline(self):
        r = Rig(FILES)
        r.mp.raise_on_append = 2
        want = [stock("R1#1", "k", 0, 100, "/m/a.mp4"), stock("R2#1", "j", 200, 300, "/m/b.mp4")]
        with self.assertRaises(RuntimeError):
            r.run([], want)
        self.assertEqual(len(r.tl.items), 1)
        self.assertTrue(r.in_sync(r.saved))
        r.mp.raise_on_append = None
        items, c, probs = r.run(r.saved, want)  # the next build picks up where it stopped
        self.assertEqual((c["added"], c["kept"], probs), (1, 1, []))
        self.assertTrue(r.in_sync(items))


if __name__ == "__main__":
    unittest.main()
