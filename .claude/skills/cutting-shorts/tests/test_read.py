import unittest
import helpers  # noqa: F401
import build as glue
import sync
import shorts_resolve as sr


def seen(track, start, end, file, uid="u"):
    return {"uid": uid, "track": track, "start": start, "end": end, "file": file,
            "src_in": 0, "src_out": end - start, "props": {"ClipColor": ""}}


FETCHED = {"rows": {
    "a": [{"kind": "stock", "files": [{"file": "/x/stok/R1-1.mp4"}]}],
    "b": [{"kind": "graphic", "files": [{"file": "/x/grafik/G1-1.mp4"}], "hold": "/x/stills/G1-1-hold.png"}],
    "c": [{"kind": "placeholder", "files": [{"file": "/x/stills/R2-1.png"}]}],
    "d": [{"kind": "screenshot", "files": [{"file": "/x/stills/S1.png"}]}],
}}


class ReadItemsTest(unittest.TestCase):
    def test_kind_from_fetched(self):
        got = sr.read_items([seen(2, 0, 10, "/x/stok/R1-1.mp4", "1"), seen(2, 10, 20, "/x/grafik/G1-1.mp4", "2"),
                             seen(3, 0, 5, "/x/stills/R2-1.png", "3"), seen(3, 5, 9, "/x/stills/S1.png", "4"),
                             seen(2, 20, 30, "/x/stills/G1-1-hold.png", "5")], FETCHED)
        self.assertEqual([i["kind"] for i in got], ["stock", "graphic", "placeholder", "screenshot", "still"])
        self.assertEqual(got[4]["hold_of"], "/x/grafik/G1-1.mp4")
        self.assertNotIn("hold_of", got[0])
        self.assertNotIn("uid", got[0])
        self.assertEqual(set(got[0]), {"track", "start", "end", "file", "src_in", "src_out", "props", "kind"})

    def test_editor_file_is_editor_kind(self):
        got = sr.read_items([seen(2, 0, 10, "/elsewhere/clip.mp4"), seen(2, 0, 10, None)], FETCHED)
        self.assertEqual([i["kind"] for i in got], ["editor", "editor"])


class FakeItem:
    def __init__(self, track, start):
        self.track, self.start = track, start

    def GetMediaPoolItem(self):
        return None

    def GetStart(self): return 100 + self.start
    def GetDuration(self): return 10
    def GetLeftOffset(self): return 0
    def GetProperty(self): return {}
    def GetClipColor(self): return ""
    def GetSpeed(self): return 100
    def GetUniqueId(self): return f"{self.track}-{self.start}"


class FakeTl:
    def GetTrackCount(self, kind): return 4
    def GetItemListInTrack(self, kind, k): return [FakeItem(k, 0)]


class TrackItemsTest(unittest.TestCase):
    def test_track_items_all_upper_tracks(self):
        seen_, by_uid = sync.track_items(FakeTl(), 100, 25, tracks=None)
        self.assertEqual([s["track"] for s in seen_], [2, 3, 4])
        self.assertEqual(len(by_uid), 3)

    def test_default_is_v2_v3(self):
        self.assertEqual([s["track"] for s in sync.track_items(FakeTl(), 100, 25)[0]], [2, 3])


if __name__ == "__main__":
    unittest.main()
