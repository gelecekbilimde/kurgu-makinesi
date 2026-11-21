import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
import crop
import faces
import matte
from fakes import FakeDetect, FakeRun, FakeSegment


def face(cx, cy=1000, h=600):
    return {"cx": cx, "cy": cy, "h": h}


class FacesTest(unittest.TestCase):
    def test_face_median_of_samples(self):
        first = [face(1500), None, face(1700), face(1600), face(9999, 50, 10), face(1650), None, face(1550),
                 face(1620)]
        detect = FakeDetect(first + [None] * 9)
        run = FakeRun()
        with tempfile.TemporaryDirectory() as tmp:
            got = faces.piece_faces("/cam/A.MOV", [[1000, 1090], [5000, 5009]], detect, run, fps=25, workdir=tmp)
        self.assertEqual(got[0], {"cx": 1620, "cy": 1000, "h": 600})  # median of the 7 detections per key
        self.assertIsNone(got[1])                                       # nothing found -> centre crop later
        cmds = run.commands("ffmpeg")
        self.assertEqual(len(cmds), 18)
        self.assertEqual(len(detect.seen), 18)
        seeks = [float(c[c.index("-ss") + 1]) * 25 for c in cmds[:9]]
        self.assertEqual([round(s) for s in seeks], [1005, 1015, 1025, 1035, 1045, 1055, 1065, 1075, 1085])
        self.assertTrue(all(c[c.index("-i") + 1] == "/cam/A.MOV" for c in cmds))
        self.assertEqual([round(float(c[c.index("-ss") + 1]) * 25) for c in cmds[9:]], list(range(5000, 5009)))


class MatteTest(unittest.TestCase):
    def test_matte_commands(self):
        t = crop.transform({"cx": 1700, "cy": 800, "h": 680}, 3840, 2160)
        run, seg = FakeRun(), FakeSegment()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "c1" / "teaser-cutout.mov"
            matte.cutout("/cam/A.MOV", [2400, 2450], t, out, seg, run, src_size=(3840, 2160), fps=25)
            self.assertFalse(any(Path(tmp, "c1").glob("*.png")))  # frames and masks cleaned up
        extract, encode = run.commands("ffmpeg")
        self.assertEqual(round(float(extract[extract.index("-ss") + 1]) * 25), 2400)
        self.assertEqual(extract[extract.index("-frames:v") + 1], "50")
        vf = extract[extract.index("-vf") + 1]
        x, y, w, h = (round(v) for v in crop.window(t, 3840, 2160))
        self.assertIn(f"crop={w}:{h}:{x}:{y}", vf)
        self.assertIn("scale=1080:1920", vf)
        self.assertEqual(len(seg.seen), 50)                 # one segmentation per teaser frame
        self.assertIn("alphamerge", " ".join(encode))
        self.assertEqual(encode[encode.index("-c:v") + 1], "prores_ks")
        self.assertEqual(encode[encode.index("-profile:v") + 1], "4444")
        self.assertEqual(encode[encode.index("-pix_fmt") + 1], "yuva444p10le")
        self.assertEqual(encode[-1], str(out))


if __name__ == "__main__":
    unittest.main()
